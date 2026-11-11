# -*- coding: utf-8 -*-
import io, re
p = r'D:\WDXMGZ\xgsz-admin-web\app.html'
c = io.open(p, encoding='utf-8').read()
i = c.find('<img src="data:image/png;base64,')
print('img start:', i)
if i >= 0:
    j = c.find('>', i)
    print('img end (first > after):', j)
    print('last chars:', repr(c[j-20:j+5]))
    print('tag length:', j - i + 1)
# try regex
m = re.search(r'<img[^>]*>', c)
print('regex match:', repr(m.group(0)[:60]) if m else None)
