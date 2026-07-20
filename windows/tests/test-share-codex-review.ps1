#requires -Version 7.0

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$shareScript = Join-Path $repoRoot 'share-codex-review.ps1'
$testRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    'quick-tunnel-windows-tests-{0}' -f [guid]::NewGuid().ToString('N')
)
$expectedTestPrefix = [System.IO.Path]::GetFullPath(
    (Join-Path ([System.IO.Path]::GetTempPath()) 'quick-tunnel-windows-tests-')
)
$resolvedTestRoot = [System.IO.Path]::GetFullPath($testRoot)
if (-not $resolvedTestRoot.StartsWith($expectedTestPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to create test root outside the expected temp prefix: $resolvedTestRoot"
}

New-Item -ItemType Directory -Path $testRoot | Out-Null

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Assert-Equal {
    param(
        [object]$Actual,
        [object]$Expected,
        [string]$Message
    )

    if ($Actual -cne $Expected) {
        throw "$Message Expected '$Expected', got '$Actual'."
    }
}

function Assert-ThrowsLike {
    param(
        [scriptblock]$Action,
        [string]$Pattern,
        [string]$Message
    )

    try {
        & $Action
    }
    catch {
        if ($_.Exception.Message -like $Pattern) {
            return
        }
        throw "$Message Unexpected error: $($_.Exception.Message)"
    }

    throw "$Message No error was thrown."
}

function Invoke-Test {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    & $Action
    Write-Host "PASS: $Name" -ForegroundColor Green
}

function Get-ReviewTempDirectories {
    return @(
        Get-ChildItem -LiteralPath ([System.IO.Path]::GetTempPath()) `
            -Directory `
            -Filter 'share-codex-review-*' `
            -ErrorAction SilentlyContinue |
            ForEach-Object { $_.FullName }
    )
}

try {
    # Dot-sourcing loads the production functions without running the CLI body.
    . $shareScript -FolderPath $testRoot

    Invoke-Test 'inventory exclusions, oversize files, ordering, and hashes' {
        $source = Join-Path $testRoot 'inventory'
        New-Item -ItemType Directory -Path $source | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $source '.git') | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $source '.ssh') | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $source 'private') | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $source 'b.txt'), 'b')
        [System.IO.File]::WriteAllText((Join-Path $source 'A.txt'), 'a')
        [System.IO.File]::WriteAllText((Join-Path $source '.env'), 'ignored')
        [System.IO.File]::WriteAllText((Join-Path $source '.git\config'), 'ignored')
        [System.IO.File]::WriteAllText((Join-Path $source '.ssh\config'), 'ignored')
        [System.IO.File]::WriteAllText((Join-Path $source 'private\notes.txt'), 'ignored')
        [System.IO.File]::WriteAllBytes((Join-Path $source 'large.bin'), [byte[]](0..31))

        $AdditionalExclude = @('private', 'private/*')
        $inventory = Get-ShareInventory -RootPath $source -MaximumFileBytes 16
        $paths = @($inventory.Files | ForEach-Object { $_.RelativePath })
        Assert-Equal ($paths -join ',') 'A.txt,b.txt' 'Inventory paths were not filtered and sorted.'
        Assert-True ($inventory.ExcludedCount -ge 4) 'Expected excluded entries were not counted.'
        Assert-Equal $inventory.OversizeCount 1 'Oversized entry count differed.'
        Assert-True ($inventory.Files[0].ContentHash -match '^[a-f0-9]{64}$') 'Inventory hash was missing.'
    }

    Invoke-Test 'secret scan supports UTF-8, UTF-16, and malformed UTF-8' {
        $source = Join-Path $testRoot 'encodings'
        New-Item -ItemType Directory -Path $source | Out-Null
        $fakeSecret = 'ghp_' + ('A' * 36)
        $utf8Path = Join-Path $source 'utf8.txt'
        $utf16Path = Join-Path $source 'utf16.txt'
        $mixedPath = Join-Path $source 'mixed.txt'
        [System.IO.File]::WriteAllText($utf8Path, $fakeSecret, [System.Text.UTF8Encoding]::new($false))
        [System.IO.File]::WriteAllText($utf16Path, $fakeSecret, [System.Text.Encoding]::Unicode)
        $mixedBytes = [System.Collections.Generic.List[byte]]::new()
        $mixedBytes.AddRange([System.Text.Encoding]::ASCII.GetBytes('prefix'))
        $mixedBytes.Add(0xFF)
        $mixedBytes.AddRange([System.Text.Encoding]::ASCII.GetBytes($fakeSecret))
        [System.IO.File]::WriteAllBytes($mixedPath, $mixedBytes.ToArray())

        foreach ($path in @($utf8Path, $utf16Path, $mixedPath)) {
            $item = Get-Item -LiteralPath $path
            $entry = [pscustomobject]@{
                SourcePath = $path
                RelativePath = $item.Name
                Length = $item.Length
            }
            Assert-True (Test-ContainsPotentialSecret -File $entry) "Secret was not detected in $($item.Name)."
        }
    }

    Invoke-Test 'unreadable secret-scan input fails closed' {
        $path = Join-Path $testRoot 'locked.txt'
        [System.IO.File]::WriteAllText($path, 'safe')
        $item = Get-Item -LiteralPath $path
        $entry = [pscustomobject]@{
            SourcePath = $path
            RelativePath = $item.Name
            Length = $item.Length
        }
        $lock = [System.IO.FileStream]::new(
            $path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::None
        )
        try {
            Assert-ThrowsLike `
                -Action { Test-ContainsPotentialSecret -File $entry } `
                -Pattern "Unable to secret-scan*Nothing was shared*" `
                -Message 'Unreadable files must stop sharing.'
        }
        finally {
            $lock.Dispose()
        }
    }

    Invoke-Test 'staging rejects an equal-length source mutation' {
        $source = Join-Path $testRoot 'mutation-source'
        $destinationRoot = Join-Path $testRoot 'mutation-stage'
        New-Item -ItemType Directory -Path $source | Out-Null
        New-Item -ItemType Directory -Path $destinationRoot | Out-Null
        $sourcePath = Join-Path $source 'review.txt'
        $destinationPath = Join-Path $destinationRoot 'review.txt'
        [System.IO.File]::WriteAllText($sourcePath, 'first')
        $AdditionalExclude = @()
        $entry = (Get-ShareInventory -RootPath $source -MaximumFileBytes 1024).Files[0]
        [System.IO.File]::WriteAllText($sourcePath, 'other')

        Assert-ThrowsLike `
            -Action {
                Copy-InventoryEntry `
                    -File $entry `
                    -RootPath $source `
                    -DestinationPath $destinationPath
            } `
            -Pattern 'Source file changed during staging*' `
            -Message 'Equal-length source mutation was not rejected.'
    }

    Invoke-Test 'inventory and staging reject reparse-point traversal' {
        $source = Join-Path $testRoot 'reparse-source'
        $outside = Join-Path $testRoot 'reparse-outside'
        New-Item -ItemType Directory -Path (Join-Path $source 'nested') -Force | Out-Null
        New-Item -ItemType Directory -Path $outside -Force | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $source 'nested\review.txt'), 'inside')
        [System.IO.File]::WriteAllText((Join-Path $outside 'review.txt'), 'outside')
        $AdditionalExclude = @()
        $entry = (Get-ShareInventory -RootPath $source -MaximumFileBytes 1024).Files[0]
        Move-Item -LiteralPath (Join-Path $source 'nested') -Destination (Join-Path $source 'nested-original')
        New-Item -ItemType Junction -Path (Join-Path $source 'nested') -Target $outside | Out-Null

        Assert-ThrowsLike `
            -Action {
                Copy-InventoryEntry `
                    -File $entry `
                    -RootPath $source `
                    -DestinationPath (Join-Path $testRoot 'reparse-stage.txt')
            } `
            -Pattern 'Source path crossed a reparse point during staging*' `
            -Message 'Ancestor junction traversal was not rejected.'

        $junctionInventory = Get-ShareInventory -RootPath $source -MaximumFileBytes 1024
        Assert-True (
            @($junctionInventory.Files.RelativePath) -notcontains 'nested/review.txt'
        ) 'Inventory followed an ancestor junction.'
    }

    Invoke-Test 'validate-only succeeds and removes its staging directory' {
        $source = Join-Path $testRoot 'validate-success'
        New-Item -ItemType Directory -Path $source | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $source 'review.txt'), 'safe review content')
        $before = @(Get-ReviewTempDirectories)
        $output = & (Get-Command pwsh).Source `
            -NoLogo `
            -NoProfile `
            -File $shareScript `
            $source `
            -ValidateOnly `
            -NoQrCode 2>&1 | Out-String
        $exitCode = $LASTEXITCODE
        $after = @(Get-ReviewTempDirectories)
        $leftovers = @($after | Where-Object { $before -notcontains $_ })

        Assert-Equal $exitCode 0 'Validate-only returned a failure.'
        Assert-True ($output -like '*Validation complete. No public tunnel was opened.*') 'Validate-only success text was absent.'
        Assert-True ($output -notlike '*Share URL:*') 'Validate-only unexpectedly opened a public tunnel.'
        Assert-Equal $leftovers.Count 0 'Validate-only left a staging directory behind.'
        $pidMatch = [regex]::Match($output, 'Local read-only server verified:.*\(PID (\d+)\)')
        Assert-True $pidMatch.Success 'Validate-only did not report the server PID.'
        $serverPid = [int]$pidMatch.Groups[1].Value
        Assert-True ($null -eq (Get-Process -Id $serverPid -ErrorAction SilentlyContinue)) 'Validate-only left its server process running.'
    }

    Invoke-Test 'public confirmation cancels before cloudflared discovery' {
        $source = Join-Path $testRoot 'cancel-public'
        New-Item -ItemType Directory -Path $source | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $source 'review.txt'), 'safe')
        $output = 'CANCEL' | & (Get-Command pwsh).Source `
            -NoLogo `
            -NoProfile `
            -File $shareScript `
            $source `
            -NoQrCode 2>&1 | Out-String
        $exitCode = $LASTEXITCODE

        Assert-Equal $exitCode 0 'Cancellation returned a failure.'
        Assert-True ($output -like '*PUBLIC SHARING WARNING*') 'Public warning was absent.'
        Assert-True ($output -like '*Sharing cancelled. No public tunnel was opened.*') 'Cancellation confirmation was absent.'
        Assert-True ($output -notlike '*Share URL:*') 'Cancellation unexpectedly produced a public URL.'
    }

    Invoke-Test 'validate-only JSON uses the versioned NDJSON contract' {
        $source = Join-Path $testRoot 'validate-json'
        New-Item -ItemType Directory -Path $source | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $source 'review.txt'), 'safe')
        $outputLines = @(
            & (Get-Command pwsh).Source `
                -NoLogo `
                -NoProfile `
                -File $shareScript `
                $source `
                -ValidateOnly `
                -NoQrCode `
                -Json
        )
        $exitCode = $LASTEXITCODE
        $events = @($outputLines | ForEach-Object { $_ | ConvertFrom-Json })

        Assert-Equal $exitCode 0 'JSON validate-only returned a failure.'
        Assert-Equal (($events | ForEach-Object { $_.event }) -join ',') 'validated,cleanup' 'JSON lifecycle events differed.'
        $requiredFields = @(
            'schema_version', 'event', 'mode', 'public_url', 'expires_at',
            'server_pid', 'tunnel_pid', 'staging_root', 'error'
        ) | Sort-Object
        foreach ($event in $events) {
            $actualFields = @($event.PSObject.Properties.Name) | Sort-Object
            Assert-Equal ($actualFields -join ',') ($requiredFields -join ',') 'JSON fields differed.'
            Assert-Equal $event.schema_version 1 'JSON schema version differed.'
            Assert-Equal $event.mode 'validate_only' 'JSON mode differed.'
            Assert-True ($null -eq $event.public_url) 'Validate-only JSON included a public URL.'
            Assert-True ($null -eq $event.tunnel_pid) 'Validate-only JSON included a tunnel PID.'
            Assert-True ($null -eq $event.error) 'Successful validate-only JSON included an error.'
        }
        Assert-True (-not (Test-Path -LiteralPath $events[-1].staging_root)) 'JSON cleanup event referenced a live staging directory.'
        Assert-True ($null -eq (Get-Process -Id $events[0].server_pid -ErrorAction SilentlyContinue)) 'JSON validate-only left its server process running.'
    }

    Invoke-Test 'public JSON event exposes the documented live contract' {
        $Json = $true
        try {
            $event = Write-ReviewEvent `
                -Event 'public_ready' `
                -Mode 'public' `
                -PublicUrl 'https://example.trycloudflare.com/__index__.html' `
                -ExpiresAt '2026-07-19T13:00:00.0000000+00:00' `
                -ServerPid 101 `
                -TunnelPid 202 `
                -StagingRoot 'C:\Temp\staging' `
                -ErrorMessage $null | ConvertFrom-Json
        }
        finally {
            $Json = $false
        }

        Assert-Equal $event.schema_version 1 'Public JSON schema version differed.'
        Assert-Equal $event.event 'public_ready' 'Public JSON event name differed.'
        Assert-Equal $event.mode 'public' 'Public JSON mode differed.'
        Assert-Equal $event.server_pid 101 'Public JSON server PID differed.'
        Assert-Equal $event.tunnel_pid 202 'Public JSON tunnel PID differed.'
        Assert-True ($event.public_url -like 'https://*') 'Public JSON URL was absent.'
    }

    Invoke-Test 'machine errors redact paths and sensitive values' {
        $message = "Unable to read $testRoot; token=example-sensitive-value"
        $redacted = Get-RedactedMachineError `
            -Message $message `
            -SensitivePaths @($testRoot)
        Assert-True ($redacted -notlike "*$testRoot*") 'Machine error retained a local path.'
        Assert-True ($redacted -notlike '*example-sensitive-value*') 'Machine error retained a sensitive value.'
        Assert-True ($redacted -like '*[[]PATH[]]*') 'Machine error omitted the path redaction marker.'
        Assert-True ($redacted -like '*[[]REDACTED[]]*') 'Machine error omitted the sensitive-value marker.'

        $missingPath = Join-Path $testRoot 'missing-folder'
        $outputLines = @(
            & (Get-Command pwsh).Source `
                -NoLogo `
                -NoProfile `
                -File $shareScript `
                $missingPath `
                -ValidateOnly `
                -NoQrCode `
                -Json
        )
        $exitCode = $LASTEXITCODE
        $event = $outputLines[0] | ConvertFrom-Json
        Assert-Equal $exitCode 1 'Missing-folder JSON check did not fail.'
        Assert-Equal $event.event 'error' 'Missing-folder JSON did not emit an error event.'
        Assert-True ($event.error -notlike "*$missingPath*") 'Error event retained the missing local path.'
        Assert-True ($event.error -like '*[[]PATH[]]*') 'Error event omitted its path redaction marker.'
    }

    Invoke-Test 'headless wait ignores closed standard input' {
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        $timedOut = Wait-ForReviewStop `
            -Duration ([TimeSpan]::FromMilliseconds(75)) `
            -IgnoreStandardInput
        $stopwatch.Stop()
        Assert-True $timedOut 'Headless wait did not report a timeout.'
        Assert-True ($stopwatch.ElapsedMilliseconds -ge 50) 'Headless wait returned early on standard-input state.'
    }

    Invoke-Test 'temporary cleanup fails closed when a file is locked' {
        $cleanupRoot = Join-Path $testRoot 'cleanup-locked'
        New-Item -ItemType Directory -Path $cleanupRoot | Out-Null
        $lockedPath = Join-Path $cleanupRoot 'locked.txt'
        [System.IO.File]::WriteAllText($lockedPath, 'keep locked')
        $lock = [System.IO.FileStream]::new(
            $lockedPath,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::None
        )
        try {
            Assert-ThrowsLike `
                -Action { Remove-TemporaryRoot -Path $cleanupRoot } `
                -Pattern '*' `
                -Message 'Locked staging content must make cleanup fail.'
            Assert-True (Test-Path -LiteralPath $cleanupRoot) 'Failed cleanup was incorrectly reported as removed.'
        }
        finally {
            $lock.Dispose()
        }
        Remove-TemporaryRoot -Path $cleanupRoot
        Assert-True (-not (Test-Path -LiteralPath $cleanupRoot)) 'Unlocked staging content was not removed.'
    }

    Invoke-Test 'validate-only blocks empty and secret-bearing inventories' {
        $emptySource = Join-Path $testRoot 'validate-empty'
        $secretSource = Join-Path $testRoot 'validate-secret'
        New-Item -ItemType Directory -Path $emptySource | Out-Null
        New-Item -ItemType Directory -Path $secretSource | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $emptySource '.env'), 'excluded')
        $fakeSecret = 'ghp_' + ('B' * 36)
        [System.IO.File]::WriteAllText((Join-Path $secretSource 'credential.txt'), $fakeSecret)

        $emptyOutput = & (Get-Command pwsh).Source -NoLogo -NoProfile -File $shareScript $emptySource -ValidateOnly -NoQrCode 2>&1 | Out-String
        $emptyExitCode = $LASTEXITCODE
        $secretOutput = & (Get-Command pwsh).Source -NoLogo -NoProfile -File $shareScript $secretSource -ValidateOnly -NoQrCode 2>&1 | Out-String
        $secretExitCode = $LASTEXITCODE

        Assert-Equal $emptyExitCode 1 'Empty inventory did not fail.'
        Assert-True ($emptyOutput -like '*No shareable files remain after exclusions.*') 'Empty inventory error was absent.'
        Assert-Equal $secretExitCode 1 'Secret-bearing inventory did not fail.'
        Assert-True ($secretOutput -like '*credential.txt*') 'Secret-bearing path was not reported.'
        Assert-True ($secretOutput -notlike "*$fakeSecret*") 'Secret value leaked into diagnostics.'
        Assert-True ($secretOutput -notlike '*Local read-only server verified:*') 'Secret-bearing input reached the local server.'
    }

    Write-Host 'Windows Quick Tunnel tests: PASS' -ForegroundColor Green
}
finally {
    if (Test-Path -LiteralPath $testRoot) {
        $finalTestRoot = [System.IO.Path]::GetFullPath($testRoot)
        if (-not $finalTestRoot.StartsWith($expectedTestPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove unexpected path: $finalTestRoot"
        }
        Remove-Item -LiteralPath $finalTestRoot -Recurse -Force
    }
}
