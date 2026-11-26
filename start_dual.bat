@echo off
title Free Fire Dual-Stream Live Leaderboard (6+6 Concurrent)
echo ===================================================================
echo   FREE FIRE DUAL-STREAM SCOREBOARD AI TRACKER (6+6 CONCURRENT)
echo ===================================================================
echo.

set SRC1=vision-engine\Assets\video_6.mp4
set SRC2=vision-engine\Assets\video_7.mp4
if not "%~1"=="" set SRC1=%~1
if not "%~2"=="" set SRC2=%~2

python -u vision-engine\launch_dual.py --source1 "%SRC1%" --source2 "%SRC2%" %3 %4 %5 %6
pause

