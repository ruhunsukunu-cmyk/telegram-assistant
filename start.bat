@echo off
chcp 65001 >nul
title Telegram Asistan Botu
echo =======================================================
echo          🤖 TELEGRAM KİŞİSEL ASİSTAN BOTU
echo =======================================================
echo.

if not exist ".env" (
    echo [UYARI] .env dosyasi bulunamadi! .env.example kopyalaniyor...
    copy .env.example .env >nul
)

echo Bot baslatiliyor...
echo Kapatmak icin: Ctrl + C
echo.

.\venv\Scripts\python.exe bot.py
pause
