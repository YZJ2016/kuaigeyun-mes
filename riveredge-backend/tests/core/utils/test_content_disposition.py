from core.utils.content_disposition import build_attachment_content_disposition


def test_build_attachment_content_disposition_ascii():
    header = build_attachment_content_disposition("attendance_2026-10.xlsx")
    assert header == 'attachment; filename="attendance_2026-10.xlsx"'


def test_build_attachment_content_disposition_utf8():
    header = build_attachment_content_disposition("attendance_2026-10_工程部.xlsx")
    assert header.startswith("attachment; filename*=UTF-8''")
    assert "工程部" not in header
