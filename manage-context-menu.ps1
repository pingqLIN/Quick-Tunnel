#requires -Version 7.0

<#
.SYNOPSIS
Installs, removes, or inspects the per-user Explorer context menu entry.

.EXAMPLE
.\manage-context-menu.ps1 -Action Install

.EXAMPLE
.\manage-context-menu.ps1 -Action Status

.EXAMPLE
.\manage-context-menu.ps1 -Action Uninstall
#>

[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]
param(
    [ValidateSet('Install', 'Uninstall', 'Status')]
    [string]$Action = 'Status',

    [switch]$Yes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$shareScriptPath = Join-Path $PSScriptRoot 'share-codex-review.ps1'
$pwshCommand = Get-Command pwsh.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$menuText = '分享給 Codex / ChatGPT 審查'
$menuIcon = if ($null -ne $pwshCommand) { "$($pwshCommand.Source),0" } else { 'powershell.exe,0' }

$entries = @(
    [pscustomobject]@{
        Description = '資料夾本身的右鍵選單'
        KeyPath     = 'HKCU:\Software\Classes\Directory\shell\ShareCodexReview'
        FolderToken = '%1'
    },
    [pscustomobject]@{
        Description = '資料夾空白處的右鍵選單'
        KeyPath     = 'HKCU:\Software\Classes\Directory\Background\shell\ShareCodexReview'
        FolderToken = '%V'
    }
)

function Get-ExpectedCommand {
    param([string]$FolderToken)

    if ($null -eq $pwshCommand) {
        throw 'PowerShell 7 (pwsh.exe) was not found.'
    }

    return ('"{0}" -NoLogo -NoProfile -File "{1}" "{2}" -WaitForAcknowledgement' -f $pwshCommand.Source, $shareScriptPath, $FolderToken)
}

function Confirm-RegistryChange {
    param([string]$ExpectedWord)

    if ($Yes -or $WhatIfPreference) {
        return $true
    }

    $answer = Read-Host "Type $ExpectedWord to continue"
    return $answer -ceq $ExpectedWord
}

function Get-EntryStatus {
    param([object]$Entry)

    $commandKeyPath = Join-Path $Entry.KeyPath 'command'
    if (-not (Test-Path -LiteralPath $commandKeyPath)) {
        return 'Not installed'
    }

    $actualCommand = (Get-Item -LiteralPath $commandKeyPath).GetValue('')
    $expectedCommand = Get-ExpectedCommand -FolderToken $Entry.FolderToken
    if ($actualCommand -ceq $expectedCommand) {
        return 'Installed'
    }

    return 'Drift detected'
}

function Install-Entry {
    param([object]$Entry)

    $expectedCommand = Get-ExpectedCommand -FolderToken $Entry.FolderToken
    $commandKeyPath = Join-Path $Entry.KeyPath 'command'
    if (-not $PSCmdlet.ShouldProcess($Entry.KeyPath, 'Install Explorer context menu entry')) {
        return
    }

    New-Item -Path $Entry.KeyPath -Force | Out-Null
    Set-Item -Path $Entry.KeyPath -Value $menuText
    New-ItemProperty -Path $Entry.KeyPath -Name 'Icon' -Value $menuIcon -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $Entry.KeyPath -Name 'Position' -Value 'Top' -PropertyType String -Force | Out-Null
    if ($Entry.FolderToken -eq '%1') {
        New-ItemProperty -Path $Entry.KeyPath -Name 'MultiSelectModel' -Value 'Single' -PropertyType String -Force | Out-Null
    }

    New-Item -Path $commandKeyPath -Force | Out-Null
    Set-Item -Path $commandKeyPath -Value $expectedCommand
}

function Uninstall-Entry {
    param([object]$Entry)

    if (-not (Test-Path -LiteralPath $Entry.KeyPath)) {
        return
    }

    if ($PSCmdlet.ShouldProcess($Entry.KeyPath, 'Remove Explorer context menu entry')) {
        Remove-Item -LiteralPath $Entry.KeyPath -Recurse -Force
    }
}

try {
    if ($Action -eq 'Status') {
        foreach ($entry in $entries) {
            $status = Get-EntryStatus -Entry $entry
            Write-Host "$($entry.Description): $status"
        }
        return
    }

    if (-not (Test-Path -LiteralPath $shareScriptPath -PathType Leaf)) {
        throw "Share script not found: $shareScriptPath"
    }

    if ($Action -eq 'Install') {
        if (-not (Confirm-RegistryChange -ExpectedWord 'INSTALL')) {
            Write-Host 'Installation cancelled. Registry was not changed.' -ForegroundColor Yellow
            return
        }

        foreach ($entry in $entries) {
            Install-Entry -Entry $entry
        }

        if ($WhatIfPreference) {
            Write-Host 'Install preview complete. Registry was not changed.' -ForegroundColor Cyan
        }
        else {
            Write-Host 'Context menu installed for the current Windows user.' -ForegroundColor Green
            Write-Host 'On Windows 11, check "Show more options" if it is not visible in the first menu.'
        }
        return
    }

    if (-not (Confirm-RegistryChange -ExpectedWord 'REMOVE')) {
        Write-Host 'Removal cancelled. Registry was not changed.' -ForegroundColor Yellow
        return
    }

    foreach ($entry in $entries) {
        Uninstall-Entry -Entry $entry
    }

    if ($WhatIfPreference) {
        Write-Host 'Removal preview complete. Registry was not changed.' -ForegroundColor Cyan
    }
    else {
        Write-Host 'Context menu removed for the current Windows user.' -ForegroundColor Green
    }
}
catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
