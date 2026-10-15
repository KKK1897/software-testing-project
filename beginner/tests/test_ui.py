"""真实页面三条流程；失败截图和trace留在本机，trace分享前需脱敏。"""
import json
import os
import re
import uuid
import pytest
import allure
from helpers.api_client import ROOT, OUTPUT, redis_read, ERP, redact
from helpers.inventory_data import stock, register_ui_document, ok
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / 'tools/pw-browsers')
from playwright.sync_api import sync_playwright, expect
pytestmark = pytest.mark.ui
RUN_ID = uuid.uuid4().hex[:12]

@pytest.fixture
def ui(request):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not request.config.getoption('--headed'))
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        yield page
        out = OUTPUT / 'ui' / RUN_ID
        out.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=str(out / (request.node.name + '.png')), full_page=True)
            allure.attach.file(str(out / (request.node.name + '.png')), name='页面截图', attachment_type=allure.attachment_type.PNG)
            context.tracing.stop(path=str(out / (request.node.name + '-trace.zip')))
            allure.attach.file(str(out / (request.node.name + '-trace.zip')), name='Playwright trace（仅本机，分享前脱敏）', attachment_type='application/zip', extension='zip')
        finally:
            browser.close()

def login(page, name='jsh'):
    with page.expect_response('**/user/randomImage') as image:
        page.goto('http://127.0.0.1:3000', wait_until='domcontentloaded')
    data = image.value.json()['data']
    page.get_by_placeholder('请输入用户名').fill(name)
    page.get_by_placeholder('请输入密码', exact=True).fill('123456')
    page.get_by_placeholder('请输入验证码').fill(redis_read('captcha_codes:' + data['uuid']))
    page.get_by_role('button', name='登 录').click()
    page.wait_for_url('**/dashboard/analysis', timeout=30000)
    if page.locator('.introjs-skipbutton').is_visible():
        page.locator('.introjs-skipbutton').click()
    expect(page.get_by_text('退出登录', exact=True)).to_be_visible()

def test_ui_login_logout(ui):
    login(ui)
    ui.get_by_text('退出登录', exact=True).click()
    ui.get_by_role('button', name='确 定').click()
    expect(ui.get_by_placeholder('请输入用户名')).to_be_visible(timeout=15000)

def test_ui_readonly_hides_depot_create(ui):
    identities = json.loads((ROOT / 'runtime/identities.json').read_text(encoding='utf-8'))
    login(ui, identities['readonly']['loginName'])
    ui.get_by_text('基本资料', exact=True).click()
    ui.get_by_text('仓库信息', exact=True).click()
    expect(ui.get_by_placeholder('请输入仓库名称查询')).to_be_visible()
    expect(ui.get_by_role('button', name=re.compile('新\\s*增'))).to_have_count(0)

def test_ui_purchase_and_sale_stock(ui, client, data):
    """页面保存采购和销售，接口核对单据，再在商品库存页面确认90件。"""
    identities = json.loads((ROOT / 'runtime/identities.json').read_text(encoding='utf-8'))
    login(ui, identities['operator']['loginName'])
    default_depot = next(row['id'] for row in client.listing('depot')['rows'] if row['isDefault'])
    assert stock(client, data, default_depot) == 0
    partners = client.listing('supplier')['rows']
    supplier = next(row['supplier'] for row in partners if row['id'] == data['supplier'])
    customer = next(row['supplier'] for row in partners if row['id'] == data['customer'])
    documents = []
    for menu, page_name, partner, quantity, expected_stock in [
        ('采购管理', '采购入库', supplier, 100, 100),
        ('销售管理', '销售出库', customer, 10, 90),
    ]:
        ui.get_by_text(menu, exact=True).click()
        ui.get_by_text(page_name, exact=True).click()
        ui.get_by_role('button', name=re.compile('新增')).first.click()
        if ui.locator('.introjs-skipbutton').is_visible():
            ui.locator('.introjs-skipbutton').click()
        modal = ui.locator('.ant-modal:visible')
        modal.get_by_text('请选择供应商' if menu == '采购管理' else '请选择客户', exact=True).click()
        ui.get_by_role('option', name=partner, exact=True).click()
        modal.get_by_role('button', name='扫码录入').click()
        scan = modal.get_by_placeholder(re.compile('请扫.*回车'))
        scan.fill(data['tag'])
        scan.press('Enter')
        quantity_input = modal.locator('input[id^="operNumber_"]:visible').first
        expect(quantity_input).to_have_value('1')
        quantity_input.fill(str(quantity))
        quantity_input.press('Tab')
        number = modal.get_by_placeholder('请输入单据编号').input_value()
        with ui.expect_response('**/depotHead/addDepotHeadAndDetail') as saved:
            modal.get_by_role('button', name=re.compile('^保\\s*存$')).click()
        assert saved.value.status == 200
        assert saved.value.json()['code'] == 200, saved.value.json()
        expect(modal).to_be_hidden()
        assert stock(client, data, default_depot) == expected_stock
        detail = client.get('/depotHead/getDetailByNumber', number=number)
        assert detail['code'] == 200 and detail['data']['number'] == number
        register_ui_document(data, detail['data'])
        found = client.listing('depotHead', {
            'number': number,
            'type': '入库' if menu == '采购管理' else '出库',
            'subType': '采购' if menu == '采购管理' else '销售',
        })
        assert found['total'] == 1
        rows = ok(client.get('/depotItem/getDetailList', headerId=detail['data']['id'], mpList=''))['data']['rows']
        assert len(rows) == 1
        assert rows[0]['barCode'] == data['tag']
        assert rows[0]['operNumber'] == quantity
        assert rows[0]['depotId'] == default_depot
        documents.append({'number': number, 'stock': expected_stock, 'response': saved.value.json(), 'detail': detail})
    ui.get_by_text('报表查询', exact=True).click()
    ui.get_by_text('商品库存', exact=True).click()
    ui.get_by_placeholder('请输入条码、名称、助记码、规格、型号等信息', exact=True).fill(data['tag'])
    with ui.expect_response('**/material/getListWithStock?*') as queried:
        ui.get_by_role('button', name='查 询', exact=True).click()
    assert queried.value.status == 200
    assert queried.value.json()['code'] == 200
    assert queried.value.json()['data']['currentStock'] == 90
    expect(ui.get_by_text(re.compile(r'^总库存：90(?:\.0+)?，'))).to_be_visible()
    evidence = {'data': data, 'depot': default_depot, 'documents': documents}
    output_file = OUTPUT / ('ui-business-' + data['tag'] + '.json')
    output_file.write_text(
        json.dumps(redact(evidence), ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
