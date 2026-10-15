"""CSV, Markdown, JSON and Excel export using only the Python standard library."""
import csv
import io
import json
import zipfile
from xml.sax.saxutils import escape

FIELDS = [("id", "用例编号"), ("requirement_id", "需求编号"), ("point", "测试点"), ("title", "用例名称"), ("priority", "优先级"), ("category", "类型"), ("preconditions", "前置条件"), ("steps", "操作步骤"), ("expected", "预期结果"), ("source", "需求来源"), ("source_text", "需求原文"), ("questions", "待确认项"), ("review", "审核状态"), ("review_note", "审核备注")]


def rows(suite):
    return [[label for _, label in FIELDS]] + [["\n".join(f"{i+1}. {v}" for i, v in enumerate(c[key])) if isinstance(c[key], list) else str(c[key]) for key, _ in FIELDS] for c in suite["cases"]]


def export(suite, kind):
    if kind == "json":
        return json.dumps(suite, ensure_ascii=False, indent=2).encode("utf-8"), "application/json"
    data = rows(suite)
    if kind == "csv":
        output = io.StringIO(newline="")
        # Prevent spreadsheet formula execution from uploaded/model-generated content.
        csv.writer(output).writerows([["'" + v if v.lstrip().startswith(("=", "+", "-", "@")) else v for v in row] for row in data])
        return output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"
    if kind == "md":
        parts = ["# 测试用例", suite["notice"], "生成模式：" + suite["mode"]]
        for c in suite["cases"]:
            parts.append("\n## " + c["id"] + " " + c["title"])
            parts.extend(f"- **{label}**：" + (" / ".join(c[key]) if isinstance(c[key], list) else str(c[key])) for key, label in FIELDS)
        return "\n\n".join(parts).encode("utf-8"), "text/markdown; charset=utf-8"
    if kind != "xlsx":
        raise ValueError("不支持的导出格式")
    output = io.BytesIO()
    sheet_rows = []
    for number, row in enumerate(data, 1):
        cells = []
        for col, value in enumerate(row, 1):
            letter, n = "", col
            while n:
                n, rem = divmod(n-1, 26); letter = chr(65+rem) + letter
            value = "".join(ch for ch in value if ord(ch) >= 32 or ch in "\n\t\r")
            cells.append(f'<c r="{letter}{number}" t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>')
        sheet_rows.append(f'<row r="{number}">' + "".join(cells) + '</row>')
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="测试用例" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(sheet_rows) + '</sheetData></worksheet>')
    return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
