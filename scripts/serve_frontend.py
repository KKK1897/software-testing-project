"""本机静态页面服务 + 后端反向代理，与官方 Nginx 路由语义对应。"""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT/'upstream/jshERP/jshERP-web/dist'), **kwargs)
    def proxy(self):
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        headers = {k:v for k,v in self.headers.items() if k.lower() not in ('host','connection','accept-encoding')}
        with requests.Session() as session:
            session.trust_env = False
            r = session.request(self.command, 'http://127.0.0.1:9999'+self.path, data=body, headers=headers, timeout=30)
        self.send_response(r.status_code)
        for k,v in r.headers.items():
            if k.lower() not in ('transfer-encoding','content-encoding','content-length','connection'):
                self.send_header(k,v)
        self.send_header('Content-Length', str(len(r.content)))
        self.end_headers()
        self.wfile.write(r.content)
    def do_GET(self):
        if self.path.startswith('/jshERP-boot/'):
            return self.proxy()
        if not Path(self.translate_path(self.path)).exists():
            self.path='/index.html'
        return super().do_GET()
    do_POST = proxy
    do_PUT = proxy
    do_DELETE = proxy
ThreadingHTTPServer(('127.0.0.1', 3000), Handler).serve_forever()
