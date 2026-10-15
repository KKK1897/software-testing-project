import hashlib
import os
import json
import socket
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv('ERP_BASE_URL','http://127.0.0.1:9999/jshERP-boot')
assert BASE in ('http://127.0.0.1:9999/jshERP-boot','http://127.0.0.1:19999/jshERP-boot'),'只允许本机基线/补丁测试端口'
_last_write = 0.0
HISTORY=[]

def redact(value):
    if isinstance(value,dict):
        return {k:('[REDACTED]' if any(word in k.lower() for word in ('password','token','cookie','secret','phonenum','telephone','email','base64')) else redact(v)) for k,v in value.items()}
    if isinstance(value,list):return [redact(v) for v in value]
    return value

def redis_read(key):
    """只读本机验证码，RESP 客户端不暴露通用写命令。"""
    password = json.loads((ROOT/'runtime/local.json').read_text())['redis_password']
    def send(sock, *args):
        payload = b'*'+str(len(args)).encode()+b'\r\n'
        for arg in args:
            raw=arg.encode()
            payload += b'$'+str(len(raw)).encode()+b'\r\n'+raw+b'\r\n'
        sock.sendall(payload)
    with socket.create_connection(('127.0.0.1',16379), timeout=5) as sock:
        f=sock.makefile('rb')
        send(sock,'AUTH',password)
        assert f.readline()==b'+OK\r\n'
        send(sock,'GET',key)
        header=f.readline()
        assert header.startswith(b'$') and header!=b'$-1\r\n', header
        return f.read(int(header[1:-2])).decode().strip('"')

class ERP:
    def __init__(self):
        self.session=requests.Session()
        self.session.trust_env=False
        # ResourceController同时声明javascript/json；异常DTO需要JSON协商。
        self.session.headers['Accept']='application/json'
    def request(self, method, path, **kwargs):
        global _last_write
        # LogService 同秒重复写入会注销会话。显式负载节奏，不是失败重试。
        if method in ('POST','PUT','DELETE'):
            # MySQL 无小数位时间列会四舍五入到下一秒，留出跨秒边界。
            remaining = 2.1-(time.monotonic()-_last_write)
            if remaining > 0:
                time.sleep(remaining)
            _last_write=time.monotonic()
        response=self.session.request(method,BASE+path,timeout=(5,25),**kwargs)
        try:response_body=response.json()
        except ValueError:response_body=response.text[:4000]
        HISTORY.append(redact({'method':method,'path':path,'request':kwargs,'http_status':response.status_code,'response':response_body}))
        if response.status_code>=400:
            record={'method':method,'path':path,'status':response.status_code,
                    'request_headers':{k:v for k,v in response.request.headers.items() if k.lower() not in ('x-access-token','cookie','authorization')},
                    'response_headers':dict(response.headers),'response':response.text[:4000]}
            (ROOT/'artifacts/last-http-error.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        response.raise_for_status()
        return response.json()
    def get(self,path,**params):
        return self.request('GET',path,params=params)
    def post(self,path,body):
        return self.request('POST',path,json=body)
    def captcha(self):
        data=self.get('/user/randomImage')['data']
        return {'uuid':data['uuid'],'code':redis_read('captcha_codes:'+data['uuid'])}
    def login(self, name='jsh', password='123456'):
        data=self.post('/user/login',dict(loginName=name,password=hashlib.md5(password.encode()).hexdigest(),**self.captcha()))
        assert data['code']==200 and data['data']['msgTip']=='user can login',data
        self.session.headers['X-Access-Token']=data['data']['token']
        return data
    def listing(self,kind,search=None, page=1,size=100):
        data=self.get('/'+kind+'/list',search=json.dumps(search or {},ensure_ascii=False),currentPage=page,pageSize=size)
        assert data['code']==200,data
        return data['data']

if __name__=='__main__':
    client=ERP()
    result=client.login()
    print('LOGIN',result['data']['msgTip'])
    for kind in ['depot','account','supplier','systemConfig','material','role']:
        print(kind,json.dumps(client.listing(kind),ensure_ascii=False))
