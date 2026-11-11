#!/bin/env python3
# -*- coding: utf-8 -*-

# Copyright: (c) SmallFlyingPigs Organization. https://github.com/small-flying-pigs
# Copyright: (c) <pigs@dnsjia.com>
# Released under the AGPL-3.0 License.


"""
@Time: 2020/9/27 11:28
@Author: yu.jiang <safemonitor@outlook.com>
@License: Apache License
@File: user.py
"""

import logging
import traceback
from collections import defaultdict
from decouple import config

from django.contrib.auth import authenticate, login
from django.db.models import Q
from django.http import JsonResponse
from django_redis import get_redis_connection
from rest_framework import status
from rest_framework.views import APIView

from apps.account.models import User
from apps.account.serializers.users import UserInfoSerializer
from apps.rbac.models import Role
from utils.authorization import MyAuthentication
from utils.http_response import APIResponse
from utils.jwt_token import create_token
from utils.csrf_disable import CsrfExemptSessionAuthentication
from utils.code import RandCode
from utils.pagination import MyPageNumberPagination
from utils.permissions import MyPermission

logger = logging.getLogger('default')


class UserLoginView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        """
        {'username': 'gujiwork@pigs.com', 'password': '123456', 'remember': True}
        用户登录校验
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        request_id = request.META.get("HTTP_X_REQUEST_ID", "")
        try:
            data = request.data
            user_name = data['username']
            user_pwd = data['password']
            user = authenticate(username=user_name, password=user_pwd)

            if user and user.is_active:
                login(request, user)
                user_obj = user
                permissions_list = Role.objects.filter(user__id=user_obj.id).all().values(
                    'permissions__method', 'permissions__path'
                )
                permissions = defaultdict(list)
                for i in permissions_list:
                    permissions[i.get('permissions__path')].append(i.get('permissions__method'))
                for key in permissions.keys():
                    permissions[key] = list(set(permissions[key]))
                pk = user_obj.id

                token = create_token({'username': user_obj.username, 'permissions': permissions}, 1440)
                data = {"token": token, "name": user.name, "avatar": user.avatar, "id": pk,
                        "role": user.role, "is_superuser": user.is_superuser}
                try:
                    from apps.ops.views import record_audit
                    record_audit(user.name, 'login', '登录', '用户登录', request)
                except Exception:
                    pass
                return APIResponse(data=data)

            return APIResponse(errcode=20001, errmsg='邮箱或密码错误', status=status.HTTP_200_OK, request_id=request_id)

        except BaseException as e:
            logger.error("用户登录失败, 失败原因: %s" % str(traceback.format_exc()))
            logger.error(e)
            return APIResponse(
                errcode=99999, errmsg='登陆失败, 系统遇到未知错误!',
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                request_id=request_id
            )


class CheckEmailExistView(APIView):
    permission_classes = []
    authentication_classes = [CsrfExemptSessionAuthentication, ]

    def post(self, request, *args, **kwargs):
        """
        检查用户Email是否存在
        :param request:
        :param args:
        :param kwargs:
        :return:
        """

        try:
            data = request.data
            if User.objects.filter(email=data['email']).exists():
                return APIResponse(errcode=0, errmsg='账号已存在!')

            else:
                return APIResponse(errcode=4002, errmsg='账号不存在!')

        except Exception:
            return APIResponse(errcode=5001, errmsg='系统异常，请刷新后重试！')


class SendCodeView(APIView):
    permission_classes = []
    authentication_classes = [CsrfExemptSessionAuthentication, ]

    def post(self, request, *args, **kwargs):
        """
        找回密码，发送验证码
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        try:
            data = request.data
            email = data['email']
            if not User.objects.filter(email=email).exists():
                return JsonResponse(data={'errcode': 1007, 'msg': '账号不存在'})
            code = RandCode.get_code()

            from tasks.email import send_email
            title = '找回密码'
            msg = "账号：{email}, 您当前正在进行找回密码, 您的验证码是：{code}, 打死也不要将验证码告诉别人!".format(email=email, code=code['code'])
            msg_en = f"Account number: {email}, you are trying to retrieve your password, your verification code is: {code['code']}, don't tell others about your verification code!"

            # 使用默认配置连接到redis
            conn = get_redis_connection('default')
            conn.set(email, code['code'])
            conn.expire(email, 60 * 15)
            send_email.delay(email, code['code'], title, msg, msg_en, config('DOMAIN_URL'), subject=title)
            return APIResponse(errcode=0, errmsg='验证码已发送,请稍后查看邮箱')

        except BaseException as e:
            logger.error("获取验证码出错, 原因: %s" % str(traceback.format_exc()))
            print(traceback.format_exc())
            return APIResponse(errcode=1008, errmsg='获取验证码异常')


class CheckCodeView(APIView):
    permission_classes = []
    authentication_classes = [CsrfExemptSessionAuthentication, ]

    def post(self, request, *args, **kwargs):
        """
        找回密码，校验验证码
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        try:
            data = request.data
            code = data['code']
            email = data['email']

            # 使用默认配置连接到redis
            conn = get_redis_connection('default')
            check_code = conn.get(email)
            check_code = check_code.decode('utf-8')

            print(code, check_code)
            if int(code) != int(check_code):
                return APIResponse(errcode=1010, errmsg='验证码已过期或不正确')
            return APIResponse(errcode=0, errmsg='验证码校验通过')

        except BaseException as e:
            logger.error("校验验证码出现异常, 原因: %s" % str(traceback.format_exc()))
            print(traceback.format_exc())
            return APIResponse(errcode=1010, errmsg='验证码已过期或不正确')


class ResetPwdView(APIView):
    permission_classes = []
    authentication_classes = [CsrfExemptSessionAuthentication, ]

    def post(self, request, *args, **kwargs):
        """
        找回密码， 修改新密码
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        try:
            data = request.data
            conn = get_redis_connection('default')
            check_code = conn.get(data['username'])
            if check_code is not None:
                check_code = check_code.decode('utf-8')
                if int(data['code']) != int(check_code):
                    return APIResponse(errcode=1011, errmsg='验证码已过期或不正确')

                user = User.objects.get(email=data['username'])
                user.set_password(data['password'])
                user.save()
                logger.info("密码修改成功, data={%s}" % str(data))
                return APIResponse(errcode=0, errmsg='密码修改成功')

            return APIResponse(errcode=1011, errmsg='验证码已过期或不正确')

        except Exception as e:
            logger.error(str(e))
            logger.error('修改密码失败, 失败原因:%s' % str(traceback.format_exc()))
            return APIResponse(errcode=1012, errmsg='密码修改失败,请重试！')


class ChangePwdView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission, ]

    def post(self, request, *args, **kwargs):
        """
        修改密码
        :param request:
        :param args:
        :param kwargs:
        :return:
        """

        try:
            data = request.data
            email = data.get('email')
            password = data.get('password')
            # 修改密码时校验用户身份, 限制当前用户不能修改他人密码
            obj = User.objects.filter(email=request.user.email).values()
            if obj and request.user.email != email:
                return APIResponse(errcode=403, errmsg='无权限修改')

            if email is not None and password is not None:
                user = User.objects.get(email=email)
                user.set_password(password)
                user.save()
                logger.info("用户%s, 密码修改成功！" % str(request.user.name))
                return APIResponse(data={'msg': '密码修改成功'})
            return APIResponse(errcode=1012, errmsg='登录过期,请重新登录后再试！')

        except Exception as e:
            logger.error(str(e))
            logger.error('密码修改失败: %s' % str(traceback.format_exc()))
            return APIResponse(errcode=1012, errmsg='密码修改失败！')


class UserRoleView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission, ]

    def put(self, request, *args, **kwargs):
        """
        更新用户角色：既支持 roles 列表（Role.id），也支持 role（角色 key）
        """
        try:
            if not request.user.is_superuser:
                return APIResponse(errcode=403, errmsg='无权限分配角色')
            payload = request.data
            user_obj = User.objects.filter(id=payload['id']).first()
            if not user_obj:
                return APIResponse(errcode=404, errmsg='用户不存在')
            # 新方式：按角色 key（superadmin / lead / engineer）直接设定
            role_key = payload.get('role')
            if role_key:
                label = dict(User.ROLE_CHOICES).get(role_key)
                if not label:
                    return APIResponse(errcode=400, errmsg='未知角色：%s' % role_key)
                # 名额限制：超级管理员 1 人、交付主管 1 人（交付工程师不限）
                if role_key in ('superadmin', 'lead'):
                    others = User.objects.filter(role=role_key).exclude(id=user_obj.id)
                    if others.exists():
                        return APIResponse(errcode=400, errmsg='%s仅限 1 人，当前已有：%s'
                                           % (label, others.first().username))
                role_obj = Role.objects.filter(name=label).first()
                if not role_obj:
                    return APIResponse(errcode=400, errmsg='角色未初始化，请先执行 seed_roles')
                old_role = user_obj.role
                user_obj.role = role_key
                user_obj.roles.set([role_obj])
                user_obj.save(update_fields=['role'])
                try:
                    from apps.ops.views import record_audit
                    record_audit(getattr(request.user, 'name', None), 'role',
                                 resource='分配角色：%s' % user_obj.username,
                                 detail='%s → %s' % (old_role or '未分配', label))
                except Exception:
                    pass
                return APIResponse(data={'msg': '角色已更新为 %s' % label})
            # 兼容旧方式：roles 列表
            user_obj.roles.clear()
            user_obj.roles.add(*payload['roles'])
            user_obj.save()
            return APIResponse(data={'msg': '用户角色更新成功'})
        except Exception as e:
            logger.error('用户角色更新异常: %s' % str(traceback.format_exc()))
            return APIResponse(errcode=500, errmsg='用户角色更新异常！')


class AccountInfoView(APIView):
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission, ]

    def get(self, request, *args, **kwargs):
        """
        获取用户信息
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        try:
            if request.user.is_superuser:
                search_user = request.GET.get('search', None)
                if search_user:
                    paginator = MyPageNumberPagination()
                    query_user = User.objects.filter(
                        Q(username__contains=search_user) | Q(email__contains=search_user) | Q(
                            mobile__contains=search_user) | Q(name__contains=search_user) |
                        Q(department__contains=search_user) | Q(position__contains=search_user))
                    query_users = paginator.paginate_queryset(query_user, self.request, view=self)
                    ser = UserInfoSerializer(query_users, many=True)
                    page_ser = paginator.get_paginated_response(ser.data)
                    return APIResponse(data=page_ser.data)
                else:
                    query_user = User.objects.all()
                    paginator = MyPageNumberPagination()
                    query_users = paginator.paginate_queryset(query_user, self.request, view=self)
                    serializer_user_info = UserInfoSerializer(query_users, many=True)
                    page_ser = paginator.get_paginated_response(serializer_user_info.data)
                    return APIResponse(data=page_ser.data)

            else:
                query_user = User.objects.filter(name=request.user.name)
                paginator = MyPageNumberPagination()
                query_users = paginator.paginate_queryset(query_user, self.request, view=self)
                serializer_user_info = UserInfoSerializer(query_users, many=True)
                page_ser = paginator.get_paginated_response(serializer_user_info.data)
                return APIResponse(data=page_ser.data)

        except Exception as e:
            logger.error(str(e))
            logger.error("获取用户信息失败: %s" % str(traceback.format_exc()))
            return APIResponse(errcode=1010, errmsg='获取用户信息失败, 系统遇到未知错误!')

    def post(self, request, *args, **kwargs):
        """新增用户（仅超级管理员），角色受名额约束"""
        try:
            if not request.user.is_superuser:
                return APIResponse(errcode=403, errmsg='无权限新增用户')
            data = request.data
            username = (data.get('username') or '').strip()
            name = (data.get('name') or '').strip()
            password = data.get('password') or ''
            role_key = data.get('role') or 'engineer'
            if not username or not name:
                return APIResponse(errcode=400, errmsg='用户名和姓名不能为空')
            if len(password) < 6:
                return APIResponse(errcode=400, errmsg='密码至少 6 位')
            if User.objects.filter(username=username).exists():
                return APIResponse(errcode=400, errmsg='用户名已存在：%s' % username)
            label = dict(User.ROLE_CHOICES).get(role_key)
            if not label:
                return APIResponse(errcode=400, errmsg='未知角色：%s' % role_key)
            if role_key in ('superadmin', 'lead') and User.objects.filter(role=role_key).exists():
                return APIResponse(errcode=400, errmsg='%s仅限 1 人' % label)
            u = User(username=username, name=name, mobile=data.get('mobile') or '',
                     email=data.get('email') or '', department=data.get('department') or '',
                     role=role_key)
            u.set_password(password)
            u.save()
            role_obj = Role.objects.filter(name=label).first()
            if role_obj:
                u.roles.set([role_obj])
            try:
                from apps.ops.views import record_audit
                record_audit(getattr(request.user, 'name', None), 'create_user',
                             resource='新增用户：%s' % username, detail='角色：%s' % label)
            except Exception:
                pass
            return APIResponse(data={'id': u.id, 'username': u.username, 'role': role_key})
        except Exception as e:
            logger.error('新增用户异常: %s' % str(traceback.format_exc()))
            return APIResponse(errcode=500, errmsg='新增用户异常！')
    def put(self, request, *args, **kwargs):
        """禁用 / 启用用户登录"""
        if not request.user.is_superuser:
            return APIResponse(errcode=403, errmsg='无权限修改用户')
        try:
            data = request.data
            User.objects.filter(id=data['id']).update(is_active=data['is_active'])
            return APIResponse(data={'msg': '更新用户成功'})
        except Exception as e:
            logger.error('更新用户异常：%s' % str(traceback.format_exc()))
            return APIResponse(errcode=500, errmsg='更新用户异常！')

    def delete(self, request, *args, **kwargs):
        """
        删除用户
        :param request:
        :param args:
        :param kwargs:
        :return:
        """
        if not request.user.is_superuser:
            return APIResponse(errcode=403, errmsg='无权限删除！')
        try:
            user_id = request.query_params.get('id')
            if not user_id:
                return APIResponse(errcode=400, errmsg='缺少用户 id')
            target = User.objects.filter(id=user_id).first()
            if not target:
                return APIResponse(errcode=404, errmsg='用户不存在')
            if target.id == request.user.id:
                return APIResponse(errcode=400, errmsg='不能删除当前登录账号')
            if target.is_superuser and User.objects.filter(is_superuser=True).count() <= 1:
                return APIResponse(errcode=400, errmsg='至少保留一个超级管理员')
            username, role = target.username, target.role
            target.delete()
            try:
                from apps.ops.views import record_audit
                record_audit(getattr(request.user, 'name', None), 'delete_user',
                             resource='删除用户：%s' % username, detail='角色：%s' % (role or '未分配'))
            except Exception:
                pass
            return APIResponse(data={'msg': '删除用户成功'})
        except Exception as e:
            logger.error(str(e))
            logger.error('删除用户异常：%s' % str(traceback.format_exc()))
            return APIResponse(errcode=500, errmsg='删除用户异常！')


class UserResetPasswordView(APIView):
    """管理员重置用户密码（用户忘记密码 / 新用户首次登录）"""

    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def post(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            return APIResponse(errcode=403, errmsg='无权限重置密码')
        uid = request.data.get('id')
        password = str(request.data.get('password') or '')
        if not uid:
            return APIResponse(errcode=400, errmsg='缺少用户 id')
        if len(password) < 6:
            return APIResponse(errcode=400, errmsg='新密码至少 6 位')
        target = User.objects.filter(id=uid).first()
        if not target:
            return APIResponse(errcode=404, errmsg='用户不存在')
        target.set_password(password)
        target.save(update_fields=['password'])
        try:
            from apps.ops.views import record_audit
            record_audit(getattr(request.user, 'name', None), 'reset_password',
                         resource='重置密码：%s' % target.username, detail='管理员重置')
        except Exception:
            pass
        return APIResponse(data={'msg': '密码已重置'})


class UserProfileView(APIView):
    """个人设置：查看 / 修改当前用户资料与密码"""
    authentication_classes = [MyAuthentication]
    permission_classes = [MyPermission]

    def get(self, request, *args, **kwargs):
        u = request.user
        login_records = []
        try:
            from apps.ops.models import AuditLog
            for log in AuditLog.objects.filter(action='login', user=u.name).order_by('-id')[:5]:
                login_records.append({
                    'time': log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else '',
                    'ip': log.ip or '-',
                    'result': log.result or '成功',
                    'detail': log.detail or log.resource or '登录',
                })
        except Exception:
            login_records = []
        return APIResponse(data={
            'id': u.id, 'username': u.username, 'name': u.name or '',
            'email': u.email or '', 'mobile': u.mobile or '',
            'department': getattr(u, 'department', '') or '',
            'role': u.role or '',
            'role_label': u.get_role_display() if u.role else '',
            'is_superuser': bool(u.is_superuser),
            'login_records': login_records,
        })

    def post(self, request, *args, **kwargs):
        u = request.user
        data = request.data
        new_pwd = data.get('new_password')
        if new_pwd:
            old_pwd = data.get('old_password') or ''
            if not u.check_password(old_pwd):
                return APIResponse(errcode=4001, errmsg='原密码不正确')
            if len(str(new_pwd)) < 6:
                return APIResponse(errcode=4002, errmsg='新密码至少 6 位')
            u.set_password(new_pwd)
        if data.get('name') is not None:
            u.name = data.get('name')
        if data.get('email') is not None:
            u.email = data.get('email')
        if data.get('mobile') is not None:
            u.mobile = data.get('mobile')
        if data.get('department') is not None and hasattr(u, 'department'):
            u.department = data.get('department')
        u.save()
        return APIResponse(data={'msg': '保存成功'})
