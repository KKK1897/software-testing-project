"""串行执行1/3/5用户JMeter库存查询，保留原始结果和资源观测。"""
import csv
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'beginner'))
sys.path.insert(0, str(PROJECT / 'scripts'))
from helpers.api_client import ERP, OUTPUT, redact
from execution_lock import execution_lock


def percentile(values, fraction):
    """按排序样本线性插值计算百分位。"""
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def run():
    directory = OUTPUT / 'performance' / datetime.now().strftime('%Y%m%d-%H%M%S')
    directory.mkdir(parents=True)
    properties = PROJECT / 'runtime/beginner-jmeter.properties'
    backend_log = PROJECT / 'runtime/logs.home_IS_UNDEFINED/jshERP.log'
    offset = backend_log.stat().st_size
    summary = {
        'status': '运行中',
        'hardware': {'logical_cpus': psutil.cpu_count(), 'memory_gib': psutil.virtual_memory().total / 1024**3, 'os': platform.platform()},
        'stages': [],
    }
    java = PROJECT / 'tools/jdk8u472-b08/bin/java.exe'
    jmeter = PROJECT / 'tools/apache-jmeter-5.6.3/bin/ApacheJMeter.jar'
    plan = Path(__file__).with_name('stock-query.jmx')
    try:
        with ERP() as client:
            client.login()
            summary['data_count'] = client.listing('material')['total']
            summary['query_match_count'] = client.get('/material/getListWithStock', currentPage=1, pageSize=20, materialParam='QA_', zeroStock=0)['data']['total']
            properties.write_text('qa.token=' + client.session.headers['X-Access-Token'] + '\n', encoding='ascii')
        for users in [1, 3, 5]:
            result_file = directory / f'{users}users.jtl'
            command = [
                str(java), '-Xms128m', '-Xmx512m', '-jar', str(jmeter),
                '-n', '-t', str(plan), '-q', str(properties), f'-Jusers={users}',
                '-l', str(result_file), '-j', str(directory / f'{users}users.log'),
            ]
            resources = []
            high_cpu_seconds = 0
            with (directory / f'{users}users.stdout.log').open('w', encoding='utf-8') as log:
                process = subprocess.Popen(command, cwd=PROJECT, stdout=log, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 65
                try:
                    while process.poll() is None:
                        cpu = psutil.cpu_percent(interval=1)
                        memory = psutil.virtual_memory()
                        services = []
                        for service in psutil.process_iter(['name', 'cmdline']):
                            try:
                                owned = str(PROJECT).lower() in ' '.join(service.info['cmdline'] or []).lower()
                                if owned and service.info['name'] in ('java.exe', 'mysqld.exe', 'redis-server.exe'):
                                    services.append({'pid': service.pid, 'name': service.info['name'], 'rss': service.memory_info().rss})
                            except (psutil.AccessDenied, psutil.NoSuchProcess):
                                continue
                        resources.append({'time': time.time(), 'cpu_percent': cpu, 'available_bytes': memory.available, 'services': services})
                        high_cpu_seconds = high_cpu_seconds + 1 if cpu > 90 else 0
                        if memory.available < 1024**3 or high_cpu_seconds >= 15 or time.monotonic() > deadline:
                            raise RuntimeError('CPU/内存/65秒时限触发停止条件')
                    assert process.returncode == 0, f'JMeter退出码{process.returncode}'
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)
                    (directory / f'{users}users.resources.json').write_text(json.dumps(resources, indent=2), encoding='utf-8')
            with result_file.open(encoding='utf-8-sig') as stream:
                rows = list(csv.DictReader(stream))
            assert rows, 'JMeter没有生成样本'
            first_time = min(int(row['timeStamp']) for row in rows)
            measured = [row for row in rows if int(row['timeStamp']) >= first_time + 10000]
            assert measured, '预热后没有可统计样本'
            elapsed = [int(row['elapsed']) for row in measured]
            start = min(int(row['timeStamp']) for row in measured)
            end = max(int(row['timeStamp']) + int(row['elapsed']) for row in measured)
            seconds = (end - start) / 1000
            stage = {
                'users': users, 'samples': len(measured), 'measurement_seconds': seconds,
                'p50_ms': percentile(elapsed, .5), 'p95_ms': percentile(elapsed, .95),
                'throughput_rps': len(measured) / seconds,
                'error_rate': sum(row['success'] != 'true' for row in measured) / len(measured),
                'all_sample_error_rate': sum(row['success'] != 'true' for row in rows) / len(rows),
                'cpu_max_percent': max(sample['cpu_percent'] for sample in resources),
                'available_min_gib': min(sample['available_bytes'] for sample in resources) / 1024**3,
                'jtl': result_file.name,
            }
            summary['stages'].append(stage)
            print(json.dumps(stage, ensure_ascii=False), flush=True)
            if stage['all_sample_error_rate'] > .05:
                raise RuntimeError('含预热的业务错误率超过5%，不再升级负载')
        summary['status'] = '通过' if all(stage['all_sample_error_rate'] == 0 for stage in summary['stages']) else '失败'
    except Exception as error:
        summary['status'] = '准备错误' if not summary['stages'] else '失败'
        summary['error'] = str(error)
        raise
    finally:
        properties.unlink(missing_ok=True)
        with backend_log.open('rb') as stream:
            stream.seek(offset)
            log_text = stream.read().decode('utf-8', errors='replace')
        summary['backend_log_observation'] = {
            'source': str(backend_log.relative_to(PROJECT)), 'start_byte': offset,
            'observed_lines': len(log_text.splitlines()),
            'WARN': len(re.findall(r'\bWARN\b', log_text)),
            'ERROR': len(re.findall(r'\bERROR\b', log_text)),
        }
        (directory / 'summary.json').write_text(json.dumps(redact(summary), ensure_ascii=False, indent=2), encoding='utf-8')
        (OUTPUT / 'performance/latest.txt').write_text(str(directory), encoding='utf-8')
        print('原始结果：' + str(directory), flush=True)


if __name__ == '__main__':
    with execution_lock():
        run()
