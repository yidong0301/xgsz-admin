#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指标总览：节点 CPU/内存用量、Pod Top N、近 60 分钟趋势、阈值告警。"""
import logging

from rest_framework.views import APIView

from apps.ops.models import MetricSample
from utils.authorization import MyAuthentication
from utils.http_response import APIResponse
from utils.metrics import cluster_names, node_usage, pod_usage
from utils.permissions import MyPermission

logger = logging.getLogger('default')

CPU_WARN = 85.0
MEM_CRIT = 90.0


def _trend(label, node, limit=60):
    rows = list(MetricSample.objects.filter(cluster=label, node=node).order_by('-created_at')[:limit])
    rows.reverse()
    return [{'t': r.created_at.strftime('%H:%M'), 'cpu': round(r.cpu_pct, 1), 'mem': round(r.mem_pct, 1)}
            for r in rows]


class MetricsOverviewView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        cluster = request.query_params.get('cluster') or ''
        if not cluster:
            names = cluster_names()
            cluster = names[0] if names else ''
        nodes, err = node_usage(cluster)
        label = (nodes[0]['cluster'] if nodes else (cluster or 'default'))
        pods = pod_usage(cluster, top=8) if nodes else []
        # 采样任务可能用集群名（kind）或 default 作为标签，两种都兜一下
        trend = {}
        for n in nodes:
            t = _trend(label, n['name'])
            if not t:
                for alt in ('default', 'kind'):
                    if alt != label:
                        t = _trend(alt, n['name'])
                        if t:
                            break
            trend[n['name']] = t

        alerts = []
        for n in nodes:
            if n.get('cpu_pct') is not None and n['cpu_pct'] >= CPU_WARN:
                alerts.append({
                    'level': 'warning', 'kind': 'cpu', 'node': n['name'],
                    'title': '节点 CPU 使用率过高',
                    'detail': '%s CPU %s%%（%s / %s）' % (n['name'], n['cpu_pct'], n['cpu_text'], n['cpu_total_text']),
                })
            if n.get('mem_pct') is not None and n['mem_pct'] >= MEM_CRIT:
                alerts.append({
                    'level': 'error', 'kind': 'mem', 'node': n['name'],
                    'title': '节点内存使用率过高',
                    'detail': '%s 内存 %s%%（%s / %s）' % (n['name'], n['mem_pct'], n['mem_text'], n['mem_total_text']),
                })

        return APIResponse(data={
            'cluster': label,
            'clusters': cluster_names(),
            'available': bool(nodes),
            'error': err,
            'nodes': nodes,
            'top_pods': pods,
            'trend': trend,
            'alerts': alerts,
            'thresholds': {'cpu': CPU_WARN, 'memory': MEM_CRIT},
        })
