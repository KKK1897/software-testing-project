"""进阶：采购付款、跨仓调拨、销售分次收款及库存/账务一致性。"""
import json

import allure

from helpers.api_client import OUTPUT, redact
from helpers.inventory_data import assert_document, bill_body, ok, stock
from helpers.settlement_data import (
    account_balance, account_ledger, assert_debt, finance_document,
    money, settlement_body,
)


def test_purchase_payment_transfer_sale_collection(client, settlement_data):
    """库存、往来欠款和账户流水同时闭环，收款分60+90验证部分结算。"""
    data = settlement_data
    steps = []

    def checkpoint(name, expected_stock, expected_balance):
        values = [stock(client, data, data['a']), stock(client, data, data['b'])]
        balance = account_balance(client, data)
        steps.append({'step': name, 'stock': values, 'balance': str(balance)})
        assert values == expected_stock, values
        assert balance == money(expected_balance), balance

    with allure.step('登录后确认独立QA账户期初2000、两仓零库存'):
        checkpoint('期初', [0, 0], 2000)
        assert account_ledger(client, data)['total'] == 0

    with allure.step('采购入库100件×10元，形成应付1000，尚未付款'):
        purchase_body = bill_body(data, '采购', 100)
        ok(client.post('/depotHead/addDepotHeadAndDetail', purchase_body))
        purchase = assert_document(client, purchase_body)
        assert_debt(client, data, purchase, expected_remaining=1000, expected_paid=0)
        checkpoint('采购未付', [100, 0], 2000)

    with allure.step('关联采购单付款1000，应付结清、账户余额1000'):
        payment_body = settlement_body(data, purchase, '付款', 1000, need_debt=1000)
        ok(client.post('/accountHead/addAccountHeadAndDetail', payment_body))
        payment = finance_document(client, data, payment_body)
        assert_debt(client, data, purchase, expected_remaining=0, expected_paid=1000)
        checkpoint('采购已付', [100, 0], 1000)

    with allure.step('A仓调拨30件至B仓，不影响账户余额'):
        transfer_body = bill_body(data, '调拨', 30)
        ok(client.post('/depotHead/addDepotHeadAndDetail', transfer_body))
        transfer = assert_document(client, transfer_body)
        checkpoint('调拨', [70, 30], 1000)

    with allure.step('B仓销售10件×15元，形成应收150，尚未收款'):
        sale_body = bill_body(data, '销售', 10)
        info = json.loads(sale_body['info'])
        rows = json.loads(sale_body['rows'])
        info.update(totalPrice=150, discountLastMoney=150)
        rows[0].update(unitPrice=15, allPrice=150, taxLastMoney=150)
        sale_body = {'info': json.dumps(info, ensure_ascii=False), 'rows': json.dumps(rows, ensure_ascii=False)}
        ok(client.post('/depotHead/addDepotHeadAndDetail', sale_body))
        sale = assert_document(client, sale_body)
        assert_debt(client, data, sale, expected_remaining=150, expected_paid=0)
        checkpoint('销售未收', [70, 20], 1000)

    with allure.step('先收60元，已收60、待收90，账户1060'):
        first_body = settlement_body(data, sale, '收款', 60, need_debt=150)
        ok(client.post('/accountHead/addAccountHeadAndDetail', first_body))
        first_receipt = finance_document(client, data, first_body)
        assert_debt(client, data, sale, expected_remaining=90, expected_paid=60)
        checkpoint('部分收款', [70, 20], 1060)

    with allure.step('再收90元，应收结清，账户1150，库存总90'):
        final_body = settlement_body(data, sale, '收款', 90, need_debt=150, finish_debt=60)
        ok(client.post('/accountHead/addAccountHeadAndDetail', final_body))
        final_receipt = finance_document(client, data, final_body)
        assert_debt(client, data, sale, expected_remaining=0, expected_paid=150)
        checkpoint('全部结清', [70, 20], 1150)

    with allure.step('核对三张资金单与业务单的关联，三条流水及净额-850'):
        purchase_links = ok(client.get('/accountHead/getFinancialBillNoByBillId', billId=purchase['id']))['data']
        sale_links = ok(client.get('/accountHead/getFinancialBillNoByBillId', billId=sale['id']))['data']
        # 该接口SQL只返回bill_no，不能假定它同时返回资金单ID。
        assert {row['billNo'] for row in purchase_links} == {payment['billNo']}
        assert len(purchase_links) == 1
        assert {row['billNo'] for row in sale_links} == {first_receipt['billNo'], final_receipt['billNo']}
        assert len(sale_links) == 2
        ledger = account_ledger(client, data)
        expected = {payment['billNo']: -1000, first_receipt['billNo']: 60, final_receipt['billNo']: 90}
        assert ledger['total'] == 3 and len(ledger['rows']) == 3, ledger
        actual = {row['number']: money(row['changeAmount']) for row in ledger['rows']}
        assert actual == {number: money(amount) for number, amount in expected.items()}, ledger
        expected_balances = {payment['billNo']: 1000, first_receipt['billNo']: 1060, final_receipt['billNo']: 1150}
        for row in ledger['rows']:
            assert money(row['balance']) == money(expected_balances[row['number']]), row
        assert sum(actual.values()) == -850
        assert account_balance(client, data) == 2000 + sum(actual.values())
        assert stock(client, data, data['a']) + stock(client, data, data['b']) == 90

    evidence = {
        'tag': data['tag'], 'data': data, 'steps': steps,
        'inventory_documents': [purchase['number'], transfer['number'], sale['number']],
        'financial_documents': list(expected), 'ledger': ledger,
        'result': '通过', 'scope': 'ERP内部收付款记账，不是真实支付网关',
    }
    path = OUTPUT / ('settlement-' + data['tag'] + '.json')
    path.write_text(json.dumps(redact(evidence), ensure_ascii=False, indent=2), encoding='utf-8')
    allure.attach.file(str(path), '库存与资金闭环证据', allure.attachment_type.JSON)


def test_duplicate_payment_number_does_not_pay_twice(client, settlement_data):
    data = settlement_data
    purchase_body = bill_body(data, '采购', 8)
    ok(client.post('/depotHead/addDepotHeadAndDetail', purchase_body))
    purchase = assert_document(client, purchase_body)
    payment_body = settlement_body(data, purchase, '付款', 80, need_debt=80)
    ok(client.post('/accountHead/addAccountHeadAndDetail', payment_body))
    payment = finance_document(client, data, payment_body)

    response = client.post('/accountHead/addAccountHeadAndDetail', payment_body)

    assert response['code'] == 9500005, response
    assert finance_document(client, data, payment_body)['id'] == payment['id']
    assert account_balance(client, data) == 1920
    assert account_ledger(client, data)['total'] == 1
    assert_debt(client, data, purchase, expected_remaining=0, expected_paid=80)
    assert stock(client, data, data['a']) == 8
    assert stock(client, data, data['b']) == 0


def test_empty_payment_details_roll_back(client, settlement_data):
    data = settlement_data
    purchase_body = bill_body(data, '采购', 8)
    ok(client.post('/depotHead/addDepotHeadAndDetail', purchase_body))
    purchase = assert_document(client, purchase_body)
    body = settlement_body(data, purchase, '付款', 80, need_debt=80)
    body['rows'] = '[]'

    response = client.post('/accountHead/addAccountHeadAndDetail', body)

    assert response['code'] == 9500003, response
    info = json.loads(body['info'])
    found = client.listing('accountHead', {'type': '付款', 'billNo': info['billNo']})
    assert found['total'] == 0 and found['rows'] == [], found
    assert account_balance(client, data) == 2000
    assert account_ledger(client, data)['total'] == 0
    links = ok(client.get('/accountHead/getFinancialBillNoByBillId', billId=purchase['id']))['data']
    assert links == [], links
    assert_debt(client, data, purchase, expected_remaining=80, expected_paid=0)
    assert stock(client, data, data['a']) == 8
    assert stock(client, data, data['b']) == 0
