#!/bin/env python3
# -*- coding: utf-8 -*-

"""
@Time: 2020/9/27 11:28
@Author: yu.jiang <safemonitor@outlook.com>
@License: Apache License
@File: user.py

"""

from django.conf.urls import url

from apps.account.views.dingtalk import DingLogin, DingCallBack
from apps.account.views.user import UserLoginView, CheckEmailExistView, SendCodeView, CheckCodeView, ResetPwdView, \
    ChangePwdView, AccountInfoView, UserRoleView, UserProfileView, UserResetPasswordView
from apps.account.views.health import HealthCheckView
from apps.account.views.alerts import AlertView, AlertClaimView, AlertCloseView, AlertReadView
from apps.account.views.qr_login import QrCreateView, QrStatusView, QrApproveView

app_name = 'account'

urlpatterns = [
    url(r'^(?P<version>[v1|v2]+)/user/login$', UserLoginView.as_view(), name='login'),
    url(r'^(?P<version>[v1|v2]+)/user/dingding$', DingLogin.as_view(), name='ding_login'),
    url(r'^(?P<version>[v1|v2]+)/user/dingding/callback$', DingCallBack.as_view(), name='ding_callback'),
    url(r'^(?P<version>[v1|v2]+)/user/check_email_exist$', CheckEmailExistView.as_view(), name='check_email_exists'),
    url(r'^(?P<version>[v1|v2]+)/user/password/send_code$', SendCodeView.as_view(), name='send_code'),
    url(r'^(?P<version>[v1|v2]+)/user/password/check_code$', CheckCodeView.as_view(), name='check_code'),
    url(r'^(?P<version>[v1|v2]+)/user/password/reset_pwd$', ResetPwdView.as_view(), name='reset_pwd'),
    url(r'^(?P<version>[v1|v2]+)/user/password/change$', ChangePwdView.as_view(), name='change_pwd'),
    url(r'^(?P<version>[v1|v2]+)/users$', AccountInfoView.as_view(), name='account_info'),
    url(r'^(?P<version>[v1|v2]+)/user/role$', UserRoleView.as_view(), name='user_role'),
    url(r'^(?P<version>[v1|v2]+)/user/profile$', UserProfileView.as_view(), name='user_profile'),
    url(r'^(?P<version>[v1|v2]+)/user/reset_password$', UserResetPasswordView.as_view(), name='user_reset_password'),
    url(r'^(?P<version>[v1|v2]+)/user/qr/create$', QrCreateView.as_view(), name='qr_create'),
    url(r'^(?P<version>[v1|v2]+)/user/qr/status$', QrStatusView.as_view(), name='qr_status'),
    url(r'^(?P<version>[v1|v2]+)/user/qr/approve$', QrApproveView.as_view(), name='qr_approve'),
    url(r'^(?P<version>[v1|v2]+)/health$', HealthCheckView.as_view(), name='health'),
    url(r'^(?P<version>[v1|v2]+)/alerts$', AlertView.as_view(), name='alerts'),
    url(r'^(?P<version>[v1|v2]+)/alerts/read$', AlertReadView.as_view(), name='alert_read'),
    url(r'^(?P<version>[v1|v2]+)/alerts/claim$', AlertClaimView.as_view(), name='alert_claim'),
    url(r'^(?P<version>[v1|v2]+)/alerts/close$', AlertCloseView.as_view(), name='alert_close'),

]