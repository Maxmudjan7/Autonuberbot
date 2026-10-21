@echo off
chcp 65001 > nul
title Telegram Mini App Tunnel (Cloudflare)
echo ========================================================
echo        TELEGRAM MINI APP TUNNEL ISHGA TUSHMOQDA...
echo ========================================================
echo.
"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:5000
pause

