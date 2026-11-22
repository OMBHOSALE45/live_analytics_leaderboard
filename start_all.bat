@echo off
title Free Fire Live Leaderboard & Vision Tracker
echo ===================================================================
echo   FREE FIRE LIVE SCOREBOARD AI TRACKER - 1-CLICK LAUNCHER
echo ===================================================================
echo.

:: 1. Start Node.js Server in Background
echo [1/3] Starting Backend Server (Port 3001)...
start "FF-Live-Server" /B node server\server.js

:: 2. Wait for server to bind port
timeout /t 2 /nobreak >nul

:: 3. Open UI in Default Browser
echo [2/3] Opening Leaderboard UI in Browser...
start http://localhost:3001

:: 4. Start Python Vision Engine
echo [3/3] Starting Vision Engine (OpenCV + ONNX OCR)...
echo Press 'q' in OpenCV window to quit, or 's' to re-calibrate slots.
echo.
python vision-engine\scoreboard_detector.py --source .\Assets\video_1.mp4 --display

pause

