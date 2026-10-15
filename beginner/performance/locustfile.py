"""库存查询性能任务。先读这个文件，再读负责组织运行的run.py。"""
import csv
import json
import os
import sys
import time
from pathlib import Path

from locust import HttpUser, constant, events, task
from locust.runners import LocalRunner

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'beginner'))
from helpers.api_client import BASE, OUTPUT, redact

SAMPLE_FILE = None
FIELDS = ['start_time', 'response_time_ms', 'http_status', 'business_code', 'success', 'error']


@events.init.add_listener
def prepare_recording(environment, **kwargs):
    """只接受本地runner传入的Token和证据路径，拒绝远程/分布式运行。"""
    global SAMPLE_FILE
    assert isinstance(environment.runner, LocalRunner), '仅支持本机单进程'
    assert (environment.host or InventoryUser.host) == BASE, '只允许本机ERP9999'
    assert os.environ.get('ERP_PERF_TOKEN'), '请使用python performance/run.py启动'
    SAMPLE_FILE = Path(os.environ['ERP_PERF_SAMPLES']).resolve()
    assert SAMPLE_FILE.is_relative_to((OUTPUT / 'locust').resolve())
    with SAMPLE_FILE.open('w', encoding='utf-8', newline='') as stream:
        csv.DictWriter(stream, fieldnames=FIELDS).writeheader()


@events.spawning_complete.add_listener
def record_reached_users(user_count, **kwargs):
    """保存实际完成爬升的用户数，避免把计划人数当成实测人数。"""
    if SAMPLE_FILE is not None:
        SAMPLE_FILE.with_suffix('.users.json').write_text(
            json.dumps({'users': user_count, 'time': time.time()}), encoding='utf-8',
        )


class InventoryUser(HttpUser):
    """每个模拟用户有独立HTTP会话；本场景复用同一个测试账号Token。"""
    host = BASE
    wait_time = constant(0.2)

    def on_start(self):
        """负载开始前带上已有登录身份，查询耗时不包含登录。"""
        assert self.host == BASE, '禁止访问非本地ERP'
        self.client.trust_env = False
        self.client.headers.update({
            'Accept': 'application/json',
            'X-Access-Token': os.environ['ERP_PERF_TOKEN'],
        })

    @task
    def query_stock(self):
        """查询QA商品库存；HTTP成功和业务成功必须同时满足。"""
        with self.client.get(
            '/material/getListWithStock',
            params={'currentPage': 1, 'pageSize': 20, 'materialParam': 'QA_', 'zeroStock': 0},
            name='库存查询',
            timeout=(3, 5),
            allow_redirects=False,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f'HTTP状态异常：{response.status_code}')
                return
            try:
                body = response.json()
            except ValueError:
                response.failure('响应不是JSON')
                return
            if not isinstance(body, dict) or body.get('code') != 200:
                response.failure('业务码不是200')
                return
            data = body.get('data')
            if not isinstance(data, dict):
                response.failure('data不是对象')
            elif not isinstance(data.get('rows'), list) or not isinstance(data.get('total'), (int, float)):
                response.failure('库存列表结构错误')
            else:
                response.success()


@events.request.add_listener
def record_sample(response_time, exception, response=None, start_time=None, **kwargs):
    """保存逐请求耗时，失败附脱敏响应；不保存请求头和Token。"""
    if SAMPLE_FILE is None:
        return
    body = None
    if response is not None:
        try:
            body = response.json()
        except ValueError:
            body = response.text[:1000]
    record = {
        'start_time': start_time if start_time is not None else time.time() - response_time / 1000,
        'response_time_ms': response_time,
        'http_status': response.status_code if response is not None else 0,
        'business_code': body.get('code') if isinstance(body, dict) else None,
        'success': exception is None,
        'error': str(exception) if exception is not None else '',
    }
    with SAMPLE_FILE.open('a', encoding='utf-8', newline='') as stream:
        csv.DictWriter(stream, fieldnames=FIELDS).writerow(record)
    if exception is not None:
        failure = {**record, 'response': redact(body)}
        with SAMPLE_FILE.with_suffix('.failures.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(failure, ensure_ascii=False) + '\n')
