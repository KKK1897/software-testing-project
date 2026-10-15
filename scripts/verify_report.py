"""实际浏览器打开本机Allure，核对统计并留截图。"""
import functools,json,os,threading,argparse
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from erp_client import ROOT
os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(ROOT/'tools/pw-browsers')
from playwright.sync_api import sync_playwright,expect

def verify(shareable=False):
    directory=ROOT/('artifacts/shareable/allure-acceptance-report' if shareable else 'artifacts/allure-acceptance-report')
    summary=json.loads((directory/'widgets/summary.json').read_text(encoding='utf-8'))
    assert summary['statistic']=={'failed':3,'broken':0,'skipped':0,'passed':37,'unknown':0,'total':40},summary['statistic']
    patch=json.loads((ROOT/'artifacts/allure-patch-report/widgets/summary.json').read_text(encoding='utf-8'))
    assert patch['statistic']['total']==6 and patch['statistic']['passed']==6,patch['statistic']
    handler=functools.partial(SimpleHTTPRequestHandler,directory=str(directory))
    server=ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            try:
                page=browser.new_page(viewport={'width':1440,'height':1000})
                page.goto(f'http://127.0.0.1:{server.server_port}',wait_until='networkidle')
                expect(page.get_by_text('test cases',exact=True)).to_be_visible()
                expect(page.get_by_text('40',exact=True).first).to_be_visible()
                page.screenshot(path=str(ROOT/('artifacts/allure-shareable-overview.png' if shareable else 'artifacts/allure-acceptance-overview.png')),full_page=True)
                (ROOT/'artifacts/allure-overview-text.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
                failed=next(json.loads(f.read_text(encoding='utf-8')) for f in (directory/'data/test-cases').glob('*.json') if json.loads(f.read_text(encoding='utf-8')).get('name')=='test_concurrent_duplicate_document_integrity')
                page.goto(f'http://127.0.0.1:{server.server_port}/#testresult/{failed["uid"]}',wait_until='networkidle')
                expect(page.get_by_text(failed['name'],exact=True).first).to_be_visible()
            finally:browser.close()
    finally:server.shutdown();server.server_close();thread.join(timeout=3)
    print('Allure页面真实打开；基线40/37/3和补丁6/6统计一致。')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--shareable',action='store_true');args=parser.parse_args()
    verify(args.shareable)
