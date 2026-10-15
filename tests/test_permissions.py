import json,uuid
from erp_client import ERP,ROOT,BASE

def test_readonly_cannot_create_depot(client):
    identities=json.loads((ROOT/'runtime/identities.json').read_text(encoding='utf-8'))
    low=ERP();low.login(identities['readonly']['loginName'])
    name='QA_DENIED_'+uuid.uuid4().hex[:10]
    response=low.post('/depot/add',dict(name=name,sort='99'))
    found=client.listing('depot',{'name':name})
    evidence={'identity':identities['readonly'],'request':{'path':'/depot/add','body':{'name':name,'sort':'99'}},'response':response,'verification':found}
    (ROOT/'artifacts/readonly-create-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    assert found['total']==0 and found['rows']==[], '只读角色通过后端新增了仓库，详见 readonly-create-evidence.json'
    assert response['code'] in (401,403), response

def test_operator_can_create_depot(client):
    identities=json.loads((ROOT/'runtime/identities.json').read_text(encoding='utf-8'))
    operator=ERP();operator.login(identities['operator']['loginName'])
    name='QA_OP_'+uuid.uuid4().hex[:10]
    response=operator.post('/depot/add',dict(name=name,sort='99'))
    assert response['code']==200
    assert client.listing('depot',{'name':name})['total']==1

def test_missing_document_returns_empty_success(client):
    number='QA_ABSENT_'+uuid.uuid4().hex
    response=client.get('/depotHead/getDetailByNumber',number=number)
    (ROOT/'artifacts/missing-document-evidence.json').write_text(json.dumps({'number':number,'response':response},ensure_ascii=False,indent=2),encoding='utf-8')
    # Controller 明确初始化空 DTO；Service 空列表异常破坏该响应合同。
    assert response['code']==200 and response['data'].get('id') is None,response
