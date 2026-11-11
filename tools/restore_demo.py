# -*- coding: utf-8 -*-
r"""一键恢复演示数据：建表 → 建管理员 → 导入 data/demo_data.json

用法（在 D:\WDXMGZ 下）：python tools/restore_demo.py
前提：docker compose 已启动（backend 容器在运行）
"""
import os, sys, subprocess

BASE = r'D:\WDXMGZ'
PY = os.path.join(BASE, 'venv', 'Scripts', 'python.exe')
BACKEND = 'wdxmgz-backend-1'


def run(cmd, desc):
    print('[%s]' % desc)
    r = subprocess.run(cmd, cwd=BASE)
    if r.returncode != 0:
        print('  [警告] 命令返回非 0（%s），继续' % r.returncode)


# 1. 建表
run(['docker', 'exec', BACKEND, 'python', 'manage.py', 'migrate'], '1/3 建表迁移')

# 2. 管理员
admin_code = (
    "import os,django;"
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE','xgsz_admin.settings');"
    "django.setup();"
    "from apps.account.models import User;"
    "u,c=User.objects.get_or_create(username='admin',defaults={'name':'管理员'});"
    "u.is_superuser=True;u.is_staff=True;u.set_password('admin123456');u.save();"
    "print('admin ok')"
)
run(['docker', 'exec', BACKEND, 'python', '-c', admin_code], '2/3 创建管理员')

# 3. 导入演示数据
seed = os.path.join(BASE, 'tools', 'seed_from_json.py')
if os.path.exists(PY) and os.path.exists(seed):
    run([PY, seed], '3/3 导入演示数据')
else:
    print('[警告] 未找到 venv 或 seed 脚本，跳过演示数据')

print('')
print('一键恢复完成：登录 admin / admin123456')
