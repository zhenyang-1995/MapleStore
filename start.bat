@echo off
echo ==========================================
echo    MapleStory - Auto Script Launcher
echo ==========================================
echo.

:: Check dependencies
echo Checking dependencies...
python -c "import pynput, mss, cv2, numpy" 2>nul
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
echo 1. Key Record - Simple
echo 2. Key Record - Full
echo.
echo [Vision]
echo 3. Vision - Simple
echo 4. Vision - Full
echo.
echo 0. Exit
echo.

set /p choice=Enter number (0-4):

if "%choice%"=="1" goto run1
if "%choice%"=="2" goto run2
if "%choice%"=="3" goto run3
if "%choice%"=="4" goto run4
if "%choice%"=="0" goto end
echo.
echo Invalid choice, please try again.
echo.
goto menu

:run1
echo.
echo Starting [Key Record - Simple]...
python mxd_auto_simple.py
pause
goto menu

:run2
echo.
echo Starting [Key Record - Full]...
python key_recorder.py
pause
goto menu

:run3
echo.
echo Starting [Vision - Simple]...
python mxd_vision_simple.py
pause
goto menu

:run4
echo.
echo Starting [Vision - Full]...
python mxd_vision_auto.py
pause
goto menu

:end
echo.
echo Bye!
timeout /t 1 >nul
exit
