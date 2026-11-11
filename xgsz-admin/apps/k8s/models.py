#!/bin/env python3
# -*- coding: utf-8 -*-

# Copyright: (c) SmallFlyingPigs Organization. https://github.com/small-flying-pigs
# Copyright: (c) <pigs@dnsjia.com>
# Released under the AGPL-3.0 License.

from django.db import models


class InferenceTask(models.Model):
    """
    推理任务：提交到 K8s 以 Job 方式运行 AI 推理
    """
    STATUS_CHOICES = (
        ('PENDING', '待执行'),
        ('SUBMITTED', '已提交'),
        ('RUNNING', '运行中'),
        ('SUCCEEDED', '成功'),
        ('FAILED', '失败'),
        ('STOPPED', '已停止'),
        ('SUBMIT_ERROR', '提交失败'),
    )

    name = models.CharField(max_length=128, verbose_name='任务名称')
    cluster = models.CharField(max_length=64, verbose_name='目标集群', default='', blank=True,
                               help_text='kube/clusters/<集群名>.yaml；为空时用默认集群')
    task_type = models.CharField(max_length=16, verbose_name='任务形态', default='BATCH',
                                 choices=(('SERVICE', '在线服务'), ('BATCH', '批任务')))
    namespace = models.CharField(max_length=64, verbose_name='命名空间', default='default')
    image = models.CharField(max_length=256, verbose_name='镜像')
    command = models.TextField(verbose_name='命令', null=True, blank=True, help_text='JSON 数组，如 ["python","run.py"]')
    args = models.TextField(verbose_name='参数', null=True, blank=True, help_text='JSON 数组')
    env_vars = models.TextField(verbose_name='环境变量', null=True, blank=True, help_text='JSON 对象，如 {"A":"1"}')
    cpu = models.CharField(max_length=16, verbose_name='CPU', default='1')
    memory = models.CharField(max_length=16, verbose_name='内存', default='2Gi')
    gpu = models.IntegerField(verbose_name='GPU 数量', default=0)
    gpu_node = models.ForeignKey('cmdb.GPUNode', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='绑定GPU节点')
    node_selector = models.TextField(verbose_name='节点选择器', null=True, blank=True, help_text='JSON，如 {"gpu":"true"}')
    status = models.CharField(max_length=16, verbose_name='状态', choices=STATUS_CHOICES, default='PENDING')
    job_name = models.CharField(max_length=128, verbose_name='K8s 资源名', null=True, blank=True)
    service_name = models.CharField(max_length=128, verbose_name='K8s Service 名', null=True, blank=True)
    service_port = models.IntegerField(verbose_name='服务端口', default=80)
    node_port = models.IntegerField(verbose_name='NodePort', null=True, blank=True)
    replicas = models.IntegerField(verbose_name='副本数', default=1)
    timeout_seconds = models.IntegerField(verbose_name='超时秒数', default=3600)
    image_pull_secret = models.CharField(max_length=128, verbose_name='镜像拉取密钥', null=True, blank=True)
    pod_name = models.CharField(max_length=128, verbose_name='Pod 名称', null=True, blank=True)
    owner = models.CharField(max_length=64, verbose_name='负责人', null=True, blank=True)
    probe_port = models.IntegerField(verbose_name='存活探针端口', null=True, blank=True,
                                     help_text='填写后生成 livenessProbe(httpGet)，假死自动重启')
    probe_path = models.CharField(max_length=128, verbose_name='存活探针路径', null=True, blank=True, default='/healthz')
    error_msg = models.TextField(verbose_name='错误信息', null=True, blank=True)
    failure_reason = models.TextField(verbose_name='失败原因', null=True, blank=True)
    exit_code = models.IntegerField(verbose_name='退出码', null=True, blank=True)
    started_at = models.DateTimeField(verbose_name='开始运行时间', null=True, blank=True,
                                     help_text='来自 K8s Job startTime / Deployment 首次可用')
    finished_at = models.DateTimeField(verbose_name='结束时间', null=True, blank=True,
                                      help_text='来自 K8s Job completionTime 或失败判定时间')
    last_synced_at = models.DateTimeField(verbose_name='最近同步时间', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'k8s_inference_task'
        verbose_name = '推理任务'
        verbose_name_plural = verbose_name
        ordering = ['-id']

    def __str__(self):
        return self.name
