@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在检查运行依赖...
python -c "import cv2, numpy, PIL" >nul 2>nul
if errorlevel 1 (
    echo 缺少依赖，开始安装 opencv-python numpy pillow ...
    python -m pip install opencv-python numpy pillow -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo 依赖安装失败，请手动执行: python -m pip install opencv-python numpy pillow
        pause
        exit /b 1
    )
)
python image_locator.py
if errorlevel 1 pause
