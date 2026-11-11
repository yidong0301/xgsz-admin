#!/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import traceback

from rest_framework.views import APIView

from apps.workflow.models import TaskTemplate, TaskExecution, Pipeline, PipelineExecution
from utils.authorization import MyAuthentication
from utils.http_response import APIResponse
from utils.permissions import MyPermission
from utils.pagination import MyPageNumberPagination

logger = logging.getLogger('default')


def _tpl_dict(t):
    return {'id': t.id, 'name': t.name, 'description': t.description, 'steps': t.steps,
            'target_type': t.target_type, 'cluster': t.cluster, 'namespace': t.namespace,
            'image': t.image, 'cpu': t.cpu, 'memory': t.memory, 'gpu': t.gpu,
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S') if t.created_at else ''}


def _exec_dict(e):
    return {'id': e.id, 'name': e.name, 'status': e.status, 'steps_result': e.steps_result,
            'log': e.log, 'triggered_by': e.triggered_by,
            'target_type': getattr(e, 'target_type', 'local'),
            'cluster': getattr(e, 'cluster', None), 'namespace': getattr(e, 'namespace', None),
            'created_at': e.created_at.strftime('%Y-%m-%d %H:%M:%S') if e.created_at else '',
            'finished_at': e.finished_at.strftime('%Y-%m-%d %H:%M:%S') if e.finished_at else ''}


def _pipe_dict(p):
    return {'id': p.id, 'name': p.name, 'description': p.description, 'stages': p.stages,
            'created_at': p.created_at.strftime('%Y-%m-%d %H:%M:%S') if p.created_at else ''}


def _pe_dict(e):
    return {'id': e.id, 'name': e.name, 'version': e.version, 'status': e.status, 'log': e.log,
            'triggered_by': e.triggered_by,
            'created_at': e.created_at.strftime('%Y-%m-%d %H:%M:%S') if e.created_at else '',
            'finished_at': e.finished_at.strftime('%Y-%m-%d %H:%M:%S') if e.finished_at else ''}


# ============ 任务编排 ============

class TaskTemplateView(APIView):
    """任务模板：列表 / 创建"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        paginator = MyPageNumberPagination()
        page = paginator.paginate_queryset(TaskTemplate.objects.all(), request, view=self)
        return APIResponse(data=paginator.get_paginated_response([_tpl_dict(t) for t in page]).data)

    def post(self, request, *args, **kwargs):
        name = request.data.get('name')
        if not name:
            return APIResponse(errcode=400, errmsg='缺少模板名称')
        steps = request.data.get('steps')
        if isinstance(steps, (list, dict)):
            steps = json.dumps(steps, ensure_ascii=False)
        target = (request.data.get('target_type') or 'local').strip()
        if target not in ('local', 'k8s'):
            return APIResponse(errcode=400, errmsg='执行方式不合法：%s' % target)
        t = TaskTemplate.objects.create(
            name=name, description=request.data.get('description'), steps=steps or '[]',
            target_type=target,
            cluster=(request.data.get('cluster') or 'kind').strip() or 'kind',
            namespace=(request.data.get('namespace') or 'default').strip() or 'default',
            image=(request.data.get('image') or 'nginx:alpine').strip() or 'nginx:alpine',
            cpu=(request.data.get('cpu') or '500m').strip() or '500m',
            memory=(request.data.get('memory') or '256Mi').strip() or '256Mi',
            gpu=int(request.data.get('gpu') or 0),
        )
        return APIResponse(data=_tpl_dict(t))


class TaskExecutionView(APIView):
    """任务执行：列表 / 触发"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        paginator = MyPageNumberPagination()
        page = paginator.paginate_queryset(TaskExecution.objects.all(), request, view=self)
        return APIResponse(data=paginator.get_paginated_response([_exec_dict(e) for e in page]).data)

    def post(self, request, *args, **kwargs):
        template_id = request.data.get('template_id')
        name = request.data.get('name')
        template = TaskTemplate.objects.filter(id=template_id).first() if template_id else None
        if not template:
            return APIResponse(errcode=400, errmsg='模板不存在')
        e = TaskExecution.objects.create(template=template, name=name or ('执行-' + template.name),
                                         triggered_by=getattr(request.user, 'name', None))
        try:
            from tasks.workflow import execute_task_template
            execute_task_template.delay(e.id)
            return APIResponse(data=_exec_dict(e))
        except Exception as ex:
            logger.error('触发任务失败: %s' % traceback.format_exc())
            e.status = 'FAILED'
            e.log = '触发失败: %s' % str(ex)
            e.save()
            return APIResponse(errcode=500, errmsg='触发失败: %s' % str(ex))


class TaskExecutionDetailView(APIView):
    """任务执行详情（含步骤结果 + 日志）"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        e = TaskExecution.objects.filter(id=kwargs.get('pk')).first()
        if not e:
            return APIResponse(errcode=404, errmsg='执行记录不存在')
        return APIResponse(data=_exec_dict(e))


# ============ CI/CD 流水线 ============

class PipelineView(APIView):
    """流水线：列表 / 创建"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        paginator = MyPageNumberPagination()
        page = paginator.paginate_queryset(Pipeline.objects.all(), request, view=self)
        return APIResponse(data=paginator.get_paginated_response([_pipe_dict(p) for p in page]).data)

    def post(self, request, *args, **kwargs):
        name = request.data.get('name')
        if not name:
            return APIResponse(errcode=400, errmsg='缺少流水线名称')
        stages = request.data.get('stages')
        if isinstance(stages, (list, dict)):
            stages = json.dumps(stages, ensure_ascii=False)
        p = Pipeline.objects.create(name=name, description=request.data.get('description'), stages=stages or '[]')
        return APIResponse(data=_pipe_dict(p))


class PipelineExecutionView(APIView):
    """流水线执行：列表 / 触发"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        paginator = MyPageNumberPagination()
        page = paginator.paginate_queryset(PipelineExecution.objects.all(), request, view=self)
        return APIResponse(data=paginator.get_paginated_response([_pe_dict(e) for e in page]).data)

    def post(self, request, *args, **kwargs):
        pipeline_id = request.data.get('pipeline_id')
        pipeline = Pipeline.objects.filter(id=pipeline_id).first() if pipeline_id else None
        if not pipeline:
            return APIResponse(errcode=400, errmsg='流水线不存在')
        version = request.data.get('version')
        pe = PipelineExecution.objects.create(pipeline=pipeline, name=request.data.get('name') or ('执行-' + pipeline.name),
                                              version=version, triggered_by=getattr(request.user, 'name', None))
        try:
            from tasks.workflow import execute_pipeline
            execute_pipeline.delay(pe.id)
            return APIResponse(data=_pe_dict(pe))
        except Exception as ex:
            logger.error('触发流水线失败: %s' % traceback.format_exc())
            pe.status = 'FAILED'
            pe.log = '触发失败: %s' % str(ex)
            pe.save()
            return APIResponse(errcode=500, errmsg='触发失败: %s' % str(ex))


class PipelineExecutionDetailView(APIView):
    """流水线执行详情"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        e = PipelineExecution.objects.filter(id=kwargs.get('pk')).first()
        if not e:
            return APIResponse(errcode=404, errmsg='执行记录不存在')
        return APIResponse(data=_pe_dict(e))
