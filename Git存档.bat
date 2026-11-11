@echo off
chcp 936 >nul
cd /d D:\WDXMGZ
echo ========================================
echo   代码存档（Git 提交）
echo ========================================
echo.
git status --short
echo.
set /p MSG=请输入这次改动说明（直接回车=日常更新）: 
if "%MSG%"=="" set MSG=日常更新
git add -A
git commit -m "%MSG%"
echo.
echo 存档完成！
pause