import io
import json
from pathlib import Path
import re
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
import zipfile
from xml.etree import ElementTree

from beginner.ai_testing.case_generator import build_suite, requirements_from_text
from beginner.ai_testing.case_export import export
from beginner.ai_testing.file_parser import extract_text
from beginner.ai_testing import server

DOC = '登录密码连续错误5次，账号锁定30分钟。\n只读用户不能新增仓库。'


class GenerationTests(unittest.TestCase):
    def test_local_coverage_traceability_and_unknowns(self):
        suite = build_suite('需求.md', DOC)
        self.assertEqual({c['requirement_id'] for c in suite['cases']}, {'REQ-001','REQ-002'})
        self.assertTrue(all(c['source_text'] in DOC and c['source'].startswith('需求.md:L') for c in suite['cases']))
        self.assertTrue(all(c['review'] == '待审核' for c in suite['cases']))
        self.assertIn('待确认', str(suite))

    def test_unrelated_empty_and_oversized_rejected(self):
        for text in ('', '今天天气晴朗，花园里的花开了。', '需求' * 17000):
            with self.assertRaises(ValueError): requirements_from_text(text)

    def model_payload(self):
        return json.dumps({'cases': [{'requirement_id':'REQ-001','point':'锁定阈值','title':'连续5次密码错误锁定','priority':'P1','category':'边界','preconditions':['正常账号'],'steps':['连续输错5次密码','尝试登录'],'expected':'账号锁定30分钟','questions':['第4次错误后的提示待确认']}]}, ensure_ascii=False)

    def test_model_schema_and_source_are_checked(self):
        with patch('beginner.ai_testing.case_generator.generate', return_value=self.model_payload()) as mock:
            suite = build_suite('login.txt', DOC.splitlines()[0], True)
        self.assertEqual(suite['mode'], '模型生成')
        self.assertEqual(suite['cases'][0]['source_text'], DOC.splitlines()[0])
        self.assertTrue(mock.called)

    def test_model_missing_requirement_is_not_saved_as_success(self):
        with patch('beginner.ai_testing.case_generator.generate', return_value=self.model_payload()):
            with self.assertRaisesRegex(ValueError, '遗漏'): build_suite('req.txt', DOC, True)

    def test_invalid_model_source_and_json_rejected(self):
        for response in ('not json', self.model_payload().replace('REQ-001','REQ-999')):
            with patch('beginner.ai_testing.case_generator.generate', return_value=response):
                with self.assertRaises(ValueError): build_suite('req.txt', DOC, True)

    def test_exports_preserve_chinese_and_neutralize_formulas(self):
        suite = build_suite('需求.txt', DOC)
        suite['cases'][0]['title'] = '=HYPERLINK("evil")'
        csv_bytes, _ = export(suite, 'csv')
        self.assertIn("'=HYPERLINK", csv_bytes.decode('utf-8-sig'))
        xlsx, _ = export(suite, 'xlsx')
        with zipfile.ZipFile(io.BytesIO(xlsx)) as z:
            sheet = ElementTree.fromstring(z.read('xl/worksheets/sheet1.xml'))
            self.assertFalse(list(sheet.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}f')))
            self.assertIn('需求.txt', z.read('xl/worksheets/sheet1.xml').decode())
        self.assertEqual(len(json.loads(export(suite,'json')[0])['cases']),len(suite['cases']))

    def test_docx_and_pdf_parsing(self):
        from pypdf import PdfWriter
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'req.docx'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>只读用户不能新增仓库。</w:t></w:r></w:p></w:body></w:document>')
            self.assertEqual(extract_text(path),'只读用户不能新增仓库。')
            pdf = Path(temp)/'blank.pdf'; writer = PdfWriter(); writer.add_blank_page(300,300); writer.write(pdf)
            self.assertEqual(extract_text(pdf),'')


class HttpWorkflowTests(unittest.TestCase):
    def test_upload_edit_review_and_download_no_model_or_erp(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(server,'PROJECT_ROOT',Path(temp)), patch('beginner.ai_testing.case_generator.generate') as model:
            httpd = server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            thread = threading.Thread(target=httpd.serve_forever,daemon=True); thread.start()
            base = 'http://127.0.0.1:' + str(httpd.server_port)
            try:
                home = urlopen(base).read().decode()
                self.assertNotIn('<script',home)
                token = re.search('name="token" value="([^"]+)"',home).group(1)
                boundary = '----testboundary'
                body = (f'--{boundary}\r\nContent-Disposition: form-data; name="token"\r\n\r\n{token}\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="requirements.txt"\r\nContent-Type: text/plain\r\n\r\n{DOC}\r\n--{boundary}--\r\n').encode()
                response = urlopen(Request(base+'/api/upload',body,{'Content-Type':'multipart/form-data; boundary='+boundary}))
                job = response.url.split('/')[-1]
                self.assertIn('TC-001',response.read().decode())
                suite = json.loads(urlopen(base+'/export/'+job+'/json').read())
                case = suite['cases'][0]
                fields = {k:'\n'.join(v) if isinstance(v,list) else v for k,v in case.items()}
                fields.update(token=token,review='已确认',review_note='已核对需求',expected='人工确认的预期')
                urlopen(Request(base+'/review/'+job+'/'+case['id'],urlencode(fields).encode())).read()
                updated = json.loads(urlopen(base+'/export/'+job+'/json').read())
                self.assertEqual(updated['cases'][0]['review'],'已确认')
                self.assertEqual(updated['cases'][0]['expected'],'人工确认的预期')
                self.assertTrue(zipfile.is_zipfile(io.BytesIO(urlopen(base+'/export/'+job+'/xlsx').read())))
                with self.assertRaises(HTTPError) as error: urlopen(Request(base+'/api/upload',body,{'Content-Type':'multipart/form-data; boundary='+boundary,'Origin':'https://other.example'}))
                self.assertEqual(error.exception.code,400)
                model.assert_not_called()
            finally:
                httpd.shutdown(); httpd.server_close(); thread.join()


if __name__ == '__main__': unittest.main()
