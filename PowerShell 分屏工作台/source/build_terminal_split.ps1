$ErrorActionPreference = "Stop"

$compiler = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path -LiteralPath $compiler)) {
    throw "The .NET Framework C# compiler was not found: $compiler"
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$distDirectory = Join-Path $projectRoot "dist"
New-Item -ItemType Directory -Path $distDirectory -Force | Out-Null
$buildOutput = Join-Path $distDirectory "PowerShellSplitWorkbench.build.exe"
$iconGeneratorOutput = Join-Path $distDirectory "GenerateWorkbenchIcon.build.exe"
$loggerOutput = Join-Path $distDirectory "PowerShellSplitWorkbench.PaneLogger.exe"
$legacyLoggerOutput = Join-Path $distDirectory "PowerShellSplitWorkbench.PaneLogger.legacy-delete-me.exe"
$pendingLoggerOutput = Join-Path $distDirectory "PowerShellSplitWorkbench.PaneLogger.pending-delete"
$localizedTitle = "powershell " + [char]0x5206 + [char]0x5C4F + [char]0x5DE5 + [char]0x4F5C + [char]0x53F0
$output = Join-Path $distDirectory ($localizedTitle + " V1.3.1 - Mangetic - 2026-9-11.exe")
$source = Join-Path $PSScriptRoot "PowerShellSplitWorkbench.cs"
$loggerSource = Join-Path $PSScriptRoot "PowerShellSplitWorkbench.PaneLogger.cs"
$iconGeneratorSource = Join-Path $PSScriptRoot "GenerateWorkbenchIcon.cs"
$assetsDirectory = Join-Path $projectRoot "assets"
$icon = Join-Path $assetsDirectory "powershell-split-workbench.ico"
$iconPreview = Join-Path $assetsDirectory "powershell-split-workbench.png"
$wtInstaller = Join-Path $assetsDirectory "Windows Terminal Installer.exe"
$manifest = Join-Path $PSScriptRoot "PowerShellSplitWorkbench.manifest"

if (-not (Test-Path -LiteralPath $wtInstaller)) {
    throw "The embedded Windows Terminal installer was not found: $wtInstaller"
}
$expectedInstallerHash = "A78B8A22B3FDA382D74FD0575876C5A9E681D6E8D2866D0709BB43765C9F24A6"
$actualInstallerHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $wtInstaller).Hash
if ($actualInstallerHash -ne $expectedInstallerHash) {
    throw "The Windows Terminal installer SHA-256 does not match the approved Microsoft-signed asset."
}

Remove-Item -LiteralPath $buildOutput -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $iconGeneratorOutput -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $assetsDirectory -Force | Out-Null
& $compiler /nologo /target:exe /platform:anycpu /optimize+ /reference:System.dll /reference:System.Drawing.dll "/out:$iconGeneratorOutput" $iconGeneratorSource
if ($LASTEXITCODE -ne 0) {
    throw "Icon generator compilation failed with exit code $LASTEXITCODE."
}
& $iconGeneratorOutput $icon $iconPreview
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $icon)) {
    throw "Icon generation failed with exit code $LASTEXITCODE."
}
& $compiler /nologo /target:winexe /main:Program /platform:anycpu /optimize+ /reference:System.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:System.Management.dll "/win32manifest:$manifest" "/win32icon:$icon" "/resource:$wtInstaller,PowerShellSplitWorkbench.WindowsTerminalInstaller.exe" "/out:$buildOutput" $source $loggerSource
if ($LASTEXITCODE -ne 0) {
    throw "C# compilation failed with exit code $LASTEXITCODE."
}

try {
    # Never rename a running main EXE to make an update appear successful.
    # That hid stale GUI processes under a pending-delete filename and made
    # them look unrelated in Task Manager. If the application is still open,
    # fail clearly and preserve both the running build and its filename.
    Copy-Item -LiteralPath $buildOutput -Destination $output -Force -ErrorAction Stop
    if (Test-Path -LiteralPath $loggerOutput) {
        try {
            Remove-Item -LiteralPath $loggerOutput -Force -ErrorAction Stop
        } catch {
            # Windows allows a running EXE to be renamed but not deleted.
            # Remove the .exe suffix so new launches cannot use the legacy file;
            # the application and future builds retry deletion after old panes exit.
            try {
                if (Test-Path -LiteralPath $pendingLoggerOutput) {
                    Remove-Item -LiteralPath $pendingLoggerOutput -Force -ErrorAction SilentlyContinue
                }
                Move-Item -LiteralPath $loggerOutput -Destination $pendingLoggerOutput -Force -ErrorAction Stop
            } catch { }
        }
    }
    Remove-Item -LiteralPath $legacyLoggerOutput -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pendingLoggerOutput -Force -ErrorAction SilentlyContinue
} catch {
    throw "Unable to update the final EXE. Close the PowerShell split workbench window and run the build again. Windows Terminal panes do not need to be closed. Details: $($_.Exception.Message)"
} finally {
    Remove-Item -LiteralPath $buildOutput -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $iconGeneratorOutput -Force -ErrorAction SilentlyContinue
}

Write-Host "Build completed: $output"
Write-Host "Pane logger is embedded in the main EXE."
Write-Host "Microsoft-signed Windows Terminal installer is embedded in the main EXE."
Write-Host "Application icon embedded: $icon"
