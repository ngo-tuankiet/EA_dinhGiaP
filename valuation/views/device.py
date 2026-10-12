"""Giao diện gọn cho điện thoại, nhận diện ở server qua User-Agent; desktop giữ nguyên (D54).

Streamlit không biết độ rộng màn hình ở phía Python nên dùng User-Agent: chuỗi "Mobi" (MDN) có trên
iPhone/Android phone, không có trên iPad/tablet Android → máy tính bảng hiển thị như desktop.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import streamlit as st

_RANK = {"error": 0, "warning": 1, "info": 2, "success": 3}


def is_phone_ua(user_agent: str | None) -> bool:
    return "Mobi" in (user_agent or "")


def is_phone() -> bool:
    return is_phone_ua(st.context.headers.get("User-Agent"))


def phone_collapsible(label: str) -> Any:
    """Điện thoại: mục đóng sẵn, bấm mới mở. Desktop: container không khung → hiển thị như cũ."""
    return st.expander(label, expanded=False) if is_phone() else st.container()


def split_alerts(
    alerts: Iterable[tuple[str, str, str | None]], max_visible: int
) -> tuple[list[tuple[str, str, str | None]], list[tuple[str, str, str | None]]]:
    """(hiện ngay, gom lại): giữ thứ tự gốc; tối đa `max_visible` cảnh báo error/warning nặng nhất được hiện ngay."""
    items = list(alerts)
    order = sorted(range(len(items)), key=lambda i: (_RANK.get(items[i][0], 9), i))
    # Chỉ error/warning được hiện ngay; info/success (ghi chú phương pháp, "đạt") luôn vào nhóm gom.
    top = {
        i for i in order[:max_visible] if _RANK.get(items[i][0], 9) <= _RANK["warning"]
    }
    return [a for i, a in enumerate(items) if i in top], [
        a for i, a in enumerate(items) if i not in top
    ]


def render_alerts(
    alerts: list[tuple[str, str, str | None]], max_visible: int = 2
) -> None:
    """Desktop: hiện tất cả như cũ. Điện thoại: chỉ `max_visible` cảnh báo nặng nhất, còn lại gom vào
    một mục đóng sẵn — không xoá cảnh báo nào (lỗi dữ liệu vẫn phải tới được người dùng).
    """
    shown, rest = split_alerts(alerts, max_visible) if is_phone() else (alerts, [])
    for level, body, icon in shown:
        getattr(st, level)(body, icon=icon)
    if rest:
        with st.expander(f"Cảnh báo khác ({len(rest)})", expanded=False):
            for level, body, icon in rest:
                getattr(st, level)(body, icon=icon)
