@echo off
setlocal
cd /d "%~dp0"

where cl >nul 2>nul
if errorlevel 1 (
  set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
  if exist "%VSWHERE%" (
    for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do (
      set "VSINSTALL=%%i"
    )
  )

  if defined VSINSTALL (
    call "%VSINSTALL%\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
  )
)

where cl >nul 2>nul
if errorlevel 1 (
  echo Cannot find cl.exe.
  echo Please install Visual Studio Build Tools with "Desktop development with C++".
  echo Or run this bat from "x64 Native Tools Command Prompt for VS".
  exit /b 1
)

cl /nologo /EHsc /O2 /MT /utf-8 /DUNICODE /D_UNICODE RelayUsbTest.cpp ^
  /link /SUBSYSTEM:WINDOWS setupapi.lib hid.lib user32.lib gdi32.lib comctl32.lib ^
  /OUT:RelayUsbTest.exe

if errorlevel 1 (
  echo.
  echo Build failed.
  exit /b 1
)

echo.
echo Build ok: RelayUsbTest.exe
