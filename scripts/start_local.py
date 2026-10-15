"""启动既有隔离环境；绝不初始化/重置已有数据库。"""
import json,os,socket,subprocess,time
from pathlib import Path
import requests
from erp_client import ROOT,ERP

def listening(port):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=1):return True
    except OSError:return False

def wait(condition,seconds=45):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            if condition():return
        except (OSError,requests.RequestException,AssertionError,KeyError):pass
        time.sleep(.3)
    raise RuntimeError('服务未在限定时间内就绪，请检查本次启动日志')

def start():
    assert (ROOT/'runtime/local.json').exists(),'先执行 init_local.py'
    stamp=time.strftime('%Y%m%d-%H%M%S')
    java=ROOT/'tools/jdk8u472-b08/bin/java.exe'
    from bootstrap import mysql_binary
    services=[('mysql',13306,[str(mysql_binary()),'--no-defaults','--console',f'--datadir={ROOT.as_posix()}/runtime/mysql-data','--port=13306','--bind-address=127.0.0.1','--mysqlx=OFF','--default-authentication-plugin=mysql_native_password']),
              ('redis',16379,[str(ROOT/'tools/redis-3.2.100/redis-server.exe'),str(ROOT/'runtime/redis.conf')]),
              ('backend',9999,[str(java),'-Xms128m','-Xmx768m','-jar',str(ROOT/'upstream/jshERP/jshERP-boot/target/jshERP.jar'),f'--spring.config.additional-location=file:{ROOT.as_posix()}/runtime/application.properties']),
              ('frontend',3000,[str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'scripts/serve_frontend.py')])]
    for name,port,args in services:
        if not listening(port):
            with (ROOT/f'artifacts/start-{stamp}-{name}.log').open('w') as log:
                proc=subprocess.Popen(args,cwd=ROOT/'runtime',stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            (ROOT/f'runtime/{name}.pid').write_text(str(proc.pid))
            wait(lambda:listening(port))
        print(f'{name}: 127.0.0.1:{port}',flush=True)
    c=ERP()
    wait(lambda:c.login()['data']['msgTip']=='user can login')
    assert c.get('/user/getUserSession')['data']['user']['loginName']=='jsh'
    assert c.listing('material')['total']>=0
    r=requests.get('http://127.0.0.1:3000',timeout=10)
    assert r.status_code==200 and '<script' in r.text
    print('登录、会话、商品查询和前端入口健康验收通过')
if __name__=='__main__':start()
