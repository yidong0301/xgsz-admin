#!/bin/env python3
# -*- coding: utf-8 -*-

# Copyright: (c) SmallFlyingPigs Organization. https://github.com/small-flying-pigs
# Copyright: (c) <pigs@dnsjia.com>
# Released under the AGPL-3.0 License.

"""
ASGI config for xgsz-admin project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xgsz_admin.settings')

# Initialize Django early so the AppRegistry is populated before importing channels/consumers
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.conf.urls import url
from django.urls import re_path, path

from consumer.webssh import SSHConsumer
from consumer.ecs_webssh import EcsSSHConsumer
from consumer.application import AppDiagnosisConsumer
from utils.ws_auth import QueryAuthMiddleware, TokenAuthMiddlewareStack


application = ProtocolTypeRouter({
    "http": django_asgi_app,
    # Just HTTP for now. (We can add other protocols later.)

    'websocket': TokenAuthMiddlewareStack(
        URLRouter([
            url(r'^ws/pod/(?P<ns>\w+.*)/(?P<pod_name>\w+.*)/(?P<cols>\d+.*)/(?P<rows>\d+.*)', SSHConsumer.as_asgi()),
            url(r'^ws/ecs/webssh/(?P<ecs_id>\w+.*)/(?P<cols>\d+.*)/(?P<rows>\d+.*)', EcsSSHConsumer.as_asgi()),
            url(r'^ws/application/diagnosis/(?P<agentId>\w+.*)$', AppDiagnosisConsumer.as_asgi()),
        ])
    )

})
# application = get_asgi_application()
