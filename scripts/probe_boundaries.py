"""补充边界探索：保留精确响应和副作用，未知业务码不自动判作正确拒绝。"""
import json,uuid
from erp_client import ERP,ROOT,HISTORY,redact
from core_scenario import create_data,bill_body,stock
from execution_lock import execution_lock

def run():
    c=ERP();c.login();results=[]
    for length in (20,21):
        name=('QA_LEN_'+uuid.uuid4().hex)[:length]
        try:response=c.post('/depot/add',{'name':name,'sort':'99'})
        except Exception as exc:response={'transport_exception':type(exc).__name__,'evidence':HISTORY[-1]}
        rows=c.listing('depot',{'name':name})['rows']
        results.append({'case':'warehouse_length','length':length,'name':name,'response':response,'rows':rows})
        for row in rows:
            if row['name']==name:c.request('DELETE','/depot/delete',params={'id':row['id']})
    d=create_data(c)
    name=d['tag']+'_DUP'
    body={'name':name,'unit':'件','enableSerialNumber':'0','enableBatchNumber':'0','meList':[{'barCode':d['tag'],'commodityUnit':'件','purchaseDecimal':10}],'sortList':'[]'}
    try:response=c.post('/material/add',body)
    except Exception as exc:response={'transport_exception':type(exc).__name__,'evidence':HISTORY[-1]}
    results.append({'case':'duplicate_barcode','response':response,'new_materials':c.listing('material',{'materialParam':name})})
    b=bill_body(d,'采购',1);rows=json.loads(b['rows']);rows[0]['operNumber']='abc';b['rows']=json.dumps(rows)
    try:response=c.post('/depotHead/addDepotHeadAndDetail',b)
    except Exception as exc:response={'transport_exception':type(exc).__name__,'evidence':HISTORY[-1]}
    info=json.loads(b['info'])
    results.append({'case':'quantity_text','request':b,'response':response,'documents':c.listing('depotHead',{'number':info['number'],'type':'入库','subType':'采购'}),'stock':stock(c,d,d['a'])})
    (ROOT/'artifacts/boundary-exploration.json').write_text(json.dumps(redact({'data':d,'observations':results,'history':HISTORY}),ensure_ascii=False,indent=2),encoding='utf-8')
    print('已记录4个边界观察；脚本退出0仅表示取证结束，业务判定需查看报告。')

if __name__=='__main__':
    with execution_lock():run()
