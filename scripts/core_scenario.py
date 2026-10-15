import json
import uuid
from datetime import datetime
from erp_client import ERP, ROOT

def ok(response):
    assert response['code']==200,response
    return response

def create_data(client):
    tag='QA_'+uuid.uuid4().hex[:12]
    directory=ROOT/'artifacts/data-manifests';directory.mkdir(exist_ok=True)
    path=directory/f'{tag}.json'
    progress={'tag':tag,'phase':'creating','created_depots':[]}
    path.write_text(json.dumps(progress),encoding='utf-8')
    depots=[]
    for suffix in ['A','B']:
        name=tag+'_'+suffix
        ok(client.post('/depot/add',dict(name=name,sort='90',remark=tag)))
        depots.append(next(r['id'] for r in client.listing('depot',{'name':name})['rows'] if r['name']==name))
        progress['created_depots']=depots.copy()
        path.write_text(json.dumps(progress),encoding='utf-8')
    ok(client.post('/material/add',dict(name=tag,unit='件',standard='QA',model='TEST',enableSerialNumber='0',enableBatchNumber='0',
        meList=[dict(barCode=tag,commodityUnit='件',purchaseDecimal=10,commodityDecimal=15,wholesaleDecimal=15,lowDecimal=0)],sortList='[]')))
    material=next(r for r in client.listing('material',{'materialParam':tag})['rows'] if r['name']==tag)
    suppliers=client.listing('supplier')['rows']
    result=dict(tag=tag,a=depots[0],b=depots[1],material=material['id'],
                supplier=next(r['id'] for r in suppliers if r['type']=='供应商'),
                customer=next(r['id'] for r in suppliers if r['type']=='客户'),
                account=client.listing('account')['rows'][0]['id'])
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def register_ui_document(data,detail):
    path=ROOT/'artifacts/data-manifests'/f'{data["tag"]}.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    documents=manifest.setdefault('ui_documents',[])
    record={'id':detail['id'],'number':detail['number']}
    if record not in documents:documents.append(record)
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

def bill_body(d,kind,quantity,number=None):
    number=number or d['tag']+'_'+uuid.uuid4().hex[:8]
    info=dict(type='入库' if kind=='采购' else '出库',subType=kind,number=number,defaultNumber=number,
              operTime=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),totalPrice=quantity*10,
              discount=0,discountMoney=0,discountLastMoney=quantity*10,changeAmount=0,totalTax=0,
              otherMoney=0,status='0',remark=d['tag'])
    row=dict(barCode=d['tag'],unit='件',operNumber=quantity,unitPrice=10,allPrice=quantity*10,
             taxRate=0,taxMoney=0,taxLastMoney=quantity*10,depotId=d['b'] if kind=='销售' else d['a'])
    if kind=='调拨':
        row['anotherDepotId']=d['b']
    else:
        info.update(accountId=d['account'],organId=d['supplier'] if kind=='采购' else d['customer'])
    return dict(info=json.dumps(info,ensure_ascii=False),rows=json.dumps([row],ensure_ascii=False))

def stock(client,d,depot):
    response=ok(client.get('/material/getListWithStock',currentPage=1,pageSize=20,depotIds=str(depot),materialParam=d['tag'],zeroStock=0))
    return response['data']['currentStock']

def run():
    client=ERP();client.login()
    cfg=client.listing('systemConfig')['rows'][0]
    assert cfg['forceApprovalFlag']=='0' and cfg['inOutManageFlag']=='0',cfg
    d=create_data(client)
    evidence={'data':d,'configuration':cfg,'steps':[]}
    try:
        for kind,quantity,expected in [('采购',100,[100,0]),('调拨',30,[70,30]),('销售',10,[70,20])]:
            body=bill_body(d,kind,quantity)
            result=ok(client.post('/depotHead/addDepotHeadAndDetail',body))
            number=json.loads(body['info'])['number']
            detail=ok(client.get('/depotHead/getDetailByNumber',number=number))['data']
            values=[stock(client,d,d['a']),stock(client,d,d['b'])]
            evidence['steps'].append(dict(kind=kind,request=body,response=result,document=detail,stock=values,expected=expected))
            assert values==expected,(values,expected)
            assert detail['number']==number and detail['status']=='0',detail
        assert sum(values)==90
        evidence['result']='PASS'
        print(json.dumps({'result':'PASS','tag':d['tag'],'stock':values,'total':sum(values)},ensure_ascii=False))
    finally:
        (ROOT/'artifacts/core-scenario.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':
    from execution_lock import execution_lock
    with execution_lock():run()
