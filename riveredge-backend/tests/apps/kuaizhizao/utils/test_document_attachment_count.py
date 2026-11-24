"""document_attachment_count 工具单测。"""

from apps.kuaizhizao.utils.document_attachment_count import (
    count_document_attachments,
    normalize_document_attachments_for_carry,
    sum_header_and_line_attachment_counts,
)


def test_count_document_attachments_empty():
    assert count_document_attachments(None) == 0
    assert count_document_attachments([]) == 0
    assert count_document_attachments([{}]) == 0


def test_count_document_attachments_valid_items():
    attachments = [
        {"uid": "1", "name": "a.pdf"},
        {"uuid": "2"},
        {"url": "https://x"},
        {"name": "only-name"},
        "bad",
    ]
    assert count_document_attachments(attachments) == 4


def test_normalize_document_attachments_for_carry():
    raw = [{"uid": "file-a", "name": "图纸.pdf"}, {"name": "no-uid"}, 42]
    carried = normalize_document_attachments_for_carry(raw)
    assert carried is not None
    assert len(carried) == 1
    assert carried[0]["uid"] == "file-a"
    assert normalize_document_attachments_for_carry(None) is None


def test_sum_header_and_line_attachment_counts():
    header = [{"uid": "h1"}]
    lines = [[{"name": "l1"}], [], [{"url": "u"}]]
    assert sum_header_and_line_attachment_counts(header, lines) == 3