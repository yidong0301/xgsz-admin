#!/bin/env python3
# -*- coding: utf-8 -*-

import logging

from django.db import connection
from django_redis import get_redis_connection
from rest_framework.views import APIView

from utils.authorization import MyAuthentication
from utils.http_response import APIResponse
from utils.permissions import MyPermission

logger = logging.getLogger('default')


class HealthCheckView(APIView):
    """
    系统自检：检查 MySQL / Redis / MongoDB / K8s / Celery 各组件的连通状态
    """

    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        checks = {}

        # 1. MySQL
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            checks['mysql'] = {'status': 'ok', 'detail': '连接正常'}
        except Exception as e:
            checks['mysql'] = {'status': 'error', 'detail': str(e)[:200]}

        # 2. Redis
        try:
            r = get_redis_connection('default')
            r.ping()
            checks['redis'] = {'status': 'ok', 'detail': '连接正常'}
        except Exception as e:
            checks['redis'] = {'status': 'error', 'detail': str(e)[:200]}

        # 3. MongoDB
        try:
            import pymongo
            from decouple import config
            client = pymongo.MongoClient(
                host=config('MONGO_HOST'), port=int(config('MONGO_PORT')),
                serverSelectionTimeoutMS=2000)
            client.admin.command('ping')
            checks['mongodb'] = {'status': 'ok', 'detail': '连接正常'}
        except Exception as e:
            checks['mongodb'] = {'status': 'error', 'detail': str(e)[:200]}

        # 4. K8s
        try:
            from kubernetes import config as kconfig, client as kclient
            kconfig.load_kube_config(config_file=None)
            v1 = kclient.CoreV1Api()
            v1.list_namespace(limit=1)
            checks['k8s'] = {'status': 'ok', 'detail': '集群可达'}
        except Exception as e:
            checks['k8s'] = {'status': 'error', 'detail': str(e)[:200]}

        # 5. Celery
        try:
            from xgsz_admin.celery import app as celery_app
            insp = celery_app.control.inspect(timeout=3)
            stats = insp.ping()
            if stats:
                checks['celery'] = {'status': 'ok', 'detail': '%d 个 worker 在线' % len(stats)}
            else:
                checks['celery'] = {'status': 'warning', 'detail': '无 worker 响应'}
        except Exception as e:
            checks['celery'] = {'status': 'warning', 'detail': str(e)[:200]}

        ok_count = sum(1 for c in checks.values() if c['status'] == 'ok')
        checks['summary'] = {'ok': ok_count, 'total': len(checks), 'healthy': ok_count == len(checks)}

        return APIResponse(data=checks)
