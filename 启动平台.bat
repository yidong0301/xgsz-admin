@echo off
chcp 936 >nul
title 芯光数智 · 智能运维平台
cd /d D:\WDXMGZ

echo ========================================
echo    芯光数智 · 智能运维平台 启动器
echo ========================================
echo.

echo [1/5] 检查 Docker Desktop ...
tasklist /FI "IMAGENAME eq Docker Desktop.exe" 2>nul | find /I "Docker Desktop.exe" >nul
if errorlevel 1 (
    echo    Docker Desktop 未运行，正在启动（约需 1-2 分钟）...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
) else (
    echo    Docker Desktop 已在运行
)

echo [2/5] 等待 Docker 引擎就绪 ...
:waitdocker
docker version --format "{{.Server.Version}}" >nul 2>&1
if errorlevel 1 (
    timeout /t 5 /nobreak >nul
    goto waitdocker
)
echo    Docker 已就绪

echo [3/5] 关闭旧的 xgsz-* 容器（避免端口冲突，保留 K8s 集群）...
docker update --restart=no xgsz-nginx xgsz-mysql xgsz-redis xgsz-mongo >nul 2>&1
docker stop xgsz-nginx xgsz-mysql xgsz-redis xgsz-mongo >nul 2>&1

echo [4/5] 重启平台容器（干净重建，保证网络互通）...
docker compose down >nul 2>&1
docker compose up -d

echo [5/5] 等待服务就绪（约 25 秒）...
timeout /t 25 /nobreak >nul

echo.
echo ========================================
echo    平台已启动！
echo    本机访问:  http://localhost:8080
echo    局域网:    http://10.177.209.251:8080
echo    账号:      admin / admin123456
echo ========================================
echo.
start http://localhost:8080
pause