# AI 辅助测试说明

## 目标与边界

模块基于已有业务规则、缺陷记录和 JUnit 失败现场，生成可审核的测试建议和缺陷报告草稿。它不修改 ERP 数据、不执行测试、不自动提交缺陷，也不把模型推断当作产品事实。

输出使用 `文件#标题` 作为来源。没有本地依据就提示补充资料；模型模式只可使用已提供的证据。模型不能读取 Redis 密码、Token、原始验证码或生产环境。

## 三项能力

1. **测试知识检索**：从业务用例、缺陷记录和测试报告检索证据，回答权限、重复提交和库存一致性测试问题。
2. **候选测试点生成**：根据需求提出正常、边界、权限和并发方向；候选项须人工审核后才可写成 Pytest。
3. **失败分析草稿**：读取 JUnit 失败现场并关联本地缺陷记录，输出失败现场、可关联证据和人工审核项。

## 使用

从项目根目录执行：

```powershell
# 纯本地模式：不需要 Key，不访问网络
.venv/Scripts/python.exe -m beginner.ai_testing.cli ask "只读用户为什么不能创建仓库" --local-only
.venv/Scripts/python.exe -m beginner.ai_testing.cli suggest "采购单重复提交" --local-only
.venv/Scripts/python.exe -m beginner.ai_testing.cli analyze --junit beginner/artifacts/api-final.xml --local-only
```

输出默认保存到 `beginner/artifacts/ai/`，不会修改 JUnit、Allure 或原始测试结果。

## 启用模型

设置环境变量后去掉 `--local-only`。使用 DeepSeek 兼容接口，不把 Key 写入仓库或报告：

```powershell
$env:DEEPSEEK_API_KEY = "你的Key"
.venv/Scripts/python.exe -m beginner.ai_testing.cli analyze --junit beginner/artifacts/api-final.xml
```

支持可选变量 `AI_TEST_API_KEY`、`AI_TEST_API_BASE`、`AI_TEST_MODEL`。模型不可用时退回本地证据模式，不伪造 AI 结论。

## 面试演示闭环

用 `api-final.xml` 的只读越权失败为例：JUnit 失败现场 → 检索 DEF-002 的规则与副作用证据 → 输出“页面按钮限制不能替代后端授权”的关联 → 人工确认缺陷和回归范围。并发重复入库仅作历史进阶风险，不写成默认用例已通过或已修复。
