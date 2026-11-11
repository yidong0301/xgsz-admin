# -*- coding: utf-8 -*-
import io

p = r'D:\WDXMGZ\xgsz-admin-web\app.html'
c = io.open(p, encoding='utf-8').read()

reps = [
    ('<title>\u82af\u5149\u6570\u667a \u00b7 \u667a\u80fd\u8fd0\u7ef4\u5e73\u53f0</title>',
     '<title>\u82af\u5149\u6570\u667a \u00b7 \u4ea4\u4ed8\u5e73\u53f0\uff08xgsz-admin\uff09</title>'),
    ('<div class="lc-sub">\u667a\u80fd\u8fd0\u7ef4\u5e73\u53f0</div>',
     '<div class="lc-sub">\u4ea4\u4ed8\u5e73\u53f0 \u00b7 CMDB / CI-CD / \u8fd0\u7ef4\u7ba1\u7406</div>'),
]

for a, b in reps:
    if a in c:
        c = c.replace(a, b)
        print('replaced:', a[:30])
    else:
        print('NOT FOUND:', a[:30])

io.open(p, 'w', encoding='utf-8').write(c)
print('done')
