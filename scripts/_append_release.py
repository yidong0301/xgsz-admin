# -*- coding: utf-8 -*-
import io

p = r'D:\WDXMGZ\xgsz-admin\apps\ops\views.py'
c = io.open(p, encoding='utf-8').read()

if 'class ReleaseOrderView' in c:
    print('already exists')
else:
    code = '''

class ReleaseOrderView(APIView):
    """发布单：GET 列表 / POST 创建"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        from utils.pagination import MyPageNumberPagination
        from apps.ops.models import ReleaseOrder
        qs = ReleaseOrder.objects.all()
        status_f = request.query_params.get('status')
        if status_f:
            qs = qs.filter(status=status_f)
        env = request.query_params.get('env')
        if env:
            qs = qs.filter(env=env)
        paginator = MyPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = [{'id': r.id, 'release_no': r.release_no, 'app_name': r.app_name, 'env': r.env,
                 'namespace': r.namespace, 'cluster': r.cluster, 'image': r.image, 'version': r.version,
                 'replicas': r.replicas, 'status': r.status, 'reason': r.reason, 'creator': r.creator,
                 'approver': r.approver, 'k8s_deployment': r.k8s_deployment,
                 'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S') if r.created_at else ''}
                for r in page]
        return APIResponse(data=paginator.get_paginated_response(data).data)

    def post(self, request, *args, **kwargs):
        from apps.ops.models import ReleaseOrder
        import time
        data = request.data
        app_name = data.get('app_name')
        image = data.get('image')
        if not app_name or not image:
            return APIResponse(errcode=400, errmsg='应用名和镜像不能为空')
        no = 'REL%s%03d' % (time.strftime('%Y%m%d%H%M%S'), ReleaseOrder.objects.count() % 1000)
        who = getattr(getattr(request, 'user', None), 'name', None) or 'admin'
        r = ReleaseOrder.objects.create(
            release_no=no, app_name=app_name, env=data.get('env', 'test'),
            namespace=data.get('namespace', 'default'), cluster=data.get('cluster', 'kind'),
            image=image, version=data.get('version'), replicas=int(data.get('replicas') or 1),
            reason=data.get('reason'), creator=who,
        )
        return APIResponse(data={'id': r.id, 'release_no': r.release_no})


class ReleaseOrderActionView(APIView):
    """发布单操作：approve / reject / execute / rollback"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, pk, action, *args, **kwargs):
        from apps.ops.models import ReleaseOrder
        from django.utils import timezone
        r = ReleaseOrder.objects.filter(id=pk).first()
        if not r:
            return APIResponse(errcode=404, errmsg='\\u53d1\\u5e03\\u5355\\u4e0d\\u5b58\\u5728')
        who = getattr(getattr(request, 'user', None), 'name', None) or 'admin'
        if action == 'approve':
            r.status = 'APPROVED'
            r.approver = who
            r.approved_at = timezone.now()
            r.approver_remark = request.data.get('remark', '')
        elif action == 'reject':
            r.status = 'REJECTED'
            r.approver = who
            r.approver_remark = request.data.get('remark', '')
        elif action == 'execute':
            r.status = 'RELEASED'
            r.released_at = timezone.now()
        elif action == 'rollback':
            r.status = 'ROLLED_BACK'
        else:
            return APIResponse(errcode=400, errmsg='\\u672a\\u77e5\\u64cd\\u4f5c')
        r.save()
        return APIResponse(data={'id': r.id, 'status': r.status})
'''
    c = c.rstrip() + code
    io.open(p, 'w', encoding='utf-8').write(c)
    print('appended')
