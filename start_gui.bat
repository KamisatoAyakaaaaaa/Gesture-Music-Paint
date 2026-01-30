@echo off
chcp 65001 >nul
title Gesture Music Paint - Desktop App

echo ============================================
echo   Gesture Music Paint - Desktop App
echo ============================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)

:: 检查模型文件
if not exist "hand_landmarker.task" (
    echo [警告] 未找到手势识别模型文件 hand_landmarker.task
    echo 请从 MediaPipe 官网下载并放置在当前目录
    echo.
)

:: 启动 GUI
echo 正在启动桌面应用...
python gui_app.py

pause
