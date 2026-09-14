"""Extracts a flat list of question strings from an uploaded security
questionnaire. Real enterprise questionnaires vary wildly in format, so this
is intentionally a heuristic, not a full document-structure parser — good
enough for MVP, with the human reviewer catching anything mis-split before
answers ship (see F4: "never auto-submits")."""

import csv
import io
import re

import openpyxl
from pypdf import PdfReader

_NUMBERED_MARKER = re.compile(r"^\d{1,3}[.)]")


def _looks_like_question(line: str) -> bool:
    line = line.strip()
    if len(line) < 8:
        return False
    if line.endswith("?"):
        return True
    # numbered/lettered list items are common in questionnaire exports. A
    # trailing space after the marker (the overwhelmingly common style --
    # "1. Do you...", "2) Have you...") must still match, which a bare
    # `line[:3].rstrip(".)").isdigit()` check does not: rstrip only strips
    # "." and ")" characters, so a marker like "1. " (ending in a space)
    # is left untouched and never reads as a digit.
    if _NUMBERED_MARKER.match(line):
        return True
    return len(line) > 2 and line[1] in ").:" and line[0].isalpha()


def parse_pdf(content: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(content))
    lines: list[str] = []
    for page in reader.pages:
        lines.extend(page.extract_text().splitlines())
    return [l.strip() for l in lines if _looks_like_question(l)]


def parse_csv(content: bytes) -> list[str]:
    text = content.decode("utf-8", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]
    col = next((i for i, h in enumerate(header) if "question" in h), 0)
    body = rows[1:] if any("question" in h for h in header) else rows
    return [row[col].strip() for row in body if len(row) > col and row[col].strip()]


def parse_xlsx(content: bytes) -> list[str]:
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []
    header = [str(h).strip().lower() if h else "" for h in rows[0]]
    col = next((i for i, h in enumerate(header) if "question" in h), 0)
    body = rows[1:] if any("question" in h for h in header) else rows
    questions = []
    for row in body:
        if col < len(row) and row[col]:
            questions.append(str(row[col]).strip())
    return questions


def parse_questionnaire(content: bytes, file_type: str) -> list[str]:
    if file_type == "pdf":
        return parse_pdf(content)
    if file_type == "csv":
        return parse_csv(content)
    if file_type == "xlsx":
        return parse_xlsx(content)
    raise ValueError(f"Unsupported file type: {file_type}")
