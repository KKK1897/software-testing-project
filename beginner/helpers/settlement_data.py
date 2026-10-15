"""进阶链路：ERP收付款记账、关联欠款及账户余额查询，不连接支付网关。"""
import json
import uuid
from datetime import datetime
from decimal import Decimal

from helpers.api_client import ROOT
from helpers.inventory_data import create_data, ok


def money(value):
    """金额用Decimal核对，避免二进制小数比较造成误差。"""
    return Decimal(str(value))


def save_manifest(data):
    path = ROOT / 'artifacts/data-manifests' / (data['tag'] + '.json')
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def create_settlement_data(client, test_id):
    """新建两仓、商品、供应商、客户、2000元期初的QA账户，持续登记归属。"""
    configuration = client.listing('systemConfig')['rows'][0]
    assert configuration['forceApprovalFlag'] == '0', '准备错误：本场景要求关闭强制审核'
    assert configuration['inOutManageFlag'] == '0', '准备错误：本场景要求保存单据即生效'
    data = create_data(client)
    data.pop('_manifest')
    data['test'] = test_id
    data['finance'] = {'phase': 'preparing', 'partners': [], 'documents': []}
    save_manifest(data)
    for kind, suffix, key in [('供应商', '_S', 'supplier'), ('客户', '_C', 'customer')]:
        name = data['tag'] + suffix
        ok(client.post('/supplier/add', {
            'supplier': name, 'type': kind, 'beginNeedPay': 0,
            'beginNeedGet': 0, 'sort': '99', 'description': data['tag'],
        }))
        rows = client.listing('supplier', {'supplier': name, 'type': kind})['rows']
        partner = next(row for row in rows if row['supplier'] == name)
        data[key] = partner['id']
        data['finance']['partners'].append({'id': partner['id'], 'name': name, 'type': kind})
        save_manifest(data)
    account_name = data['tag'] + '_PAY'
    ok(client.post('/account/add', {
        'name': account_name, 'serialNo': data['tag'], 'initialAmount': 2000,
        'sort': '99', 'remark': data['tag'],
    }))
    rows = client.listing('account', {'name': account_name})['rows']
    account = next(row for row in rows if row['name'] == account_name)
    assert not account['isDefault'], 'QA账户不得改变原默认结算账户'
    data['account'] = account['id']
    data['finance'].update({
        'phase': 'ready', 'account_id': account['id'],
        'account_name': account_name, 'initial_amount': 2000,
    })
    save_manifest(data)
    return data


def settlement_body(data, document, kind, amount, need_debt, finish_debt=0):
    """关联采购/销售单；付款表头传负数，明细正数，遵循该版本页面协议。"""
    assert kind in ('付款', '收款')
    number = data['tag'] + '_' + ('FK' if kind == '付款' else 'SK') + '_' + uuid.uuid4().hex[:8]
    signed_amount = -amount if kind == '付款' else amount
    info = {
        'type': kind, 'billNo': number,
        'billTime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'organId': data['supplier'] if kind == '付款' else data['customer'],
        'accountId': data['account'], 'totalPrice': signed_amount,
        'changeAmount': signed_amount, 'discountMoney': 0,
        'status': '0', 'remark': data['tag'],
    }
    rows = [{
        'billNumber': document['number'], 'needDebt': need_debt,
        'finishDebt': finish_debt, 'eachAmount': amount, 'remark': data['tag'],
    }]
    return {'info': json.dumps(info, ensure_ascii=False), 'rows': json.dumps(rows, ensure_ascii=False)}


def finance_document(client, data, body):
    """核对单据唯一、表头、金额和关联业务单，并登记安全清理所需证据。"""
    info = json.loads(body['info'])
    expected = json.loads(body['rows'])[0]
    result = client.listing('accountHead', {'type': info['type'], 'billNo': info['billNo']})
    assert result['total'] == 1 and len(result['rows']) == 1, result
    document = ok(client.get('/accountHead/getDetailByNumber', billNo=info['billNo']))['data']
    for field in ('billNo', 'type', 'accountId', 'organId', 'status'):
        assert document[field] == info[field], document
    assert money(document['changeAmount']) == abs(money(info['changeAmount']))
    assert money(document['totalPrice']) == abs(money(info['totalPrice']))
    details = ok(client.get('/accountItem/getDetailList', headerId=document['id']))['data']
    assert details['total'] == 1 and len(details['rows']) == 1, details
    row = details['rows'][0]
    assert row['billNumber'] == expected['billNumber'], row
    for field in ('needDebt', 'finishDebt', 'eachAmount'):
        assert money(row[field]) == money(expected[field]), row
    registered = {
        'id': document['id'], 'billNo': document['billNo'], 'type': document['type'],
        'bill_number': expected['billNumber'], 'amount': expected['eachAmount'],
    }
    if registered not in data['finance']['documents']:
        data['finance']['documents'].append(registered)
        save_manifest(data)
    return document


def debt_list(client, data, partner):
    search = {'organId': partner, 'number': data['tag']}
    return ok(client.get(
        '/depotHead/debtList', search=json.dumps(search, ensure_ascii=False),
        currentPage=1, pageSize=100,
    ))['data']


def assert_debt(client, data, document, expected_remaining, expected_paid):
    """部分结算核对已付/剩余，全额结算必须从欠款列表消失。"""
    result = debt_list(client, data, document['organId'])
    if expected_remaining == 0:
        assert result['total'] == 0 and result['rows'] == [], result
    else:
        assert result['total'] == 1 and len(result['rows']) == 1, result
        row = result['rows'][0]
        assert row['number'] == document['number'], row
        assert money(row['debt']) == money(expected_remaining), row
        assert money(row['finishDebt']) == money(expected_paid), row
        assert money(row['needDebt']) == money(expected_remaining) + money(expected_paid), row


def account_balance(client, data):
    result = ok(client.get(
        '/account/listWithBalance', name=data['finance']['account_name'], serialNo=data['tag'],
        currentPage=1, pageSize=20,
    ))['data']
    assert result['total'] == 1 and len(result['rows']) == 1, result
    account = result['rows'][0]
    assert account['id'] == data['account'], account
    assert money(account['initialAmount']) == 2000, account
    return money(account['currentAmount'])


def account_ledger(client, data):
    return ok(client.get(
        '/account/findAccountInOutList', currentPage=1, pageSize=100,
        accountId=data['account'], initialAmount=data['finance']['initial_amount'],
    ))['data']
