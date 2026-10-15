# Python测试实践：ERP自动化测试与AI用例评审工作台

面向软件测试岗位的两个实践项目：一个用真实ERP验证业务结果，一个辅助整理、评审和导出测试用例。测试与工作台代码主要使用Python；ERP来自开源jshERP，不是本项目开发的业务系统。

|项目|目的与技术点|入口|
|---|---|---|
|jshERP进销存与收付款自动化测试|Pytest、Requests、Playwright、Locust、Allure；验证库存、单据、欠款和账户流水，记录权限及异常风险|[测试项目说明](beginner/README.md)|
|AI辅助测试用例生成与评审工作台|Python、Requests、PyPDF、Unittest；需求来源追溯、模型输出校验、人工编辑审核、多格式导出|[工作台说明](beginner/docs/用例生成工作台说明.md)|

## 项目一：真实ERP业务自动化测试

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

## 项目二：AI辅助测试用例生成与评审

上传 TXT、Markdown、DOCX、文字型 PDF，生成带需求来源的结构化测试点与测试用例；支持网页编辑审核，导出 XLSX、CSV、Markdown、JSON。默认本地规则模式，选用 AI 模式需配置模型密钥。生成内容尚未执行测试。

用于减少需求整理、来源核对与交付文件维护中的重复操作：需求编号关联提取文本行号和原文；校验必填字段、优先级及需求覆盖；逐条人工编辑、审核与备注。输出格式正确不保证业务判断正确，本版本不将需求自动转换为可执行测试脚本。模型模式会发送文档提取文本到配置服务，仅使用获准发送的资料。

首次运行（仅文档生成工作台，无需启动 ERP / MySQL / Redis）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-workbench.txt
.\.venv\Scripts\python.exe -m beginner.ai_testing.server
```

打开 http://127.0.0.1:8765 。页面与业务处理由 Python 完成，无 JavaScript 或 Node.js 依赖。

需要 AI 模型时，在启动服务前设置环境变量（以下默认使用 DeepSeek 官方服务；第三方平台需改地址与模型名称）：

```powershell
$env:AI_TEST_API_KEY="替换为自己的密钥"
$env:AI_TEST_API_BASE="https://api.deepseek.com/v1"
$env:AI_TEST_MODEL="deepseek-chat"
```

密钥不得提交；`.env.example` 仅是说明，程序不会自动加载 `.env`。

### 自动验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s beginner/ai_testing/tests -p "test_*.py" -v
```

GitHub Actions 执行相同离线验证，模型响应使用替身，不需要 API 密钥，不访问 ERP。检查范围包括结构化生成、需求来源、响应校验、上传、编辑审核、导出和安全错误提示。

2026-10-15本次上传前，本机实际执行上述Unittest命令，12项测试通过；未实际调用模型API，不将替身结果写成模型服务验收。

详见 [用例生成工作台说明](beginner/docs/用例生成工作台说明.md)，可上传 [登录权限需求示例](beginner/docs/登录权限需求示例.md) 体验。

## 资料与归档

优先阅读上述两个项目入口；旧测试与环境辅助文件保留原位置，关系见[归档索引](beginner/archive/保留与归档.md)。原始运行产物、Trace、数据库及失败现场保留本地，仓库提供代码和中文结果摘要。旧报告的产物链接可能仅在原本机存在，不代表上传了完整运行环境。已有GitHub Actions仅验证工作台离线功能，不启动ERP，也不代表接口/UI/性能已在云端执行通过。

来源与成果边界见[NOTICE](NOTICE.md)。不主张缺陷为首次发现，不推断上游最新版本仍受影响。停止工作台按Ctrl+C；停止ERP见测试项目说明。
