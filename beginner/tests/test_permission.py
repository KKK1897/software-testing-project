import json
import uuid

from helpers.api_client import ERP, ROOT


def test_operator_can_create_depot(client):
    identities = json.loads((ROOT / 'runtime/identities.json').read_text(encoding='utf-8'))
    # 短名称避免超过仓库name字段20字符限制，默认留存供页面复查。
    name = 'QA_OP_' + uuid.uuid4().hex[:10]
    with ERP() as operator:
        operator.login(identities['operator']['loginName'])
        response = operator.post('/depot/add', {'name': name, 'sort': '99'})
        assert response['code'] == 200, response
    found = client.listing('depot', {'name': name})
    assert found['total'] == 1
    assert found['rows'][0]['name'] == name


def test_readonly_cannot_create_depot(client):
    identities = json.loads((ROOT / 'runtime/identities.json').read_text(encoding='utf-8'))
    name = 'QA_DEN_' + uuid.uuid4().hex[:10]
    with ERP() as readonly:
        readonly.login(identities['readonly']['loginName'])
        response = readonly.request('POST', '/depot/add', json={'name': name, 'sort': '99'})
    found = client.listing('depot', {'name': name})
    # 先核对真实副作用；任何HTTP错误都不能代替授权拒绝和零新增。
    assert found['total'] == 0 and found['rows'] == [], 'DEF-002：只读用户实际创建仓库，失败现场保留'
    body = response.json()
    assert response.status_code in (200, 401, 403), response.status_code
    assert body['code'] in (401, 403), body


def test_missing_document_returns_empty_success(client):
    number = 'QA_ABSENT_' + uuid.uuid4().hex
    response = client.get('/depotHead/getDetailByNumber', number=number)
    # Controller空DTO合同：不存在应返回空记录，业务500仍是缺陷。
    assert response['code'] == 200 and response['data'].get('id') is None, response
