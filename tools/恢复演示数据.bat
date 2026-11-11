@echo off
chcp 65001 >nul
cd /d D:\WDXMGZ
echo ========================================
echo    一键恢复演示数据
echo ========================================
echo.

echo [1/3] 建表迁移...
docker exec wdxmgz-backend-1 python manage.py migrate

echo [2/3] 创建管理员 admin / admin123456...
docker exec wdxmgz-backend-1 python -c "import os,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','xgsz_admin.settings');django.setup();from apps.account.models import User;u,c=User.objects.get_or_create(username='admin',defaults={'name':'管理员'});u.is_superuser=True;u.is_staff=True;u.set_password('admin123456');u.save();print('admin ok')"

echo [3/3] 导入演示数据 demo_data.json...
D:\WDXMGZ\venv\Scripts\python.exe D:\WDXMGZ\tools\seed_from_json.py

echo.
echo ========================================
echo    恢复完成！登录 admin / admin123456
echo ========================================
pause
