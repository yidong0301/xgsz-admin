#!/bin/env python3
# -*- coding: utf-8 -*-

# Copyright: (c) SmallFlyingPigs Organization. https://github.com/small-flying-pigs
# Copyright: (c) <pigs@dnsjia.com>
# Released under the AGPL-3.0 License.


"""
# @File  : urls.py
# @Author: 风哥
# @Email: gujiwork@outlook.com
# @Date  : 2020/12/7
# @Desc  :
"""

from django.conf.urls import url
from django.urls import path

from apps.k8s.views.deployment import DeploymentViews, DetailDeploymentViews, DeploymentHistoryVersionViews
from apps.k8s.views.logs import LogsView
from apps.k8s.views.namespace import NamespaceView
from apps.k8s.views.node import NodeView, DarinNodeAndPod, NodeDetailView, NodeEventsView, NodeMetrics
from apps.k8s.views.pod import PodFromNodeView, DetailPodView, PodViews
from apps.k8s.views.events import EventsView, DeploymentEventsView
from apps.k8s.views.scale import DeploymentScaleViews
from apps.k8s.views.inference import (InferenceTaskView, InferenceTaskDetailView, InferenceTaskStopView,
                                      InferenceTaskLogsView, InferenceTaskUsageView, InferenceMetaView,
                                      InferenceTaskEventsView, InferenceTaskRerunView,
                                      InferenceTaskRenameView)
from apps.k8s.views.node_manage import (ManagedNodeListView, ManagedNodeDetailView,
                                        ManagedNodeCordonView, ManagedNodeDrainView,
                                        ManagedNodeLabelsView, ManagedNodeTaintsView,
                                        ManagedNodeRegisterAssetView)

app_name = 'k8s'

urlpatterns = [
    url(r'^(?P<version>[v1|v2]+)/drain/nodes$', DarinNodeAndPod.as_view(), name='node_drain'),
    url(r'^(?P<version>[v1|v2]+)/nodes$', NodeView.as_view(), name='nodes'),
    url(r'^(?P<version>[v1|v2]+)/detail/node$', NodeDetailView.as_view(), name='detail_node'),
    url(r'^(?P<version>[v1|v2]+)/events/node$', NodeEventsView.as_view(), name='event_node'),
    url(r'^(?P<version>[v1|v2]+)/event/deployment$', DeploymentEventsView.as_view(), name='event_node'),
    url(r'^(?P<version>[v1|v2]+)/metrics/node$', NodeMetrics.as_view(), name='metrics_node'),
    url(r'^(?P<version>[v1|v2]+)/pods/node$', PodFromNodeView.as_view(), name='pod_to_node'),
    url(r'^(?P<version>[v1|v2]+)/pods/list$', PodViews.as_view(), name='pods'),
    url(r'^(?P<version>[v1|v2]+)/event/pod$', EventsView.as_view(), name='event_pod'),
    url(r'^(?P<version>[v1|v2]+)/namespaces$', NamespaceView.as_view(), name='namespaces'),
    url(r'^(?P<version>[v1|v2]+)/pod$', DetailPodView.as_view(), name='pod'),
    url(r'^(?P<version>[v1|v2]+)/logs$', LogsView.as_view(), name='logs'),
    url(r'^(?P<version>[v1|v2]+)/deployments$', DeploymentViews.as_view(), name='deployments'),
    url(r'^(?P<version>[v1|v2]+)/deployment/detail$', DetailDeploymentViews.as_view(), name='deployment'),
    url(r'^(?P<version>[v1|v2]+)/deployment/scale$', DeploymentScaleViews.as_view(), name='scale'),
    url(r'^(?P<version>[v1|v2]+)/deployment/history$', DeploymentHistoryVersionViews.as_view(), name='history_version'),
    # 推理任务（SERVICE=Deployment+Service，BATCH=Job）
    url(r'^(?P<version>[v1|v2]+)/inference/task$', InferenceTaskView.as_view(), name='inference_task'),
    url(r'^(?P<version>[v1|v2]+)/inference/meta$', InferenceMetaView.as_view(), name='inference_meta'),
    url(r'^(?P<version>[v1|v2]+)/inference/task/(?P<pk>\d+)$', InferenceTaskDetailView.as_view(), name='inference_task_detail'),
    url(r'^(?P<version>[v1|v2]+)/inference/task/(?P<pk>\d+)/stop$', InferenceTaskStopView.as_view(), name='inference_task_stop'),
    url(r'^(?P<version>[v1|v2]+)/inference/task/(?P<pk>\d+)/logs$', InferenceTaskLogsView.as_view(), name='inference_task_logs'),
    url(r'^(?P<version>[v1|v2]+)/inference/task/(?P<pk>\d+)/events$', InferenceTaskEventsView.as_view(), name='inference_task_events'),
    url(r'^(?P<version>[v1|v2]+)/inference/task/(?P<pk>\d+)/rerun$', InferenceTaskRerunView.as_view(), name='inference_task_rerun'),
    url(r'^(?P<version>[v1|v2]+)/inference/task/(?P<pk>\d+)/rename$', InferenceTaskRenameView.as_view(), name='inference_task_rename'),
    url(r'^(?P<version>[v1|v2]+)/inference/task/(?P<pk>\d+)/usage$', InferenceTaskUsageView.as_view(), name='inference_task_usage'),
    # 节点/机器管理（集群感知）
    url(r'^(?P<version>[v1|v2]+)/manage/nodes$', ManagedNodeListView.as_view(), name='managed_nodes'),
    url(r'^(?P<version>[v1|v2]+)/manage/node/detail$', ManagedNodeDetailView.as_view(), name='managed_node_detail'),
    url(r'^(?P<version>[v1|v2]+)/manage/node/cordon$', ManagedNodeCordonView.as_view(), name='managed_node_cordon'),
    url(r'^(?P<version>[v1|v2]+)/manage/node/drain$', ManagedNodeDrainView.as_view(), name='managed_node_drain'),
    url(r'^(?P<version>[v1|v2]+)/manage/node/labels$', ManagedNodeLabelsView.as_view(), name='managed_node_labels'),
    url(r'^(?P<version>[v1|v2]+)/manage/node/taints$', ManagedNodeTaintsView.as_view(), name='managed_node_taints'),
    url(r'^(?P<version>[v1|v2]+)/manage/node/register-asset$', ManagedNodeRegisterAssetView.as_view(),
        name='managed_node_register_asset'),
]