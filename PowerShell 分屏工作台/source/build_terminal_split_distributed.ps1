$ErrorActionPreference = "Stop"

$compiler = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path -LiteralPath $compiler)) {
    throw "The .NET Framework C# compiler was not found: $compiler"
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$distDirectory = Join-Path $projectRoot "dist"
New-Item -ItemType Directory -Path $distDirectory -Force | Out-Null
$buildOutput = Join-Path $distDirectory "PowerShellSplitWorkbench.distributed.build.exe"
$localizedTitle = "powershell " + [char]0x5206 + [char]0x5C4F + [char]0x5DE5 + [char]0x4F5C + [char]0x53F0
$variantSuffix = [char]0x5206 + [char]0x5E03 + [char]0x5F00 + [char]0x542F
$output = Join-Path $distDirectory ($localizedTitle + " V1.1 - Mangetic - 2026-9-11 - " + $variantSuffix + ".exe")
$source = Join-Path $PSScriptRoot ("PowerShellSplitWorkbench-" + $variantSuffix + ".cs")
$manifest = Join-Path $PSScriptRoot "PowerShellSplitWorkbench.manifest"

if (-not (Test-Path -LiteralPath $source)) {
    throw "Distributed source file was not found: $source"
}

Remove-Item -LiteralPath $buildOutput -Force -ErrorAction SilentlyContinue
& $compiler /nologo /target:winexe /platform:anycpu /optimize+ /reference:System.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll "/win32manifest:$manifest" "/out:$buildOutput" $source
if ($LASTEXITCODE -ne 0) {
    throw "C# compilation failed with exit code $LASTEXITCODE."
}

try {
    Copy-Item -LiteralPath $buildOutput -Destination $output -Force
} catch {
    throw "Unable to update the distributed EXE. Close the running application and try again. Details: $($_.Exception.Message)"
} finally {
    Remove-Item -LiteralPath $buildOutput -Force -ErrorAction SilentlyContinue
}

Write-Host "Distributed build completed: $output"
