import os,runpy,json,re
from erp_client import ROOT
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'tools/pw-browsers')
from playwright.sync_api import sync_playwright
login=runpy.run_path(str(ROOT/'tests/test_ui.py'))['login']
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1920,'height':1080})
    login(page)
    page.get_by_text('采购管理',exact=True).click()
    page.get_by_text('采购入库',exact=True).click()
    print(page.get_by_role('button').all_text_contents(),flush=True)
    page.get_by_role('button',name=re.compile('新增')).first.click()
    page.wait_for_load_state('networkidle')
    if page.locator('.introjs-skipbutton').is_visible():page.locator('.introjs-skipbutton').click()
    print(page.locator('.ant-modal:visible').inner_text())
    print(json.dumps(page.locator('.ant-modal:visible input').evaluate_all('(els)=>els.map(e=>({id:e.id,placeholder:e.placeholder,role:e.getAttribute("role"),value:e.value}))'),ensure_ascii=False))
    page.screenshot(path=str(ROOT/'artifacts/purchase-form.png'))
    browser.close()
