"""Locust断言的离线检查：不请求ERP，不计入19条业务接口用例。"""
import csv
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from performance import locustfile


@pytest.mark.parametrize('status,body,invalid_json,expected_failure', [
    (200, {'code': 200, 'data': {'rows': [], 'total': 0}}, False, False),
    (500, {'code': 200, 'data': {'rows': [], 'total': 0}}, False, True),
    (200, {'code': 500, 'data': '查询失败'}, False, True),
    (200, None, True, True),
    (200, [], False, True),
    (200, {'code': 200, 'data': None}, False, True),
    (200, {'code': 200, 'data': {'rows': None, 'total': 0}}, False, True),
    (200, {'code': 200, 'data': {'rows': [], 'total': None}}, False, True),
])
def test_stock_response_classification(status, body, invalid_json, expected_failure):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = body
    if invalid_json:
        response.json.side_effect = ValueError('invalid JSON')
    response.__enter__.return_value = response
    client = MagicMock()
    client.get.return_value = response
    user = SimpleNamespace(client=client)

    locustfile.InventoryUser.query_stock(user)

    assert response.failure.called == expected_failure
    assert response.success.called == (not expected_failure)
    assert client.get.call_args.kwargs['allow_redirects'] is False


def test_failed_response_record_is_redacted(tmp_path, monkeypatch):
    sample_file = tmp_path / 'unit.samples.csv'
    with sample_file.open('w', encoding='utf-8', newline='') as stream:
        csv.DictWriter(stream, fieldnames=locustfile.FIELDS).writeheader()
    monkeypatch.setattr(locustfile, 'SAMPLE_FILE', sample_file)
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {'code': 500, 'token': 'unit-secret-token', 'password': 'unit-secret-password'}

    locustfile.record_sample(
        response_time=12, exception=RuntimeError('业务码不是200'),
        response=response, start_time=100,
    )

    with sample_file.open(encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]['success'] == 'False'
    assert rows[0]['http_status'] == '200'
    assert rows[0]['business_code'] == '500'
    evidence = sample_file.with_suffix('.failures.jsonl').read_text(encoding='utf-8')
    assert 'unit-secret-token' not in evidence
    assert 'unit-secret-password' not in evidence
    assert '[REDACTED]' in evidence
