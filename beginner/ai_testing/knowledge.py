"""Local, citation-first retrieval over test plans and defect records."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re

TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}|[\u4e00-\u9fff]{2,}")

@dataclass(frozen=True)
class Evidence:
    source: str
    heading: str
    text: str
    score: int

def tokens(text: str) -> set[str]:
    result = {item.lower() for item in TOKEN.findall(text)}
    # Chinese has no word boundary in plain Markdown. Adding overlapping
    # bigrams makes “只读用户” match “只读后端可新增仓库” without a model.
    chinese = "".join(char for char in text if "\u4e00" <= char <= "\u9fff")
    result.update(chinese[index:index + 2] for index in range(len(chinese) - 1))
    return result

def _sections(path: Path, root: Path) -> list[Evidence]:
    heading, buffer, result = "文档开头", [], []
    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            result.append(Evidence(path.relative_to(root).as_posix(), heading, body, 0))
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            flush(); heading = line.lstrip("#").strip(); buffer = []
        else:
            buffer.append(line)
    flush()
    return result

class LocalKnowledgeBase:
    """Deterministic retrieval: it never manufactures a citation."""
    def __init__(self, project_root: Path):
        self.root = project_root.resolve()
        paths = [
            self.root / "beginner/docs/业务与测试用例.md",
            self.root / "beginner/docs/缺陷记录.md",
            self.root / "beginner/docs/测试报告.md",
            self.root / "docs/缺陷与问题记录.md",
        ]
        self.evidence = [item for path in paths if path.exists() for item in _sections(path, self.root)]
    def search(self, question: str, limit: int = 4) -> list[Evidence]:
        query = tokens(question)
        found = []
        for item in self.evidence:
            score = len(query & tokens(item.heading + "\n" + item.text))
            if score:
                found.append(Evidence(item.source, item.heading, item.text, score))
        return sorted(found, key=lambda item: (-item.score, item.source, item.heading))[:limit]
