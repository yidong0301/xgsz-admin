# -*- coding: utf-8 -*-
import io
p = r'D:\WDXMGZ\xgsz-admin-web\app.html'
c = io.open(p, encoding='utf-8').read()
i = c.find('class="brand"')
print('index:', i)
print(repr(c[i-30:i+320]))
