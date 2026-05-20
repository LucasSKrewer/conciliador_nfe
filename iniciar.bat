@echo off
title Conciliador NF-e
chcp 65001 >nul
cd /d %~dp0
echo Iniciando Conciliador NF-e...
echo.
python app.py
pause
