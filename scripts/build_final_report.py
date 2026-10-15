"""从最终真实JUnit/JMeter结果生成质量摘要，不合并历史轮次冒充单次执行。"""
import json,xml.etree.ElementTree as ET
from erp_client import ROOT

def main():
    path=ROOT/'artifacts/acceptance-junit.xml'
    grouped={}
    for c in ET.parse(path).getroot().iter('testcase'):
        key=(c.attrib['classname'],c.attrib['name'])
        if key not in grouped or c.find('error') is not None or c.find('failure') is not None:grouped[key]=c
    cases=list(grouped.values())
    counts={'通过':0,'失败':0,'准备错误':0,'跳过':0}
    failures=[]
    for c in cases:
        state='准备错误' if c.find('error') is not None else '失败' if c.find('failure') is not None else '跳过' if c.find('skipped') is not None else '通过'
        counts[state]+=1
        if state in ('失败','准备错误'):failures.append((state,c.attrib['name']))
    summary='、'.join(f'{v}条{k}' for k,v in counts.items())
    lines=['# 最终质量报告','',f'固定业务基线 v3.5 / 7ca0f9d68fef761d98b00854d09e975eba291465。最新完整单次运行共{len(cases)}条：{summary}。数据直接来自 [acceptance-junit.xml](../artifacts/acceptance-junit.xml)，不是将历史通过结果相加。','',
    '## 验收结论','',
    '本地系统与核心库存链路实际可用，测试项目具备真实复现和诊断证据；被测产品存在未解决缺陷，不能给出产品全面通过结论。部署使用独立 JDBC 兼容构建，业务基线未混入 DEF-001 补丁。','',
    '|状态|用例|','|---|---|']
    lines += [f'|{state}|{name}|' for state,name in failures]
    lines += ['', '## 业务与技术证据','',
    '- A仓采购100→调拨30到B→B销售10：A70、B20、总90，按单号核对3张单据；artifacts/core-scenario.json。',
    '- UI为真实Chromium：登录退出、基础资料、供应商必填、只读按钮、采购销售库存；实际执行状态以本轮JUnit为准。',
    '- 默认保存生效与强制审核配置分开验证；非法单据除响应外还核对单据列表与库存不变。',
    '- DEF-001为空单号详情空列表错误，隔离补丁回归结果在patch类JUnit；DEF-002为只读仓库接口写入；DEF-003为并发同单号重复入库。缺陷范围与证据见缺陷文档。',
    '- 历史final40轮：32通过、3失败、5个浏览器沙箱准备错误；保留原报告，不能计为5个UI产品缺陷。',
    '- 未使用Mock替代ERP，未操作公共演示环境，未推送、发布、提交Issue或PR。','',
    '## 遗留与限制','',
    '- 未修复的权限与并发库存问题使产品上线验收不通过；不是测试项目必须把所有产品缺陷修好。',
    '- 用例目录中的补充边界明确标为未执行/规则待澄清，不计通过或覆盖率。自然会话过期、禁用后的旧会话、复杂审批和批次序列号未全面验证。',
    '- 操作员已实际通过页面仓库新增、采购和销售库存闭环；操作员调拨页面未单独验收。只读能力不能仅靠按钮隐藏保证。',
    '- 财务仅使用完成进销存所需的现有结算账户；没有验收完整财务或多租户。',
    '- 数据默认留存，通过唯一标识重复运行；清理只支持登记的数据，不宣称清理全部早期探索数据。',
    '- 性能仅为本机短时小负载；原始JTL与资源数据可追溯，不推断生产容量或数据库瓶颈。',
    '- GitHub Actions配置已提供，远程CI尚未执行；新Windows空机器和远程runner尚未验证。','',
    '## 交付索引','',
    '[环境部署与排障](环境部署与排障.md) · [业务规则与测试计划](业务规则与测试计划.md) · [用例映射](测试用例与规则映射.md) · [缺陷记录](缺陷与问题记录.md) · [自动化与CI](自动化与CI使用说明.md) · [性能报告](性能测试报告.md) · [最小SQL](最小SQL说明.md) · [面试与演示](面试与演示草稿.md) · [交接清单](交接进度.md)']
    (ROOT/'docs/最终质量报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (ROOT/'artifacts/final-counts.json').write_text(json.dumps({'source':str(path.relative_to(ROOT)),'total':len(cases),'counts':counts},ensure_ascii=False,indent=2),encoding='utf-8')
    print(summary)

if __name__=='__main__':main()
