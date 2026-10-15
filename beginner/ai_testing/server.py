"""All-Python HTML rendering, upload, review and download; no JavaScript."""
from email import policy
from email.parser import BytesParser
from html import escape as h
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import parse_qs, urlparse
from uuid import uuid4
from .case_generator import build_suite
from .case_export import export
from .file_parser import ALLOWED_SUFFIXES, MAX_BYTES, UploadError, extract_text
from .llm import LLMUnavailable, LLMCallError, key_configured

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()

def layout(body):
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>AI 测试用例生成与评审</title><style>body{max-width:1050px;margin:30px auto;padding:0 20px;font:16px system-ui;line-height:1.7;background:#f4f7fb;color:#172033}section,article{background:white;padding:22px;margin:18px 0;border:1px solid #dbe3ee;border-radius:12px}button{background:#175cd3;color:white;padding:10px 18px;border:0;border-radius:6px;cursor:pointer}textarea{display:block;width:95%;min-height:65px;padding:8px}input,select{padding:7px}small{color:#516177}nav a{margin-right:18px}blockquote{border-left:3px solid #9db7dd;padding-left:14px;white-space:pre-wrap}label{display:block;margin:10px 0}</style><nav><a href="/">上传文档</a></nav>' + body + '</html>'

def csrf():
    return '<input type="hidden" name="token" value="' + TOKEN + '">'

def homepage():
    status = '已读取密钥（尚未验证有效性）' if key_configured() else '未读取到密钥，请配置后重启服务'
    return layout('<h1>AI 测试用例生成与评审工作台</h1><p>模型配置状态：' + status + '</p><p>上传需求、接口说明或测试文档，生成带来源的测试点和结构化测试用例。</p><section><form action="/api/upload" method="post" enctype="multipart/form-data">' + csrf() + '<label>需求文件 <input type="file" name="file" accept=".txt,.md,.docx,.pdf" required></label><label>生成方式 <select name="use_model"><option value="false">本地规则模板（无需密钥）</option><option value="true">AI 模型生成（需配置密钥）</option></select></label><p><small>单文件最多 3 MB、文字最多 32000 字符。AI 模式会将文档文字发送至配置的模型服务；扫描 PDF 请先 OCR。</small></p><button>生成测试点与用例</button></form></section><p>可逐条编辑、审核，并导出 Excel、CSV、Markdown、JSON。候选用例不会自动执行。</p>')

def suite_page(job, suite):
    parts = [f'<h1>{h(suite["filename"])} — 测试用例</h1><p>模式：{h(suite["mode"])} ｜需求 {len(suite["requirements"])} 条｜候选用例 {len(suite["cases"])} 条</p><p>{h(suite["notice"])}</p><nav>']
    parts.extend(f'<a href="/export/{job}/{kind}">导出 {kind.upper()}</a>' for kind in ('xlsx', 'csv', 'md', 'json'))
    parts.append('</nav>')
    for c in suite['cases']:
        parts.append(f'<article><h2>{h(c["id"])} · {h(c["title"])}</h2><p>需求 {h(c["requirement_id"])} ｜{h(c["priority"])} ｜{h(c["category"])}</p><blockquote>{h(c["source"])}\n{h(c["source_text"])}</blockquote>')
        parts.append(f'<form action="/review/{job}/{c["id"]}" method="post">' + csrf())
        for key, label in (('point','测试点'),('title','用例名称'),('preconditions','前置条件（每行一项）'),('steps','操作步骤（每行一步）'),('expected','预期结果'),('questions','待确认项'),('review_note','审核备注')):
            value = '\n'.join(c[key]) if isinstance(c[key], list) else c[key]
            parts.append(f'<label>{label}<textarea name="{key}">{h(value)}</textarea></label>')
        parts.append('<label>审核状态<select name="review">' + ''.join(f'<option {"selected" if c["review"] == s else ""}>{s}</option>' for s in ('待审核','已确认','需修改','已排除')) + '</select></label><button>保存修改和审核状态</button></form></article>')
    return layout(''.join(parts))

class Handler(BaseHTTPRequestHandler):
    def send_body(self, status, body, mime='text/html; charset=utf-8', filename=None):
        if isinstance(body, str): body = body.encode('utf-8')
        self.send_response(status); self.send_header('Content-Type', mime); self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        if filename: self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
        self.end_headers(); self.wfile.write(body)

    def job_path(self, job):
        if len(job) != 32 or any(c not in '0123456789abcdef' for c in job): raise ValueError('无效任务编号')
        return PROJECT_ROOT / 'beginner/artifacts/ai/case_jobs' / job

    def read_suite(self, job):
        return json.loads((self.job_path(job) / 'cases.json').read_text(encoding='utf-8'))

    def do_GET(self):
        parts = urlparse(self.path).path.strip('/').split('/')
        try:
            if parts == ['']: self.send_body(200, homepage())
            elif len(parts) == 2 and parts[0] == 'suite': self.send_body(200, suite_page(parts[1], self.read_suite(parts[1])))
            elif len(parts) == 3 and parts[0] == 'export':
                body, mime = export(self.read_suite(parts[1]), parts[2]); self.send_body(200, body, mime, 'test-cases.' + parts[2])
            else: self.send_body(404, layout('<p>页面不存在</p>'))
        except (ValueError, FileNotFoundError): self.send_body(404, layout('<p>任务或导出格式不存在</p>'))

    def do_POST(self):
        try:
            host, origin = self.headers.get('Host',''), self.headers.get('Origin')
            if origin and origin != 'http://' + host: raise ValueError('拒绝跨站请求')
            if self.path == '/api/upload': self.upload()
            elif self.path.startswith('/review/'): self.review()
            else: self.send_body(404, layout('<p>接口不存在</p>'))
        except (LLMUnavailable, LLMCallError) as exc: self.send_body(502, layout('<h1>模型调用失败</h1><p>' + h(str(exc)) + '</p>'))
        except (UploadError, ValueError) as exc: self.send_body(400, layout('<h1>无法完成</h1><p>' + h(str(exc)) + '</p>'))
        except Exception: self.send_body(502, layout('<h1>生成失败</h1><p>请检查模型密钥、网络和配置，或选择本地规则模式。错误结果未作为成功用例保存。</p>'))

    def redirect(self, job):
        self.send_response(303); self.send_header('Location','/suite/' + job); self.send_header('Content-Length','0'); self.end_headers()

    def upload(self):
        size = int(self.headers.get('Content-Length','0'))
        if not 0 < size <= MAX_BYTES + 16384: raise UploadError('上传内容为空或超过 3 MB')
        content_type = self.headers.get('Content-Type','')
        if not content_type.startswith('multipart/form-data'): raise UploadError('需要文件上传')
        message = BytesParser(policy=policy.default).parsebytes(('Content-Type: ' + content_type + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + self.rfile.read(size))
        fields = {p.get_param('name', header='content-disposition'): p for p in message.iter_parts()}
        if 'token' not in fields or str(fields['token'].get_content()).strip() != TOKEN: raise ValueError('页面已过期，请重新打开首页')
        part = fields.get('file')
        if part is None or not part.get_filename(): raise UploadError('请选择文件')
        filename = Path(str(part.get_filename()).replace('\\','/')).name
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES: raise UploadError('仅支持 TXT、Markdown、Word 和 PDF')
        data = part.get_payload(decode=True) or b''
        if not data or len(data) > MAX_BYTES: raise UploadError('文件为空或超过 3 MB')
        job = uuid4().hex; folder = self.job_path(job); folder.mkdir(parents=True)
        target = folder / ('source' + suffix); target.write_bytes(data)
        text = extract_text(target); (folder / 'extracted.txt').write_text(text, encoding='utf-8')
        use_model = 'use_model' in fields and str(fields['use_model'].get_content()).strip() == 'true'
        suite = build_suite(filename, text, use_model)
        (folder / 'cases.json').write_text(json.dumps(suite, ensure_ascii=False, indent=2), encoding='utf-8'); self.redirect(job)

    def review(self):
        parts = self.path.strip('/').split('/')
        if len(parts) != 3: raise ValueError('无效审核地址')
        _, job, case_id = parts
        size = int(self.headers.get('Content-Length','0'))
        if not 0 < size <= 100000: raise ValueError('审核内容过长')
        fields = parse_qs(self.rfile.read(size).decode('utf-8'), keep_blank_values=True)
        if fields.get('token',[''])[0] != TOKEN: raise ValueError('页面已过期，请重新打开首页')
        with LOCK:
            suite = self.read_suite(job); case = next((c for c in suite['cases'] if c['id'] == case_id), None)
            if case is None: raise ValueError('用例不存在')
            status = fields.get('review',[''])[0]
            if status not in {'待审核','已确认','需修改','已排除'}: raise ValueError('审核状态无效')
            for key in ('point','title','preconditions','steps','expected','questions','review_note'):
                value = fields.get(key,[''])[0].strip()
                if key in {'point','title','steps','expected'} and not value: raise ValueError('测试点、名称、步骤和预期不能为空')
                case[key] = [v.strip() for v in value.splitlines() if v.strip()] if key in {'preconditions','steps','questions'} else value
            case['review'] = status
            (self.job_path(job) / 'cases.json').write_text(json.dumps(suite, ensure_ascii=False, indent=2), encoding='utf-8')
        self.redirect(job)

def main():
    print('AI 测试用例生成与评审：http://127.0.0.1:8765')
    ThreadingHTTPServer(('127.0.0.1',8765), Handler).serve_forever()

if __name__ == '__main__': main()
