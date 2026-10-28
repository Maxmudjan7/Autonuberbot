@echo off
chcp 65001 > nul
title Telegram Userbot Akkauntni Ulash
echo ========================================================
echo        TELEGRAM USERBOT AKKAUNTINI ULASH OYNASI
echo ========================================================
echo.
echo Bu yerda o'zingizning Telegram raqamingizni ulab olasiz.
echo Bot aynan shu akkauntingiz orqali diller botidan
echo raqam va kodlarni oladi.
echo.
if exist "C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe" (
    "C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe" login_userbot.py
) else (
    python login_userbot.py
)
echo.
pause
