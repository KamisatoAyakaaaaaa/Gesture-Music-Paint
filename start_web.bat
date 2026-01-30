@echo off
chcp 65001 >nul
title Gesture Music Paint - Web Server

echo ============================================
echo   Gesture Music Paint - Web Server
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

:: 启动服务器
echo 正在启动服务器...
echo 访问地址: http://localhost:5000
echo.
python web_server.py

pause
