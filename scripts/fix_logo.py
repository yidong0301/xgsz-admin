# -*- coding: utf-8 -*-
import re, io
p = r'D:\WDXMGZ\xgsz-admin-web\app.html'
c = io.open(p, encoding='utf-8').read()
new, n = re.subn(r'<img[^>]*>', '<div class="brand-mark">芯</div>', c, count=1)
print('replaced:', n)
if n:
    io.open(p, 'w', encoding='utf-8').write(new)
    print('saved')
