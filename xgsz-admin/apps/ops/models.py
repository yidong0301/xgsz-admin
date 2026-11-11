#!/bin/env python3
# -*- coding: utf-8 -*-

from django.db import models


class AuditLog(models.Model):
    """
    操作审计日志：记录关键操作（登录、资产变更、任务提交等）
    """
    user = models.CharField(max_length=64, verbose_name='操作人', null=True, blank=True)
    action = models.CharField(max_length=32, verbose_name='操作类型')
    resource = models.CharField(max_length=128, verbose_name='操作对象', null=True, blank=True)
    detail = models.TextField(verbose_name='详情', null=True, blank=True)
    ip = models.CharField(max_length=64, verbose_name='来源IP', null=True, blank=True)
    result = models.CharField(max_length=16, verbose_name='操作结果', default='成功')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='操作时间')

    class Meta:
        db_table = 'ops_audit_log'
        verbose_name = '操作审计日志'
        verbose_name_plural = verbose_name
        ordering = ['-id']

    def __str__(self):
        return '%s %s %s' % (self.user, self.action, self.resource or '')


class OpsLog(models.Model):
    """
    运维日志：记录系统/组件的运维事件（启停、健康检查、任务失败、巡检等）
    """
    LEVEL_CHOICES = (
        ('INFO', '信息'),
        ('WARN', '警告'),
        ('ERROR', '错误'),
    )
    SOURCE_CHOICES = (
        ('system', '系统'),
        ('docker', '容器'),
        ('k8s', 'K8s'),
        ('mysql', 'MySQL'),
        ('redis', 'Redis'),
        ('mongo', 'MongoDB'),
        ('celery', 'Celery'),
        ('task', '推理任务'),
        ('workflow', '任务编排'),
        ('inspection', '巡检'),
        ('auth', '登录认证'),
    )
    level = models.CharField(max_length=8, choices=LEVEL_CHOICES, default='INFO', verbose_name='级别')
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default='system', verbose_name='来源')
    message = models.CharField(max_length=256, verbose_name='事件')
    detail = models.TextField(null=True, blank=True, verbose_name='详情')
    operator = models.CharField(max_length=64, null=True, blank=True, verbose_name='操作人')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='时间')

    class Meta:
        db_table = 'ops_log'
        verbose_name = '运维日志'
        verbose_name_plural = verbose_name
        ordering = ['-id']

    def __str__(self):
        return '[%s] %s %s' % (self.level, self.source, self.message)


class InspectionRecord(models.Model):
    """
    运维巡检记录：定时/手动采集，标记异常
    """
    STATUS_CHOICES = (
        ('HEALTHY', '正常'),
        ('WARNING', '有异常'),
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='HEALTHY', verbose_name='巡检结果')
    anomaly_count = models.IntegerField(default=0, verbose_name='异常数量')
    anomalies = models.TextField(verbose_name='异常明细', null=True, blank=True, help_text='JSON 数组')
    checked_at = models.DateTimeField(auto_now_add=True, verbose_name='巡检时间')

    class Meta:
        db_table = 'ops_inspection_record'
        verbose_name = '巡检记录'
        verbose_name_plural = verbose_name
        ordering = ['-id']

    def __str__(self):
        return '%s %s' % (self.checked_at.strftime('%Y-%m-%d %H:%M:%S'), self.status)


class ReleaseOrder(models.Model):
    """发布单：持续交付的最小闭环（创建 → 审批 → 发布 → 回滚）"""
    STATUS_CHOICES = (
        ('PENDING', '待审批'),
        ('APPROVED', '已审批'),
        ('RELEASING', '发布中'),
        ('RELEASED', '已发布'),
        ('FAILED', '发布失败'),
        ('ROLLED_BACK', '已回滚'),
        ('REJECTED', '已拒绝'),
    )
    HEALTH_CHOICES = (
        ('UNKNOWN', '未检查'),
        ('DEPLOYING', '检查中'),
        ('HEALTHY', '健康'),
        ('UNHEALTHY', '异常'),
    )
    ENV_CHOICES = (
        ('dev', '开发环境'),
        ('test', '测试环境'),
        ('prod', '生产环境'),
    )
    release_no = models.CharField(max_length=32, verbose_name='发布单号', unique=True)
    app_name = models.CharField(max_length=64, verbose_name='应用/服务名')
    env = models.CharField(max_length=8, choices=ENV_CHOICES, default='test', verbose_name='目标环境')
    namespace = models.CharField(max_length=64, default='default', verbose_name='命名空间')
    cluster = models.CharField(max_length=64, default='kind', verbose_name='目标集群')
    image = models.CharField(max_length=256, verbose_name='镜像地址')
    version = models.CharField(max_length=64, null=True, blank=True, verbose_name='版本号')
    replicas = models.IntegerField(default=1, verbose_name='副本数')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='PENDING', verbose_name='状态')
    reason = models.CharField(max_length=256, null=True, blank=True, verbose_name='变更说明')
    creator = models.CharField(max_length=64, null=True, blank=True, verbose_name='创建人')
    approver = models.CharField(max_length=64, null=True, blank=True, verbose_name='审批人')
    approver_remark = models.CharField(max_length=256, null=True, blank=True, verbose_name='审批意见')
    k8s_deployment = models.CharField(max_length=128, null=True, blank=True, verbose_name='K8s Deployment')
    previous_image = models.CharField(max_length=256, null=True, blank=True, verbose_name='上一版本镜像')
    previous_replicas = models.IntegerField(null=True, blank=True, verbose_name='上一版本副本数')
    health_status = models.CharField(max_length=16, choices=HEALTH_CHOICES, default='UNKNOWN', verbose_name='健康状态')
    health_detail = models.TextField(null=True, blank=True, verbose_name='健康检查详情', help_text='JSON')
    executed_by = models.CharField(max_length=64, null=True, blank=True, verbose_name='发布执行人')
    duration_ms = models.IntegerField(null=True, blank=True, verbose_name='发布耗时(毫秒)')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='审批时间')
    released_at = models.DateTimeField(null=True, blank=True, verbose_name='发布时间')

    class Meta:
        db_table = 'ops_release_order'
        verbose_name = '发布单'
        verbose_name_plural = verbose_name
        ordering = ['-id']

    def __str__(self):
        return '%s %s %s' % (self.release_no, self.app_name, self.status)


class AlertState(models.Model):
    """告警处理状态机：OPEN(待认领) -> ACKED(已认领锁定) -> CLOSED(填单关闭)"""
    STATUS_CHOICES = (
        ('OPEN', '待认领'),
        ('ACKED', '已认领'),
        ('CLOSED', '已关闭'),
    )
    alert_key = models.CharField(max_length=64, unique=True, verbose_name='告警指纹')
    title = models.CharField(max_length=256, verbose_name='告警标题')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='OPEN', verbose_name='状态')
    claimed_by = models.CharField(max_length=64, null=True, blank=True, verbose_name='认领人')
    claimed_at = models.DateTimeField(null=True, blank=True, verbose_name='认领时间')
    closed_by = models.CharField(max_length=64, null=True, blank=True, verbose_name='关闭人')
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name='关闭时间')
    note = models.TextField(null=True, blank=True, verbose_name='处理结果')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'ops_alert_state'
        verbose_name = '告警处理状态'
        verbose_name_plural = verbose_name
        ordering = ['-updated_at']

    def __str__(self):
        return '%s %s' % (self.alert_key, self.status)


class EnvConfig(models.Model):
    """环境运行配置参数：保存后「应用到集群」会写入 ConfigMap 并重启引用它的应用。

    这是真实生效的配置（不是演示数据）：同一 (环境, 集群, 命名空间, 键) 唯一。
    """
    ENV_CHOICES = (('dev', '开发环境'), ('test', '测试环境'), ('prod', '生产环境'))

    env = models.CharField(max_length=16, choices=ENV_CHOICES, default='dev', verbose_name='环境')
    cluster = models.CharField(max_length=64, default='kind', verbose_name='集群')
    namespace = models.CharField(max_length=64, default='default', verbose_name='命名空间')
    key = models.CharField(max_length=128, verbose_name='配置键')
    value = models.TextField(blank=True, default='', verbose_name='配置值')
    remark = models.CharField(max_length=256, null=True, blank=True, verbose_name='说明')
    updated_by = models.CharField(max_length=64, null=True, blank=True, verbose_name='更新人')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'env_config'
        verbose_name = '环境配置参数'
        verbose_name_plural = verbose_name
        ordering = ['key']
        unique_together = ('env', 'cluster', 'namespace', 'key')
        indexes = [models.Index(fields=['env', 'cluster', 'namespace'])]

    def __str__(self):
        return '%s/%s/%s %s' % (self.env, self.cluster, self.namespace, self.key)


class NotificationRead(models.Model):
    """通知已读状态：按用户记录告警指纹的已读，铃铛红点按未读数显示。

    与告警处理状态（AlertState）分开：已读只代表「用户看过这条通知」，
    不代表已经认领/关闭告警。
    """

    user = models.CharField(max_length=64, verbose_name='用户')
    alert_key = models.CharField(max_length=64, verbose_name='通知指纹')
    read_at = models.DateTimeField(auto_now_add=True, verbose_name='已读时间')

    class Meta:
        db_table = 'ops_notification_read'
        verbose_name = '通知已读状态'
        verbose_name_plural = verbose_name
        ordering = ['-read_at']
        unique_together = ('user', 'alert_key')

    def __str__(self):
        return '%s %s' % (self.user, self.alert_key)


class MetricSample(models.Model):
    """节点指标采样（每分钟一条，用于趋势曲线；24 小时后自动清理）"""
    cluster = models.CharField(max_length=64, default='kind', verbose_name='集群')
    node = models.CharField(max_length=128, verbose_name='节点')
    cpu_pct = models.FloatField(default=0, verbose_name='CPU 使用率%')
    mem_pct = models.FloatField(default=0, verbose_name='内存使用率%')
    cpu_cores = models.FloatField(default=0, verbose_name='CPU 使用核数')
    mem_bytes = models.BigIntegerField(default=0, verbose_name='内存使用字节')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='采样时间')

    class Meta:
        db_table = 'ops_metric_sample'
        verbose_name = '节点指标采样'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [models.Index(fields=['cluster', 'node', '-created_at'])]

    def __str__(self):
        return '%s/%s %.1f%%' % (self.cluster, self.node, self.cpu_pct)
