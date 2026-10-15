"""Evidence-bound AI suggestions and deterministic failure-report scaffolding."""
from __future__ import annotations
from pathlib import Path
from xml.etree import ElementTree
from .knowledge import Evidence, LocalKnowledgeBase
from .llm import LLMUnavailable, generate

SYSTEM = """你是软件测试助手。只可依据给定证据回答，不得声称缺陷已修复、根因已证实、线上可用或性能达标。输出中文 Markdown，按结论、证据、候选测试点、人工审核项组织。每项结论都标注 [来源: 文件#标题]；证据不足时明确写证据不足。"""

def cite(item: Evidence) -> str:
    return f"[来源: {item.source}#{item.heading}]"

def context(items: list[Evidence]) -> str:
    return "\n\n".join(f"{cite(item)}\n{item.text[:1800]}" for item in items)

def ask(project_root: Path, question: str, use_llm: bool = True) -> str:
    evidence = LocalKnowledgeBase(project_root).search(question)
    if not evidence:
        return "# 测试知识库回答\n\n未找到能够支持该问题的本地测试资料。请补充业务规则、接口文档或历史缺陷证据。"
    local = "\n".join(f"- {cite(item)}\n  {item.text[:420].replace(chr(10), ' ')}" for item in evidence)
    if not use_llm:
        return "# 测试知识库检索结果\n\n" + local
    try:
        return generate(SYSTEM, f"问题：{question}\n\n证据：\n{context(evidence)}")
    except LLMUnavailable:
        return "# 测试知识库检索结果（未调用模型）\n\n" + local

def failure_report(project_root: Path, junit_path: Path, use_llm: bool = True) -> str:
    root = ElementTree.parse(junit_path).getroot()
    failed = []
    for case in root.iter("testcase"):
        failure = case.find("failure")
        if failure is None:
            failure = case.find("error")
        if failure is not None:
            failed.append({"case": case.attrib.get("name", "unknown"), "message": failure.attrib.get("message", ""), "detail": (failure.text or "")[:2000]})
    if not failed:
        return "# AI 测试失败分析\n\n当前 JUnit 文件没有失败或错误用例，未生成缺陷结论。"
    evidence = LocalKnowledgeBase(project_root).search(" ".join(x["case"] + " " + x["message"] for x in failed), limit=5)
    raw = "\n".join(f"- 用例：{x['case']}\n  失败：{x['message']}\n  现场：{x['detail']}" for x in failed)
    if use_llm:
        try:
            return generate(SYSTEM, f"JUnit失败现场：\n{raw}\n\n可用证据：\n{context(evidence)}\n\n根因只能写为线索，并给出最小回归建议。")
        except LLMUnavailable:
            pass
    sources = "\n".join(f"- {cite(item)}" for item in evidence) or "- 未匹配到本地规则，请人工补充证据。"
    return "# AI 测试失败分析（本地证据模式）\n\n## 失败现场\n" + raw + "\n\n## 可关联证据\n" + sources + "\n\n## 人工审核项\n- 核对失败是否由环境、数据准备或产品行为导致。\n- 未配置模型时不生成根因结论；请结合请求、日志和数据库副作用确认。"

def suggest_cases(project_root: Path, requirement: str, use_llm: bool = True) -> str:
    evidence = LocalKnowledgeBase(project_root).search(requirement, limit=5)
    local = """# AI 候选测试点（需人工审核）

## 输入需求
%s

## 基于证据的候选方向
%s

## 最小测试卡片
- 正常链路：明确输入、预期响应和业务副作用。
- 边界与异常：空值、非法值、重复提交与失败后无残留。
- 权限：页面限制与直接接口调用分别验证。
- 并发：仅在隔离数据和可回收环境中验证同一业务标识的竞争条件。

## 人工审核项
- AI 候选点不是已执行用例；确认接口合同、测试数据和预期后再落地到 Pytest。
""" % (requirement, "\n".join(f"- {cite(item)}" for item in evidence) or "- 无匹配证据，需补充需求说明。")
    if not use_llm or not evidence:
        return local
    try:
        return generate(SYSTEM, f"需求：{requirement}\n\n证据：\n{context(evidence)}\n\n输出可审核的候选测试点，不生成或执行代码。")
    except LLMUnavailable:
        return local
