"""Evidence-first planning and allow-listed Pytest execution."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os
import subprocess
import sys
from typing import Iterable

from .assistant import cite, context
from .knowledge import Evidence, LocalKnowledgeBase
from .llm import LLMUnavailable, generate


WORKBENCH_SYSTEM = """你是软件测试助手。只能根据上传需求和本地证据提出候选测试点，所有结论必须保留来源。不得把候选点说成已执行，不得执行命令、改代码或声称缺陷已修复。输出中文 Markdown，并保留“人工审核项”。"""

TEST_PROFILES = {
    "smoke": ["beginner/tests/test_login.py", "beginner/tests/test_basic_data.py"],
    "regression": [
        "beginner/tests/test_login.py",
        "beginner/tests/test_basic_data.py",
        "beginner/tests/test_inventory.py",
        "beginner/tests/test_permission.py",
        "beginner/tests/test_ui.py",
    ],
}


def _source_list(items: Iterable[Evidence]) -> str:
    return "\n".join(f"- {cite(item)}" for item in items) or "- 未匹配到项目内规则；以下内容只能作为待审核候选项。"


def _guarantee_sources(answer: str, evidence: list[Evidence]) -> str:
    """Always retain traceable sources even if a compatible model omits them."""
    return answer.rstrip() + "\n\n## 检索证据\n" + _source_list(evidence) + "\n\n## 人工审核项\n- 确认候选点、数据前置条件与预期结果后，才可加入自动化回归。\n"


def generate_plan(project_root: Path, filename: str, document_text: str, use_llm: bool = False) -> str:
    if not document_text.strip():
        raise ValueError("文件中没有可提取的文字，无法生成测试点。")
    query = document_text[:8000]
    evidence = LocalKnowledgeBase(project_root).search(query, limit=5)
    local = f"""# AI 候选测试点（待人工审核）

## 上传资料
- 文件：{filename}
- 提取文本长度：{len(document_text)} 字符

## 候选覆盖
- 正常流：按需求中的主业务路径验证响应、单据状态和库存等业务副作用。
- 边界与异常：空值、非法值、缺字段、库存不足、失败后无残留。
- 权限：同时验证页面权限与绕过页面直接调用接口。
- 幂等与并发：针对重复单号、重复点击或网络重试，验证最终单据和库存只生效一次。

## 本地关联证据
{_source_list(evidence)}

## 人工审核项
- 上传资料与现有规则是否属于同一模块。
- 将候选点映射到接口、测试数据和明确断言后，才可纳入自动化。
"""
    if not use_llm:
        return local
    try:
        answer = generate(WORKBENCH_SYSTEM, f"上传文件：{filename}\n\n需求内容：\n{query}\n\n项目证据：\n{context(evidence)}")
        return _guarantee_sources(answer, evidence)
    except LLMUnavailable:
        return local


def run_profile(project_root: Path, profile: str, timeout_seconds: int = 240) -> dict[str, object]:
    """Run only an allow-listed test profile; no user command reaches the shell."""
    if profile not in TEST_PROFILES:
        raise ValueError("仅支持 smoke 或 regression 测试集。")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = project_root / "beginner" / "artifacts" / "ai" / "runs" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    junit = run_dir / f"{profile}.xml"
    output = run_dir / f"{profile}.log"
    command = [sys.executable, "-m", "pytest", *TEST_PROFILES[profile], f"--junitxml={junit}", "-q"]
    try:
        completed = subprocess.run(
            command, cwd=project_root, capture_output=True, text=True, timeout=timeout_seconds,
            env={**os.environ, "PYTHONUTF8": "1"}, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output.write_text((exc.stdout or "") + "\n[超时：测试进程已终止]", encoding="utf-8")
        return {"profile": profile, "status": "timeout", "junit": str(junit.relative_to(project_root)), "log": str(output.relative_to(project_root))}
    output.write_text((completed.stdout or "") + "\n" + (completed.stderr or ""), encoding="utf-8")
    return {
        "profile": profile,
        "status": "passed" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "junit": str(junit.relative_to(project_root)),
        "log": str(output.relative_to(project_root)),
    }
