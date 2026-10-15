"""用Python组织本机Locust逐级负载测试，生成原始记录及中文报告。"""
import argparse
import csv
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import psutil

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'beginner'))
sys.path.insert(0, str(PROJECT / 'scripts'))
from helpers.api_client import BASE, ERP, OUTPUT
from execution_lock import execution_lock


def percentile(values, fraction):
    """对逐请求耗时排序，按位置线性插值计算P50/P95。"""
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def resource_sample():
    """记录宿主CPU/内存及命令行归属本项目的服务RSS。"""
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    services = []
    for service in psutil.process_iter(['name', 'cmdline']):
        try:
            command = ' '.join(service.info['cmdline'] or []).lower()
            if str(PROJECT).lower() in command and service.info['name'] in ('java.exe', 'mysqld.exe', 'redis-server.exe'):
                services.append({'pid': service.pid, 'name': service.info['name'], 'rss': service.memory_info().rss})
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return {'time': time.time(), 'cpu_percent': cpu, 'available_bytes': memory.available, 'services': services}


def run_stage(directory, users, token, duration=30, warmup=10, spawn_rate=None):
    """独立执行一档负载；剔除预热，保留全部失败样本。"""
    sample_file = directory / f'{users}users.samples.csv'
    child_environment = {key: value for key, value in os.environ.items() if not key.startswith('LOCUST_')}
    child_environment.update({
        'ERP_PERF_TOKEN': token,
        'ERP_PERF_SAMPLES': str(sample_file),
        'PYTHONIOENCODING': 'utf-8',
    })
    command = [
        sys.executable, '-m', 'locust',
        '-f', str(Path(__file__).with_name('locustfile.py')),
        '--headless', '--host', BASE,
        '--users', str(users), '--spawn-rate', str(spawn_rate or users / 3),
        '--run-time', f'{duration}s', '--stop-timeout', '5', '--only-summary',
        '--csv', str(directory / f'{users}users'),
        '--html', str(directory / f'{users}users.html'),
        '--logfile', str(directory / f'{users}users.log'),
        '--exit-code-on-error', '1',
    ]
    resources = []
    high_cpu_seconds = 0
    with (directory / f'{users}users.stdout.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=PROJECT / 'beginner', env=child_environment, stdout=log, stderr=subprocess.STDOUT)
        child_environment.pop('ERP_PERF_TOKEN')
        deadline = time.monotonic() + duration + 35
        try:
            while process.poll() is None:
                sample = resource_sample()
                resources.append(sample)
                high_cpu_seconds = high_cpu_seconds + 1 if sample['cpu_percent'] > 90 else 0
                if sample['available_bytes'] < 1024**3 or high_cpu_seconds >= 15 or time.monotonic() > deadline:
                    raise RuntimeError('CPU/内存/单档运行时限触发停止条件')
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            (directory / f'{users}users.resources.json').write_text(json.dumps(resources, indent=2), encoding='utf-8')
    if not sample_file.exists():
        raise RuntimeError(f'Locust没有生成请求记录，退出码{process.returncode}，请检查stdout日志')
    with sample_file.open(encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise RuntimeError('Locust没有实际请求，不能判定为通过')
    failed = sum(row['success'] != 'True' for row in rows)
    if process.returncode not in (0, 1) or process.returncode == 1 and failed == 0:
        raise RuntimeError(f'Locust执行错误：退出码{process.returncode}，请检查日志')
    first_time = min(float(row['start_time']) for row in rows)
    measured = [row for row in rows if float(row['start_time']) >= first_time + warmup]
    if not measured:
        raise RuntimeError('预热后没有测量样本')
    elapsed = [float(row['response_time_ms']) for row in measured]
    start = min(float(row['start_time']) for row in measured)
    end = max(float(row['start_time']) + float(row['response_time_ms']) / 1000 for row in measured)
    seconds = end - start
    users_file = sample_file.with_suffix('.users.json')
    reached = json.loads(users_file.read_text(encoding='utf-8')) if users_file.exists() else {}
    if reached.get('users') != users:
        raise RuntimeError(f'未确认达到目标{users}用户，不能宣称完成该档负载')
    return {
        'users': users, 'status': '失败' if failed else '通过',
        'reached_users': reached['users'],
        'samples': len(measured), 'measurement_seconds': seconds,
        'p50_ms': percentile(elapsed, .5), 'p95_ms': percentile(elapsed, .95),
        'throughput_rps': len(measured) / seconds,
        'error_rate': sum(row['success'] != 'True' for row in measured) / len(measured),
        'all_samples': len(rows), 'all_failures': failed,
        'all_sample_error_rate': failed / len(rows), 'exit_code': process.returncode,
        'cpu_max_percent': max(sample['cpu_percent'] for sample in resources),
        'available_min_gib': min(sample['available_bytes'] for sample in resources) / 1024**3,
        'samples_file': sample_file.name,
    }


def write_report(directory, summary):
    """仅根据这次真实样本生成简明中文报告，不混入旧JMeter结果。"""
    lines = [
        '# Locust库存查询实际报告', '',
        f"时间：{summary['started_at']}；状态：{summary['status']}；Locust {summary['locust_version']}。", '',
        '固定本地jshERP v3.5兼容构建，后端9999；本轮与功能测试、UI、清理、构建串行执行。',
        f"每档{summary['duration_seconds']}秒，首请求起{summary['warmup_seconds']}秒预热剔除；每任务后思考200ms。",
        f"每秒新增用户：{summary['spawn_rate'] or '每档用户数/3'}；达到目标用户的证据见*.samples.users.json。",
        '所有模拟用户使用独立HTTP会话、同一测试账号Token，仅测库存查询，不包含验证码/登录耗时。',
        f"商品总数：{summary.get('data_count', '未取得')}；QA_匹配：{summary.get('query_match_count', '未取得')}；每页20条、隐藏零库存。", '',
        '|用户|状态|测量样本|P50 ms|P95 ms|吞吐 req/s|测量错误率|含预热失败/总数|',
        '|---|---|---|---|---|---|---|---|',
    ]
    for stage in summary['stages']:
        lines.append(
            f"|{stage['users']}|{stage['status']}|{stage['samples']}|{stage['p50_ms']:.2f}|{stage['p95_ms']:.2f}|"
            f"{stage['throughput_rps']:.3f}|{stage['error_rate']:.2%}|{stage['all_failures']}/{stage['all_samples']}|"
        )
    lines += [
        '', 'P50/P95采用原始测量样本线性插值，含失败请求；吞吐=测量样本数/首个测量请求开始至最后完成的秒数。',
        'Locust原生HTML/CSV包含预热且使用其自身统计口径，不能与本表直接混算。',
        'HTTP200仍要检查业务code200及rows/total结构，业务失败不会记为成功；失败响应已脱敏保存。',
        '停止条件：可用内存<1GiB、CPU连续15次采样>90%、单档进程超过计划时长35秒；整档错误率>5%或测量P95>2000ms停止升级。',
        '任意失败样本使该档和整轮标为失败；不足停止阈值仍不代表通过。未执行档位标为未执行。',
        '这是单机、单接口、同一账号的短时闭环负载；用户数不等于同时在途请求数，不代表最大容量、独立账号并发或长时稳定性。',
    ]
    observation = summary.get('backend_log_observation', {})
    lines += ['', '后端日志观察：' + json.dumps(observation, ensure_ascii=False)]
    for stage in summary['stages']:
        lines.append(f"资源{stage['users']}用户：宿主CPU峰值{stage['cpu_max_percent']:.1f}%，可用内存最低{stage['available_min_gib']:.2f}GiB；项目服务RSS见resources.json。")
    if 'error' in summary:
        lines += ['', '中断原因：' + summary['error']]
    lines += ['', '未执行档位：' + str(summary['not_executed_users'])]
    lines += ['', '逐请求CSV、失败响应JSONL、Locust HTML/CSV、进程日志和资源样本均在本报告同目录。']
    (directory / '报告.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def run(user_counts, duration=30, warmup=10, spawn_rate=None):
    directory = OUTPUT / 'locust' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    directory.mkdir(parents=True)
    backend_log = PROJECT / 'runtime/logs.home_IS_UNDEFINED/jshERP.log'
    offset = backend_log.stat().st_size if backend_log.exists() else None
    summary = {
        'status': '准备错误', 'started_at': datetime.now().astimezone().isoformat(),
        'locust_version': version('locust'), 'planned_users': user_counts,
        'duration_seconds': duration, 'warmup_seconds': warmup, 'spawn_rate': spawn_rate,
        'hardware': {'logical_cpus': psutil.cpu_count(), 'memory_gib': psutil.virtual_memory().total / 1024**3, 'os': platform.platform()},
        'stages': [],
    }
    try:
        with ERP() as client:
            client.login()
            summary['data_count'] = client.listing('material')['total']
            summary['query_match_count'] = client.get(
                '/material/getListWithStock', currentPage=1, pageSize=20,
                materialParam='QA_', zeroStock=0,
            )['data']['total']
            token = client.session.headers['X-Access-Token']
        for users in user_counts:
            stage = run_stage(directory, users, token, duration, warmup, spawn_rate)
            summary['stages'].append(stage)
            print(json.dumps(stage, ensure_ascii=False), flush=True)
            if stage['all_sample_error_rate'] > .05:
                raise RuntimeError('含预热业务错误率超过5%，停止升级负载')
            if stage['p95_ms'] > 2000:
                raise RuntimeError('测量P95超过2000ms，停止升级负载')
        summary['status'] = '失败' if any(stage['all_failures'] for stage in summary['stages']) else '通过'
    except Exception as error:
        summary['status'] = '失败' if summary['stages'] else '准备错误'
        summary['error'] = str(error)
        print(f"{summary['status']}：{error}", flush=True)
    finally:
        completed = [stage['users'] for stage in summary['stages']]
        summary['not_executed_users'] = [users for users in user_counts if users not in completed]
        if offset is not None and backend_log.exists():
            with backend_log.open('rb') as stream:
                stream.seek(offset)
                text = stream.read().decode('utf-8', errors='replace')
            events = [line for line in text.splitlines() if re.search(r'\b(WARN|ERROR)\b', line)]
            summary['backend_log_observation'] = {
                'source': str(backend_log.relative_to(PROJECT)), 'start_byte': offset,
                'observed_lines': len(text.splitlines()),
                'WARN': len(re.findall(r'\bWARN\b', text)), 'ERROR': len(re.findall(r'\bERROR\b', text)),
            }
            safe_events = [re.sub(r'(?i)\b[0-9a-f]{32}\b', '[REDACTED]', line) for line in events]
            (directory / 'backend-events.json').write_text(json.dumps(safe_events, ensure_ascii=False, indent=2), encoding='utf-8')
        (directory / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        (OUTPUT / 'locust/latest.txt').write_text(str(directory), encoding='utf-8')
        write_report(directory, summary)
        print('原始结果：' + str(directory), flush=True)
    return 0 if summary['status'] == '通过' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='本地库存查询Locust性能测试')
    parser.add_argument('--users', nargs='+', type=int, choices=[1, 3, 5, 10, 30, 50, 100], default=[1, 3, 5])
    parser.add_argument('--duration', type=int, default=30, help='每档总秒数，30至300')
    parser.add_argument('--warmup', type=int, default=10, help='剔除的预热秒数')
    parser.add_argument('--spawn-rate', type=float, default=None, help='每秒新增用户数，默认每档用户数/3')
    arguments = parser.parse_args()
    if arguments.users != sorted(set(arguments.users)):
        parser.error('用户档位必须去重且升序，例如--users 1 3 5')
    if not 30 <= arguments.duration <= 300 or not 10 <= arguments.warmup <= arguments.duration - 20:
        parser.error('总时长须30至300秒，预热至少10秒且测量至少20秒')
    if arguments.spawn_rate is not None and not 0 < arguments.spawn_rate <= 50:
        parser.error('每秒新增用户数须大于0且不超过50')
    if arguments.warmup < max(arguments.users) / (arguments.spawn_rate or max(arguments.users) / 3) + 5:
        parser.error('预热须覆盖爬升时间并留至少5秒稳定时间')
    with execution_lock():
        sys.exit(run(arguments.users, arguments.duration, arguments.warmup, arguments.spawn_rate))
