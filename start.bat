@echo off
chcp 65001 >nul
echo ==========================================
echo    冒险岛Online - 自动刷怪脚本启动器
echo ==========================================
echo.

:: 检查依赖
echo 正在检查依赖...
python -c "import pynput, mss, cv2, numpy" 2>nul
if errorlevel 1 (
    echo 检测到缺少依赖，正在安装...
    pip install pynput mss opencv-python numpy pygetwindow pillow -q
    echo 依赖安装完成
) else (
    echo 依赖检查通过
)
echo.

:menu
echo 请选择要启动的脚本:
echo.
echo 【方式一：按键记录式】
echo 1. 按键记录 - 简化版 (推荐新手)
echo 2. 按键记录 - 完整版
echo.
echo 【方式二：图像识别式】
echo 3. 图像识别 - 简化版 (推荐)
echo 4. 图像识别 - 完整版
echo.
echo 0. 退出
echo.

set /p choice="输入数字 (0-4): "

if "%choice%"=="1" (
    echo.
    echo 启动 [按键记录 - 简化版]...
    python mxd_auto_simple.py
    goto menu
) else if "%choice%"=="2" (
    echo.
    echo 启动 [按键记录 - 完整版]...
    python key_recorder.py
    goto menu
) else if "%choice%"=="3" (
    echo.
    echo 启动 [图像识别 - 简化版]...
    python mxd_vision_simple.py
    goto menu
) else if "%choice%"=="4" (
    echo.
    echo 启动 [图像识别 - 完整版]...
    python mxd_vision_auto.py
    goto menu
) else if "%choice%"=="0" (
    echo.
    echo 再见!
    timeout /t 1 >nul
    exit
) else (
    echo.
    echo 无效选择，请重新输入
    echo.
    goto menu
)
