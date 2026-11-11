#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指标采样：每分钟把各集群节点的 CPU/内存使用率写入 MetricSample，供趋势曲线使用。"""
import logging
from datetime import timedelta

from django.utils import timezone

from xgsz_admin.celery import app
from apps.ops.models import MetricSample

logger = logging.getLogger('default')

KEEP_HOURS = 24


@app.task
def sample_node_metrics():
    from utils.metrics import cluster_names, node_usage
    saved, skipped = 0, []
    for cluster in cluster_names():
        rows, err = node_usage(cluster)
        if err:
            skipped.append('%s:%s' % (cluster, err[:60]))
            continue
        for r in rows:
            MetricSample.objects.create(
                cluster=r['cluster'], node=r['name'],
                cpu_pct=r['cpu_pct'] or 0, mem_pct=r['mem_pct'] or 0,
                cpu_cores=r['cpu'], mem_bytes=r['mem'],
            )
            saved += 1
    cutoff = timezone.now() - timedelta(hours=KEEP_HOURS)
    MetricSample.objects.filter(created_at__lt=cutoff).delete()
    if skipped:
        logger.info('指标采样部分跳过：%s' % '；'.join(skipped))
    return {'saved': saved, 'skipped': skipped}
