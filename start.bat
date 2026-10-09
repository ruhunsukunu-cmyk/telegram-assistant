@echo off
chcp 65001 >nul
title Ruhun Sukunu Shorts Takipcisi
cd /d "%~dp0"
if not exist ".env" copy .env.example .env >nul
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe bot.py
) else (
  python bot.py
)
pause
