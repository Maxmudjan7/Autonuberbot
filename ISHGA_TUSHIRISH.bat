@echo off
chcp 65001 > nul
title Telegram Premium Bot
echo ========================================================
echo        TELEGRAM PREMIUM BOT ISHGA TUSHMOQDA...
echo ========================================================
echo.
if exist "C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe" (
    "C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe" main.py
) else (
    python main.py
)
echo.
pause
