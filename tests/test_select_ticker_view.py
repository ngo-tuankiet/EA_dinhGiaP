import datetime
from types import SimpleNamespace

from valuation.views.select_ticker import _format_run_option


def test_format_run_option_handles_missing_created_at():
    run = SimpleNamespace(id=17, analyst="Analyst", created_at=None)

    assert _format_run_option(run) == "Vòng 17 - Analyst (không rõ thời gian)"


def test_format_run_option_formats_created_at():
    run = SimpleNamespace(
        id=18,
        analyst="Phi",
        created_at=datetime.datetime(2026, 8, 29, 14, 35),
    )

    assert _format_run_option(run) == "Vòng 18 - Phi (29/08 14:35)"
