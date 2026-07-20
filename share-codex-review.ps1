#requires -Version 7.0

<#
.SYNOPSIS
Temporarily shares a filtered, read-only copy of a folder for AI review.

.DESCRIPTION
Creates a temporary staging copy, excludes common secret and dependency paths,
serves the copy on 127.0.0.1, and opens a Cloudflare Quick Tunnel. The source
folder is never served directly. Sharing stops when Enter is pressed or when
the duration limit is reached.

.EXAMPLE
.\share-codex-review.ps1 "D:\Projects\MyProject"

.EXAMPLE
.\share-codex-review.ps1 "D:\Projects\MyProject" -DurationMinutes 10 -Yes
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$FolderPath,

    [ValidateRange(0, 65535)]
    [int]$Port = 0,

    [ValidateRange(1, 1440)]
    [int]$DurationMinutes = 30,

    [ValidateRange(1, 10240)]
    [int]$MaxFileSizeMB = 25,

    [ValidateRange(1, 5)]
    [int]$QuickTunnelAttempts = 3,

    [ValidateRange(1, 60)]
    [int]$QuickTunnelRetryBaseSeconds = 5,

    [string[]]$AdditionalExclude = @(),

    [switch]$Yes,

    [switch]$NoQrCode,

    [switch]$ValidateOnly,

    [switch]$WaitForAcknowledgement,

    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$excludedDirectoryNames = @(
    '.git', '.hg', '.svn', '.del',
    'node_modules', 'bower_components',
    '.venv', 'venv', '__pycache__',
    '.next', '.nuxt', '.cache',
    '.terraform', '.wrangler', '.cloudflared',
    '.ssh', '.gnupg', '.aws', '.azure', '.gcloud'
)

$excludedFilePatterns = @(
    '.env', '.env.*',
    '.npmrc', '.netrc', '.pypirc',
    '*.pem', '*.key', '*.pfx', '*.p12', '*.ppk',
    '*.kdbx', '*.jks', '*.keystore',
    'id_rsa*', 'id_ed25519*', 'id_ecdsa*', 'id_dsa*',
    'credentials*.json', 'service-account*.json', 'secrets.*',
    '*.tfstate', '*.tfstate.*'
)

$textFileExtensions = @(
    '.ps1', '.psm1', '.psd1', '.py', '.js', '.mjs', '.cjs', '.jsx',
    '.ts', '.tsx', '.json', '.jsonc', '.yaml', '.yml', '.toml', '.ini',
    '.config', '.conf', '.md', '.txt', '.html', '.htm', '.css', '.scss',
    '.xml', '.cs', '.fs', '.vb', '.go', '.rs', '.java', '.kt', '.rb',
    '.php', '.sh', '.bash', '.zsh', '.bat', '.cmd', '.sql', '.graphql', '.log'
)

$secretPatterns = @(
    '-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----',
    '\bAKIA[0-9A-Z]{16}\b',
    '\bgh[pousr]_[A-Za-z0-9]{36,255}\b',
    '\bgithub_pat_[A-Za-z0-9_]{20,255}\b',
    '\bsk-(?:proj-|svcacct-|ant-api\d{2}-)?[A-Za-z0-9_-]{20,255}\b',
    '\bxox[baprs]-[A-Za-z0-9-]{10,255}\b',
    '\bAIza[0-9A-Za-z_-]{35}\b'
)

function Test-IsReparsePoint {
    param([System.IO.FileSystemInfo]$Item)

    return [bool]($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
}

function Test-MatchesAdditionalExclude {
    param([string]$RelativePath)

    foreach ($pattern in $AdditionalExclude) {
        if ($RelativePath -like $pattern) {
            return $true
        }
    }

    return $false
}

function Test-IsExcludedFileName {
    param([string]$Name)

    foreach ($pattern in $excludedFilePatterns) {
        if ($Name -like $pattern) {
            return $true
        }
    }

    return $false
}

function Get-ShareInventory {
    param(
        [string]$RootPath,
        [long]$MaximumFileBytes
    )

    $files = [System.Collections.Generic.List[object]]::new()
    $pendingDirectories = [System.Collections.Generic.Stack[System.IO.DirectoryInfo]]::new()
    $pendingDirectories.Push([System.IO.DirectoryInfo]::new($RootPath))
    $excludedCount = 0
    $oversizeCount = 0

    while ($pendingDirectories.Count -gt 0) {
        $directory = $pendingDirectories.Pop()

        foreach ($childDirectory in $directory.EnumerateDirectories()) {
            $relativePath = [System.IO.Path]::GetRelativePath($RootPath, $childDirectory.FullName).Replace('\', '/')
            if (
                (Test-IsReparsePoint -Item $childDirectory) -or
                ($excludedDirectoryNames -contains $childDirectory.Name) -or
                (Test-MatchesAdditionalExclude -RelativePath $relativePath)
            ) {
                $excludedCount++
                continue
            }

            $pendingDirectories.Push($childDirectory)
        }

        foreach ($file in $directory.EnumerateFiles()) {
            $relativePath = [System.IO.Path]::GetRelativePath($RootPath, $file.FullName).Replace('\', '/')
            if (
                (Test-IsReparsePoint -Item $file) -or
                (Test-IsExcludedFileName -Name $file.Name) -or
                (Test-MatchesAdditionalExclude -RelativePath $relativePath)
            ) {
                $excludedCount++
                continue
            }

            if ($file.Length -gt $MaximumFileBytes) {
                $oversizeCount++
                continue
            }

            $files.Add([pscustomobject]@{
                SourcePath   = $file.FullName
                RelativePath = $relativePath
                Length       = $file.Length
                ContentHash  = Get-FileSha256 -Path $file.FullName -RelativePath $relativePath
            })
        }
    }

    $sortedFiles = @(
        $files | Sort-Object `
            @{ Expression = { $_.RelativePath.ToUpperInvariant() } }, `
            @{ Expression = { $_.RelativePath } }
    )

    return [pscustomobject]@{
        Files         = $sortedFiles
        ExcludedCount = $excludedCount
        OversizeCount = $oversizeCount
    }
}

function Get-FileSha256 {
    param(
        [string]$Path,
        [string]$RelativePath
    )

    try {
        $stream = [System.IO.FileStream]::new(
            $Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::Read
        )
        try {
            $sha256 = [System.Security.Cryptography.SHA256]::Create()
            try {
                $hashBytes = $sha256.ComputeHash($stream)
            }
            finally {
                $sha256.Dispose()
            }
        }
        finally {
            $stream.Dispose()
        }
    }
    catch {
        throw "Unable to inspect share candidate '$RelativePath'. Nothing was shared: $($_.Exception.Message)"
    }

    return -join ($hashBytes | ForEach-Object { $_.ToString('x2') })
}

function Get-ScannableTextContent {
    param([object]$File)

    try {
        $bytes = [System.IO.File]::ReadAllBytes($File.SourcePath)
    }
    catch {
        throw "Unable to secret-scan '$($File.RelativePath)'. Nothing was shared: $($_.Exception.Message)"
    }

    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
        return [System.Text.Encoding]::Unicode.GetString($bytes, 2, $bytes.Length - 2)
    }
    if ($bytes.Length -ge 2 -and $bytes[0] -eq 0xFE -and $bytes[1] -eq 0xFF) {
        return [System.Text.Encoding]::BigEndianUnicode.GetString($bytes, 2, $bytes.Length - 2)
    }
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        return [System.Text.Encoding]::UTF8.GetString($bytes, 3, $bytes.Length - 3)
    }

    # UTF-8 replacement decoding keeps the scan available for mixed or malformed
    # text while preserving ASCII secret markers. Read failures remain fail-closed.
    return [System.Text.Encoding]::UTF8.GetString($bytes)
}

function Test-ContainsPotentialSecret {
    param([object]$File)

    $extension = [System.IO.Path]::GetExtension($File.SourcePath).ToLowerInvariant()
    if (($textFileExtensions -notcontains $extension) -or $File.Length -gt 2MB) {
        return $false
    }

    $content = Get-ScannableTextContent -File $File
    foreach ($pattern in $secretPatterns) {
        if ([regex]::IsMatch($content, $pattern, [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)) {
            return $true
        }
    }

    return $false
}

function Copy-InventoryEntry {
    param(
        [object]$File,
        [string]$RootPath,
        [string]$DestinationPath
    )

    $rootItem = Get-Item -LiteralPath $RootPath -Force
    if (Test-IsReparsePoint -Item $rootItem) {
        throw 'The selected folder cannot be a reparse point.'
    }

    $rootFullPath = [System.IO.Path]::GetFullPath($RootPath).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $sourceFullPath = [System.IO.Path]::GetFullPath($File.SourcePath)
    $rootPrefix = $rootFullPath + [System.IO.Path]::DirectorySeparatorChar
    if (-not $sourceFullPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Source path escaped the selected folder during staging: $($File.RelativePath)"
    }

    $pathParts = @($File.RelativePath -split '/')
    $currentDirectory = $rootFullPath
    for ($partIndex = 0; $partIndex -lt $pathParts.Count - 1; $partIndex++) {
        $currentDirectory = Join-Path $currentDirectory $pathParts[$partIndex]
        $directoryItem = Get-Item -LiteralPath $currentDirectory -Force
        if (
            -not ($directoryItem -is [System.IO.DirectoryInfo]) -or
            (Test-IsReparsePoint -Item $directoryItem)
        ) {
            throw "Source path crossed a reparse point during staging: $($File.RelativePath)"
        }
    }

    $sourceItem = Get-Item -LiteralPath $sourceFullPath -Force
    if ((Test-IsReparsePoint -Item $sourceItem) -or -not ($sourceItem -is [System.IO.FileInfo])) {
        throw "Source path is no longer a regular file during staging: $($File.RelativePath)"
    }
    if ($sourceItem.Length -ne $File.Length) {
        throw "Source file changed during staging: $($File.RelativePath)"
    }

    $sourceStream = $null
    $destinationStream = $null
    try {
        $sourceStream = [System.IO.FileStream]::new(
            $sourceFullPath,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::Read
        )
        if ($sourceStream.Length -ne $File.Length) {
            throw "Source file changed during staging: $($File.RelativePath)"
        }

        $destinationStream = [System.IO.FileStream]::new(
            $DestinationPath,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        $sourceStream.CopyTo($destinationStream)
        $destinationStream.Flush($true)
        if ($destinationStream.Length -ne $File.Length) {
            throw "Staged file length mismatch: $($File.RelativePath)"
        }
    }
    finally {
        if ($null -ne $destinationStream) {
            $destinationStream.Dispose()
        }
        if ($null -ne $sourceStream) {
            $sourceStream.Dispose()
        }
    }

    $stagedHash = Get-FileSha256 -Path $DestinationPath -RelativePath $File.RelativePath
    if ($stagedHash -cne $File.ContentHash) {
        Remove-Item -LiteralPath $DestinationPath -Force -ErrorAction SilentlyContinue
        throw "Source file changed during staging: $($File.RelativePath)"
    }
}

function Write-HumanOutput {
    param(
        [string]$Message,
        [System.ConsoleColor]$ForegroundColor
    )

    if ($Json) {
        return
    }
    if ($PSBoundParameters.ContainsKey('ForegroundColor')) {
        Write-Host $Message -ForegroundColor $ForegroundColor
    }
    else {
        Write-Host $Message
    }
}

function Write-HumanWarning {
    param([string]$Message)

    if (-not $Json) {
        Write-Warning $Message
    }
}

function Write-ReviewEvent {
    param(
        [string]$Event,
        [ValidateSet('validate_only', 'public')]
        [string]$Mode,
        [AllowNull()]
        [object]$PublicUrl,
        [AllowNull()]
        [object]$ExpiresAt,
        [AllowNull()]
        [Nullable[int]]$ServerPid,
        [AllowNull()]
        [Nullable[int]]$TunnelPid,
        [AllowNull()]
        [object]$StagingRoot,
        [AllowNull()]
        [object]$ErrorMessage
    )

    if (-not $Json) {
        return
    }

    [ordered]@{
        schema_version = 1
        event          = $Event
        mode           = $Mode
        public_url     = $PublicUrl
        expires_at     = $ExpiresAt
        server_pid     = $ServerPid
        tunnel_pid     = $TunnelPid
        staging_root   = $StagingRoot
        error          = $ErrorMessage
    } | ConvertTo-Json -Compress | Write-Output
}

function Get-RedactedMachineError {
    param(
        [string]$Message,
        [AllowNull()]
        [object[]]$SensitivePaths = @()
    )

    $redacted = $Message -replace '(?i)(authorization|token|secret|password)(\s*[:=]\s*)(?:Bearer\s+)?\S+', '$1$2[REDACTED]'
    $pathStrings = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    foreach ($path in $SensitivePaths) {
        if ($null -eq $path -or [string]::IsNullOrWhiteSpace([string]$path)) {
            continue
        }
        [void]$pathStrings.Add([string]$path)
        try {
            [void]$pathStrings.Add([System.IO.Path]::GetFullPath([string]$path))
        }
        catch {
            # Keep the original spelling when the input is not a valid path.
        }
    }
    foreach ($pathString in @($pathStrings | Sort-Object Length -Descending)) {
        $redacted = [regex]::Replace(
            $redacted,
            [regex]::Escape($pathString),
            '[PATH]',
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
    }
    return $redacted
}

function Wait-ForReviewStop {
    param(
        [TimeSpan]$Duration,
        [switch]$IgnoreStandardInput
    )

    $delayTask = [System.Threading.Tasks.Task]::Delay($Duration)
    if ($IgnoreStandardInput) {
        $delayTask.GetAwaiter().GetResult()
        return $true
    }

    $readLineTask = [Console]::In.ReadLineAsync()
    $completedTask = [System.Threading.Tasks.Task]::WhenAny(
        $readLineTask,
        $delayTask
    ).GetAwaiter().GetResult()
    return [object]::ReferenceEquals($completedTask, $delayTask)
}

function Remove-TemporaryRoot {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
    if (Test-Path -LiteralPath $Path) {
        throw "Temporary staging directory still exists after cleanup: $Path"
    }
}

function ConvertTo-UrlPath {
    param([string]$RelativePath)

    $encodedSegments = foreach ($segment in ($RelativePath -split '/')) {
        [System.Uri]::EscapeDataString($segment)
    }

    return ($encodedSegments -join '/')
}

function New-ReviewIndex {
    param(
        [string]$DestinationPath,
        [object[]]$SharedFiles,
        [string]$SourceFolderName,
        [int]$ExcludedCount,
        [int]$OversizeCount
    )

    $builder = [System.Text.StringBuilder]::new()
    [void]$builder.AppendLine('<!doctype html>')
    [void]$builder.AppendLine('<html lang="en">')
    [void]$builder.AppendLine('<head>')
    [void]$builder.AppendLine('  <meta charset="utf-8">')
    [void]$builder.AppendLine('  <meta name="viewport" content="width=device-width, initial-scale=1">')
    [void]$builder.AppendLine('  <meta name="referrer" content="no-referrer">')
    [void]$builder.AppendLine('  <meta name="codex-review-index" content="true">')
    [void]$builder.AppendLine('  <meta http-equiv="Content-Security-Policy" content="default-src ''none''; style-src ''unsafe-inline''">')
    [void]$builder.AppendLine('  <title>Codex review files</title>')
    [void]$builder.AppendLine('  <style>body{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#1f2937}h1{margin-bottom:.25rem}.meta{color:#6b7280}ul{padding-left:1.25rem}li{margin:.35rem 0}a{color:#075985;text-decoration:none}a:hover{text-decoration:underline}.size{color:#6b7280;font-size:.85em;margin-left:.5rem}code{background:#f3f4f6;padding:.1rem .3rem;border-radius:.25rem}</style>')
    [void]$builder.AppendLine('</head>')
    [void]$builder.AppendLine('<body>')
    [void]$builder.AppendLine('  <h1>Codex review files</h1>')
    $safeFolderName = [System.Net.WebUtility]::HtmlEncode($SourceFolderName)
    [void]$builder.AppendLine(('  <p class="meta">Filtered read-only snapshot of <code>{0}</code>. {1} files shared; {2} paths excluded; {3} oversized files skipped.</p>' -f $safeFolderName, $SharedFiles.Count, $ExcludedCount, $OversizeCount))
    [void]$builder.AppendLine('  <ul>')

    foreach ($file in ($SharedFiles | Sort-Object OriginalRelativePath)) {
        $safeDisplayPath = [System.Net.WebUtility]::HtmlEncode($file.OriginalRelativePath)
        $safeHref = [System.Net.WebUtility]::HtmlEncode((ConvertTo-UrlPath -RelativePath $file.SharedRelativePath))
        $size = if ($file.Length -lt 1KB) {
            "$($file.Length) B"
        }
        elseif ($file.Length -lt 1MB) {
            '{0:N1} KB' -f ($file.Length / 1KB)
        }
        else {
            '{0:N1} MB' -f ($file.Length / 1MB)
        }
        [void]$builder.AppendLine(('    <li><a href="{0}">{1}</a><span class="size">{2}</span></li>' -f $safeHref, $safeDisplayPath, $size))
    }

    [void]$builder.AppendLine('  </ul>')
    [void]$builder.AppendLine('</body>')
    [void]$builder.AppendLine('</html>')
    [System.IO.File]::WriteAllText($DestinationPath, $builder.ToString(), [System.Text.UTF8Encoding]::new($false))
}

function Get-AvailableLoopbackPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    }
    finally {
        $listener.Stop()
    }
}

function Wait-ForLocalServer {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$Url
    )

    for ($attempt = 0; $attempt -lt 25; $attempt++) {
        if ($Process.HasExited) {
            throw "Local HTTP server exited with code $($Process.ExitCode)."
        }

        try {
            $response = Invoke-WebRequest -Uri $Url -Method Head -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                return
            }
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }

    throw "Local HTTP server did not become ready: $Url"
}

function Wait-ForQuickTunnelUrl {
    param(
        [System.Diagnostics.Process]$Process,
        [string[]]$LogPaths,
        [int]$TimeoutSeconds = 45
    )

    $deadline = [DateTimeOffset]::Now.AddSeconds($TimeoutSeconds)
    while ([DateTimeOffset]::Now -lt $deadline) {
        foreach ($logPath in $LogPaths) {
            if (Test-Path -LiteralPath $logPath) {
                $logContent = Get-Content -LiteralPath $logPath -Raw -ErrorAction SilentlyContinue
                if ($logContent -match 'https://[a-z0-9-]+\.trycloudflare\.com') {
                    return $Matches[0]
                }
            }
        }

        if ($Process.HasExited) {
            throw "Cloudflare Tunnel exited with code $($Process.ExitCode) before publishing a URL."
        }

        Start-Sleep -Milliseconds 500
    }

    throw "Timed out waiting for the Cloudflare Quick Tunnel URL."
}

function Test-IsRetryableQuickTunnelFailure {
    param([string[]]$LogPaths)

    $logParts = [System.Collections.Generic.List[string]]::new()
    foreach ($logPath in $LogPaths) {
        if (Test-Path -LiteralPath $logPath) {
            $logParts.Add((Get-Content -LiteralPath $logPath -Raw -ErrorAction SilentlyContinue))
        }
    }

    $logContent = [string]::Join([Environment]::NewLine, $logParts)
    $isServerFailure =
        $logContent -match '(?i)status_code="5\d{2}' -or
        $logContent -match '(?i)\b500 Internal Server Error\b' -or
        $logContent -match '(?i)error code:\s*1101\b'
    $isMalformedResponse =
        $logContent -match '(?i)Error unmarshaling QuickTunnel response' -or
        $logContent -match '(?i)failed to unmarshal quick Tunnel'

    return $isServerFailure -and $isMalformedResponse
}

function Test-PublicReviewUrl {
    param([string]$Url)

    for ($attempt = 0; $attempt -lt 8; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -TimeoutSec 10
            $contentType = [string]$response.Headers['Content-Type']
            if (
                $response.StatusCode -eq 200 -and
                $contentType.StartsWith('text/html', [System.StringComparison]::OrdinalIgnoreCase) -and
                $response.Content -match 'name="codex-review-index"'
            ) {
                return $contentType
            }
        }
        catch {
            # A new Quick Tunnel can need a few seconds before edge requests succeed.
        }

        Start-Sleep -Seconds 2
    }

    return $null
}

function Stop-ChildProcess {
    param([System.Diagnostics.Process]$Process)

    if ($null -ne $Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        $Process.WaitForExit(5000) | Out-Null
    }
}

function Get-TunnelErrorSummary {
    param([string[]]$LogPaths)

    $diagnosticLines = [System.Collections.Generic.List[string]]::new()
    foreach ($logPath in $LogPaths) {
        if ([string]::IsNullOrWhiteSpace($logPath) -or -not (Test-Path -LiteralPath $logPath)) {
            continue
        }

        foreach ($line in (Get-Content -LiteralPath $logPath -Tail 30 -ErrorAction SilentlyContinue)) {
            if ($line -match '(?i)\b(ERR|FTL|error|failed|failure|timeout|unable|denied|refused)\b') {
                $redactedLine = $line -replace '(?i)(authorization|token|secret|password)(\s*[:=]\s*)(?:Bearer\s+)?\S+', '$1$2[REDACTED]'
                $diagnosticLines.Add($redactedLine)
            }
        }
    }

    return @($diagnosticLines | Select-Object -Last 10)
}

$serverProcess = $null
$tunnelProcess = $null
$tunnelStdoutPath = $null
$tunnelStderrPath = $null
function Invoke-QuickTunnelReview {
    $temporaryRoot = $null
    $sharingStarted = $false
    $stoppedByTimeout = $false
    $exitCode = 0
    $publicReviewUrl = $null
    $stopTime = $null
    $resolvedPath = $null

try {
    if ($Json -and $WaitForAcknowledgement) {
        throw '-Json cannot be combined with -WaitForAcknowledgement.'
    }
    if ($Json -and -not $ValidateOnly -and -not $Yes) {
        throw '-Json public mode requires -Yes so stdout remains non-interactive NDJSON.'
    }

    if (-not (Test-Path -LiteralPath $FolderPath -PathType Container)) {
        throw "Folder not found: $FolderPath"
    }

    $resolvedPath = (Resolve-Path -LiteralPath $FolderPath).Path
    $pythonCommand = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $pythonPrefixArguments = @()
    if ($null -eq $pythonCommand) {
        $pythonCommand = Get-Command py -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        $pythonPrefixArguments = @('-3')
    }
    if ($null -eq $pythonCommand) {
        throw 'Python 3 was not found. Install Python 3 or add python/py to PATH.'
    }
    $pythonVersionCheck = & $pythonCommand.Source @pythonPrefixArguments -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.9 or newer is required. Interpreter check failed: $pythonVersionCheck"
    }

    $safeServerPath = Join-Path $PSScriptRoot 'safe-review-server.py'
    if (-not (Test-Path -LiteralPath $safeServerPath -PathType Leaf)) {
        throw "Safe review server not found: $safeServerPath"
    }

    Write-HumanOutput "Preparing filtered snapshot: $resolvedPath" -ForegroundColor Cyan
    $inventory = Get-ShareInventory -RootPath $resolvedPath -MaximumFileBytes ($MaxFileSizeMB * 1MB)
    if ($inventory.Files.Count -eq 0) {
        throw 'No shareable files remain after exclusions.'
    }

    $temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("share-codex-review-{0}" -f [guid]::NewGuid().ToString('N'))
    $shareRoot = Join-Path $temporaryRoot 'share'
    New-Item -ItemType Directory -Path $shareRoot -Force | Out-Null

    $sourceRelativePaths = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($file in $inventory.Files) {
        [void]$sourceRelativePaths.Add($file.RelativePath)
    }

    $indexSuffix = 0
    do {
        $indexFileName = if ($indexSuffix -eq 0) {
            '__codex_review__.html'
        }
        else {
            "__codex_review_$indexSuffix.html"
        }
        $indexSuffix++
    } while ($sourceRelativePaths.Contains($indexFileName))

    $sharedFiles = [System.Collections.Generic.List[object]]::new()
    $stagedFiles = [System.Collections.Generic.List[object]]::new()
    foreach ($file in $inventory.Files) {
        $sharedRelativePath = $file.RelativePath
        $nativeRelativePath = $sharedRelativePath.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
        $destinationPath = Join-Path $shareRoot $nativeRelativePath
        $destinationDirectory = Split-Path -Parent $destinationPath
        New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
        Copy-InventoryEntry `
            -File $file `
            -RootPath $resolvedPath `
            -DestinationPath $destinationPath
        $stagedFiles.Add([pscustomobject]@{
            SourcePath   = $destinationPath
            RelativePath = $file.RelativePath
            Length       = $file.Length
        })
        $sharedFiles.Add([pscustomobject]@{
            OriginalRelativePath = $file.RelativePath
            SharedRelativePath   = $sharedRelativePath
            Length               = $file.Length
        })
    }

    # Scan only the hash-verified staged bytes. Scanning the live source before
    # copying would leave a hash/scan/copy time-of-check-to-time-of-use gap.
    $potentialSecretPaths = [System.Collections.Generic.List[string]]::new()
    foreach ($file in $stagedFiles) {
        if (Test-ContainsPotentialSecret -File $file) {
            $potentialSecretPaths.Add($file.RelativePath)
        }
    }

    if ($potentialSecretPaths.Count -gt 0) {
        $pathList = ($potentialSecretPaths | Sort-Object | ForEach-Object { "  - $_" }) -join [Environment]::NewLine
        throw "Potential secret material was detected. Nothing was shared. Exclude or sanitize these files and retry:$([Environment]::NewLine)$pathList"
    }

    $indexPath = Join-Path $shareRoot $indexFileName
    New-ReviewIndex `
        -DestinationPath $indexPath `
        -SharedFiles $sharedFiles `
        -SourceFolderName (Split-Path -Leaf $resolvedPath) `
        -ExcludedCount $inventory.ExcludedCount `
        -OversizeCount $inventory.OversizeCount

    Write-HumanOutput "Snapshot ready: $($sharedFiles.Count) files; $($inventory.ExcludedCount) excluded; $($inventory.OversizeCount) oversized." -ForegroundColor Green
    if ($Port -eq 0) {
        $Port = Get-AvailableLoopbackPort
    }

    $localBaseUrl = "http://127.0.0.1:$Port"
    $localReviewUrl = "$localBaseUrl/$indexFileName"
    $serverStdoutPath = Join-Path $temporaryRoot 'python.stdout.log'
    $serverStderrPath = Join-Path $temporaryRoot 'python.stderr.log'
    $serverArguments = @($pythonPrefixArguments) + @(
        $safeServerPath,
        '--port', $Port.ToString(),
        '--bind', '127.0.0.1',
        '--directory', $shareRoot,
        '--index-name', $indexFileName
    )
    $serverProcess = Start-Process `
        -FilePath $pythonCommand.Source `
        -ArgumentList $serverArguments `
        -PassThru `
        -WindowStyle Hidden `
        -RedirectStandardOutput $serverStdoutPath `
        -RedirectStandardError $serverStderrPath

    Wait-ForLocalServer -Process $serverProcess -Url $localReviewUrl
    Write-HumanOutput "Local read-only server verified: $localReviewUrl (PID $($serverProcess.Id))" -ForegroundColor Green

    if ($ValidateOnly) {
        Write-HumanOutput 'Validation complete. No public tunnel was opened.' -ForegroundColor Green
        Write-ReviewEvent `
            -Event 'validated' `
            -Mode 'validate_only' `
            -PublicUrl $null `
            -ExpiresAt $null `
            -ServerPid $serverProcess.Id `
            -TunnelPid $null `
            -StagingRoot $temporaryRoot `
            -ErrorMessage $null
        return
    }

    Write-HumanOutput ''
    Write-HumanOutput 'PUBLIC SHARING WARNING' -ForegroundColor Yellow
    Write-HumanOutput 'Anyone with the generated URL can access the filtered snapshot until this process stops.' -ForegroundColor Yellow
    Write-HumanOutput 'The URL is not protected by a password or Cloudflare Access.' -ForegroundColor Yellow

    if (-not $Yes) {
        $approval = Read-Host 'Type SHARE to open the public tunnel (anything else cancels)'
        if ($approval -cne 'SHARE') {
            Write-HumanOutput 'Sharing cancelled. No public tunnel was opened.' -ForegroundColor Yellow
            return
        }
    }

    $cloudflaredCommand = Get-Command cloudflared -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $cloudflaredCommand) {
        throw 'cloudflared was not found. Install it and add it to PATH.'
    }

    $isolatedConfigPath = Join-Path $temporaryRoot 'cloudflared-empty.yml'
    [System.IO.File]::WriteAllText($isolatedConfigPath, '{}', [System.Text.UTF8Encoding]::new($false))
    $tunnelArguments = @(
        'tunnel',
        '--config', $isolatedConfigPath,
        '--url', $localBaseUrl,
        '--no-autoupdate',
        '--management-diagnostics=false',
        '--loglevel', 'info'
    )
    $publicBaseUrl = $null
    for ($tunnelAttempt = 1; $tunnelAttempt -le $QuickTunnelAttempts; $tunnelAttempt++) {
        $tunnelStdoutPath = Join-Path $temporaryRoot "cloudflared-attempt-$tunnelAttempt.stdout.log"
        $tunnelStderrPath = Join-Path $temporaryRoot "cloudflared-attempt-$tunnelAttempt.stderr.log"
        $tunnelProcess = Start-Process `
            -FilePath $cloudflaredCommand.Source `
            -ArgumentList $tunnelArguments `
            -PassThru `
            -WindowStyle Hidden `
            -RedirectStandardOutput $tunnelStdoutPath `
            -RedirectStandardError $tunnelStderrPath

        try {
            $publicBaseUrl = Wait-ForQuickTunnelUrl `
                -Process $tunnelProcess `
                -LogPaths @($tunnelStdoutPath, $tunnelStderrPath)
            break
        }
        catch {
            $startupError = $_
            Stop-ChildProcess -Process $tunnelProcess
            $retryable = Test-IsRetryableQuickTunnelFailure -LogPaths @($tunnelStdoutPath, $tunnelStderrPath)
            if (-not $retryable -or $tunnelAttempt -eq $QuickTunnelAttempts) {
                throw $startupError
            }

            $retryDelaySeconds = [Math]::Min(
                $QuickTunnelRetryBaseSeconds * [Math]::Pow(2, $tunnelAttempt - 1),
                60
            )
            Write-HumanWarning "Cloudflare Quick Tunnel returned a transient 500/1101 response. Retrying attempt $($tunnelAttempt + 1) of $QuickTunnelAttempts in $retryDelaySeconds second(s)."
            Start-Sleep -Seconds $retryDelaySeconds
        }
    }

    if ([string]::IsNullOrWhiteSpace($publicBaseUrl)) {
        throw 'Cloudflare Quick Tunnel did not publish a URL.'
    }

    $publicReviewUrl = "$publicBaseUrl/$indexFileName"
    $sharingStarted = $true

    $publicContentType = Test-PublicReviewUrl -Url $publicReviewUrl
    Write-HumanOutput ''
    Write-HumanOutput 'Share URL:' -ForegroundColor Cyan
    Write-HumanOutput $publicReviewUrl -ForegroundColor Green
    if ($null -ne $publicContentType) {
        Write-HumanOutput "Public verification: HTTP 200, $publicContentType" -ForegroundColor Green
    }
    else {
        Write-HumanWarning 'The tunnel URL was created, but public HTTP verification did not succeed yet.'
    }
    Write-HumanOutput "Server PID: $($serverProcess.Id) | Tunnel PID: $($tunnelProcess.Id)"

    if (-not $NoQrCode -and -not $Json) {
        $qrEncodeCommand = Get-Command qrencode -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $qrEncodeCommand) {
            Write-HumanOutput ''
            & $qrEncodeCommand.Source -t ANSIUTF8 $publicReviewUrl
        }
        else {
            Write-HumanOutput 'QR code: qrencode is not installed; use the URL above.' -ForegroundColor DarkGray
        }
    }

    $stopTime = [DateTimeOffset]::Now.AddMinutes($DurationMinutes)
    Write-HumanOutput ''
    Write-HumanOutput "Quick Tunnel lifetime: $DurationMinutes minute(s)."
    Write-HumanOutput "Press ENTER to stop early. Automatic stop: $($stopTime.ToLocalTime().ToString('yyyy-MM-dd HH:mm:ss zzz'))"
    Write-ReviewEvent `
        -Event 'public_ready' `
        -Mode 'public' `
        -PublicUrl $publicReviewUrl `
        -ExpiresAt $stopTime.ToUniversalTime().ToString('o') `
        -ServerPid $serverProcess.Id `
        -TunnelPid $tunnelProcess.Id `
        -StagingRoot $temporaryRoot `
        -ErrorMessage $null
    $stoppedByTimeout = Wait-ForReviewStop `
        -Duration ([TimeSpan]::FromMinutes($DurationMinutes)) `
        -IgnoreStandardInput:$Json
    if ($stoppedByTimeout) {
        $stoppedByTimeout = $true
        Write-HumanOutput 'Quick Tunnel lifetime expired. Stopping public sharing now.' -ForegroundColor Yellow
    }
}
catch {
    $exitCode = 1
    Write-HumanOutput "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    $machineError = Get-RedactedMachineError `
        -Message $_.Exception.Message `
        -SensitivePaths @($FolderPath, $resolvedPath, $temporaryRoot)
    Write-ReviewEvent `
        -Event 'error' `
        -Mode $(if ($ValidateOnly) { 'validate_only' } else { 'public' }) `
        -PublicUrl $publicReviewUrl `
        -ExpiresAt $(if ($null -ne $stopTime) { $stopTime.ToUniversalTime().ToString('o') } else { $null }) `
        -ServerPid $(if ($null -ne $serverProcess) { $serverProcess.Id } else { $null }) `
        -TunnelPid $(if ($null -ne $tunnelProcess) { $tunnelProcess.Id } else { $null }) `
        -StagingRoot $temporaryRoot `
        -ErrorMessage $machineError
    $tunnelDiagnostics = @(Get-TunnelErrorSummary -LogPaths @($tunnelStdoutPath, $tunnelStderrPath))
    if ($tunnelDiagnostics.Count -gt 0) {
        Write-HumanOutput 'cloudflared diagnostic summary:' -ForegroundColor Yellow
        foreach ($diagnosticLine in $tunnelDiagnostics) {
            Write-HumanOutput "  $diagnosticLine" -ForegroundColor Yellow
        }
    }
}
finally {
    $cleanupRoot = $temporaryRoot
    $cleanupError = $null
    Stop-ChildProcess -Process $tunnelProcess
    Stop-ChildProcess -Process $serverProcess

    if ($null -ne $temporaryRoot -and (Test-Path -LiteralPath $temporaryRoot)) {
        try {
            Remove-TemporaryRoot -Path $temporaryRoot
        }
        catch {
            $exitCode = 1
            $cleanupError = $_.Exception
            $machineCleanupError = Get-RedactedMachineError `
                -Message "Temporary-file cleanup failed: $($cleanupError.Message)" `
                -SensitivePaths @($FolderPath, $resolvedPath, $temporaryRoot)
            Write-HumanOutput "ERROR: $machineCleanupError" -ForegroundColor Red
            Write-ReviewEvent `
                -Event 'error' `
                -Mode $(if ($ValidateOnly) { 'validate_only' } else { 'public' }) `
                -PublicUrl $publicReviewUrl `
                -ExpiresAt $(if ($null -ne $stopTime) { $stopTime.ToUniversalTime().ToString('o') } else { $null }) `
                -ServerPid $(if ($null -ne $serverProcess) { $serverProcess.Id } else { $null }) `
                -TunnelPid $(if ($null -ne $tunnelProcess) { $tunnelProcess.Id } else { $null }) `
                -StagingRoot $temporaryRoot `
                -ErrorMessage $machineCleanupError
        }
    }

    if ($sharingStarted) {
        if ($null -eq $cleanupError) {
            Write-HumanOutput "Sharing stopped at $([DateTimeOffset]::Now.ToLocalTime().ToString('yyyy-MM-dd HH:mm:ss zzz')). Temporary files were removed." -ForegroundColor Green
        }
        else {
            Write-HumanOutput "Sharing stopped, but temporary-file cleanup failed. Review the error above." -ForegroundColor Red
        }
    }

    if ($null -ne $cleanupRoot -and $null -eq $cleanupError) {
        Write-ReviewEvent `
            -Event 'cleanup' `
            -Mode $(if ($ValidateOnly) { 'validate_only' } else { 'public' }) `
            -PublicUrl $publicReviewUrl `
            -ExpiresAt $(if ($null -ne $stopTime) { $stopTime.ToUniversalTime().ToString('o') } else { $null }) `
            -ServerPid $(if ($null -ne $serverProcess) { $serverProcess.Id } else { $null }) `
            -TunnelPid $(if ($null -ne $tunnelProcess) { $tunnelProcess.Id } else { $null }) `
            -StagingRoot $cleanupRoot `
            -ErrorMessage $null
    }

    if (-not $Json -and $WaitForAcknowledgement -and ($stoppedByTimeout -or $exitCode -ne 0)) {
        $acknowledgementPrompt = if ($exitCode -ne 0) {
            'Startup failed. Review the error above, then press ENTER to close this window'
        }
        else {
            'Quick Tunnel has expired and is closed. Press ENTER to close this window'
        }
        Write-HumanOutput $acknowledgementPrompt -ForegroundColor Yellow
        Read-Host | Out-Null
    }

    if ($null -ne $cleanupError) {
        throw $cleanupError
    }
}

if ($exitCode -ne 0) {
    exit $exitCode
}
}

if ($MyInvocation.InvocationName -ne '.') {
    Invoke-QuickTunnelReview
}
