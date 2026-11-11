# -*- coding: utf-8 -*-
import requests, websocket

# 1. 登录拿 token
r = requests.post('http://127.0.0.1:8000/api/account/v1/user/login',
                  json={'username': 'admin', 'password': 'admin123456'}, timeout=10)
data = r.json()
token = data['data']['token']
print('token obtained:', bool(token))

# 2. WebSocket 握手（经 nginx 反代）
url = 'ws://127.0.0.1:8080/ws/pod/default/testpod/80/24?token=' + token
print('connecting:', url)
try:
    ws = websocket.create_connection(url, timeout=10)
    print('WS HANDSHAKE OK, http status:', ws.getstatus())
    ws.close()
except Exception as e:
    print('WS result:', type(e).__name__, '-', str(e)[:300])
