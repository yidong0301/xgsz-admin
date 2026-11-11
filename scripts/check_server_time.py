import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()
from apps.cmdb.models import Server

s = Server.objects.filter(status='Stopped').first()
if s:
    print('pk=', getattr(s, 'pk', None), 'hostname=', s.hostname)
    for f in ('create_time', 'purchase_date', 'expired_time', 'warranty_expire'):
        print(f, '=', repr(getattr(s, f, None)))
else:
    print('no stopped server')
