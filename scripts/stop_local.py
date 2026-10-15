"""仅停止命令行明确指向本项目的进程；不使用系统服务控制。"""
import json,time
import psutil
from erp_client import ROOT

def stop():
    root=str(ROOT.resolve()).replace('\\','/').lower()
    owned=[]
    for p in psutil.process_iter(['pid','name','cmdline']):
        try:
            command=' '.join(p.info['cmdline'] or []).replace('\\','/').lower()
            if root in command and p.info['name'].lower() in ('java.exe','mysqld.exe','redis-server.exe','python.exe'):
                if any(tag in command for tag in ('/runtime/mysql-data','/runtime/redis.conf','/target/jsherp.jar','/scripts/serve_frontend.py')):
                    owned.append(p)
        except (psutil.AccessDenied,psutil.NoSuchProcess):continue
    report=[]
    for p in owned:
        try:
            report.append({'pid':p.pid,'name':p.name(),'action':'terminate-project-process'})
            p.terminate()
        except psutil.NoSuchProcess:pass
    _,alive=psutil.wait_procs(owned,timeout=15)
    (ROOT/'artifacts/stop-services.json').write_text(json.dumps({'stopped':report,'remaining':[p.pid for p in alive]},indent=2),encoding='utf-8')
    if alive:raise RuntimeError('部分项目进程未退出，未强制杀死其它进程')
    print('项目进程已停止，保留所有数据；MySQL下次启动可能执行崩溃恢复。')
if __name__=='__main__':stop()
