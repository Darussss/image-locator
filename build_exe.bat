@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo [1/4] 检查 Python...
where python >nul 2>nul
if errorlevel 1 (
    echo 未检测到 python，请先安装 Python 3.9+ 并勾选 "Add python.exe to PATH"
    pause
    exit /b 1
)
python -V

echo [2/4] 检查依赖...
python -c "import cv2, numpy, PIL" >nul 2>nul
if errorlevel 1 (
    echo 正在安装依赖...
    python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo 依赖安装失败，请手动执行: python -m pip install -r requirements.txt
        pause
        exit /b 1
    )
)

echo [3/4] 安装 PyInstaller...
python -m pip install --upgrade pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple >nul
python -m PyInstaller --version

echo [4/4] 开始打包（文件夹版，推荐）...
set ICON=
if exist "app.ico" set ICON=--icon app.ico

python -m PyInstaller --noconfirm --clean --windowed --onedir ^
  --name "局部图片定位工具" %ICON% ^
  --exclude-module matplotlib --exclude-module scipy --exclude-module pandas ^
  image_locator.py

if errorlevel 1 (
    echo 打包失败，请查看上面的日志
    pause
    exit /b 1
)

echo.
echo 打包完成：dist\局部图片定位工具\局部图片定位工具.exe
echo 分发时请把整个 "局部图片定位工具" 文件夹压缩成 zip，接收方解压后直接运行 exe。
echo.
echo 如需单文件 exe（启动较慢、易被杀软误报），可手动执行：
echo   python -m PyInstaller --noconfirm --clean --windowed --onefile --name 局部图片定位工具 image_locator.py
pause
