#!/bin/env python3
# -*- coding: utf-8 -*-

# Copyright: (c) SmallFlyingPigs Organization. https://github.com/small-flying-pigs
# Copyright: (c) <pigs@dnsjia.com>
# Released under the AGPL-3.0 License.


"""
# @File  : deploy_chart.py.py
# @Author: 往事随风
# @Email: gujiwork@outlook.com
# @Date  : 2021/5/31
# @Desc  :
"""

import traceback
import datetime as dt
import logging

from django.http import JsonResponse
from django.db.models import Count
from rest_framework.views import APIView

from apps.cmdb.models import Server, AnsibleExecHistory
from utils.authorization import MyAuthentication
from utils.http_response import APIResponse
from utils.permissions import MyPermission

logger = logging.getLogger('default')


class DashboardChart(APIView):

    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        """
        统计应用、主机、工单、部署单数量
        :param request:
        :param args:
        :param kwargs:
        :return:
        """

        try:
            server_count = Server.objects.all().count()
            job_count = AnsibleExecHistory.objects.all().count()

            def _group(field):
                rows = Server.objects.values(field).annotate(c=Count('instance_id')).order_by('-c')
                return [{'name': r[field] or '未分类', 'value': r['c']} for r in rows]

            count_data = {
                "server_count": server_count,
                "job_count": job_count,
                "server_by_cloud_type": _group('cloud_type'),
                "server_by_status": _group('status'),
                "server_by_region": _group('region_id'),
                "server_by_owner": _group('owner'),
                "server_by_environment": _group('environment'),
            }
            return APIResponse(data=count_data)

        except Exception as e:
            logger.error(str(e))
            logger.error('获取仪表盘统计数据失败, 异常原因: %s' % str(traceback.format_exc()))
            return APIResponse(errcode=5003, errmsg="获取数据失败")

