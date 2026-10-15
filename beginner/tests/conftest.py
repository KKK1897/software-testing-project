import json
import uuid
from pathlib import Path

import allure
import pytest

from helpers.api_client import ERP, HISTORY, OUTPUT, ROOT, redact
from helpers.inventory_data import create_data
from execution_lock import execution_lock


def pytest_addoption(parser):
    parser.addoption('--cleanup-passed', action='store_true', help='定向清理通过的库存用例，失败保留')
    # --headed由已安装的pytest-playwright提供，直接复用。


@pytest.fixture(scope='session', autouse=True)
def exclusive_environment():
    """复用旧环境的文件锁，防止功能测试与性能/清理任务重叠。"""
    with execution_lock():
        yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, 'rep_' + call.when, outcome.get_result())


@pytest.fixture(autouse=True)
def evidence(request):
    """每次独立保存脱敏请求；失败数据不自动删除。"""
    HISTORY.clear()
    yield
    text = json.dumps(redact(HISTORY), ensure_ascii=False, indent=2)
    allure.attach(text, '脱敏接口请求响应', allure.attachment_type.JSON)
    directory = OUTPUT / 'requests'
    directory.mkdir(parents=True, exist_ok=True)
    filename = request.node.name + '-' + uuid.uuid4().hex[:8] + '.json'
    (directory / filename).write_text(text, encoding='utf-8')


@pytest.fixture
def client():
    with ERP() as api:
        api.login()
        yield api


@pytest.fixture
def data(client, request):
    """每条库存用例独立建两仓一商品；manifest兼容原安全清理脚本。"""
    dataset = create_data(client)
    path = dataset.pop('_manifest')
    record = dict(test=request.node.nodeid, **dataset)
    Path(path).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    allure.attach(json.dumps(record, ensure_ascii=False), '测试标识与数据归属', allure.attachment_type.JSON)
    yield dataset
    result = getattr(request.node, 'rep_call', None)
    if request.config.getoption('--cleanup-passed') and result and result.passed:
        from cleanup_data import cleanup
        cleanup(path)


@pytest.fixture
def settlement_data(client, request):
    """进阶链路使用自有往来单位和账户；失败留存，成功可定向清理。"""
    from helpers.settlement_data import create_settlement_data
    dataset = create_settlement_data(client, request.node.nodeid)
    path = ROOT / 'artifacts/data-manifests' / (dataset['tag'] + '.json')
    allure.attach(json.dumps(dataset, ensure_ascii=False), '结算链路数据归属', allure.attachment_type.JSON)
    yield dataset
    result = getattr(request.node, 'rep_call', None)
    if request.config.getoption('--cleanup-passed') and result and result.passed:
        from cleanup_data import cleanup
        cleanup(path)
