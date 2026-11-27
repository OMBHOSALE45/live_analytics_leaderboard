@echo off
title Free Fire Vision Pipeline (12 Teams + Live Spectator Feed)
echo ===================================================================
echo   FREE FIRE VISION TRACKER (12 TEAMS + LIVE SPECTATOR NAMES/EYE/HP)
echo ===================================================================
echo.

set SRC1=vision-engine\Assets\video_6.mp4
set SRC_SPEC=vision-engine\Assets\video_10.mp4
if not "%~1"=="" set SRC1=%~1
if not "%~2"=="" set SRC_SPEC=%~2

python -u vision-engine\launch_triple.py --source1 "%SRC1%" --source3 "%SRC_SPEC%" %3 %4 %5 %6
pause
