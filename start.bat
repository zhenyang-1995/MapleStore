@echo off
echo ==========================================
echo    MapleStory - Auto Script Launcher
echo ==========================================
echo.

:: Check dependencies
echo Checking dependencies...
python -c "import pynput, mss, cv2, numpy" 2>/dev/null
if errorlevel 1 (
    echo Installing missing dependencies...
    pip install pynput mss opencv-python numpy pygetwindow pillow -q
    echo Done.
) else (
    echo All dependencies OK.
)
echo.

:menu
echo Please select a script:
echo.
echo [Key Record]
echo 1. Key Record - Simple (recommended for beginners)
echo 2. Key Record - Full
echo.
echo [Vision]
echo 3. Vision - Simple (recommended)
echo 4. Vision - Full
echo.
echo 0. Exit
echo.

set /p choice=Enter number (0-4): 

if "%choice%"=="1" (
    echo.
    echo Starting [Key Record - Simple]...
    python mxd_auto_simple.py
    goto menu
)
if "%choice%"=="2" (
    echo.
    echo Starting [Key Record - Full]...
    python key_recorder.py
    goto menu
)
if "%choice%"=="3" (
    echo.
    echo Starting [Vision - Simple]...
    python mxd_vision_simple.py
    goto menu
)
if "%choice%"=="4" (
    echo.
    echo Starting [Vision - Full]...
    python mxd_vision_auto.py
    goto menu
)
if "%choice%"=="0" (
    echo.
    echo Bye!
    timeout /t 1 >/dev/null
    exit
)
echo.
echo Invalid choice, please try again.
echo.
goto menu
