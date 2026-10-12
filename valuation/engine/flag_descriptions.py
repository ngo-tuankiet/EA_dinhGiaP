"""
Mô tả tiếng Việt dễ hiểu cho các cờ (flags) mà engine định giá gắn vào kết quả.

Mục đích: khi engine trả về kết quả bất thường (vd Giá MT = 0, upside -100%),
người dùng phải THẤY NGAY lý do thay vì tưởng nhầm là lỗi hệ thống. Đây là lớp
hiển thị — không tính toán gì, chỉ dịch mã cờ → câu giải thích + mức độ.

level: "error" (kết quả cần cảnh giác cao, vd equity value âm) |
       "warning" (proxy/ước lượng, độ tin cậy thấp hơn) |
       "info" (thông tin phương pháp, không phải vấn đề)
"""
from __future__ import annotations

from typing import Any, Dict, List

FLAG_DESCRIPTIONS: Dict[str, Dict[str, str]] = {
    "NEGATIVE_EQUITY_VALUE_EV_EBITDA": {
        "level": "error",
        "message": (
            "Giá trị vốn cổ phần theo mô hình EV/EBITDA bị ÂM (nợ vay ròng lớn hơn "
            "giá trị doanh nghiệp theo bội số mục tiêu) nên được chặn về 0. Đây là "
            "dấu hiệu đòn bẩy tài chính rất cao so với EBITDA, KHÔNG có nghĩa doanh "
            "nghiệp vô giá trị — cần đối chiếu thêm phương pháp khác (DCF, so sánh) "
            "và xem xét rủi ro tài chính riêng."
        ),
    },
    "JV_VALUED_AT_PE": {
        "level": "info",
        "message": (
            "Phần vốn góp vào công ty liên doanh, liên kết đang có lãi được định giá theo "
            "lãi liên doanh 12 tháng × P/E lịch sử của chính doanh nghiệp, thay cho giá trị "
            "sổ sách (chỉ ở nhánh DCF). Sổ sách thường thấp hơn nhiều so với giá trị kinh tế."
        ),
    },
    "STALE_PRICE": {
        "level": "warning",
        "message": (
            "Giá thị trường trong DB của mã này đã CŨ (quá 5 ngày lịch so với hôm "
            "nay) — upside tính trên giá cũ có thể lệch so với thị trường hiện tại. "
            "Chạy cập nhật giá (ingest prices) trước khi tin kết quả."
        ),
    },
    "STALE_MACRO_RF": {
        "level": "warning",
        "message": (
            "Lãi suất phi rủi ro động (TPCP 10 năm) trong DB đã cũ quá 30 ngày — "
            "chi phí vốn (COE/WACC) đang chiết khấu bằng mặt bằng lãi suất cũ. "
            "Cập nhật chuỗi TPCP_10Y để định giá phản ánh vĩ mô hiện tại."
        ),
    },
    "NEGATIVE_EQUITY_VALUE_DCF": {
        "level": "error",
        "message": (
            "Giá trị vốn cổ phần theo DCF bị ÂM (nợ vay ròng lớn hơn giá trị doanh "
            "nghiệp chiết khấu) nên được chặn về 0. Thường gặp ở DN biên lợi nhuận "
            "mỏng + nợ vay lớn (vd thép). KHÔNG có nghĩa vô giá trị — cần đối chiếu "
            "phương pháp khác và đánh giá rủi ro tài chính/khả năng trả nợ."
        ),
    },
    "CORPORATE_ACTION_UNDATED": {
        "level": "warning",
        "message": (
            "Có đợt cổ tức cổ phiếu/thưởng công bố gần đây nhưng dữ liệu chưa có ngày GDKHQ: "
            "nếu đã GDKHQ, giá đã điều chỉnh mà số cổ phiếu vẫn cũ → giá trị/cp bị phóng đại. "
            "Thêm số cp sau sự kiện (nguồn VSDC) vào config/corporate_actions.yaml."
        ),
    },
    "MATERIAL_EVENT_HOLD": {
        "level": "error",
        "message": (
            "Analyst tạm chặn công bố: có sự kiện trọng yếu (lỗ lớn dự kiến, pha loãng, vụ án...) "
            "mà BCTC và giá mục tiêu CTCK chưa phản ánh. Xem lý do và nguồn trong "
            "config/event_holds.yaml; gỡ chặn khi mô hình đã cập nhật."
        ),
    },
    "UPSIDE_EXTREME_REVIEW": {
        "level": "warning",
        "message": (
            "Upside rất lớn (>150%) — giá hợp lý cao hơn 2.5 lần thị giá. Cần RÀ LẠI "
            "giả định đầu vào (tăng trưởng, biên lợi nhuận, bội số mục tiêu) trước "
            "khi tin tưởng; có thể do một năm đột biến hoặc bội số ngành quá cao."
        ),
    },
    "DOWNSIDE_EXTREME_REVIEW": {
        "level": "warning",
        "message": (
            "Định giá thấp hơn nhiều so với thị giá (giá hợp lý < 40% thị giá). Cần "
            "kiểm tra: dữ liệu đầu vào bất thường (vd capex/khấu hao một năm đột "
            "biến bị ngoại suy), lợi nhuận gần đây âm, hoặc thị trường đang định giá "
            "yếu tố mô hình chưa nắm bắt (câu chuyện tăng trưởng, tài sản ẩn)."
        ),
    },
    "VALUATION_PROXY": {
        "level": "warning",
        "message": (
            "Đây là định giá PROXY — ước lượng nhanh từ giá trị sổ sách (BCTC), "
            "chưa phải mô hình chi tiết theo dự án/mảng kinh doanh như CTCK chuyên "
            "nghiệp. Độ tin cậy thấp hơn nhóm phương pháp đầy đủ (IMPLEMENTED)."
        ),
    },
    "SECTOR_UNVALIDATED": {
        "level": "warning",
        "message": "Phân ngành của mã này chưa được đối chiếu/xác nhận thủ công — có thể ảnh hưởng phương pháp và benchmark áp dụng.",
    },
    "EBITDA_NORMALIZED_CYCLICAL": {
        "level": "info",
        "message": "EBITDA năm gần nhất lệch mạnh so với mức bình quân chuẩn hóa nhiều năm — hệ thống đã dùng EBITDA bình quân để chống nhiễu chu kỳ.",
    },
    "EARNINGS_NORMALIZED_CYCLICAL": {
        "level": "info",
        "message": "Lợi nhuận năm gần nhất lệch mạnh so với mức bình quân chuẩn hóa nhiều năm — hệ thống đã dùng EPS trung vị nhiều năm để chống nhiễu chu kỳ.",
    },
    "NEGATIVE_NORMALIZED_EARNINGS": {
        "level": "warning",
        "message": "Lợi nhuận chuẩn hóa (trung vị nhiều năm) âm hoặc bằng 0 — phương pháp P/E không áp dụng được, kết quả trả về 0.",
    },
    "NEGATIVE_EARNINGS": {
        "level": "warning",
        "message": "Doanh nghiệp đang có lợi nhuận âm — một số phương pháp so sánh (P/E) có thể không phản ánh đúng giá trị.",
    },
    "SOTP_NAV_FALLBACK": {
        "level": "info",
        "message": "Mảng vận hành không có lợi nhuận dương để định giá theo P/E — hệ thống chuyển hoàn toàn sang định giá theo giá trị sổ sách (NAV).",
    },
    "AI_RNAV_MODE": {
        "level": "info",
        "message": "Định giá RNAV đang dùng dữ liệu dự án do AI bóc tách từ báo cáo — vui lòng kiểm tra lại thông số dự án trước khi tin tưởng hoàn toàn.",
    },
    "AI_SOTP_MODE": {
        "level": "info",
        "message": "Định giá SOTP đang dùng dữ liệu mảng kinh doanh do AI bóc tách từ báo cáo — vui lòng kiểm tra lại thông số từng mảng trước khi tin tưởng hoàn toàn.",
    },
    "DDM_BLEND": {
        "level": "info",
        "message": "Mã ngành Điện — kết quả đã pha trộn thêm mô hình chiết khấu cổ tức (DDM) làm cross-check bên cạnh DCF.",
    },
    "LAND_BANK_VALUE_ADDED": {
        "level": "info",
        "message": "Giá mục tiêu đã được cộng thêm giá trị quỹ đất chưa phản ánh trong BCTC theo dữ liệu analyst tự nhập (xem tab Giả định, mục Land Bank Add-on).",
    },
    "ABSURD_UPSIDE": {
        "level": "warning",
        "message": "Upside vượt ngưỡng hợp lý (>300%) — cần rà soát lại giả định đầu vào trước khi tin tưởng kết quả này.",
    },
    "STALE_FV": {
        "level": "warning",
        "message": "Giá trị định giá nhanh (fast path) đang lệch nhiều so với định giá đầy đủ gần nhất — kết quả tạm dùng bản định giá đầy đủ (base) trong lúc chờ tính lại.",
    },
    "NEGATIVE_FV_FAST": {
        "level": "warning",
        "message": "Định giá nhanh (fast path) trả về giá trị âm hoặc bằng 0 — hệ thống tạm dùng lại kết quả định giá đầy đủ gần nhất.",
    },
    "CONSENSUS_DEVIATION_HIGH": {
        "level": "warning",
        "message": "Giá mục tiêu của hệ thống lệch trên 25% so với trung vị consensus các công ty chứng khoán — nên đối chiếu lại giả định.",
    },
    "COE_TOO_LOW": {
        "level": "error",
        "message": "Chi phí vốn cổ phần (COE) tính ra thấp bất thường — kiểm tra lại Beta/ERP trước khi tin tưởng định giá.",
    },
    "IMPLIED_PB_WARNING": {
        "level": "warning",
        "message": "P/B ngầm định (Justified P/B) nằm ngoài khoảng hợp lý [0.5x, 4.0x] — giả định ROE/COE/g có thể cần xem lại.",
    },
    "WACC_BOOK_EQUITY_FALLBACK": {
        "level": "warning",
        "message": "Chưa có giá thị trường nên WACC tạm tính theo giá trị sổ sách thay vì vốn hóa thị trường — cập nhật giá để định giá chính xác hơn.",
    },
    "CYCLICAL_TERMINAL_MIDCYCLE": {
        "level": "info",
        "message": "Ngành chu kỳ — giá trị vĩnh viễn (terminal value) đã ép về biên lợi nhuận bình quân chu kỳ (mid-cycle), chống ngoại suy đỉnh chu kỳ.",
    },
    "POOR_QUALITY": {
        "level": "warning",
        "message": (
            "Điểm chất lượng cơ bản của doanh nghiệp (Piotroski F-score) đang ở mức thấp — "
            "phản ánh sức khỏe tài chính/hiệu quả hoạt động chưa tốt ở kỳ gần nhất. Đây là "
            "tín hiệu CẢNH BÁO CHẤT LƯỢNG DOANH NGHIỆP, KHÔNG phải lỗi dữ liệu hay lỗi mô hình."
        ),
    },
    "F_SCORE_POOR_QUALITY": {
        "level": "warning",
        "message": (
            "Điểm Piotroski F-score thấp — chất lượng cơ bản (lợi nhuận, đòn bẩy, hiệu quả) yếu "
            "ở kỳ gần nhất. Là tín hiệu cơ bản cần lưu ý, KHÔNG phải lỗi dữ liệu/mô hình."
        ),
    },
    "IMPLIED_PB_OUT_OF_BOUNDS": {
        "level": "warning",
        "message": (
            "Hệ số P/B ngầm định (giá hợp lý ÷ giá trị sổ sách) nằm ngoài khoảng hợp lý của ngành — "
            "định giá có thể đang lạc quan hoặc thận trọng hơn mặt bằng ngành, nên đối chiếu thêm."
        ),
    },
    "IMPLIED_PE_OUT_OF_BOUNDS": {
        "level": "warning",
        "message": (
            "Hệ số P/E ngầm định (giá hợp lý ÷ EPS) nằm ngoài khoảng hợp lý của ngành — "
            "nên đối chiếu lại giả định tăng trưởng/biên lợi nhuận."
        ),
    },
    "IMPLIED_PE_OUT_OF_BOUNDS_EXTREME": {
        "level": "error",
        "message": (
            "Hệ số P/E ngầm định lệch RẤT XA khoảng hợp lý (dưới 4x hoặc trên 50x) — "
            "cần rà soát kỹ giả định trước khi tin tưởng kết quả."
        ),
    },
    "IMPLIED_EV_EBITDA_OUT_OF_BOUNDS": {
        "level": "warning",
        "message": (
            "Bội số EV/EBITDA ngầm định nằm ngoài khoảng hợp lý của ngành — "
            "nên đối chiếu lại giả định trước khi kết luận."
        ),
    },
    "FINANCIAL_QC_MISSING": {
        "level": "warning",
        "message": "Thiếu một số dữ liệu tài chính để chạy đầy đủ bộ kiểm định chất lượng (QC) — độ tin cậy thấp hơn.",
    },
    "DATA_INCOMPLETE": {
        "level": "warning",
        "message": "Dữ liệu đầu vào chưa đầy đủ để tính hết các chỉ số chất lượng — kết quả mang tính tham khảo.",
    },
    "SENSITIVITY_FAILED": {
        "level": "info",
        "message": "Không tính được độ nhạy (Greeks) cho mã này — không ảnh hưởng giá trị định giá chính, chỉ thiếu phần phân tích độ nhạy.",
    },
}


def describe_flags(flags: List[str]) -> List[Dict[str, str]]:
    """Trả về danh sách {code, level, message} cho các cờ đã biết; cờ lạ dùng mô tả mặc định."""
    out = []
    for f in flags or []:
        info = FLAG_DESCRIPTIONS.get(f) or FLAG_DESCRIPTIONS.get(str(f).upper())
        if info:
            out.append({"code": f, **info})
        else:
            out.append({"code": f, "level": "info", "message": f"Cờ hệ thống: {f} (chưa có mô tả chi tiết)."})
    return out
