import json
import os
import re
import uuid
import pytest
import allure
from erp_client import ROOT,redis_read,ERP
from core_scenario import stock,register_ui_document
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'tools/pw-browsers')
from playwright.sync_api import sync_playwright,expect

pytestmark=pytest.mark.ui
RUN_ID=uuid.uuid4().hex[:12]

@pytest.fixture
def ui(request):
    with sync_playwright() as p:
        browser=p.chromium.launch()
        context=browser.new_context(viewport={'width':1920,'height':1080})
        context.tracing.start(screenshots=True,snapshots=True,sources=True)
        page=context.new_page()
        yield page
        out=ROOT/'artifacts/ui'/RUN_ID;out.mkdir(parents=True,exist_ok=True)
        try:
            page.screenshot(path=str(out/(request.node.name+'.png')),full_page=True)
            allure.attach.file(str(out/(request.node.name+'.png')),name='页面截图',attachment_type=allure.attachment_type.PNG)
            context.tracing.stop(path=str(out/(request.node.name+'-trace.zip')))
            allure.attach.file(str(out/(request.node.name+'-trace.zip')),name='Playwright trace（仅本机，分享前脱敏）',attachment_type='application/zip',extension='zip')
        finally:
            browser.close()

def login(page,name='jsh'):
    with page.expect_response('**/user/randomImage') as image:
        page.goto('http://127.0.0.1:3000',wait_until='networkidle')
    data=image.value.json()['data']
    page.get_by_placeholder('请输入用户名').fill(name)
    page.get_by_placeholder('请输入密码',exact=True).fill('123456')
    page.get_by_placeholder('请输入验证码').fill(redis_read('captcha_codes:'+data['uuid']))
    page.get_by_role('button',name='登 录').click()
    page.wait_for_url('**/dashboard/analysis',timeout=30000)
    page.wait_for_load_state('networkidle')
    if page.locator('.introjs-skipbutton').is_visible():
        page.locator('.introjs-skipbutton').click()
    expect(page.get_by_text('退出登录',exact=True)).to_be_visible()

def test_ui_login_logout(ui):
    login(ui)
    ui.get_by_text('退出登录',exact=True).click()
    ui.get_by_role('button',name='确 定').click()
    expect(ui.get_by_placeholder('请输入用户名')).to_be_visible(timeout=15000)

def test_ui_create_depot(ui):
    identities=json.loads((ROOT/'runtime/identities.json').read_text(encoding='utf-8'))
    login(ui,identities['operator']['loginName'])
    expect(ui.get_by_text('系统管理',exact=True)).to_have_count(0)
    ui.get_by_text('基本资料',exact=True).click()
    ui.get_by_text('仓库信息',exact=True).click()
    ui.get_by_role('button',name=re.compile(r'新\s*增')).click()
    name='QA_UI_DEPOT_'+uuid.uuid4().hex[:8]
    ui.get_by_placeholder('请输入仓库名称',exact=True).fill(name)
    ui.get_by_placeholder('请输入排序',exact=True).fill('99')
    with ui.expect_response('**/depot/add') as saved:
        ui.get_by_role('button',name='保 存').click()
    assert saved.value.json()['code']==200
    ui.get_by_placeholder('请输入仓库名称查询').fill(name)
    ui.get_by_role('button',name='查 询').click()
    expect(ui.get_by_role('cell',name=name,exact=True)).to_be_visible()
    c=ERP();c.login()
    assert any(r['name']==name for r in c.listing('depot',{'name':name})['rows'])

def test_ui_supplier_required(ui):
    login(ui)
    ui.get_by_text('基本资料',exact=True).click()
    ui.get_by_text('供应商信息',exact=True).click()
    ui.get_by_role('button',name=re.compile(r'新\s*增')).click()
    ui.get_by_role('button',name='保 存').click()
    expect(ui.get_by_text('请输入名称!',exact=True)).to_be_visible()

def test_ui_readonly_hides_depot_create(ui):
    identities=json.loads((ROOT/'runtime/identities.json').read_text(encoding='utf-8'))
    login(ui,identities['readonly']['loginName'])
    ui.get_by_text('基本资料',exact=True).click()
    ui.get_by_text('仓库信息',exact=True).click()
    expect(ui.get_by_placeholder('请输入仓库名称查询')).to_be_visible()
    expect(ui.get_by_role('button',name=re.compile(r'新\s*增'))).to_have_count(0)

def test_ui_purchase_and_sale_stock(ui,client,data):
    identities=json.loads((ROOT/'runtime/identities.json').read_text(encoding='utf-8'))
    login(ui,identities['operator']['loginName'])
    default_depot=next(r['id'] for r in client.listing('depot')['rows'] if r['isDefault'])
    assert stock(client,data,default_depot)==0
    documents=[]
    for menu,page_name,partner,quantity,expected_stock in [
        ('采购管理','采购入库','供应商5',100,100),('销售管理','销售出库','客户3',10,90)]:
        ui.get_by_text(menu,exact=True).click()
        ui.get_by_text(page_name,exact=True).click()
        ui.get_by_role('button',name=re.compile('新增')).first.click()
        ui.wait_for_load_state('networkidle')
        if ui.locator('.introjs-skipbutton').is_visible():ui.locator('.introjs-skipbutton').click()
        modal=ui.locator('.ant-modal:visible')
        modal.get_by_text('请选择供应商' if menu=='采购管理' else '请选择客户',exact=True).click()
        ui.get_by_role('option',name=partner,exact=True).click()
        modal.get_by_role('button',name='扫码录入').click()
        scan=modal.get_by_placeholder(re.compile(r'请扫.*回车'))
        scan.fill(data['tag']);scan.press('Enter')
        qty=modal.locator('input[id^="operNumber_"]:visible').first
        expect(qty).to_have_value('1')
        qty.fill(str(quantity));qty.press('Tab')
        number=modal.get_by_placeholder('请输入单据编号').input_value()
        with ui.expect_response('**/depotHead/addDepotHeadAndDetail') as saved:
            modal.get_by_role('button',name=re.compile(r'^保\s*存$')).click()
        assert saved.value.json()['code']==200,saved.value.json()
        expect(modal).to_be_hidden()
        assert stock(client,data,default_depot)==expected_stock
        detail=client.get('/depotHead/getDetailByNumber',number=number)
        assert detail['code']==200 and detail['data']['number']==number
        register_ui_document(data,detail['data'])
        documents.append({'number':number,'stock':expected_stock,'response':saved.value.json(),'detail':detail})
    (ROOT/'artifacts/ui-purchase-sale-evidence.json').write_text(json.dumps({'data':data,'depot':default_depot,'documents':documents},ensure_ascii=False,indent=2),encoding='utf-8')
