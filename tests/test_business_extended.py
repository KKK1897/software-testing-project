import hashlib,json,uuid
from concurrent.futures import ThreadPoolExecutor
from erp_client import ERP,ROOT,BASE,redact
from core_scenario import ok,bill_body,stock

def detail(c,b):
    return ok(c.get('/depotHead/getDetailByNumber',number=json.loads(b['info'])['number']))['data']

def test_disabled_account_login_and_restore(client):
    identity=json.loads((ROOT/'runtime/identities.json').read_text(encoding='utf-8'))['operator']
    try:
        ok(client.post('/user/batchSetStatus',{'ids':str(identity['userId']),'status':2}))
        c=ERP()
        r=c.post('/user/login',dict(loginName=identity['loginName'],password=hashlib.md5(b'123456').hexdigest(),**c.captcha()))
        assert r['code']==200 and r['data']['msgTip']=='user is black' and 'token' not in r['data']
    finally:
        ok(client.post('/user/batchSetStatus',{'ids':str(identity['userId']),'status':0}))
    assert ERP().login(identity['loginName'])['data']['msgTip']=='user can login'

def test_draft_update_recalculates_stock(client,data):
    b=bill_body(data,'采购',5);ok(client.post('/depotHead/addDepotHeadAndDetail',b))
    before=detail(client,b)
    changed=bill_body(data,'采购',8,number=before['number'])
    info=json.loads(changed['info']);info['id']=before['id'];changed['info']=json.dumps(info,ensure_ascii=False)
    ok(client.request('PUT','/depotHead/updateDepotHeadAndDetail',json=changed))
    assert stock(client,data,data['a'])==8
    assert detail(client,b)['id']==before['id']

def test_audited_update_rejected(client,data):
    b=bill_body(data,'采购',5);ok(client.post('/depotHead/addDepotHeadAndDetail',b));before=detail(client,b)
    ok(client.post('/depotHead/batchSetStatus',{'ids':str(before['id']),'status':'1'}))
    changed=bill_body(data,'采购',8,number=before['number'])
    info=json.loads(changed['info']);info['id']=before['id'];changed['info']=json.dumps(info,ensure_ascii=False)
    r=client.request('PUT','/depotHead/updateDepotHeadAndDetail',json=changed)
    assert r['code']==8500023 and stock(client,data,data['a'])==5

def test_audited_delete_rejected(client,data):
    b=bill_body(data,'采购',5);ok(client.post('/depotHead/addDepotHeadAndDetail',b));before=detail(client,b)
    ok(client.post('/depotHead/batchSetStatus',{'ids':str(before['id']),'status':'1'}))
    r=client.request('DELETE','/depotHead/delete',params={'id':before['id']})
    assert r['code']==8500011 and stock(client,data,data['a'])==5
    assert detail(client,b)['status']=='1'

def test_force_approval_stock_timing(client,data):
    cfg=client.listing('systemConfig')['rows'][0]
    try:
        ok(client.request('PUT','/systemConfig/update',json={**cfg,'forceApprovalFlag':'1'}))
        b=bill_body(data,'采购',11);ok(client.post('/depotHead/addDepotHeadAndDetail',b));doc=detail(client,b)
        assert stock(client,data,data['a'])==0
        ok(client.post('/depotHead/batchSetStatus',{'ids':str(doc['id']),'status':'1'}))
        assert stock(client,data,data['a'])==11
        ok(client.post('/depotHead/batchSetStatus',{'ids':str(doc['id']),'status':'0'}))
        assert stock(client,data,data['a'])==0
    finally:
        ok(client.request('PUT','/systemConfig/update',json=cfg))

def test_supplier_create_update_query(client):
    name='QA_SUP_'+uuid.uuid4().hex[:8]
    ok(client.post('/supplier/add',{'supplier':name,'type':'供应商','contacts':'测试联系人'}))
    rows=client.listing('supplier',{'supplier':name,'type':'供应商'})['rows']
    row=next(r for r in rows if r['supplier']==name)
    try:
        ok(client.request('PUT','/supplier/update',json={**row,'contacts':'更新联系人'}))
        found=ok(client.get('/supplier/info',id=row['id']))['data']['info']
        assert found['contacts']=='更新联系人'
    finally:
        ok(client.request('DELETE','/supplier/delete',params={'id':row['id']}))
    assert not any(r['supplier']==name for r in client.listing('supplier',{'supplier':name,'type':'供应商'})['rows'])

def test_concurrent_duplicate_document_integrity(client,data):
    b=bill_body(data,'采购',3)
    token=client.session.headers['X-Access-Token']
    def send(_):
        c=ERP();c.session.headers['X-Access-Token']=token
        r=c.session.post(BASE+'/depotHead/addDepotHeadAndDetail',json=b,timeout=(5,25))
        try:body=r.json()
        except ValueError:body=r.text
        return {'http':r.status_code,'body':body}
    # 刻意并发同一单号；不经普通写入节奏，不进行失败重试。
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(send,range(2)))
    # 并发日志规则可能使原Token失效；明确建立观察者身份验证已提交结果。
    observer=ERP();observer.login()
    info=json.loads(b['info'])
    listing=observer.listing('depotHead',{'number':info['number'],'type':'入库','subType':'采购'})
    current=stock(observer,data,data['a'])
    evidence={'request':b,'responses':responses,'documents':listing,'stock':current}
    (ROOT/'artifacts/concurrent-duplicate-evidence.json').write_text(json.dumps(redact(evidence),ensure_ascii=False,indent=2),encoding='utf-8')
    assert listing['total']==1 and current==3,evidence
    assert sorted(r['body'].get('code') for r in responses if isinstance(r['body'],dict))==[200,8500022],responses
