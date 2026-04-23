@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title TMMI - Tuomi's Magisk Module Installer

REM ════════════════════════════════════════════════════════════════
REM  DEBUG MODE CHECK  (run.bat debug)
REM ════════════════════════════════════════════════════════════════
set DEBUG=0
if /i "%1"=="debug" set DEBUG=1

REM ── Use local ADB ──
if exist "adb.exe" (
    set ADB=.\adb.exe
) else (
    set ADB=adb
)

REM ════════════════════════════════════════════════════════════════
REM  LOAD CONFIG  (tmmi.cfg)
REM ════════════════════════════════════════════════════════════════
set CFG=tmmi.cfg
set SAVED_IP=
set SAVED_MODE=
set SAVED_PORT=5000
set SKIP_BANNER=0

if exist "%CFG%" (
    for /f "usebackq tokens=1,2 delims==" %%A in ("%CFG%") do (
        if "%%A"=="last_ip"     set SAVED_IP=%%B
        if "%%A"=="last_mode"   set SAVED_MODE=%%B
        if "%%A"=="port"        set SAVED_PORT=%%B
        if "%%A"=="skip_banner" set SKIP_BANNER=%%B
    )
)

REM ════════════════════════════════════════════════════════════════
REM  BANNER
REM ════════════════════════════════════════════════════════════════
if "%SKIP_BANNER%"=="1" goto skip_banner
cls
echo.
echo   ████████╗███╗   ███╗███╗   ███╗██╗
echo   ╚══██╔══╝████╗ ████║████╗ ████║██║
echo      ██║   ██╔████╔██║██╔████╔██║██║
echo      ██║   ██║╚██╔╝██║██║╚██╔╝██║██║
echo      ██║   ██║ ╚═╝ ██║██║ ╚═╝ ██║██║
echo      ╚═╝   ╚═╝     ╚═╝╚═╝     ╚═╝╚═╝
echo.
echo   Tuomi's Magisk Module Installer
if "%DEBUG%"=="1" (
    echo   ┌─────────────────────────────────────────────────────┐
    echo   │                  DEBUG MODE ACTIVE                  │
    echo   └─────────────────────────────────────────────────────┘
)
echo   ─────────────────────────────────────────────────────────
echo.
:skip_banner

REM ════════════════════════════════════════════════════════════════
REM  PYTHON CHECK  (run once at top)
REM ════════════════════════════════════════════════════════════════
python --version >nul 2>nul
if %errorlevel% neq 0 (
    python3 --version >nul 2>nul
    if %errorlevel% neq 0 (
        echo   [FAIL]  Python not found.
        echo           Install from https://www.python.org/downloads/
        echo.
        pause & exit /b 1
    )
    set PYTHON=python3
) else (
    set PYTHON=python
)
echo   [  OK  ]  Python found

REM ════════════════════════════════════════════════════════════════
REM  DEPENDENCY CHECK  (run once at top)
REM ════════════════════════════════════════════════════════════════
echo   Checking dependencies...
%PYTHON% -c "import flask, flask_socketio, requests" >nul 2>nul
if %errorlevel% neq 0 (
    echo   [ INS ]  Installing dependencies...
    %PYTHON% -m pip install -r requirements.txt --quiet
    if %errorlevel% neq 0 (
        echo   [FAIL]  pip install failed. Run manually:
        echo           pip install -r requirements.txt
        pause & exit /b 1
    )
    echo   [  OK  ]  Dependencies installed
) else (
    echo   [  OK  ]  Dependencies already satisfied
)
o   [  OK  ]  Dependencies already satisfied
)
echo.

REM ════════════════════════════════════════════════════════════════
REM  DEBUG: SKIP DEVICE CHECK
REM ════════════════════════════════════════════════════════════════
if "%DEBUG%"=="1" (
    echo   [DEBUG]  Skipping device check - launching UI only
    echo   [DEBUG]  Port: %SAVED_PORT%
    echo.
    goto launch
)

REM ════════════════════════════════════════════════════════════════
REM  ADB CHECK
REM ════════════════════════════════════════════════════════════════
%ADB% version >nul 2>nul
if %errorlevel% neq 0 (
    echo   [FAIL]  ADB not found.
    echo           Place adb.exe + AdbWinApi.dll + AdbWinUsbApi.dll next to run.bat
    echo           Download: https://developer.android.com/tools/releases/platform-tools
    echo.
    pause & exit /b 1
)
echo   [  OK  ]  ADB found
echo.

REM ════════════════════════════════════════════════════════════════
REM  ADB SERVER RESTART
REM ════════════════════════════════════════════════════════════════
%ADB% kill-server >nul 2>nul
timeout /t 1 /nobreak >nul
%ADB% start-server >nul 2>nul

REM ════════════════════════════════════════════════════════════════
REM  SCAN FOR CONNECTED DEVICES
REM ════════════════════════════════════════════════════════════════
echo   ─────────────────────────────────────────────────────────
echo   Scanning for connected devices...
echo.

set FOUND_USB=
set FOUND_WIFI=
set DEVICE=

for /f "tokens=1,2" %%A in ('%ADB% devices ^| findstr /v "List"') do (
    if "%%B"=="device" (
        echo %%A | findstr /r "[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*" >nul
        if !errorlevel! equ 0 (
            if not defined FOUND_WIFI set FOUND_WIFI=%%A
        ) else (
            if not defined FOUND_USB set FOUND_USB=%%A
        )
    )
)

if defined FOUND_USB  echo   [FOUND]  USB device:  %FOUND_USB%
if defined FOUND_WIFI echo   [FOUND]  WiFi device: %FOUND_WIFI%
if not defined FOUND_USB if not defined FOUND_WIFI echo   [ -- ]   No devices currently connected

REM ── Offer to use already-connected USB device ──
if defined FOUND_USB (
    echo.
    set USE_EXISTING=Y
    set /p USE_EXISTING=   Use already-connected USB device? [Y/n]: 
    if /i "!USE_EXISTING!" neq "n" (
        set DEVICE=%FOUND_USB%
        call :get_device_info
        call :check_magisk
        call :check_battery
        goto try_wifi_existing
    )
)

REM ── Offer to use already-connected WiFi device ──
if defined FOUND_WIFI (
    echo.
    set USE_EXISTING=Y
    set /p USE_EXISTING=   Use already-connected WiFi device (%FOUND_WIFI%)? [Y/n]: 
    if /i "!USE_EXISTING!" neq "n" (
        set DEVICE=%FOUND_WIFI%
        call :get_device_info
        call :check_magisk
        call :check_battery
        goto launch
    )
)

REM ════════════════════════════════════════════════════════════════
REM  CONNECTION MODE SELECTION
REM ════════════════════════════════════════════════════════════════
:choose_mode
echo.
echo   ─────────────────────────────────────────────────────────
echo   Connection Mode:
echo.
echo     [1]  USB + switch to Wireless  (recommended)
echo     [2]  USB only
echo     [3]  Wireless only
echo.
if defined SAVED_MODE echo   Last used mode: %SAVED_MODE%
echo.
set MODECHOICE=
set /p MODECHOICE=   Choose [1/2/3]: 
if "!MODECHOICE!"=="" set MODECHOICE=%SAVED_MODE%
if "!MODECHOICE!"=="1" goto mode_usb_wifi
if "!MODECHOICE!"=="2" goto mode_usb_only
if "!MODECHOICE!"=="3" goto mode_wifi_only
echo   Invalid choice, defaulting to 1.
goto mode_usb_wifi

REM ════════════════════════════════════════════════════════════════
REM  MODE 1: USB → WIFI
REM ════════════════════════════════════════════════════════════════
:mode_usb_wifi
set SAVED_MODE=1
echo.
echo   ─────────────────────────────────────────────────────────
echo   Connect your phone via USB. Ensure USB Debugging is on.
echo.
pause
call :wait_usb
if not defined DEVICE goto fail_no_device
call :get_device_info
call :check_magisk
call :check_battery

:try_wifi_existing
call :get_ip
if not defined PHONE_IP (
    echo   [WARN]  Could not get IP. Staying on USB.
    goto launch
)
echo   [ ..  ]  Switching to WiFi ADB...
%ADB% tcpip 5555 >nul 2>nul
timeout /t 2 /nobreak >nul
%ADB% disconnect >nul 2>nul
timeout /t 1 /nobreak >nul
%ADB% connect %PHONE_IP%:5555 >nul 2>nul
timeout /t 3 /nobreak >nul

%ADB% devices | find "%PHONE_IP%" >nul
if %errorlevel% equ 0 (
    echo   [  OK  ]  WiFi ADB connected: %PHONE_IP%
    set DEVICE=%PHONE_IP%:5555
) else (
    echo   [WARN]  WiFi failed, staying on USB: %DEVICE%
)
goto launch

REM ════════════════════════════════════════════════════════════════
REM  MODE 2: USB ONLY
REM ════════════════════════════════════════════════════════════════
:mode_usb_only
set SAVED_MODE=2
echo.
echo   Connect your phone via USB.
echo.
pause
call :wait_usb
if not defined DEVICE goto fail_no_device
call :get_device_info
call :check_magisk
call :check_battery
goto launch

REM ════════════════════════════════════════════════════════════════
REM  MODE 3: WIFI ONLY
REM ════════════════════════════════════════════════════════════════
:mode_wifi_only
set SAVED_MODE=3
echo.
if defined SAVED_IP (
    echo   Last used IP: %SAVED_IP%
    set PHONE_IP=
    set /p PHONE_IP=   Enter device IP [Enter to use %SAVED_IP%]: 
    if "!PHONE_IP!"=="" set PHONE_IP=%SAVED_IP%
) else (
    set /p PHONE_IP=   Enter device IP address: 
)
if not defined PHONE_IP goto fail_no_device

echo   [ ..  ]  Connecting to !PHONE_IP!:5555...
%ADB% connect !PHONE_IP!:5555 >nul 2>nul
timeout /t 3 /nobreak >nul

%ADB% devices | find "!PHONE_IP!" >nul
if %errorlevel% neq 0 (
    echo   [FAIL]  Could not connect to !PHONE_IP!:5555
    echo           Ensure Wireless Debugging is enabled.
    pause & exit /b 1
)
echo   [  OK  ]  Connected: !PHONE_IP!:5555
set DEVICE=!PHONE_IP!:5555
call :get_device_info
call :check_magisk
call :check_battery
goto launch

REM ════════════════════════════════════════════════════════════════
REM  LAUNCH
REM ════════════════════════════════════════════════════════════════
:launch
call :check_port
call :save_config

echo.
echo   ─────────────────────────────────────────────────────────
echo   Launch Summary
echo   ─────────────────────────────────────────────────────────
if defined DEVICE_NAME  echo   Device  : %DEVICE_NAME%
if defined DEVICE       echo   ADB ID  : %DEVICE%
if defined MAGISK_VER   echo   Magisk  : %MAGISK_VER%
if "%DEBUG%"=="1"  (    echo   Mode    : DEBUG ^(no device^) )
echo   Port    : %SAVED_PORT%
echo   URL     : http://localhost:%SAVED_PORT%
echo   ─────────────────────────────────────────────────────────

REM ── Debug: list installed modules ──
if "%DEBUG%"=="1" (
    echo.
    echo   [DEBUG]  Installed Magisk Modules:
    echo   ─────────────────────────────────────────────────────────
    for /f "delims=" %%M in ('%ADB% -s %DEVICE% shell "ls /data/adb/modules 2>/dev/null"') do (
        set MOD_STATE=enabled
        for /f "delims=" %%S in ('%ADB% -s %DEVICE% shell "[ -f /data/adb/modules/%%M/disable ] && echo disabled || echo enabled" 2^>nul') do (
            set MOD_STATE=%%S
        )
        echo     %%M  [!MOD_STATE!]
    )
    echo   ─────────────────────────────────────────────────────────
    set FLASK_ENV=development
    set FLASK_DEBUG=1
)

echo.
echo   Starting in 3...
timeout /t 1 /nobreak >nul
echo   Starting in 2...
timeout /t 1 /nobreak >nul
echo   Starting in 1...
timeout /t 1 /nobreak >nul
echo.

start "" http://localhost:%SAVED_PORT%
set PORT=%SAVED_PORT%
%PYTHON% app.py

echo.
pause
exit /b 0

REM ════════════════════════════════════════════════════════════════
REM  SAVE CONFIG
REM ════════════════════════════════════════════════════════════════
:save_config
(
    echo last_ip=%PHONE_IP%
    echo last_mode=%SAVED_MODE%
    echo port=%SAVED_PORT%
    echo skip_banner=%SKIP_BANNER%
) > "%CFG%"
exit /b 0

REM ════════════════════════════════════════════════════════════════
REM  SUBROUTINE: PORT CHECK
REM ════════════════════════════════════════════════════════════════
:check_port
netstat -ano 2>nul | find ":%SAVED_PORT% " | find "LISTENING" >nul
if %errorlevel% equ 0 (
    echo.
    echo   [WARN]  Port %SAVED_PORT% is already in use.
    set SAVED_PORT=5001
    set /p SAVED_PORT=   Enter a different port [default 5001]: 
    if "!SAVED_PORT!"=="" set SAVED_PORT=5001
    echo   [  OK  ]  Using port !SAVED_PORT!
) else (
    echo   [  OK  ]  Port %SAVED_PORT% is free
)
exit /b 0

REM ════════════════════════════════════════════════════════════════
REM  SUBROUTINE: GET DEVICE NAME
REM ════════════════════════════════════════════════════════════════
:get_device_info
set DEV_BRAND=
set DEV_MODEL=
for /f "delims=" %%A in ('%ADB% shell getprop ro.product.brand 2^>nul') do set DEV_BRAND=%%A
for /f "delims=" %%A in ('%ADB% shell getprop ro.product.model 2^>nul') do set DEV_MODEL=%%A
set DEVICE_NAME=%DEV_BRAND% %DEV_MODEL%
echo   [  OK  ]  Device: %DEVICE_NAME%
exit /b 0

REM ════════════════════════════════════════════════════════════════
REM  SUBROUTINE: CHECK MAGISK
REM ════════════════════════════════════════════════════════════════
:check_magisk
set MAGISK_VER=
for /f "delims=" %%A in ('%ADB% shell "magisk -v 2>/dev/null"') do set MAGISK_VER=%%A
if not defined MAGISK_VER (
    echo   [WARN]  Magisk not detected. Module installation may not work.
    echo.
) else (
    echo   [  OK  ]  Magisk: %MAGISK_VER%
)
exit /b 0

REM ════════════════════════════════════════════════════════════════
REM  SUBROUTINE: CHECK BATTERY
REM ════════════════════════════════════════════════════════════════
:check_battery
set BATTERY=
for /f "tokens=2 delims=: " %%A in ('%ADB% shell "dumpsys battery 2>/dev/null | grep level"') do set BATTERY=%%A
if defined BATTERY (
    if !BATTERY! lss 20 (
        echo   [WARN]  Battery is at !BATTERY!%%. Recommend charging before installing modules^^!
        echo.
        set CONT=Y
        set /p CONT=   Continue anyway? [y/N]: 
        if /i "!CONT!" neq "y" (
            echo   Exiting. Please charge your device.
            pause & exit /b 1
        )
    ) else (
        echo   [  OK  ]  Battery: !BATTERY!%%
    )
)
exit /b 0

REM ════════════════════════════════════════════════════════════════
REM  SUBROUTINE: WAIT FOR USB DEVICE
REM ════════════════════════════════════════════════════════════════
:wait_usb
set RETRY=0
:usb_loop
set /a RETRY+=1
for /f "tokens=1" %%A in ('%ADB% devices ^| findstr "device$"') do (
    set DEVICE=%%A
    echo   [  OK  ]  USB device: !DEVICE!
    exit /b 0
)
if %RETRY% lss 15 (
    set /a REMAINING=15-%RETRY%
    title TMMI - Waiting for device... [!REMAINING!s]
    timeout /t 1 /nobreak >nul
    goto usb_loop
)
echo   [FAIL]  No USB device detected after 15 seconds.
exit /b 1

REM ════════════════════════════════════════════════════════════════
REM  SUBROUTINE: GET WIFI IP
REM ════════════════════════════════════════════════════════════════
:get_ip
set PHONE_IP=
for /f "tokens=2 delims= " %%A in ('%ADB% shell ip addr show wlan0 2^>nul ^| findstr "inet "') do (
    for /f "tokens=1 delims=/" %%B in ("%%A") do (
        set PHONE_IP=%%B
        exit /b 0
    )
)
exit /b 0

REM ════════════════════════════════════════════════════════════════
REM  FAIL
REM ════════════════════════════════════════════════════════════════
:fail_no_device
echo.
echo   [FAIL]  No device found. Exiting.
pause & exit /b 1
