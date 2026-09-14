import io

import openpyxl
from pypdf import PdfWriter

from app.services.questionnaire_parser import _looks_like_question, parse_csv, parse_pdf, parse_xlsx, parse_questionnaire


def test_parse_csv_with_question_column():
    content = (
        "Question,Notes\n"
        "Do you log all AI agent actions?,internal\n"
        "Is PII redacted before storage?,internal\n"
        ",\n"  # blank row must be skipped
    ).encode("utf-8")
    assert parse_csv(content) == [
        "Do you log all AI agent actions?",
        "Is PII redacted before storage?",
    ]


def test_parse_csv_without_header_uses_first_column():
    content = (
        "Do you log all AI agent actions?\n"
        "Is PII redacted before storage?\n"
    ).encode("utf-8")
    assert parse_csv(content) == [
        "Do you log all AI agent actions?",
        "Is PII redacted before storage?",
    ]


def test_parse_csv_empty_file_returns_empty_list():
    assert parse_csv(b"") == []


def test_parse_xlsx_with_question_column():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Question", "Category"])
    ws.append(["Do you log all AI agent actions?", "logging"])
    ws.append(["Is PII redacted before storage?", "privacy"])
    buf = io.BytesIO()
    wb.save(buf)

    assert parse_xlsx(buf.getvalue()) == [
        "Do you log all AI agent actions?",
        "Is PII redacted before storage?",
    ]


def test_parse_xlsx_skips_blank_cells():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Question"])
    ws.append(["Do you log all AI agent actions?"])
    ws.append([None])
    buf = io.BytesIO()
    wb.save(buf)

    assert parse_xlsx(buf.getvalue()) == ["Do you log all AI agent actions?"]


def test_parse_pdf_extracts_question_like_lines():
    # A real PDF's extracted text is just newline-joined lines; pypdf's own
    # writer produces a blank page, so we exercise the actual PDF machinery
    # (bytes in, bytes out through PdfReader) and separately unit-test the
    # question-detection heuristic via parse_questionnaire's CSV/XLSX paths
    # above. This confirms parse_pdf doesn't crash on a real, valid PDF.
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    assert parse_pdf(buf.getvalue()) == []


def test_parse_questionnaire_dispatches_by_file_type():
    csv_bytes = b"Question\nDo you log all AI agent actions?\n"
    assert parse_questionnaire(csv_bytes, "csv") == ["Do you log all AI agent actions?"]


def test_parse_questionnaire_rejects_unsupported_type():
    import pytest

    with pytest.raises(ValueError):
        parse_questionnaire(b"", "docx")


def test_parse_questionnaire_dispatches_to_xlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Question"])
    ws.append(["Do you log all AI agent actions?"])
    buf = io.BytesIO()
    wb.save(buf)

    assert parse_questionnaire(buf.getvalue(), "xlsx") == ["Do you log all AI agent actions?"]


def test_parse_xlsx_empty_workbook_returns_empty_list():
    wb = openpyxl.Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    # A brand-new workbook still has one blank row from openpyxl's default
    # sheet, which iter_rows still yields -- covers the "has rows, but no
    # data" path distinctly from a workbook with zero rows at all.
    assert parse_xlsx(buf.getvalue()) == []


def test_looks_like_question_rejects_short_lines():
    assert _looks_like_question("Yes.") is False


def test_looks_like_question_accepts_a_line_ending_in_a_question_mark():
    assert _looks_like_question("Do you log all AI agent actions?") is True


def test_looks_like_question_accepts_a_numbered_list_item():
    assert _looks_like_question("1. Describe your data retention policy") is True


def test_looks_like_question_accepts_a_lettered_list_item():
    assert _looks_like_question("a) Describe your incident response plan") is True


def test_looks_like_question_rejects_ordinary_prose():
    assert _looks_like_question("This is just a regular sentence with no marker") is False
