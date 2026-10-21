@echo off
chcp 65001 > nul
title GitHub'ga yangilanishlarni yuklash
echo ========================================================
echo        GITHUB'GA YANGILANISHLARNI YUKLASH
echo ========================================================
echo.
"C:\Program Files\Git\cmd\git.exe" add .
set /p commit_msg="O'zgarishlar tavsifini yozing (masalan: yangilanish): "
if "%commit_msg%"=="" set commit_msg=Yangilanish
"C:\Program Files\Git\cmd\git.exe" commit -m "%commit_msg%"
"C:\Program Files\Git\cmd\git.exe" push origin main
echo.
echo ========================================================
echo        YANGILANISHLAR GITHUB'GA YUKLANDI!
echo ========================================================
echo.
pause
