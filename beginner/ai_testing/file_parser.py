"""Safe, local file extraction for the AI-assisted testing workbench."""
from __future__ import annotations

from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree


ALLOWED_SUFFIXES = {".txt", ".md", ".docx", ".pdf"}
MAX_BYTES = 3 * 1024 * 1024


class UploadError(ValueError):
    """A user-facing upload validation error."""


def extract_text(path: Path) -> str:
    """Return text from a small text, Word or PDF file without executing it."""
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UploadError("仅支持 .txt、.md、.docx 和 .pdf 文件。")
    if path.stat().st_size > MAX_BYTES:
        raise UploadError("单个文件不能超过 3 MB。")
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    if suffix == ".docx":
        return _docx_text(path)
    return _pdf_text(path)


def _docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise UploadError("无法读取 Word 文档，请确认文件未损坏。") from exc
    paragraphs = []
    for paragraph in root.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        text = "".join(node.text or "" for node in paragraph.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise UploadError("当前 Python 环境未安装 pypdf，暂不能解析 PDF；可先上传同内容的 TXT、Markdown 或 Word。") from exc
    try:
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    except Exception as exc:  # pypdf has multiple parser exceptions
        raise UploadError("无法提取 PDF 文字；扫描件请先 OCR 后再上传。") from exc
    return re.sub(r"\n{3,}", "\n\n", text).strip()
