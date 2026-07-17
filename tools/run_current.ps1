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

    ".cpp" {
        $dir = Split-Path -LiteralPath $File -Parent
        $buildBat = Join-Path $dir "build_msvc.bat"

        if (-not (Test-Path -LiteralPath $buildBat)) {
            Write-Host "No build_msvc.bat found in: $dir"
            Write-Host "This auto-run task currently supports the relay C++ folder."
            exit 1
        }

        Push-Location $dir
        try {
            Write-Host "Build C++: $File"
            & cmd /c build_msvc.bat
            if ($LASTEXITCODE -ne 0) {
                exit $LASTEXITCODE
            }

            $exe = Join-Path $dir "RelayUsbTest.exe"
            if (Test-Path -LiteralPath $exe) {
                Write-Host "Run C++ exe: $exe"
                & $exe
                exit $LASTEXITCODE
            }

            Write-Host "Build succeeded, but exe not found: $exe"
            exit 1
        }
        finally {
            Pop-Location
        }
    }

    default {
        Write-Host "Unsupported file type: $ext"
        Write-Host "Supported: .py, .cpp"
        exit 1
    }
}
