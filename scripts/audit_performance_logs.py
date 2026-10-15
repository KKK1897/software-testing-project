"""按JTL时间窗核对本次性能运行的后端日志级别。"""
import csv,json,re
from datetime import datetime
from erp_client import ROOT

summary=json.loads((ROOT/'artifacts/performance/summary.json').read_text(encoding='utf-8'))
rows=[]
for stage in summary['stages']:
    rows.extend(csv.DictReader((ROOT/stage['jtl']).open(encoding='utf-8-sig')))
start=datetime.fromtimestamp(min(int(r['timeStamp']) for r in rows)/1000).strftime('%Y/%m/%d-%H:%M:%S')
end=datetime.fromtimestamp(max(int(r['timeStamp'])+int(r['elapsed']) for r in rows)/1000).strftime('%Y/%m/%d-%H:%M:%S')
path=ROOT/'runtime/logs.home_IS_UNDEFINED/jshERP.log'
counts={'lines_in_window':0,'WARN':0,'ERROR':0};events=[]
with path.open(encoding='utf-8',errors='replace') as f:
    for line in f:
        if start<=line[:19]<=end:
            counts['lines_in_window']+=1
            match=re.search(r'\b(WARN|ERROR)\b',line)
            if match:
                counts[match[1]]+=1
                events.append(re.sub(r'(?i)\b[0-9a-f]{32}\b','[REDACTED]',line[:1200]))
result={'source':str(path.relative_to(ROOT)),'jtl':[stage['jtl'] for stage in summary['stages']],'start_local':start,'end_local':end,**counts,'events':events}
assert counts['lines_in_window']>0,'时间窗内没有日志，不可声称已观察'
(ROOT/'artifacts/performance/backend-log-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='events'},ensure_ascii=False))
