"""两仓一商品的数据准备、单据构造及接口核对。"""
import json
import uuid
from datetime import datetime

from helpers.api_client import ROOT


def ok(response):
    assert response['code'] == 200, response
    return response


def create_data(client):
    """建立唯一QA仓库与商品，复用已有供应商、客户、结算账户。"""
    tag = 'QA_' + uuid.uuid4().hex[:12]
    directory = ROOT / 'artifacts/data-manifests'
    directory.mkdir(exist_ok=True)
    path = directory / (tag + '.json')
    progress = {'tag': tag, 'phase': 'creating', 'created_depots': []}
    path.write_text(json.dumps(progress), encoding='utf-8')
    depot_ids = []
    for suffix in ['A', 'B']:
        name = tag + '_' + suffix
        ok(client.post('/depot/add', {'name': name, 'sort': '90', 'remark': tag}))
        rows = client.listing('depot', {'name': name})['rows']
        depot_ids.append(next(row['id'] for row in rows if row['name'] == name))
        progress['created_depots'] = depot_ids.copy()
        path.write_text(json.dumps(progress), encoding='utf-8')
    material_body = {
        'name': tag,
        'unit': '件',
        'standard': 'QA',
        'model': 'TEST',
        'enableSerialNumber': '0',
        'enableBatchNumber': '0',
        'meList': [{
            'barCode': tag, 'commodityUnit': '件',
            'purchaseDecimal': 10, 'commodityDecimal': 15,
            'wholesaleDecimal': 15, 'lowDecimal': 0,
        }],
        'sortList': '[]',
    }
    ok(client.post('/material/add', material_body))
    material = next(row for row in client.listing('material', {'materialParam': tag})['rows'] if row['name'] == tag)
    suppliers = client.listing('supplier')['rows']
    dataset = {
        'tag': tag,
        'a': depot_ids[0],
        'b': depot_ids[1],
        'material': material['id'],
        'supplier': next(row['id'] for row in suppliers if row['type'] == '供应商'),
        'customer': next(row['id'] for row in suppliers if row['type'] == '客户'),
        'account': client.listing('account')['rows'][0]['id'],
    }
    path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding='utf-8')
    dataset['_manifest'] = str(path)
    return dataset


def bill_body(data, kind, quantity, number=None):
    """生成一张单明细草稿；销售走B仓，采购走A仓，调拨A到B。"""
    number = number or data['tag'] + '_' + uuid.uuid4().hex[:8]
    amount = quantity * 10
    info = {
        'type': '入库' if kind == '采购' else '出库',
        'subType': kind,
        'number': number,
        'defaultNumber': number,
        'operTime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'totalPrice': amount,
        'discount': 0,
        'discountMoney': 0,
        'discountLastMoney': amount,
        'changeAmount': 0,
        'totalTax': 0,
        'otherMoney': 0,
        'status': '0',
        'remark': data['tag'],
    }
    row = {
        'barCode': data['tag'],
        'unit': '件',
        'operNumber': quantity,
        'unitPrice': 10,
        'allPrice': amount,
        'taxRate': 0,
        'taxMoney': 0,
        'taxLastMoney': amount,
        'depotId': data['b'] if kind == '销售' else data['a'],
    }
    if kind == '调拨':
        row['anotherDepotId'] = data['b']
    else:
        info['accountId'] = data['account']
        info['organId'] = data['supplier'] if kind == '采购' else data['customer']
    return {'info': json.dumps(info, ensure_ascii=False), 'rows': json.dumps([row], ensure_ascii=False)}


def stock(client, data, depot):
    """查询当前测试商品在指定仓库的库存数量。"""
    response = ok(client.get(
        '/material/getListWithStock', currentPage=1, pageSize=20,
        depotIds=str(depot), materialParam=data['tag'], zeroStock=0,
    ))
    return response['data']['currentStock']


def document_search(body):
    info = json.loads(body['info'])
    return {key: info[key] for key in ('number', 'type', 'subType')}


def assert_document_absent(client, body):
    """失败/删除后用列表查零行，避免缺失单号详情缺陷干扰断言。"""
    result = client.listing('depotHead', document_search(body))
    assert result['total'] == 0 and result['rows'] == [], result


def assert_document(client, body):
    """同时核对唯一单据、表头及商品数量/仓库明细，返回表头。"""
    info = json.loads(body['info'])
    expected = json.loads(body['rows'])[0]
    listing = client.listing('depotHead', document_search(body))
    assert listing['total'] == 1 and len(listing['rows']) == 1, listing
    detail = ok(client.get('/depotHead/getDetailByNumber', number=info['number']))['data']
    for field in ('number', 'type', 'subType', 'status'):
        assert detail[field] == info[field], detail
    rows = ok(client.get('/depotItem/getDetailList', headerId=detail['id'], mpList=''))['data']['rows']
    assert len(rows) == 1, rows
    for field in ('barCode', 'operNumber', 'depotId'):
        assert rows[0][field] == expected[field], rows
    if info['subType'] == '调拨':
        assert rows[0]['anotherDepotId'] == expected['anotherDepotId'], rows
    return detail


def register_ui_document(data, detail):
    """登记页面自动单号，供原清理脚本校验归属后逆序删除。"""
    path = ROOT / 'artifacts/data-manifests' / (data['tag'] + '.json')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    manifest.setdefault('ui_documents', []).append({'id': detail['id'], 'number': detail['number']})
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
