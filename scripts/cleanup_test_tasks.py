import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r'D:\WDXMGZ\xgsz-admin')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')
import django
django.setup()
from apps.k8s.models import InferenceTask

# 要清理的测试任务（空名/乱码/nginx测试/real-test 等）
test_ids = [9, 10, 35, 36, 37, 38, 39, 40, 41]
qs = InferenceTask.objects.filter(id__in=test_ids)
print('将删除 %d 条:' % qs.count())
for t in qs.order_by('id'):
    print(' ', t.id, '|', t.name, '|', t.image, '|', t.status)
qs.delete()
print('剩余任务:', InferenceTask.objects.count())
