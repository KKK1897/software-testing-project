from pathlib import Path
from beginner.ai_testing.workbench import generate_plan


ROOT = Path(__file__).resolve().parents[2]


def test_uploaded_requirement_generates_candidate_points_with_review_and_sources():
    result = generate_plan(ROOT, "采购需求.md", "采购单需要防止重复提交，只读用户不能创建仓库", use_llm=False)
    assert "候选测试点" in result
    assert "人工审核" in result
    assert "来源" in result
