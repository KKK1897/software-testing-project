"""按单个测试 manifest 清理；只允许本地 QA 数据库和本次登记的ID。"""
import argparse,json
from pathlib import Path
import pymysql
from erp_client import ROOT,ERP
from core_scenario import ok
from execution_lock import execution_lock


def cleanup_financial_documents(client, data):
    """只清理进阶manifest登记的资金单；先完整核对账户、往来单位和关联商品。"""
    finance = data['finance']
    assert finance['phase'] == 'ready', '财务数据准备不完整，保留现场供核对'
    assert finance['account_id'] == data['account']
    assert finance['account_name'] == data['tag'] + '_PAY'
    account = ok(client.get('/account/info', id=data['account']))['data']['info']
    assert account['name'] == finance['account_name'] and account['remark'] == data['tag']
    assert account['serialNo'] == data['tag'] and account['initialAmount'] == finance['initial_amount']
    assert not account['isDefault'], '不得删除默认账户'
    assert len(finance['partners']) == 2
    for registered in finance['partners']:
        partner = ok(client.get('/supplier/info', id=registered['id']))['data']['info']
        suffix = '_S' if registered['type'] == '供应商' else '_C'
        assert partner['supplier'] == registered['name'] == data['tag'] + suffix
        assert partner['type'] == registered['type']
        key = 'supplier' if registered['type'] == '供应商' else 'customer'
        assert registered['id'] == data[key]
    # 拒绝存在未登记资金单或其他资金流水的账户。
    actual_ids = set()
    for kind in ('付款', '收款'):
        listing = client.listing('accountHead', {'type': kind, 'accountId': data['account']}, size=1000)
        assert listing['total'] == len(listing['rows'])
        actual_ids.update(row['id'] for row in listing['rows'])
    assert actual_ids == {row['id'] for row in finance['documents']}
    ledger = ok(client.get(
        '/account/findAccountInOutList', currentPage=1, pageSize=1000,
        accountId=data['account'], initialAmount=finance['initial_amount'],
    ))['data']
    assert ledger['total'] == len(ledger['rows']) == len(finance['documents'])
    assert {row['number'] for row in ledger['rows']} == {row['billNo'] for row in finance['documents']}
    # 全部归属核验完成后才开始删除，不能凭QA前缀就删除。
    for registered in finance['documents']:
        head = ok(client.get('/accountHead/getDetailByNumber', billNo=registered['billNo']))['data']
        assert head['id'] == registered['id'] and head['accountId'] == data['account']
        assert head['billNo'].startswith(data['tag'] + '_') and head['status'] == '0'
        assert head['type'] == registered['type'] and head['remark'] == data['tag']
        expected_partner = data['supplier'] if head['type'] == '付款' else data['customer']
        assert head['organId'] == expected_partner
        assert head['changeAmount'] == registered['amount']
        rows = ok(client.get('/accountItem/getDetailList', headerId=head['id']))['data']['rows']
        assert len(rows) == 1 and rows[0]['billNumber'] == registered['bill_number']
        assert rows[0]['eachAmount'] == registered['amount']
        assert registered['bill_number'].startswith(data['tag'] + '_')
        bill = ok(client.get('/depotHead/getDetailByNumber', number=registered['bill_number']))['data']
        items = ok(client.get('/depotItem/getDetailList', headerId=bill['id'], mpList=''))['data']['rows']
        assert items and all(row['barCode'] == data['tag'] for row in items)
    for registered in reversed(finance['documents']):
        ok(client.request('DELETE', '/accountHead/delete', params={'id': registered['id']}))
        found = client.listing('accountHead', {'type': registered['type'], 'billNo': registered['billNo']})
        assert found['total'] == 0 and found['rows'] == []
    balance = ok(client.get(
        '/account/listWithBalance', name=finance['account_name'], serialNo=data['tag'],
        currentPage=1, pageSize=20,
    ))['data']['rows']
    assert len(balance) == 1 and balance[0]['currentAmount'] == finance['initial_amount']

def cleanup(manifest):
    manifest=Path(manifest).resolve()
    assert manifest.parent==(ROOT/'artifacts/data-manifests').resolve(),'仅允许本项目manifest'
    d=json.loads(manifest.read_text(encoding='utf-8'))
    assert d['tag'].startswith('QA_') and len(d['tag'])==15
    assert all(k in d for k in ('a','b','material')),'部分创建失败的manifest只供定位，需按已记录ID核对后处理'
    cfg=json.loads((ROOT/'runtime/local.json').read_text(encoding='utf-8'))
    # 唯一必要SQL：只读核验连接确属项目独立数据目录，防止误清其它环境。
    with pymysql.connect(host='127.0.0.1',port=13306,user='erpqa',password=cfg['db_password'],database='jsh_erp_qa') as conn:
        with conn.cursor() as cursor:
            cursor.execute('SELECT DATABASE(), @@datadir')
            database,datadir=cursor.fetchone()
            assert database=='jsh_erp_qa' and Path(datadir).resolve()==(ROOT/'runtime/mysql-data').resolve()
    c=ERP();c.login()
    # 先按来源ID+名称双校验，再经业务接口逆向删除。
    for depot in [d['a'],d['b']]:
        item=ok(c.get('/depot/info',id=depot))['data']['info']
        assert item['name'] in [d['tag']+'_A',d['tag']+'_B']
    if 'finance' in d:
        cleanup_financial_documents(c, d)
    # UI 使用产品自动单号；只处理 manifest 明确登记且每条明细条码匹配的单据。
    verified_ui_searches = []
    for registered in reversed(d.get('ui_documents',[])):
        bill=ok(c.get('/depotHead/getDetailByNumber',number=registered['number']))['data']
        assert bill['id']==registered['id'] and bill['number']==registered['number']
        # 列表接口依赖subType计算权限范围；删除后仍按已核实的类型查询。
        verified_ui_searches.append({
            'number': bill['number'],
            'type': bill['type'],
            'subType': bill['subType'],
        })
        details=ok(c.get('/depotItem/getDetailList',headerId=bill['id'],mpList=''))['data']['rows']
        assert details and all(row['barCode']==d['tag'] for row in details),'单据包含未登记商品，拒绝删除'
        if bill['status']=='1':ok(c.post('/depotHead/batchSetStatus',dict(ids=str(bill['id']),status='0')))
        elif bill['status']!='0':raise RuntimeError('复杂UI单据状态拒绝删除')
        ok(c.request('DELETE','/depotHead/delete',params={'id':bill['id']}))
    for kind,type_ in [('销售','出库'),('调拨','出库'),('采购','入库')]:
        bills=c.listing('depotHead',{'number':d['tag'],'type':type_,'subType':kind},size=1000)['rows']
        for bill in bills:
            assert bill['number'].startswith(d['tag']+'_')
            if bill['status']=='1':ok(c.post('/depotHead/batchSetStatus',dict(ids=str(bill['id']),status='0')))
            elif bill['status']!='0':raise RuntimeError('复杂单据状态拒绝自动删除')
            ok(c.request('DELETE','/depotHead/delete',params={'id':bill['id']}))
    material=ok(c.get('/material/info',id=d['material']))['data']['info']
    assert material['name']==d['tag']
    ok(c.request('DELETE','/material/delete',params={'id':d['material']}))
    for depot in [d['a'],d['b']]:ok(c.request('DELETE','/depot/delete',params={'id':depot}))
    assert c.listing('depot',{'name':d['tag']})['total']==0,'仓库删除后仍可查到'
    assert c.listing('material',{'materialParam':d['tag']})['total']==0,'商品删除后仍可查到'
    for search in verified_ui_searches:
        result = c.listing('depotHead', search)
        assert result['total'] == 0 and result['rows'] == [], 'UI单据删除后仍可查到'
    if 'finance' in d:
        finance = d['finance']
        ok(c.request('DELETE', '/account/delete', params={'id': d['account']}))
        assert c.listing('account', {'name': finance['account_name']})['total'] == 0
        for partner in finance['partners']:
            ok(c.request('DELETE', '/supplier/delete', params={'id': partner['id']}))
            assert c.listing('supplier', {'supplier': partner['name'], 'type': partner['type']})['total'] == 0
    marker=manifest.with_suffix('.cleaned.json')
    verification = '商品、仓库及登记UI单据查询均为空'
    if 'finance' in d:
        verification += '；登记资金单、独立结算账户和往来单位已删除，资金单删除后余额恢复期初'
    marker.write_text(json.dumps({'result':'cleaned','manifest':manifest.name,'verification':verification},ensure_ascii=False),encoding='utf-8')
    print('本manifest登记的业务测试数据已通过接口清理')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('manifest');args=parser.parse_args()
    with execution_lock():cleanup(args.manifest)
