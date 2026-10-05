"""站内信主题行格式：【分类 | 正文】（禁止【【分类】正文】嵌套）。"""

from __future__ import annotations

import re

_DOUBLE_WRAP = re.compile(r"^【【([^】]+)】(.+)】\s*$")
_LEGACY_LEADING_TAG = re.compile(r"^【([^｜|】]+)】(.+)\s*$")
_PIPE_SUBJECT = re.compile(r"^【[^】｜|]+[｜|].+】\s*$")


def format_message_subject(subject: str | None) -> str | None:
    """
    将历史/错误嵌套主题规范为【标签 | 正文】。
    已是 pipe 形式或不含 leading 【标签】 的保持不变。
    """
    if subject is None:
        return None
    s = str(subject).strip()
    if not s:
        return subject

    if _PIPE_SUBJECT.match(s):
        return s

    m = _DOUBLE_WRAP.match(s)
    if m:
        tag = m.group(1).strip()
        body = m.group(2).strip()
        return f"【{tag} | {body}】"

    m = _LEGACY_LEADING_TAG.match(s)
    if m:
        tag = m.group(1).strip()
        body = m.group(2).strip()
        if body.startswith("【"):
            return s
        return f"【{tag} | {body}】"

    return s
