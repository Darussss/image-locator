@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================
echo   把本项目上传到 GitHub（首次开源专用）
echo ==========================================
echo.

where git >nul 2>nul
if errorlevel 1 (
    echo [错误] 没检测到 git，请先安装 Git for Windows： https://git-scm.com/download/win
    pause
    exit /b 1
)

echo 先在网页上创建一个"空仓库"： https://github.com/new
echo 注意：仓库名填 image-locator，Public，下面三个勾选框（README / .gitignore / license）全部不要勾！
echo.
set /p GHUSER=请输入你的 GitHub 用户名:
if "%GHUSER%"=="" (
    echo [错误] 用户名不能为空
    pause
    exit /b 1
)
set /p GHREPO=请输入仓库名（直接回车 = image-locator）:
if "%GHREPO%"=="" set GHREPO=image-locator
set REMOTE=https://github.com/%GHUSER%/%GHREPO%.git

echo.
echo [1/4] 初始化仓库...
if exist ".git" (
    echo 已存在 .git 目录，跳过初始化
) else (
    git init
)

echo.
echo [2/4] 暂存文件（接下来请仔细核对清单）...
git add .
echo.
echo ---- 即将提交的文件列表（确认没有 zip / jpg / _internal / dist 目录）----
git status --short
echo ---------------------------------------------------------------------

echo.
set /p OK=以上清单没问题，继续提交吗？（输入 y 回车，其它键退出）:
if /i not "%OK%"=="y" (
    echo 已取消，未做任何提交
    pause
    exit /b 0
)

echo.
echo [3/4] 提交并设置远程地址...
git commit -m "feat: 局部图片定位工具首个开源版本"
if errorlevel 1 (
    echo [提示] 提交失败，可能没有改动或尚未配置 user.name / user.email
    pause
    exit /b 1
)
git branch -M main
git remote remove origin >nul 2>nul
git remote add origin %REMOTE%

echo.
echo [4/4] 推送到 %REMOTE%
echo （首次会弹出 GitHub 登录窗口，选择 Sign in with your browser 授权即可）
git push -u origin main
if errorlevel 1 (
    echo.
    echo [失败] 推送没成功，常见原因：
    echo   1. 网页建仓库时勾选了 README/license，导致远程已有提交 -^> 先执行 git pull --rebase origin main 再 git push
    echo   2. 认证失败 -^> 需要 Personal Access Token（见教程第 5 步）
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   成功！打开 %REMOTE% 查看
echo   下一步：发 Release 上传 局部图片定位工具_Win64.zip
echo ==========================================
pause
