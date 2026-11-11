# -*- coding: utf-8 -*-
"""给 k8s 视图的模块级 load_kube_config 加 try/except，避免无 kubeconfig 时整个 URL 配置崩溃"""
import re, io

files = [
    r'D:\WDXMGZ\xgsz-admin\apps\k8s\views\cluster.py',
    r'D:\WDXMGZ\xgsz-admin\apps\k8s\views\deployment.py',
    r'D:\WDXMGZ\xgsz-admin\apps\k8s\views\namespace.py',
    r'D:\WDXMGZ\xgsz-admin\apps\k8s\views\pod.py',
    r'D:\WDXMGZ\xgsz-admin\apps\k8s\views\node.py',
    r'D:\WDXMGZ\xgsz-admin\apps\k8s\views\events.py',
    r'D:\WDXMGZ\xgsz-admin\apps\k8s\views\scale.py',
]

# 匹配独立一行的 config.load_kube_config(...)
pattern = re.compile(r'^([ \t]*)config\.load_kube_config\([^)]*\)[ \t]*$', re.MULTILINE)

for fp in files:
    with io.open(fp, 'r', encoding='utf-8') as f:
        c = f.read()
    def repl(m):
        indent = m.group(1)
        call = m.group(0).strip()
        return ('%stry:\n%s    %s\nexcept Exception:\n%s    pass'
                % (indent, indent, call, indent))
    new_c, n = pattern.subn(repl, c)
    with io.open(fp, 'w', encoding='utf-8') as f:
        f.write(new_c)
    print('%s: 替换 %d 处' % (fp.split('\\')[-1], n))
print('done')
