# -*- coding: utf-8 -*-
"""生成容器内可用的 kubeconfig：127.0.0.1 -> host.docker.internal，跳过 TLS 校验"""
import re, io, os
src = os.path.expandvars(r'%USERPROFILE%\.kube\config')
dst_dir = r'D:\WDXMGZ\kube'
os.makedirs(dst_dir, exist_ok=True)
dst = os.path.join(dst_dir, 'config')
c = io.open(src, encoding='utf-8').read()
c = c.replace('127.0.0.1', 'host.docker.internal')
c = re.sub(r'^\s*certificate-authority-data:.*$', '    insecure-skip-tls-verify: true', c, flags=re.MULTILINE)
io.open(dst, 'w', encoding='utf-8', newline='\n').write(c)
print('saved:', dst)
print('host.docker.internal count:', c.count('host.docker.internal'))
print('insecure count:', c.count('insecure-skip-tls-verify'))
