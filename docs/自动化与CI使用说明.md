# 自动化与 CI 使用说明

所有命令在项目根目录执行。仅允许本地 9999 原始业务基线或 19999 隔离补丁环境。先执行 start_local.py；不要在不同终端同时跑写入测试、清理和性能测试。

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv/Scripts/python.exe -m pytest tests -p no:cacheprovider --junitxml=artifacts/my-run.xml --alluredir=artifacts/allure-my-run
.venv/Scripts/python.exe -m pytest tests/test_api.py::test_stock_chain -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/test_ui.py -p no:cacheprovider
$env:JAVA_HOME="$pwd/tools/jdk8u472-b08"
& tools/allure-2.32.0/bin/allure.bat generate artifacts/allure-my-run -o artifacts/report-my-run --clean
& tools/allure-2.32.0/bin/allure.bat open artifacts/report-my-run
```

具体测试名以 `pytest --collect-only -q` 为准。每次使用新的 Allure 结果目录，避免将历史多轮结果混成一次运行。用例失败必须保持非零退出；目前存在产品缺陷，因此完整基线回归预期可能失败，不能为绿灯添加 xfail、无条件重试或删除断言。

接口层为 Requests，超时为连接5秒/读取25秒。不同身份使用独立 Session；登录验证码通过仅本机 Redis 核实，并未关闭或 Mock 验证码。普通请求同时检查业务码与必要副作用。库存由查询接口核对，清理安全保护才使用只读 SQL。缺陷复现保留请求、响应、编号和服务日志。

fixture 负责客户端关闭、唯一数据生成、manifest 与证据；数据默认留存供学习复查。增加`--cleanup-passed`可在通过用例的fixture收尾按manifest逆序删除，失败用例仍保留证据；也可单独执行cleanup_data.py。新UI自动编号单据已登记ID和编号，清理时核对每条明细条码。早期未登记探索数据和部分创建失败的manifest需单独核对，不宣称所有历史数据都能一键重置。固定库上的重复运行通过唯一商品/仓库名避免冲突；性能测试必须记录当前数据规模。

UI 使用真实 Chromium 和 Playwright Python。登录退出、仓库创建、供应商必填、只读按钮、采购销售库存为5条流程；以语义按钮、标签、商品条码输入和稳定数量字段定位。截图与 trace 在 artifacts/ui；trace 可用 `python -m playwright show-trace 路径.zip` 打开。原始 trace 可能含登录凭据，只保存在隔离本机，不应直接公开。

## GitHub Actions

配置为 `.github/workflows/erp-regression.yml`，唯一维护的 CI 方案。Windows runner 安装固定 Python/Node，bootstrap 准备源码和依赖，初始化本机库并健康验收，再执行完整 API/UI 回归。无论成功失败都尝试生成 Allure、停止本项目进程并导出脱敏诊断产物。pytest 的退出码向上传递。

**远程 CI 尚未执行。** 没有推送、授权外部账号、触发 Actions 或构造成功截图。本地已运行对应构建、启动、测试和报告步骤；bootstrap 历史失败需结合环境排障文档阅读。远程历史下载可用性、runner资源与耗时仍为待验证风险。

本机完整bootstrap修正后已一次执行成功，见bootstrap-complete-validation.log；YAML已使用本机js-yaml解析确认9个步骤。YAML能解析与远程流水线成功是两回事。

报告解释：passed 为断言通过；failed 为测试调用断言失败；error 为 fixture/测试准备或清理异常；skipped 为显式跳过；用例目录中没有 JUnit 对应证据的计划项为未执行。Allure 的 broken 不应包装成产品失败，必须结合 Pytest JUnit 分类。

## 隔离补丁复现

```powershell
.venv/Scripts/python.exe scripts/start_patch.py
$env:ERP_BASE_URL='http://127.0.0.1:19999/jshERP-boot'
.venv/Scripts/python.exe -m pytest tests/test_permissions.py::test_missing_document_returns_empty_success tests/test_api.py::test_stock_chain tests/test_api.py::test_rejected_document_rolls_back -p no:cacheprovider --alluredir=artifacts/allure-patch-regression --junitxml=artifacts/patch-regression.xml
Remove-Item Env:\ERP_BASE_URL
```

补丁脚本只在runtime/patched-boot副本编译，在19999启动；原始业务基线仍是9999。新一轮请换新的结果目录。补丁只修复空单号查询，不宣称修复只读越权或并发重复入库。日志、patch源码差异和两个端口的JUnit应配套解释。
