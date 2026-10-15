import os
from erp_client import ROOT, redis_read
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'tools/pw-browsers')
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1440,'height':1000})
    with page.expect_response('**/user/randomImage') as image:
        page.goto('http://127.0.0.1:3000',wait_until='networkidle')
    data=image.value.json()['data']
    page.get_by_placeholder('请输入用户名').fill('jsh')
    page.get_by_placeholder('请输入密码',exact=True).fill('123456')
    page.get_by_placeholder('请输入验证码').fill(redis_read('captcha_codes:'+data['uuid']))
    page.get_by_role('button',name='登 录').click()
    page.wait_for_url('**/dashboard/analysis',timeout=30000)
    print(page.locator('body').inner_text())
    print(page.locator('input').evaluate_all('(els)=>els.map(e=>({id:e.id,placeholder:e.placeholder,type:e.type}))'))
    page.screenshot(path=str(ROOT/'artifacts/login-page.png'))
    browser.close()
