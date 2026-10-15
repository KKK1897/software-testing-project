import hashlib
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from erp_client import ERP,BASE
from core_scenario import ok,bill_body,stock

def document(c,body):
    return ok(c.get('/depotHead/getDetailByNumber',number=json.loads(body['info'])['number']))['data']

def assert_document_absent(c,body):
    info=json.loads(body['info'])
    result=c.listing('depotHead',{'number':info['number'],'type':info['type'],'subType':info['subType']})
    assert result['total']==0 and result['rows']==[],result

def test_login_session(client):
    result=ok(client.get('/user/getUserSession'))
    assert result['data']['user']['loginName']=='jsh'
    assert result['data']['user'].get('password') is None

def test_logout_invalidates_token(client):
    client.get('/user/logout')
    r=client.session.get(BASE+'/user/getUserSession',timeout=10)
    assert r.status_code==500 and r.text=='loginOut'

def test_anonymous_cannot_read_stock():
    c=ERP();r=c.session.get(BASE+'/material/getListWithStock',timeout=10)
    assert r.status_code==500 and r.text=='loginOut'

def test_invalid_token_cannot_read():
    c=ERP();c.session.headers['X-Access-Token']='QA_INVALID_TOKEN'
    r=c.session.get(BASE+'/depot/list',timeout=10)
    assert r.status_code==500 and r.text=='loginOut'

@pytest.mark.parametrize('name,password,message',[('QA_NO_SUCH_ACCOUNT','123456','user is not exist'),('jsh','incorrect','user password error')])
def test_invalid_credentials(name,password,message):
    c=ERP();r=c.post('/user/login',dict(loginName=name,password=hashlib.md5(password.encode()).hexdigest(),**c.captcha()))
    assert r['code']==200 and r['data']['msgTip']==message and 'token' not in r['data']

@pytest.mark.parametrize('mode,code',[('missing',500012),('wrong',500010),('unknown_uuid',500011)])
def test_captcha_rejection(mode,code):
    c=ERP();captcha=c.captcha()
    if mode=='missing':captcha={}
    if mode=='wrong':captcha['code']='WRONG'
    if mode=='unknown_uuid':captcha['uuid']=uuid.uuid4().hex
    r=c.post('/user/login',dict(loginName='jsh',password=hashlib.md5(b'123456').hexdigest(),**captcha))
    assert r['code']==code,r
    assert 'token' not in json.dumps(r)

def test_captcha_single_use():
    c=ERP();payload=dict(loginName='jsh',password=hashlib.md5(b'123456').hexdigest(),**c.captcha())
    assert c.post('/user/login',payload)['data']['msgTip']=='user can login'
    assert c.post('/user/login',payload)['code']==500011

def test_depot_create_and_filter(client,data):
    rows=client.listing('depot',{'name':data['tag']})['rows']
    assert {r['id'] for r in rows}=={data['a'],data['b']}

def test_depot_pagination(client):
    first=client.listing('depot',page=1,size=1);second=client.listing('depot',page=2,size=1)
    assert len(first['rows'])==len(second['rows'])==1
    assert first['total']==second['total'] and first['rows'][0]['id']!=second['rows'][0]['id']

def test_empty_filter(client):
    r=client.listing('depot',{'name':'QA_ABSENT_'+uuid.uuid4().hex})
    assert r['total']==0 and r['rows']==[]

def test_stock_chain(client,data):
    for kind,qty,expected in [('采购',100,[100,0]),('调拨',30,[70,30]),('销售',10,[70,20])]:
        b=bill_body(data,kind,qty);ok(client.post('/depotHead/addDepotHeadAndDetail',b))
        assert [stock(client,data,data['a']),stock(client,data,data['b'])]==expected
        detail=document(client,b)
        assert detail['status']=='0' and detail['subType']==kind
    assert sum(expected)==90

def test_audit_and_reverse_do_not_double_count(client,data):
    b=bill_body(data,'采购',100);ok(client.post('/depotHead/addDepotHeadAndDetail',b));doc=document(client,b)
    for status in ['1','0']:
        ok(client.post('/depotHead/batchSetStatus',dict(ids=str(doc['id']),status=status)))
        assert document(client,b)['status']==status
        assert stock(client,data,data['a'])==100

def test_repeat_audit_rejected(client,data):
    b=bill_body(data,'采购',7);ok(client.post('/depotHead/addDepotHeadAndDetail',b));doc=document(client,b)
    ok(client.post('/depotHead/batchSetStatus',dict(ids=str(doc['id']),status='1')))
    assert client.post('/depotHead/batchSetStatus',dict(ids=str(doc['id']),status='1'))['code']==8500012
    assert stock(client,data,data['a'])==7

def test_duplicate_number_no_extra_stock(client,data):
    b=bill_body(data,'采购',9);ok(client.post('/depotHead/addDepotHeadAndDetail',b))
    assert client.post('/depotHead/addDepotHeadAndDetail',b)['code']==8500022
    assert stock(client,data,data['a'])==9

@pytest.mark.parametrize('mode,code',[('account',8500007),('barcode',8000026),('same_depot',8500010),('target_depot',8500005)])
def test_rejected_document_rolls_back(client,data,mode,code):
    b=bill_body(data,'采购' if mode in ['account','barcode'] else '调拨',10)
    info=json.loads(b['info']);rows=json.loads(b['rows'])
    if mode=='account':info.pop('accountId')
    if mode=='barcode':rows[0]['barCode']='QA_NOT_EXIST'
    if mode=='same_depot':rows[0]['anotherDepotId']=data['a']
    if mode=='target_depot':rows[0].pop('anotherDepotId')
    b=dict(info=json.dumps(info,ensure_ascii=False),rows=json.dumps(rows,ensure_ascii=False))
    assert client.post('/depotHead/addDepotHeadAndDetail',b)['code']==code
    assert_document_absent(client,b)
    assert stock(client,data,data['a'])==stock(client,data,data['b'])==0

def test_delete_draft_reverses_stock(client,data):
    b=bill_body(data,'采购',8);ok(client.post('/depotHead/addDepotHeadAndDetail',b));doc=document(client,b)
    ok(client.request('DELETE','/depotHead/delete',params={'id':doc['id']}))
    assert stock(client,data,data['a'])==0
    assert_document_absent(client,b)

def test_fractional_quantity_preserved(client,data):
    b=bill_body(data,'采购',0.125);ok(client.post('/depotHead/addDepotHeadAndDetail',b))
    assert stock(client,data,data['a'])==0.125

def test_concurrent_queries_consistent(client,data):
    b=bill_body(data,'采购',12);ok(client.post('/depotHead/addDepotHeadAndDetail',b))
    token=client.session.headers['X-Access-Token']
    def read(_):
        c=ERP();c.session.headers['X-Access-Token']=token
        return stock(c,data,data['a'])
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert list(pool.map(read,range(6)))==[12]*6

def test_insufficient_stock_when_disallowed(client,data):
    cfg=client.listing('systemConfig')['rows'][0];original=cfg['minusStockFlag']
    try:
        ok(client.request('PUT','/systemConfig/update',json={**cfg,'minusStockFlag':'0'}))
        b=bill_body(data,'销售',1)
        assert client.post('/depotHead/addDepotHeadAndDetail',b)['code']==8000004
        assert_document_absent(client,b)
        assert stock(client,data,data['b'])==0
    finally:
        ok(client.request('PUT','/systemConfig/update',json={**cfg,'minusStockFlag':original}))
