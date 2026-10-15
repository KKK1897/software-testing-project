from pathlib import Path
from ai_testing.assistant import ask, failure_report, suggest_cases

ROOT = Path(__file__).resolve().parents[2]

def test_local_knowledge_answer_has_real_citation():
    result = ask(ROOT, "只读用户新增仓库权限", use_llm=False)
    assert "DEF-002" in result
    assert "[来源: beginner/docs/缺陷记录.md#缺陷记录与质量边界]" in result

def test_suggestions_remain_human_review_only():
    result = suggest_cases(ROOT, "采购单重复提交", use_llm=False)
    assert "人工审核" in result
    assert "自动执行" not in result

def test_junit_failure_report_uses_test_evidence(tmp_path):
    junit = tmp_path / "result.xml"
    junit.write_text('<testsuite><testcase name="test_readonly_cannot_create_depot"><failure message="创建成功" /></testcase></testsuite>', encoding="utf-8")
    result = failure_report(ROOT, junit, use_llm=False)
    assert "test_readonly_cannot_create_depot" in result
    assert "缺陷记录" in result
