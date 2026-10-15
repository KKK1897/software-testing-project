import hashlib

from helpers.api_client import ERP
from helpers.inventory_data import ok


def test_correct_login(client):
    """正确登录后会话返回当前用户且不泄露密码。"""
    response = ok(client.get('/user/getUserSession'))
    assert response['data']['user']['loginName'] == 'jsh'
    assert response['data']['user'].get('password') is None


def test_wrong_password():
    with ERP() as client:
        body = {'loginName': 'jsh', 'password': hashlib.md5(b'incorrect').hexdigest(), **client.captcha()}
        response = client.post('/user/login', body)
        assert response['code'] == 200, response
        assert response['data']['msgTip'] == 'user password error', response
        assert 'token' not in response['data']


def test_wrong_captcha():
    with ERP() as client:
        captcha = client.captcha()
        captcha['code'] = 'WRONG'
        body = {'loginName': 'jsh', 'password': hashlib.md5(b'123456').hexdigest(), **captcha}
        response = client.post('/user/login', body)
        assert response['code'] == 500010, response
        assert 'token' not in response.get('data', {})


def test_logout_invalidates_token(client):
    response_body = client.get('/user/logout')
    # 固定版本logout未设置成功码，沿用BaseResponseInfo默认400/null。
    # 退出是否成功必须以下一次携带原Token访问会话确实失效为准。
    assert response_body == {'code': 400, 'data': None}, response_body
    response = client.request('GET', '/user/getUserSession')
    # 该固定版本会话失效使用HTTP500纯文本，与业务JSON错误码不同。
    assert response.status_code == 500
    assert response.text == 'loginOut'


def test_anonymous_cannot_read_stock():
    with ERP() as client:
        response = client.request('GET', '/material/getListWithStock')
        assert response.status_code == 500
        assert response.text == 'loginOut'
