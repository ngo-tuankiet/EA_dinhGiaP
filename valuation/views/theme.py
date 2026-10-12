"""Giao diện VN100 lấy cảm hứng từ bố cục ngân hàng bán lẻ."""

from __future__ import annotations

import base64
import html
from functools import lru_cache
from pathlib import Path
from typing import Any

import streamlit as st


def escape_html(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


@lru_cache(maxsize=1)
def _theme_css() -> str:
    """Đọc font một lần, không cần kết nối Google Fonts khi mở ứng dụng."""
    assets = Path(__file__).with_name("assets")
    fonts = []
    for weight in (400, 700):
        encoded = base64.b64encode(
            (assets / f"manrope-{weight}.woff2").read_bytes()
        ).decode("ascii")
        fonts.append(
            "@font-face {font-family: Manrope; font-style: normal; "
            f"font-weight: {weight}; font-display: swap; "
            f"src: url(data:font/woff2;base64,{encoded}) format('woff2');}}"
        )
    return "\n".join(fonts) + (assets / "workspace.css").read_text(encoding="utf-8")


def render_app_theme() -> None:
    st.markdown(f"<style>{_theme_css()}</style>", unsafe_allow_html=True)


def render_shell_header() -> None:
    st.markdown(
        """
<header class="ag-shell-header">
    <div class="ag-utility-bar">
        <span>Phân tích &amp; đầu tư</span><span>Thị trường Việt Nam</span>
    </div>
    <div class="ag-brand-row">
        <div class="ag-wordmark">VN<span>100</span></div>
        <span class="ag-brand-caption">Nghiên cứu cổ phiếu</span>
    </div>
    <div class="ag-page-heading">
        <p class="ag-breadcrumb">Đầu tư / Cổ phiếu Việt Nam</p>
        <h1>Định giá cổ phiếu</h1>
    </div>
</header>
        """,
        unsafe_allow_html=True,
    )


def render_summary_banner(
    *,
    ticker: str,
    sector: str,
    headline: str,
    current_price: float,
    right_html: str,
    accent_color: str,
    bg_color: str,
    text_color: str,
) -> None:
    st.markdown(
        f"""
<section class="ag-summary-band" style="--ag-summary-color:{accent_color}; --ag-summary-bg:{bg_color}; --ag-summary-text:{text_color};" aria-label="Tổng quan định giá">
    <div class="ag-summary-main">
        <div class="ag-summary-meta"><strong>{escape_html(ticker)}</strong><span>{escape_html(sector)}</span></div>
        <h2 class="ag-summary-title">{escape_html(headline)}</h2>
        <p class="ag-summary-note">Kết quả theo giả định đang chọn</p>
    </div>
    <div class="ag-summary-market">
        <div class="ag-summary-price">Giá thị trường<strong>{current_price:,.0f} <small>VND</small></strong></div>
        {right_html}
    </div>
</section>
        """,
        unsafe_allow_html=True,
    )
