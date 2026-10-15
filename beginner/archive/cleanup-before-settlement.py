"""按单个测试 manifest 清理；只允许本地 QA 数据库和本次登记的ID。"""
import argparse,json
from pathlib import Path
import pymysql
from erp_client import ROOT,ERP
from core_scenario import ok
from execution_lock import execution_lock

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
    marker=manifest.with_suffix('.cleaned.json')
    marker.write_text(json.dumps({'result':'cleaned','manifest':manifest.name,'verification':'商品、仓库及登记UI单据查询均为空'},ensure_ascii=False),encoding='utf-8')
    print('本manifest登记的业务测试数据已通过接口清理')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('manifest');args=parser.parse_args()
    with execution_lock():cleanup(args.manifest)
