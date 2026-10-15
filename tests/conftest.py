import json
import pytest
import allure
from erp_client import ERP,ROOT,HISTORY
from core_scenario import create_data
from execution_lock import execution_lock

def pytest_addoption(parser):
    parser.addoption('--cleanup-passed',action='store_true',help='通过的业务用例按manifest清理；失败数据留存')

@pytest.fixture(scope='session',autouse=True)
def exclusive_environment():
    with execution_lock():yield

@pytest.fixture(autouse=True)
def evidence(request):
    HISTORY.clear()
    yield
    text=json.dumps(HISTORY,ensure_ascii=False,indent=2)
    allure.attach(text,'脱敏接口请求响应',allure.attachment_type.JSON)
    out=ROOT/'artifacts/request-evidence';out.mkdir(exist_ok=True)
    safe=''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in request.node.name)
    (out/(safe+'.json')).write_text(text,encoding='utf-8')

@pytest.fixture
def client():
    c=ERP();c.login()
    yield c
    c.session.close()

@pytest.fixture
def data(client,request):
    d=create_data(client)
    (ROOT/'artifacts/data-manifests').mkdir(exist_ok=True)
    (ROOT/'artifacts/data-manifests'/f'{d["tag"]}.json').write_text(json.dumps(dict(test=request.node.nodeid,**d),ensure_ascii=False,indent=2),encoding='utf-8')
    # 留存独立数据用于失败定位；受保护清理脚本按 manifest 精确回收。
    yield d
    if request.config.getoption('--cleanup-passed') and getattr(request.node,'rep_call',None) and request.node.rep_call.passed:
        from cleanup_data import cleanup
        cleanup(ROOT/'artifacts/data-manifests'/f'{d["tag"]}.json')

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    outcome=yield
    report=outcome.get_result()
    setattr(item,'rep_'+report.when,report)
