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
echo Controls:
echo   - Press 'b' or 'h' to Plot Spectator HP Border (Masking)
echo   - Press 's' to Select / Calibrate Scoreboard Slots
echo   - Press 'q' to Quit
echo.
set VIDEO_SRC=vision-engine\Assets\video_4.mp4
if not "%~1"=="" set VIDEO_SRC=%~1
python vision-engine\scoreboard_detector.py --source %VIDEO_SRC% --display

pause

