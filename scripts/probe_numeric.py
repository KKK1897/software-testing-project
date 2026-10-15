"""数值边界实际观察；不把系统允许的行为擅自改判为业务缺陷。"""
import json,argparse
from decimal import Decimal
from erp_client import ERP,ROOT,HISTORY,redact
from core_scenario import create_data,bill_body,stock,ok
from cleanup_data import cleanup
from execution_lock import execution_lock

def run(prices_only=False):
    c=ERP();c.login()
    cfg=c.listing('systemConfig')['rows'][0]
    assert cfg['forceApprovalFlag']=='0' and cfg['minusStockFlag']=='1'
    out={'configuration':cfg,'observations':[]}
    path=ROOT/('artifacts/numeric-price-verification.json' if prices_only else 'artifacts/numeric-exploration.json')
    scenarios=[('zero_quantity',0,10),('negative_quantity',-1,10),('over_six_decimals',0.1234567,10),('zero_price',1,0),('negative_price',1,-1)]
    for label,q,price in scenarios:
        if prices_only and 'price' not in label:continue
        d=create_data(c);body=bill_body(d,'采购',q)
        info=json.loads(body['info']);rows=json.loads(body['rows'])
        amount=float(Decimal(str(q))*Decimal(str(price)))
        info.update(totalPrice=amount,discountLastMoney=amount)
        rows[0].update(unitPrice=price,allPrice=amount,taxLastMoney=amount)
        body.update(info=json.dumps(info,ensure_ascii=False),rows=json.dumps(rows,ensure_ascii=False))
        entry={'case':label,'data':d,'input':{'quantity':q,'price':price},'request':body}
        try:entry['response']=c.post('/depotHead/addDepotHeadAndDetail',body)
        except Exception as exc:entry['response']={'exception':type(exc).__name__,'evidence':HISTORY[-1]}
        entry['documents']=c.listing('depotHead',{'number':info['number'],'type':'入库','subType':'采购'})
        entry['stock']=stock(c,d,d['a'])
        if entry['documents']['total']==1:
            head=entry['documents']['rows'][0]
            entry['stored_details']=ok(c.get('/depotItem/getDetailList',headerId=head['id'],mpList='',linkType='basic'))['data']
        out['observations'].append(entry)
        path.write_text(json.dumps(redact(out),ensure_ascii=False,indent=2),encoding='utf-8')
        try:
            cleanup(ROOT/'artifacts/data-manifests'/f'{d["tag"]}.json')
            entry['cleanup']='verified'
        except Exception as exc:
            entry['cleanup']={'error':str(exc)}
            path.write_text(json.dumps(redact(out),ensure_ascii=False,indent=2),encoding='utf-8')
            raise
        path.write_text(json.dumps(redact(out),ensure_ascii=False,indent=2),encoding='utf-8')
        print(label,entry['response'],entry['stock'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prices-only',action='store_true');args=parser.parse_args()
    with execution_lock():run(args.prices_only)
