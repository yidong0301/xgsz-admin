import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()
from apps.k8s.models import InferenceTask

print('total:', InferenceTask.objects.count())
print('---- 任务列表 ----')
for t in InferenceTask.objects.all().order_by('id'):
    print(t.id, '|', t.name, '|', t.image, '|', t.status, '|', (t.error_msg or '')[:28])
