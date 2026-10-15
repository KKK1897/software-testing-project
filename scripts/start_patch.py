"""编译并启动 DEF-001 隔离补丁；不覆盖上游源码或原始后端。"""
import os,subprocess,time
from erp_client import ROOT,ERP
from start_local import listening,wait

def start():
    if listening(19999):raise RuntimeError('19999 已占用；拒绝重建运行中的补丁')
    target=ROOT/'runtime/patched-boot'
    if not target.exists():
        subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'scripts/prepare_patch.py')],check=True)
    relative='src/main/java/com/jsh/erp/service/depotHead/DepotHeadService.java'
    original=(ROOT/'upstream/jshERP/jshERP-boot'/relative).read_text(encoding='utf-8')
    point=original.index('public List<DepotHeadVo4List> getDetailByNumber(')
    expected=original[:point]+original[point:].replace('if (null != list) {','if (null != list && !list.isEmpty()) {',1)
    assert (target/relative).read_text(encoding='utf-8')==expected,'补丁源与限定修复不一致'
    env=os.environ.copy();env['JAVA_HOME']=str(ROOT/'tools/jdk8u472-b08')
    subprocess.run([str(ROOT/'tools/apache-maven-3.6.3/bin/mvn.cmd'),'-B','-s',str(ROOT/'scripts/maven-settings.xml'),'-f',str(target/'pom.qa.xml'),f'-Dmaven.repo.local={ROOT}/tools/m2','-DskipTests','package'],env=env,check=True)
    with (ROOT/f'artifacts/patch-start-{int(time.time())}.log').open('w') as log:
        process=subprocess.Popen([str(ROOT/'tools/jdk8u472-b08/bin/java.exe'),'-Xms128m','-Xmx768m','-jar',str(target/'target/jshERP.jar'),f'--spring.config.additional-location=file:{ROOT.as_posix()}/runtime/application.properties','--server.port=19999'],cwd=ROOT/'runtime',stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    (ROOT/'runtime/patched-backend.pid').write_text(str(process.pid))
    wait(lambda:listening(19999))
    print('隔离补丁端口19999已监听；需执行回归验证业务，不以监听视为验收成功。')

if __name__=='__main__':start()
