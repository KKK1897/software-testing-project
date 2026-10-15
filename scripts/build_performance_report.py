"""从实际JTL汇总和资源样本生成中文报告。"""
import json
from pathlib import Path
from erp_client import ROOT

def main():
    summary=json.loads((ROOT/'artifacts/performance/summary.json').read_text(encoding='utf-8'))
    hardware=summary['hardware']
    lines=['# 性能测试报告','',
    '这是隔离本机、短时、小规模库存查询测试。基线为jshERP v3.5（JDBC兼容构建），后端9999；JMeter5.6.3/JDK8u472/MySQL8.0.46/Redis3.2.100。测试时不运行本项目功能测试、UI、清理或构建任务；宿主其他应用仍可能影响结果。','',
    f'硬件：{hardware.get("processor","未记录型号")}，{hardware["logical_cpus"]}逻辑CPU，内存{hardware["memory_bytes"]/1024**3:.2f}GiB；{hardware.get("os","Windows")}。商品总数{summary["data_count"]}，查询条件QA_匹配{summary.get("query_match_count","本轮未记录")}条。查询每页20条，不将数据量相差很大的历史轮次直接比较。','',
    '## 负载与判定','',
    '预先登录获得本机Token；只测库存查询，不把验证码处理时间算为查询延迟。1、3、5个闭环并发用户逐级执行，各级启动爬升3秒、总运行30秒。每用户请求间隔200毫秒；剔除首个请求起10秒预热，统计剩余约20秒。并发用户是线程数，请求率由响应时间和思考时间共同决定，不是固定RPS。','',
    'HTTP超时为连接3秒/读取5秒。除JMeter HTTP成功状态外，Groovy断言要求JSON业务code200及data.rows/data.total存在，避免错误页或业务失败被算成功。P50/P95按排序样本线性插值计算；吞吐量=测量样本数/从首个测量请求开始至最后一个完成的秒数。','',
    '|并发用户|测量样本|测量秒数|P50(ms)|P95(ms)|吞吐(req/s)|错误率|','|---|---|---|---|---|---|---|']
    resources=[]
    for stage in summary['stages']:
        lines.append(f'|{stage["users"]}|{stage["samples"]}|{stage["measurement_seconds"]:.3f}|{stage["p50_ms"]:.2f}|{stage["p95_ms"]:.2f}|{stage["throughput_rps"]:.3f}|{stage["error_rate"]:.2%}|')
        stamp=Path(stage['jtl']).name.split('-')[0]
        path=ROOT/f'artifacts/performance/{stamp}-{stage["users"]}-resources.json'
        resources.extend(json.loads(path.read_text(encoding='utf-8')))
    if resources:
        lines += ['',f'资源样本：宿主CPU最大{max(r["host_cpu_percent"] for r in resources):.1f}%，可用内存最小{min(r["host_available_bytes"] for r in resources)/1024**3:.2f}GiB。每秒记录Java/MySQL/Redis进程RSS，样本可能包括同名非ERP进程，因此不能将合计直接当ERP独占内存。']
    audit_path=ROOT/'artifacts/performance/backend-log-audit.json'
    if audit_path.exists():
        audit=json.loads(audit_path.read_text(encoding='utf-8'))
        if audit.get('jtl')==[stage['jtl'] for stage in summary['stages']]:
            lines += ['',f'后端日志核对：本轮时间窗{audit["start_local"]}至{audit["end_local"]}，匹配{audit["lines_in_window"]}条记录，WARN={audit["WARN"]}、ERROR={audit["ERROR"]}。依据backend-log-audit.json；这只能说明该窗口未记录相应级别异常，不等于没有所有潜在问题。']
    lines += ['', '## 停止条件与限制','',
    '可用内存低于1GiB、宿主CPU持续15秒超过90%、单档超过65秒即终止；一档完成后业务错误率超过5%不再升级负载。临时Token文件在finally中移除。原始JTL、JMeter日志及资源JSON保存在artifacts/performance，summary.json只代表最近一次运行，历史JTL仍保留。','',
    '本次只有三个短档位，不能据此宣称系统最大并发、长期稳定性或生产SLA。响应时间变化可能受到数据库查询、JVM预热和宿主调度等因素影响，未做火焰图/慢查询等因果定位，因此不认定具体瓶颈，更不以猜测开展数据库调优。','',
    '复现命令：`.venv/Scripts/python.exe scripts/run_performance.py`，随后执行`.venv/Scripts/python.exe scripts/build_performance_report.py`。使用执行锁避免本项目其他测试同时运行。']
    (ROOT/'docs/性能测试报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('性能报告已从实际结果生成')

if __name__=='__main__':main()
