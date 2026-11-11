#!/bin/env python3
# -*- coding: utf-8 -*-

from django.conf.urls import url

from apps.workflow.views import (
    TaskTemplateView, TaskExecutionView, TaskExecutionDetailView,
    PipelineView, PipelineExecutionView, PipelineExecutionDetailView,
)

app_name = 'workflow'

urlpatterns = [
    url(r'^(?P<version>[v1|v2]+)/task/template$', TaskTemplateView.as_view(), name='task_template'),
    url(r'^(?P<version>[v1|v2]+)/task/execution$', TaskExecutionView.as_view(), name='task_execution'),
    url(r'^(?P<version>[v1|v2]+)/task/execution/(?P<pk>\d+)$', TaskExecutionDetailView.as_view(), name='task_execution_detail'),
    url(r'^(?P<version>[v1|v2]+)/pipeline$', PipelineView.as_view(), name='pipeline'),
    url(r'^(?P<version>[v1|v2]+)/pipeline/execution$', PipelineExecutionView.as_view(), name='pipeline_execution'),
    url(r'^(?P<version>[v1|v2]+)/pipeline/execution/(?P<pk>\d+)$', PipelineExecutionDetailView.as_view(), name='pipeline_execution_detail'),
]
