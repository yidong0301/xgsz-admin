#!/bin/env python3
# -*- coding: utf-8 -*-

from django.utils import timezone
from rest_framework import serializers

from apps.k8s.models import InferenceTask


class InferenceTaskSerializer(serializers.ModelSerializer):
    """推理任务序列化器（含真实耗时：Job startTime → completionTime）"""

    duration_seconds = serializers.SerializerMethodField()
    duration_text = serializers.SerializerMethodField()

    class Meta:
        model = InferenceTask
        fields = '__all__'
        read_only_fields = ['status', 'job_name', 'error_msg', 'created_at', 'updated_at']

    def _duration(self, obj):
        if not getattr(obj, 'started_at', None):
            return None
        end = getattr(obj, 'finished_at', None)
        if end is None and obj.status in ('SUBMITTED', 'RUNNING'):
            end = timezone.now()
        if end is None:
            return None
        try:
            return max(int(round((end - obj.started_at).total_seconds())), 0)
        except Exception:
            return None

    def get_duration_seconds(self, obj):
        return self._duration(obj)

    def get_duration_text(self, obj):
        sec = self._duration(obj)
        if sec is None:
            return ''
        if sec < 1:
            text = '<1 秒'
        elif sec < 60:
            text = '%d 秒' % sec
        elif sec < 3600:
            text = '%d 分 %d 秒' % (sec // 60, sec % 60)
        else:
            text = '%d 小时 %d 分' % (sec // 3600, (sec % 3600) // 60)
        # 运行中的任务显示「运行了多久」，已结束的显示「耗时」
        if obj.status in ('SUBMITTED', 'RUNNING', 'PENDING'):
            return '运行 ' + text
        return text
