import json

from helpers.api_client import OUTPUT
from helpers.inventory_data import (
    assert_document, assert_document_absent, bill_body, ok, stock,
)


def test_stock_chain(client, data):
    """采购100→A调拨30至B→B销售10，最后A70/B20/总90。"""
    configuration = client.listing('systemConfig')['rows'][0]
    assert configuration['forceApprovalFlag'] == '0', '准备错误：本链路要求关闭强制审核'
    assert configuration['inOutManageFlag'] == '0', '准备错误：本链路要求保存单据直接生效'
    steps = []
    for kind, quantity, expected in [
        ('采购', 100, [100, 0]),
        ('调拨', 30, [70, 30]),
        ('销售', 10, [70, 20]),
    ]:
        body = bill_body(data, kind, quantity)
        response = ok(client.post('/depotHead/addDepotHeadAndDetail', body))
        document = assert_document(client, body)
        values = [stock(client, data, data['a']), stock(client, data, data['b'])]
        steps.append({'kind': kind, 'number': document['number'], 'response': response, 'stock': values})
        assert values == expected, values
    assert sum(values) == 90
    path = OUTPUT / ('chain-' + data['tag'] + '.json')
    path.write_text(json.dumps({'data': data, 'steps': steps}, ensure_ascii=False, indent=2), encoding='utf-8')


def test_fractional_quantity(client, data):
    body = bill_body(data, '采购', 0.125)
    ok(client.post('/depotHead/addDepotHeadAndDetail', body))
    assert_document(client, body)
    assert stock(client, data, data['a']) == 0.125
    assert stock(client, data, data['b']) == 0


def test_delete_draft_reverses_stock(client, data):
    body = bill_body(data, '采购', 8)
    ok(client.post('/depotHead/addDepotHeadAndDetail', body))
    document = assert_document(client, body)
    assert stock(client, data, data['a']) == 8
    ok(client.change('DELETE', '/depotHead/delete', params={'id': document['id']}))
    assert_document_absent(client, body)
    assert stock(client, data, data['a']) == stock(client, data, data['b']) == 0


def test_duplicate_number_no_extra_stock(client, data):
    body = bill_body(data, '采购', 9)
    ok(client.post('/depotHead/addDepotHeadAndDetail', body))
    response = client.post('/depotHead/addDepotHeadAndDetail', body)
    assert response['code'] == 8500022, response
    assert_document(client, body)
    assert stock(client, data, data['a']) == 9
    assert stock(client, data, data['b']) == 0


def test_missing_account_rolls_back(client, data):
    body = bill_body(data, '采购', 10)
    info = json.loads(body['info'])
    info.pop('accountId')
    body['info'] = json.dumps(info, ensure_ascii=False)
    response = client.post('/depotHead/addDepotHeadAndDetail', body)
    assert response['code'] == 8500007, response
    assert_document_absent(client, body)
    assert stock(client, data, data['a']) == stock(client, data, data['b']) == 0


def test_unknown_barcode_rolls_back(client, data):
    body = bill_body(data, '采购', 10)
    rows = json.loads(body['rows'])
    rows[0]['barCode'] = 'QA_NOT_EXIST_' + data['tag']
    body['rows'] = json.dumps(rows, ensure_ascii=False)
    response = client.post('/depotHead/addDepotHeadAndDetail', body)
    assert response['code'] == 8000026, response
    assert_document_absent(client, body)
    assert stock(client, data, data['a']) == stock(client, data, data['b']) == 0


def test_same_depot_transfer_rolls_back(client, data):
    body = bill_body(data, '调拨', 10)
    rows = json.loads(body['rows'])
    rows[0]['anotherDepotId'] = data['a']
    body['rows'] = json.dumps(rows, ensure_ascii=False)
    response = client.post('/depotHead/addDepotHeadAndDetail', body)
    assert response['code'] == 8500010, response
    assert_document_absent(client, body)
    assert stock(client, data, data['a']) == stock(client, data, data['b']) == 0


def test_insufficient_stock_when_disallowed(client, data):
    """临时禁止负库存，验证拒绝且无残留，finally恢复原配置。"""
    configuration = client.listing('systemConfig')['rows'][0]
    try:
        ok(client.change('PUT', '/systemConfig/update', json={**configuration, 'minusStockFlag': '0'}))
        body = bill_body(data, '销售', 1)
        response = client.post('/depotHead/addDepotHeadAndDetail', body)
        assert response['code'] == 8000004, response
        assert_document_absent(client, body)
        assert stock(client, data, data['a']) == stock(client, data, data['b']) == 0
    finally:
        ok(client.change('PUT', '/systemConfig/update', json=configuration))
