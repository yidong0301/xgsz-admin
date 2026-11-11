import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()
from datetime import datetime, timedelta
from apps.cmdb.models import Server

base = datetime(2024, 10, 1, 9, 0, 0)
n = 0
for i, s in enumerate(Server.objects.all().order_by('instance_id')):
    s.create_time = (base + timedelta(days=i * 3, hours=i % 8)).strftime('%Y-%m-%d %H:%M:%S')
    s.save(update_fields=['create_time'])
    n += 1
print('updated', n, 'servers')
