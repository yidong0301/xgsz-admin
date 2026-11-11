import json
import urllib.request

def post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))

def get(url, token):
    req = urllib.request.Request(url, headers={'Authorization': 'JWT ' + token})
    return json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))

r = post('http://localhost:8080/api/account/v1/user/login', {'username': 'admin', 'password': 'admin123456'})
token = r['data']['token']
a = get('http://localhost:8080/api/account/v1/alerts', token)
for x in a['data']['alerts']:
    print(x['title'], '|', x['detail'], '|', x['time'])
