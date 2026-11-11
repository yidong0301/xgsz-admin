@echo off
chcp 936 >nul
cd /d D:\WDXMGZ
echo ========================================
echo   存档历史（从新到旧）
echo ========================================
git log --oneline --decorate
echo.
echo 每条前面的 7 位字符就是存档编号
pause