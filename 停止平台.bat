@echo off
chcp 936 >nul
title 芯光数智 · 智能运维平台 - 停止
cd /d D:\WDXMGZ

echo ========================================
echo    芯光数智 · 智能运维平台 停止
echo ========================================
echo.

echo [1/2] 停止内网穿透隧道 ...
taskkill /f /im cpolar.exe >nul 2>&1
taskkill /f /im cloudflared.exe >nul 2>&1
echo    隧道已停止

echo [2/2] 停止平台容器 ...
docker compose stop

echo.
echo ========================================
echo    平台已停止，可以放心休息了
echo    数据不会丢失（保存在 Docker 数据卷）
echo    下次使用：双击「启动平台.bat」
echo ========================================
echo.
pause