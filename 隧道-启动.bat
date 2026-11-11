@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
cd /d D:\WDXMGZ\tools\cpolar

echo ========================================
echo   内网穿透 - 让别人访问你的平台
echo ========================================
echo.

if exist "%USERPROFILE%\.cpolar\cpolar.yml" goto run

echo [首次] 需要配置 authtoken（免费注册）
echo   1. 打开 https://dashboard.cpolar.com/auth
echo   2. 注册/登录后复制 authtoken
echo.
set /p TOKEN=请粘贴 authtoken 后回车: 
if "!TOKEN!"=="" goto end
cpolar.exe authtoken !TOKEN!
echo.

:run
echo 正在启动隧道，请保持此窗口开启...
echo 稍等几秒，会出现 https://xxxx.cpolar.cn 的公网地址
echo.
cpolar.exe http 8080
pause
goto :eof

:end
echo 未输入 token，已退出
pause