# ERP自动化测试项目

## 真实ERP业务自动化测试

被测系统固定为[jishenghua/jshERP](https://github.com/jishenghua/jshERP) v3.5，Commit `7ca0f9d68fef761d98b00854d09e975eba291465`。本项目的工作是测试设计、自动化脚本、执行、报告与缺陷分析。ERP财务验证指内部收付款结算，不包含外部支付网关。

- 19条基础接口用例＋3条进阶结算用例，覆盖登录会话、基础资料、采购入库、调拨、销售、权限和必要异常。
- 完整链路：登录→A仓采购100件→付款1000元→调拨30件至B仓→B仓销售10件→分次收款60元与90元。核对6张单据、A仓70件/B仓20件/总库存90件、欠款及账户余额2000→1150元。
- 3条Playwright UI流程：登录退出、页面采购销售、只读新增按钮限制；条件等待、截图和Trace辅助定位失败。
- Locust按10/30/50/100虚拟用户逐级查询库存，检查HTTP与业务码，保存P50/P95、吞吐量、错误率和CPU/内存观察。仅允许本机隔离环境，共享执行锁避免与功能测试混跑。
- fixture管理独立会话、唯一QA标识与定向清理；失败保留现场及脱敏证据，不以跳过或无条件重试掩盖缺陷。

### 已执行结果与边界

|范围|已记录结果|报告|
|---|---|---|
|基础接口19条|17通过、2失败，保留产品缺陷|[接口/UI历史报告](beginner/docs/测试报告.md)|
|UI 3条|修正测试脚本后3通过，保留初轮失败记录|[接口/UI历史报告](beginner/docs/测试报告.md)|
|收付款3条|3通过；另验证完整链路与原库存链路定向清理，2通过|[进阶结算验证](beginner/docs/进阶收付款链路.md)|
|10/30/50/100用户负载|四档均执行；48209次请求、11次失败。100用户P95约715ms、吞吐约175次/秒，低于50用户档|[逐级负载验证](beginner/docs/逐级负载验证.md)|

以上来自不同轮次，不是一次全量回归或全量产品验收。负载测试记录到业务500与Redis连接异常，尚未确认根因；不宣称100用户稳定通过或测出最大容量。历史并发重复单号风险见[缺陷记录](beginner/docs/缺陷记录.md)。Postman材料已检查，尚未在Postman中执行。

已有本机ERP环境，从`beginner`目录运行：

```powershell
../.venv/Scripts/python.exe ../scripts/start_local.py
../.venv/Scripts/python.exe -m pytest tests/test_login.py::test_correct_login
../.venv/Scripts/python.exe -m pytest tests/test_settlement.py::test_purchase_payment_transfer_sale_collection
../.venv/Scripts/python.exe -m pytest tests/test_ui.py --headed
../.venv/Scripts/python.exe performance/run.py --users 10 30 50 100 --duration 90 --warmup 30 --spawn-rate 5
```

新环境先看[部署说明](docs/环境部署与排障.md)。上游源码、便携工具、数据库及本机配置不随仓库上传；不能克隆后直接执行ERP测试。本次上传未从空环境重新部署验收，不清空已有数据库。
