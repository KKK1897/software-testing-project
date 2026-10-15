"""Requests会话、真实验证码登录与脱敏证据；只允许指定本机ERP。"""
import hashlib
import json
import os
import socket
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'beginner' / 'artifacts'
OUTPUT.mkdir(parents=True, exist_ok=True)
BASE = os.getenv('ERP_BASE_URL', 'http://127.0.0.1:9999/jshERP-boot')
assert BASE == 'http://127.0.0.1:9999/jshERP-boot', '学习入口仅测试本机9999业务基线'
HISTORY = []
_last_write = 0.0


def redact(value):
    """递归隐藏身份凭据、验证码图像及联系信息。"""
    private_fields = ('password', 'token', 'cookie', 'secret', 'telephone', 'phonenum', 'email', 'base64', 'contacts', 'address', 'companytel')
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            sensitive = any(word in key.lower() for word in private_fields)
            sensitive = sensitive or key.lower() in ('code', 'uuid') and isinstance(item, str)
            result[key] = '[REDACTED]' if sensitive else redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def redis_read(key):
    """仅从本项目Redis读取验证码，不关闭或绕过ERP验证码校验。"""
    assert key.startswith('captcha_codes:')
    settings = json.loads((ROOT / 'runtime/local.json').read_text(encoding='utf-8'))

    def send(connection, *arguments):
        payload = b'*' + str(len(arguments)).encode() + b'\r\n'
        for argument in arguments:
            raw = argument.encode()
            payload += b'$' + str(len(raw)).encode() + b'\r\n' + raw + b'\r\n'
        connection.sendall(payload)

    with socket.create_connection(('127.0.0.1', 16379), timeout=5) as connection:
        stream = connection.makefile('rb')
        send(connection, 'AUTH', settings['redis_password'])
        assert stream.readline() == b'+OK\r\n', '本机Redis认证失败'
        send(connection, 'GET', key)
        header = stream.readline()
        assert header.startswith(b'$') and header != b'$-1\r\n', '验证码不存在或过期'
        return stream.read(int(header[1:-2])).decode().strip('"')


class ERP:
    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers['Accept'] = 'application/json'

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.session.close()

    def request(self, method, path, **kwargs):
        """返回原始响应并记录HTTP状态；业务码由用例明确断言。"""
        global _last_write
        assert path.startswith('/') and '://' not in path
        if method in ('POST', 'PUT', 'DELETE'):
            # 上游LogService同秒重复写入会注销登录；只对普通写请求控制节奏。
            remaining = 2.1 - (time.monotonic() - _last_write)
            if remaining > 0:
                time.sleep(remaining)
            _last_write = time.monotonic()
        try:
            response = self.session.request(method, BASE + path, timeout=(5, 25), **kwargs)
        except requests.RequestException as error:
            HISTORY.append({'method': method, 'path': path, 'request': redact(kwargs), 'connection_error': type(error).__name__})
            raise
        try:
            body = response.json()
        except ValueError:
            body = response.text[:4000]
        HISTORY.append(redact({'method': method, 'path': path, 'request': kwargs, 'http_status': response.status_code, 'response': body}))
        return response

    def get(self, path, **params):
        response = self.request('GET', path, params=params)
        assert response.status_code == 200, f'HTTP状态异常: {response.status_code}'
        return response.json()

    def post(self, path, body):
        response = self.request('POST', path, json=body)
        assert response.status_code == 200, f'HTTP状态异常: {response.status_code}'
        return response.json()

    def change(self, method, path, **kwargs):
        response = self.request(method, path, **kwargs)
        assert response.status_code == 200, f'HTTP状态异常: {response.status_code}'
        return response.json()

    def captcha(self):
        response = self.get('/user/randomImage')
        assert response['code'] == 200, response
        image = response['data']
        return {'uuid': image['uuid'], 'code': redis_read('captcha_codes:' + image['uuid'])}

    def login(self, name='jsh', password='123456'):
        """按真实协议提交MD5密码和一次性验证码，保存当前Session的Token。"""
        body = {
            'loginName': name,
            'password': hashlib.md5(password.encode()).hexdigest(),
            **self.captcha(),
        }
        response = self.post('/user/login', body)
        assert response['code'] == 200, response
        assert response['data']['msgTip'] == 'user can login', response
        self.session.headers['X-Access-Token'] = response['data']['token']
        return response

    def listing(self, kind, search=None, page=1, size=100):
        response = self.get(
            '/' + kind + '/list',
            search=json.dumps(search or {}, ensure_ascii=False),
            currentPage=page,
            pageSize=size,
        )
        assert response['code'] == 200, response
        return response['data']
