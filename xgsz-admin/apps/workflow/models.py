#!/bin/env python3
# -*- coding: utf-8 -*-

from django.db import models


class TaskTemplate(models.Model):
    """
    任务编排模板：定义一组可执行的运维步骤（串行）
    steps 为 JSON 数组：[{name, command, retry, timeout, image, cpu, memory, gpu}, ...]

    target_type：
      - local：在 backend 容器内 shell 执行（演示用，不具备隔离）
      - k8s：每个步骤创建一个 K8s Job 执行（真实调度，按 CPU/内存/GPU 分配资源）
    """
    TARGET_CHOICES = (('local', '本机执行（演示）'), ('k8s', 'K8s Job（真实调度）'))

    name = models.CharField(max_length=128, verbose_name='模板名称')
    description = models.TextField(verbose_name='描述', null=True, blank=True)
    steps = models.TextField(verbose_name='步骤定义', help_text='JSON 数组')
    target_type = models.CharField(max_length=16, choices=TARGET_CHOICES, default='local', verbose_name='执行方式')
    cluster = models.CharField(max_length=64, default='kind', blank=True, verbose_name='目标集群')
    namespace = models.CharField(max_length=64, default='default', blank=True, verbose_name='命名空间')
    image = models.CharField(max_length=256, blank=True, default='busybox:1.36', verbose_name='镜像')
    cpu = models.CharField(max_length=32, default='500m', blank=True, verbose_name='CPU')
    memory = models.CharField(max_length=32, default='256Mi', blank=True, verbose_name='内存')
    gpu = models.IntegerField(default=0, verbose_name='GPU 卡数')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'workflow_task_template'
        verbose_name = '任务编排模板'
        verbose_name_plural = verbose_name
        ordering = ['-id']

    def __str__(self):
        return self.name


class TaskExecution(models.Model):
    """任务执行记录"""
    STATUS_CHOICES = (
        ('PENDING', '待执行'),
        ('RUNNING', '运行中'),
        ('SUCCEEDED', '成功'),
        ('FAILED', '失败'),
        ('PARTIAL', '部分成功'),
    )
    template = models.ForeignKey(TaskTemplate, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='模板')
    name = models.CharField(max_length=128, verbose_name='执行名称')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='PENDING', verbose_name='状态')
    target_type = models.CharField(max_length=16, default='local', verbose_name='执行方式')
    cluster = models.CharField(max_length=64, blank=True, null=True, verbose_name='集群快照')
    namespace = models.CharField(max_length=64, blank=True, null=True, verbose_name='命名空间快照')
    steps_result = models.TextField(verbose_name='步骤结果', null=True, blank=True, help_text='JSON 数组')
    log = models.TextField(verbose_name='执行日志', null=True, blank=True)
    triggered_by = models.CharField(max_length=64, verbose_name='触发人', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='结束时间')

    class Meta:
        db_table = 'workflow_task_execution'
        verbose_name = '任务执行记录'
        verbose_name_plural = verbose_name
        ordering = ['-id']

    def __str__(self):
        return self.name


class Pipeline(models.Model):
    """
    CI/CD 流水线定义
    stages 为 JSON 数组：[{name, command}, ...]
    """
    name = models.CharField(max_length=128, verbose_name='流水线名称')
    description = models.TextField(verbose_name='描述', null=True, blank=True)
    stages = models.TextField(verbose_name='阶段定义', help_text='JSON 数组')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'workflow_pipeline'
        verbose_name = 'CI/CD 流水线'
        verbose_name_plural = verbose_name
        ordering = ['-id']

    def __str__(self):
        return self.name


class PipelineExecution(models.Model):
    """流水线执行记录"""
    STATUS_CHOICES = (
        ('PENDING', '待执行'),
        ('BUILDING', '构建中'),
        ('DEPLOYING', '部署中'),
        ('SUCCEEDED', '成功'),
        ('FAILED', '失败'),
    )
    pipeline = models.ForeignKey(Pipeline, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='流水线')
    name = models.CharField(max_length=128, verbose_name='执行名称')
    version = models.CharField(max_length=64, verbose_name='版本号', null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='PENDING', verbose_name='状态')
    log = models.TextField(verbose_name='日志', null=True, blank=True)
    triggered_by = models.CharField(max_length=64, verbose_name='触发人', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='结束时间')

    class Meta:
        db_table = 'workflow_pipeline_execution'
        verbose_name = '流水线执行记录'
        verbose_name_plural = verbose_name
        ordering = ['-id']

    def __str__(self):
        return self.name
