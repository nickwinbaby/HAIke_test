param([ValidateRange(1,65535)][int]$Port = 8765, [switch]$Lan, [switch]$Console)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $Console) {
    try {
        $pythonw = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
        if (-not (Test-Path -LiteralPath $pythonw)) {
            $candidate = Get-Command pythonw.exe -ErrorAction SilentlyContinue
            if ($candidate) { $pythonw = $candidate.Source }
            else {
                $pythonPath = & py.exe -3 -c 'import sys; print(sys.executable)'
                if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ was not found.' }
                $pythonw = Join-Path (Split-Path $pythonPath.Trim()) 'pythonw.exe'
            }
        }
        if (-not (Test-Path -LiteralPath $pythonw)) { throw 'Python 3.10+ with Tkinter is required.' }
        $arguments = @(('"{0}"' -f (Join-Path $PSScriptRoot 'launcher.py')), '--port', $Port)
        if ($Lan) { $arguments += '--lan' }
        Start-Process -FilePath $pythonw -ArgumentList $arguments -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
    }
    catch {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'GNN - Launcher error') | Out-Null
        exit 1
    }
    exit 0
}
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python environment setup failed.' }
}
& $pythonExe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'static\app.js'))) {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
}
$bindAddress = '127.0.0.1'
if ($Lan) {
    $bindAddress = '0.0.0.0'
    Write-Host 'LAN mode: trusted private networks only. No authentication.' -ForegroundColor Yellow
    Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object InterfaceAlias,IPAddress
}
Write-Host "Open http://127.0.0.1:$Port" -ForegroundColor Green
$maxMessageBytes = & $pythonExe -c 'from limits import MAX_MESSAGE; print(MAX_MESSAGE)'
if ($LASTEXITCODE -ne 0) { throw 'Failed to read the service capacity settings.' }
& $pythonExe -m uvicorn app:app --host $bindAddress --port $Port --workers 1 --ws-max-size $maxMessageBytes.Trim()
