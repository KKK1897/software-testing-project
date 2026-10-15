"""Windows项目级部署，不安装服务、不修改全局配置、不重置已有数据。"""
import argparse,hashlib,json,os,shutil,socket,subprocess,sys,time,urllib.request,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SHA='7ca0f9d68fef761d98b00854d09e975eba291465'

def run(args,cwd=ROOT,env=None):
    subprocess.run([str(a) for a in args],cwd=cwd,env=env,check=True)

def mysql_binary():
    for p in [Path(r'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqld.exe'),ROOT/'tools/mysql-8.0.46-winx64/bin/mysqld.exe']:
        if p.exists() and '8.0.46' in subprocess.check_output([str(p),'--version'],text=True):return p
    raise RuntimeError('需要MySQL8.0.46便携程序；先运行bootstrap.py')

def download(url,path):
    if path.exists() and path.stat().st_size>0:return
    partial=path.with_suffix(path.suffix+'.partial')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url,timeout=120) as source,partial.open('wb') as dest:shutil.copyfileobj(source,dest)
    partial.replace(path)

def extract(url,archive,folder):
    if (ROOT/'tools'/folder).exists():return
    path=ROOT/'tools'/archive;download(url,path)
    with zipfile.ZipFile(path) as z:
        base=(ROOT/'tools').resolve()
        for name in z.namelist():
            assert (base/name).resolve().is_relative_to(base),'压缩包含越界路径'
        z.extractall(base)

def setup():
    if os.name!='nt':raise SystemExit('本部署脚本用于Windows；未声称Linux部署已经验证')
    if sys.version_info[:3]!=(3,13,2):raise SystemExit('请使用Python3.13.2运行，CI使用setup-python固定版本')
    for name in ['tools','runtime','artifacts','upstream']:(ROOT/name).mkdir(exist_ok=True)
    for port in [9999,19999]:
        probe=socket.socket();probe.settimeout(.5)
        try:
            if probe.connect_ex(('127.0.0.1',port))==0:
                raise RuntimeError('构建前请运行 scripts/stop_local.py 停止本项目服务，避免Windows锁定JAR')
        finally:probe.close()
    extract('https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u472-b08/OpenJDK8U-jdk_x64_windows_hotspot_8u472b08.zip','jdk8u472.zip','jdk8u472-b08')
    extract('https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.6.3/apache-maven-3.6.3-bin.zip','apache-maven-3.6.3-bin.zip','apache-maven-3.6.3')
    redis=ROOT/'tools/redis-3.2.100'
    if not redis.exists():
        archive=ROOT/'tools/redis-3.2.100.zip'
        download('https://github.com/microsoftarchive/redis/releases/download/win-3.2.100/Redis-x64-3.2.100.zip',archive)
        with zipfile.ZipFile(archive) as z:z.extractall(redis)
    try:mysql_binary()
    except RuntimeError:extract('https://cdn.mysql.com/Downloads/MySQL-8.0/mysql-8.0.46-winx64.zip','mysql-8.0.46.zip','mysql-8.0.46-winx64')
    extract('https://github.com/allure-framework/allure2/releases/download/2.32.0/allure-2.32.0.zip','allure-2.32.0.zip','allure-2.32.0')
    extract('https://dlcdn.apache.org/jmeter/binaries/apache-jmeter-5.6.3.zip','jmeter-cdn.zip','apache-jmeter-5.6.3')
    # Node可使用系统相同版本；不同版本时仅下载项目便携版。
    node=shutil.which('node')
    if not node or subprocess.check_output([node,'--version'],text=True).strip()!='v24.18.1':
        extract('https://nodejs.org/dist/v24.18.1/node-v24.18.1-win-x64.zip','node-v24.18.1.zip','node-v24.18.1-win-x64')
        node=str(ROOT/'tools/node-v24.18.1-win-x64/node.exe')
    env=os.environ.copy();env['JAVA_HOME']=str(ROOT/'tools/jdk8u472-b08');env['PATH']=str(Path(node).parent)+os.pathsep+env['PATH']
    env['NODE_OPTIONS']='--openssl-legacy-provider';env['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'tools/pw-browsers')
    upstream=ROOT/'upstream/jshERP'
    if not upstream.exists():run(['git','-c','http.proxy=','clone','--depth','1','--branch','v3.5','https://github.com/jishenghua/jshERP.git',upstream])
    actual=subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'],text=True).strip()
    assert actual==SHA,'上游SHA不匹配，拒绝部署'
    assert not subprocess.check_output(['git','-C',str(upstream),'diff','--name-only'],text=True).strip(),'上游存在受跟踪修改，拒绝覆盖'
    venv=ROOT/'.venv/Scripts/python.exe'
    if not venv.exists():run([sys.executable,'-m','venv',ROOT/'.venv'])
    run([venv,'-m','pip','install','--isolated','--index-url','https://pypi.org/simple','-r',ROOT/'requirements.lock.txt'])
    run([venv,'-m','playwright','install','chromium'],env=env)
    if not shutil.which('pwsh'):raise RuntimeError('需要PowerShell7（pwsh），避免Windows PowerShell5对UTF-8脚本误读')
    run(['pwsh','-NoProfile','-File',ROOT/'scripts/build_backend.ps1'],env=env)
    web=upstream/'jshERP-web';shutil.copyfile(ROOT/'locks/frontend-package-lock.json',web/'package-lock.json')
    npm=Path(node).parent/'npm.cmd'
    run([npm,'ci','--legacy-peer-deps','--ignore-scripts','--no-audit','--no-fund','--registry=https://registry.npmjs.org',f'--cache={ROOT}/tools/npm-cache'],cwd=web,env=env)
    run([npm,'run','build'],cwd=web,env=env)
    if not (ROOT/'runtime/local.json').exists():
        from start_local import listening
        if listening(13306):raise RuntimeError('13306 已被占用；拒绝初始化或连接不明数据库')
        datadir=ROOT/'runtime/mysql-data'
        if datadir.exists():raise RuntimeError('存在数据目录但没有配置，拒绝覆盖/重新初始化')
        binary=mysql_binary()
        run([binary,'--no-defaults','--initialize-insecure',f'--datadir={datadir}','--console'])
        with (ROOT/'artifacts/bootstrap-mysql.log').open('w') as log:
            p=subprocess.Popen([str(binary),'--no-defaults','--console',f'--datadir={datadir}','--port=13306','--bind-address=127.0.0.1','--mysqlx=OFF','--default-authentication-plugin=mysql_native_password'],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        (ROOT/'runtime/mysql.pid').write_text(str(p.pid))
        from start_local import wait,listening
        wait(lambda:listening(13306))
        run([venv,ROOT/'scripts/init_local.py'],env=env)
    run([venv,ROOT/'scripts/start_local.py'],env=env)
    run([venv,ROOT/'scripts/prepare_identities.py'],env=env)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'tools').glob('*.zip') if p.stat().st_size>0}
    (ROOT/'artifacts/download-sha256.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print('本机部署与登录验收完成；下载哈希已记录。')

if __name__=='__main__':setup()
