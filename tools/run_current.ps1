param(
    [Parameter(Mandatory = $true)]
    [string]$File,

    [Parameter(Mandatory = $true)]
    [string]$WorkspaceFolder
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $File)) {
    Write-Host "File not found: $File"
    exit 1
}

$ext = [System.IO.Path]::GetExtension($File).ToLowerInvariant()

switch ($ext) {
    ".py" {
        Write-Host "Run Python: $File"
        & python $File
        exit $LASTEXITCODE
    }

    default {
        Write-Host "Unsupported file type: $ext"
        Write-Host "Supported: .py"
        exit 1
    }
}
