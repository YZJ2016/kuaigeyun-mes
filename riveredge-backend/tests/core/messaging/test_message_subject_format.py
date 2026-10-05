from core.services.messaging.message_subject_format import format_message_subject


def test_double_wrap_to_pipe():
    raw = "【【工序交接】工单 GD202608140002 可开工「表面处理」】"
    assert (
        format_message_subject(raw)
        == "【工序交接 | 工单 GD202608140002 可开工「表面处理」】"
    )


def test_legacy_tag_to_pipe():
    raw = "【工序交接】工单 GD001 可开工「热处理」"
    assert format_message_subject(raw) == "【工序交接 | 工单 GD001 可开工「热处理」】"


def test_already_pipe_unchanged():
    raw = "【工序交接 | 工单 GD001 可开工「热处理」】"
    assert format_message_subject(raw) == raw


def test_plain_subject_unchanged():
    assert format_message_subject("外校到期提醒") == "外校到期提醒"
