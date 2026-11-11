#!/bin/env python3
# -*- coding: utf-8 -*-

from django.conf.urls import url

from apps.ops.views import (OpsDashboardView, InspectionView, InspectionHistoryView, NotifyView,
                            AuditLogView, OverviewView, OpsLogView, ClusterHealthView,
                            ReleaseOrderView, ReleaseOrderDetailView, ReleaseOrderCompareView,
                            ReleaseOrderLogsView, ReleaseOrderActionView)
from apps.ops.views_env import EnvConfigView, EnvConfigDetailView, EnvConfigApplyView
from apps.ops.views_metrics import MetricsOverviewView

app_name = 'ops'

urlpatterns = [
    url(r'^(?P<version>[v1|v2]+)/overview$', OverviewView.as_view(), name='overview'),
    url(r'^(?P<version>[v1|v2]+)/dashboard$', OpsDashboardView.as_view(), name='ops_dashboard'),
    url(r'^(?P<version>[v1|v2]+)/inspection$', InspectionView.as_view(), name='inspection'),
    url(r'^(?P<version>[v1|v2]+)/inspection/history$', InspectionHistoryView.as_view(), name='inspection_history'),
    url(r'^(?P<version>[v1|v2]+)/notify$', NotifyView.as_view(), name='notify'),
    url(r'^(?P<version>[v1|v2]+)/audit$', AuditLogView.as_view(), name='audit'),
    url(r'^(?P<version>[v1|v2]+)/opslog$', OpsLogView.as_view(), name='opslog'),
    url(r'^(?P<version>[v1|v2]+)/clusters$', ClusterHealthView.as_view(), name='cluster_health'),
    # 指标总览（metrics-server）
    url(r'^(?P<version>[v1|v2]+)/metrics/overview$', MetricsOverviewView.as_view(), name='metrics_overview'),
    # 环境运行配置参数（真实下发 ConfigMap + 重启引用了它的应用）
    url(r'^(?P<version>[v1|v2]+)/env-config/apply$', EnvConfigApplyView.as_view(), name='env_config_apply'),
    url(r'^(?P<version>[v1|v2]+)/env-config/(?P<pk>\d+)$', EnvConfigDetailView.as_view(), name='env_config_detail'),
    url(r'^(?P<version>[v1|v2]+)/env-config$', EnvConfigView.as_view(), name='env_config'),
    url(r'^(?P<version>[v1|v2]+)/release/(?P<pk>\d+)/compare$', ReleaseOrderCompareView.as_view(), name='release_compare'),
    url(r'^(?P<version>[v1|v2]+)/release/(?P<pk>\d+)/logs$', ReleaseOrderLogsView.as_view(), name='release_logs'),
    url(r'^(?P<version>[v1|v2]+)/release/(?P<pk>\d+)$', ReleaseOrderDetailView.as_view(), name='release_detail'),
    url(r'^(?P<version>[v1|v2]+)/release$', ReleaseOrderView.as_view(), name='release'),
    url(r'^(?P<version>[v1|v2]+)/release/(?P<pk>\d+)/(?P<action>\w+)$', ReleaseOrderActionView.as_view(), name='release_action'),
]
