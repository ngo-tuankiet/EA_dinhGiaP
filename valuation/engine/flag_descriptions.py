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
        "level": "error",
        "message": (
            "Giá thị trường trong DB của mã này đã CŨ (quá 5 ngày lịch so với hôm "
            "nay) — upside tính trên giá cũ có thể lệch so với thị trường hiện tại. "
            "Chặn công bố tới khi chạy cập nhật giá (ingest prices)."
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
    "RIGHTS_ISSUE_UNDATED": {
        "level": "info",
        "message": (
            "Có đợt phát hành quyền mua công bố gần đây nhưng dữ liệu chưa có ngày GDKHQ. Quyền mua "
            "không vào hệ số chia số cổ phiếu (đi kèm tiền, chờ BCTC phản ánh cả cp lẫn tiền) nên số cp "
            "đang dùng không sai vì thiếu ngày — chỉ nhắc theo dõi đợt phát hành; không phải lỗi dữ liệu."
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
    "VALUATION_LEGS_DIVERGE": {
        "level": "error",
        "message": (
            "Hai chân định giá được pha (DCF và bội số so sánh; hoặc RI và P/B của ngân hàng, chứng "
            "khoán, bảo hiểm) lệch nhau quá ngưỡng cấu hình (publication_gate.leg_ratio_review) hoặc một "
            "chân ≤ 0 — trung bình của hai con số vênh nhau không phải giá trị hợp lý. Số chẩn đoán vẫn giữ "
            "nhưng không phát khuyến nghị; cần rà giả định của chân lệch (ROE, biên, tái đầu tư, bội số "
            "mục tiêu, cầu nối nợ)."
        ),
    },
    "BANK_ROE_FADE_PLUG": {
        "level": "warning",
        "message": (
            "Ghi sau ':' là phần LN năm 5 của ngân hàng đến từ dòng cân phai ROE về ROE terminal (roe_fade_adjustment, "
            "mô hình 3 giai đoạn), không theo driver NIM/CIR/chi phí tín dụng — sửa driver các năm chuyển tiếp gần như "
            "không đổi kết quả. Muốn LN năm đó theo driver: chỉnh driver trên tab giả định (năm được đánh dấu bỏ phai) "
            "hoặc rà ROE ngành/λ (bank_terminal.fade_plug_flag_share)."
        ),
    },
    "MINORITY_AT_BOOK_MATERIAL": {
        "level": "warning",
        "message": (
            "Lợi ích cổ đông không kiểm soát lớn so với VCSH công ty mẹ (vượt dcf.minority_book_review) mà cầu "
            "nối DCF trừ theo GIÁ SỔ, trong khi dòng tiền FCFF là 100% hợp nhất (Damodaran: nên trừ giá trị "
            "ước tính của phần CĐKKS). Giá trị/cp có thể bị đánh cao khi công ty con đáng giá hơn sổ sách — "
            "chưa điều chỉnh vì chưa có phương pháp chuẩn ước giá trị thị trường CĐKKS từ dữ liệu sẵn có."
        ),
    },
    "CIP_DOMINATES_VALUE": {
        "level": "error",
        "message": (
            "Chi phí XDCB dở dang (cộng theo giá sổ sách vào cầu nối, tương đương giả định dự án "
            "có NPV = 0) chiếm quá ngưỡng cấu hình (dcf.cip_share_review) giá trị vốn chủ theo DCF. "
            "Giá trị hợp lý chủ yếu là giả định về dự án đang xây, chưa có dòng tiền — không phát "
            "khuyến nghị cho tới khi có tiến độ/công suất dự án để mô hình hóa trực tiếp."
        ),
    },
    "PE_LEG_TTM": {
        "level": "info",
        "message": (
            "Chân P/E phụ của DCF nhân P/E trailing lịch sử với lợi nhuận 4 quý gần nhất (cùng "
            "định nghĩa tử/mẫu). Nếu LN TTM có khoản bất thường (lãi tài chính, thanh lý) thì "
            "chân này bị ảnh hưởng theo."
        ),
    },
    "TAX_FALLBACK_EBIT": {
        "level": "warning",
        "message": (
            "Thiếu dòng tổng lợi nhuận kế toán trước thuế: thuế suất hiệu dụng tính theo cách cũ "
            "(thuế / (EBIT − lãi vay)) — mẫu số bỏ sót thu nhập tài chính/liên doanh nên có thể cao hơn thực tế."
        ),
    },
    "UPSIDE_EXTREME_REVIEW": {
        "level": "error",
        "message": (
            "Upside rất lớn (>150%) — giá hợp lý cao hơn 2.5 lần thị giá. Chặn công bố tới khi "
            "RÀ LẠI giả định đầu vào (tăng trưởng, biên lợi nhuận, bội số mục tiêu); có thể do "
            "một năm đột biến hoặc bội số ngành quá cao."
        ),
    },
    "DOWNSIDE_EXTREME_REVIEW": {
        "level": "error",
        "message": (
            "Định giá thấp hơn nhiều so với thị giá (giá hợp lý < 40% thị giá). Chặn công bố "
            "tới khi kiểm tra: dữ liệu đầu vào bất thường (vd capex/khấu hao một năm đột "
            "biến bị ngoại suy), lợi nhuận gần đây âm, hoặc thị trường đang định giá "
            "yếu tố mô hình chưa nắm bắt (câu chuyện tăng trưởng, tài sản ẩn)."
        ),
    },
    "VALUATION_PROXY": {
        "level": "error",
        "message": (
            "Đây là định giá PROXY — ước lượng nhanh từ giá trị sổ sách (BCTC), "
            "chưa phải mô hình chi tiết theo dự án/mảng kinh doanh như CTCK chuyên "
            "nghiệp. Độ tin cậy thấp hơn nhóm phương pháp đầy đủ (IMPLEMENTED) nên "
            "không công bố."
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
    "SOTP_HOLDINGS_MODE": {
        "level": "info",
        "message": (
            "SOTP theo cổ phần niêm yết (config/sotp_holdings.yaml): phần sở hữu ở công ty con/liên kết niêm "
            "yết định giá theo THỊ GIÁ × tỷ lệ lợi ích kinh tế, phần còn lại theo VCSH mẹ hợp nhất, trừ chiết "
            "khấu holding. Đây là giá trị theo giá thị trường của công ty con, không phải giá trị nội tại của chúng."
        ),
    },
    "SOTP_UNLISTED_AT_BOOK": {
        "level": "info",
        "message": "Các mảng/công ty con chưa niêm yết (hoặc chưa có giá trong DB) đang giữ theo giá trị sổ sách hợp nhất.",
    },
    "SOTP_HOLDINGS_UNVERIFIED": {
        "level": "error",
        "message": (
            "Tỷ lệ sở hữu trong config/sotp_holdings.yaml chưa được người dùng đối chiếu (reviewed_by trống, "
            "hoặc có reviewed_by nhưng thiếu/sai ngày duyệt as_of nên không tính được hạn rà soát) — "
            "không phát khuyến nghị cho tới khi xác nhận với BCTN/thuyết minh BCTC."
        ),
    },
    "SOTP_HOLDINGS_STALE": {
        "level": "error",
        "message": (
            "Bảng cổ phần SOTP đã quá hạn rà soát (review_ttl_days) hoặc giá một công ty con niêm yết bị cũ — "
            "cập nhật tỷ lệ sở hữu/giá trước khi công bố."
        ),
    },
    "SOTP_HOLDINGS_INCOMPLETE": {
        "level": "warning",
        "message": (
            "Có khai báo cổ phần niêm yết nhưng không dựng được giá/VCSH của ít nhất một công ty con — quay về "
            "proxy SOTP (bị chặn công bố)."
        ),
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
    "LAND_BANK_INPUT_MISSING": {
        "level": "error",
        "message": (
            "Có dòng quỹ đất (Land Bank Add-on) thiếu giá sổ (gia_tri_so_sach_ty, tỷ đồng; nhập 0 nếu đất không "
            "ghi trên BCĐKT) — dòng đó không được cộng và kết quả bị chặn công bố tới khi nhập đủ, để không cộng "
            "trùng giá trị đất đã nằm trong VCSH."
        ),
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
    # --- Đợt nâng cấp 10/2026 (s1–s7, fx1–fx3). Mức "error" = cổng công bố chặn. ---
    "NOT_RATED": {
        "level": "error",
        "message": "Không phát khuyến nghị: cổng công bố chặn vì một cờ/lỗi khác trong danh sách. Giá trị hợp lý chỉ là số chẩn đoán nội bộ.",
    },
    "DATA_REVIEW_REQUIRED": {
        "level": "error",
        "message": "Kết quả bị cổng công bố giữ lại — cần analyst rà dữ liệu/giả định theo các cờ đi kèm trước khi dùng.",
    },
    "PROXY_IMPLAUSIBLE": {
        "level": "error",
        "message": (
            "Proxy SOTP (lợi nhuận × P/E + sổ sách) lệch thị giá quá ngưỡng proxy_max_divergence hoặc ≤ 0 — proxy không "
            "mô tả được cấu trúc tập đoàn. Cần khai báo cổ phần công ty con trong config/sotp_holdings.yaml."
        ),
    },
    "AI_INPUTS_UNVERIFIED": {
        "level": "error",
        "message": "Định giá dùng dữ liệu mảng/dự án do AI nhập (AI_RNAV/AI_SOTP) chưa được người dùng xác nhận — không công bố.",
    },
    "SOTP_SUBSIDIARY_DATA_ERROR": {
        "level": "error",
        "message": (
            "Một công ty con/liên kết niêm yết dùng trong SOTP_HOLDINGS có lỗi dữ liệu mức chặn (vd chưa audit nguồn "
            "SOURCE_AUDIT_MISSING, xung đột nguồn, thiếu chỉ tiêu, lệch đẳng thức BCTC). Vốn hóa và VCSH của nó đi thẳng "
            "vào giá trị tập đoàn mẹ nên mã mẹ không công bố tới khi lỗi của mã con (ghi trong ngoặc) được xử lý."
        ),
    },
    "SOTP_SEGMENT_INPUT_MISSING": {
        "level": "warning",
        "message": "Mảng SOTP do AI nhập thiếu trường bắt buộc — không dùng AI_SOTP (không định giá nửa vời); các trường thiếu ghi sau dấu ':'.",
    },
    "RNAV_PROJECT_INPUT_MISSING": {
        "level": "warning",
        "message": "Dự án RNAV thiếu trường bắt buộc — không dùng RNAV theo dự án cho tới khi nhập đủ; các trường thiếu ghi sau dấu ':'.",
    },
    "MISSING_FINANCIAL_INPUT": {
        "level": "error",
        "message": (
            "Thiếu chỉ tiêu BCTC bắt buộc (hoặc chưa đủ bốn quý cho TTM) ở kỳ/chỉ tiêu ghi sau ':' — "
            "không tự điền số thay thế; chặn công bố tới khi nạp đủ dữ liệu."
        ),
    },
    "SOURCE_AUDIT_MISSING": {
        "level": "error",
        "message": (
            "Mã chưa có dòng audit đối chiếu BCTC với nguồn độc lập (data/source_quality_status.json). Chạy "
            "scripts/audit_vn100_data.py sau khi có cache nguồn; chưa audit thì không công bố."
        ),
    },
    "SOURCE_AUDIT_STALE": {
        "level": "error",
        "message": (
            "Số BCTC đã đối chiếu nguồn bị thay đổi sau lần audit (dấu vân tay các kỳ đã đối chiếu khác), hoặc audit cũ "
            "chưa lưu dấu/tập kỳ, hoặc taxonomy đổi phiên bản, hoặc số kỳ nạp sau audit chưa đối chiếu vượt "
            "audit.max_unaudited_periods (các kỳ ghi sau ':') — chạy lại audit trước khi công bố."
        ),
    },
    "SOURCE_AUDIT_PARTIAL": {
        "level": "warning",
        "message": (
            "Có kỳ BCTC nạp sau lần audit mà nguồn đối chiếu chưa có (kỳ ghi sau ':'). Các kỳ đã đối chiếu không đổi nên "
            "không chặn (tối đa audit.max_unaudited_periods kỳ, vượt thì thành SOURCE_AUDIT_STALE); làm mới cache "
            "nguồn và chạy lại audit sau mùa BCTC."
        ),
    },
    "SOURCE_CONFLICT": {
        "level": "error",
        "message": (
            "Ô BCTC trọng yếu cho định giá lệch nguồn đối chiếu độc lập (số ô ghi sau ':') và chưa đo được tác động lên giá "
            "trị hợp lý dưới ngưỡng trọng yếu — không công bố tới khi xác minh số đúng."
        ),
    },
    "SOURCE_CONFLICT_IMMATERIAL": {
        "level": "warning",
        "message": (
            "Có ô BCTC lệch nguồn đối chiếu nhưng đã đo: thay bằng số nguồn chỉ đổi giá trị hợp lý ≤ ngưỡng "
            "audit.source_conflict_fv_materiality_pct — không chặn, vẫn nên xác minh."
        ),
    },
    "SOURCE_CONTRACT_ERROR": {
        "level": "warning",
        "message": "File nguồn đối chiếu sai cấu trúc nên không so được (số báo cáo lỗi ghi sau ':') — kỳ/chỉ tiêu đó chưa được kiểm.",
    },
    "FILING_PRECEDENCE": {
        "level": "warning",
        "message": (
            "DB đang dùng BCTC chính thức đã soát xét (filing, tên miền trong audit.filing_source_domains) khác số vendor "
            "trong ngưỡng audit.filing_precedence_max_rel_diff — đúng thứ tự ưu tiên filing > vendor, chỉ cảnh báo."
        ),
    },
    "FILING_BS_INCOMPLETE": {
        "level": "warning",
        "message": (
            "Bảng cân đối từ filing của kỳ ghi sau ':' thiếu tổng mục nên bị bỏ cả bộ, dùng bảng cân đối vendor — tránh trộn "
            "hai nguồn trong một báo cáo (tổng tài sản lệch tổng nguồn vốn)."
        ),
    },
    "INCOMPLETE_YEAR_DROPPED": {
        "level": "info",
        "message": "Năm sơ khai thiếu báo cáo lưu chuyển tiền tệ bị bỏ khỏi lịch sử (không điền 0 làm lệch trung vị/tăng trưởng).",
    },
    "INCONSISTENT_YEAR_DROPPED": {
        "level": "info",
        "message": (
            "Năm cũ (ngoài mọi cửa sổ mô hình) có số liệu không khớp đẳng thức bị bỏ khỏi lịch sử. Năm nằm trong cửa sổ "
            "mô hình vẫn giữ để lỗi đẳng thức chặn công bố."
        ),
    },
    "UNEXPLAINED_CURRENT_ASSETS": {
        "level": "warning",
        "message": (
            "Tài sản ngắn hạn chênh tổng các thành phần (tiền, ĐTNH, phải thu, tồn kho, TSNH khác) quá "
            "audit.unexplained_current_assets_gap — nghi một dòng bị mất khi nạp dữ liệu; cần đối chiếu BCTC gốc."
        ),
    },
    "CIP_LINE_MISSING": {
        "level": "warning",
        "message": (
            "Năm ghi sau ':' có XDCB dở dang = 0 trong khi chi phí SXKD dở dang dài hạn > 0 — nguồn nghi xếp nhầm mã số; "
            "giữ số nguồn, không tự phân loại lại. Bội số EV lịch sử loại XDCB có thể lệch ở năm đó."
        ),
    },
    "MULTIPLE_FROM_PEER_MEDIAN": {
        "level": "warning",
        "message": (
            "Bội số mục tiêu (ghi sau ':') lấy trung vị hiện hành của nhóm ngành vì mã thiếu đủ quan sát lịch sử của chính "
            "nó — độ đặc thù của doanh nghiệp không được phản ánh."
        ),
    },
    "MULTIPLE_FROM_SECTOR_CONSTANT": {
        "level": "warning",
        "message": "Không có lịch sử bội số của mã lẫn trung vị nhóm — dùng hằng số bội số ngành trong cấu hình; độ tin cậy chân bội số thấp.",
    },
    "MULTIPLE_PRE_ISSUE_EXCLUDED": {
        "level": "info",
        "message": (
            "Quan sát bội số lịch sử trước đợt phát hành có thu tiền (quyền mua/riêng lẻ) bị loại: giá đã điều chỉnh × số "
            "cp hiện tại làm phình vốn hóa kỳ cũ so với VCSH chưa có tiền thu (relative_multiples.capital_raise_*)."
        ),
    },
    "MULTIPLE_PRE_ISSUE_PROFORMA": {
        "level": "info",
        "message": (
            "Quan sát P/B lịch sử trước đợt phát hành có thu tiền được pro-forma: vốn hóa (giá đã điều chỉnh × số cp "
            "hiện tại, đã gồm tiền thu) / (VCSH kỳ đó + tiền thu C từ LCTT, đối chiếu tăng vốn góp + thặng dư). Ghi sau "
            "':' số quan sát và C (tỷ đồng) cộng vào quan sát cũ nhất (relative_multiples.capital_raise_*)."
        ),
    },
    "NEGATIVE_DCF_LEG": {
        "level": "error",
        "message": "Chân DCF âm (nợ ròng lớn hơn giá trị doanh nghiệp chiết khấu) — không pha số âm vào trung bình; FV về 0 và không công bố.",
    },
    "BANK_NEGATIVE_VALUATION_LEG": {
        "level": "error",
        "message": "Chân RI hoặc P/B của ngân hàng âm — không pha âm thầm vào trung bình; FV về 0 và không công bố.",
    },
    "BANK_NO_MARKET_PB_HISTORY": {
        "level": "warning",
        "message": "Ngân hàng thiếu ≥ 3 năm P/B thị trường lịch sử — chân P/B dùng P/B hợp lý (ROE−g)/(COE−g), không còn là phép thử độc lập với RI.",
    },
    "SEC_NO_MARKET_PB_HISTORY": {
        "level": "warning",
        "message": "Công ty chứng khoán thiếu P/B thị trường lịch sử — chân P/B dùng P/B hợp lý cùng ROE/COE với RI nên không kiểm tra chéo được.",
    },
    "INS_NO_MARKET_PB_HISTORY": {
        "level": "warning",
        "message": "Doanh nghiệp bảo hiểm thiếu P/B thị trường lịch sử — chân P/B dùng P/B hợp lý cùng ROE/COE với RI nên không kiểm tra chéo được.",
    },
    "SEC_PAYOUT_FALLBACK": {
        "level": "warning",
        "message": "Thiếu cổ tức/LNST năm đầy đủ để đo tỷ lệ chi trả của công ty chứng khoán — dùng payout cấu hình (ghi sau ':').",
    },
    "INS_PAYOUT_FALLBACK": {
        "level": "warning",
        "message": "Thiếu cổ tức/LNST năm đầy đủ để đo tỷ lệ chi trả của doanh nghiệp bảo hiểm — dùng payout cấu hình (ghi sau ':').",
    },
    "SEC_PAYOUT_INCONSISTENT": {
        "level": "warning",
        "message": (
            "Payout dự phóng lệch payout nhất quán Gordon 1 − g/ROE quá bank_terminal.payout_consistency_tol: tăng trưởng "
            "terminal không khớp phần lợi nhuận giữ lại (Damodaran stable growth). Cờ cảnh báo, không kẹp."
        ),
    },
    "INS_PAYOUT_INCONSISTENT": {
        "level": "warning",
        "message": (
            "Payout dự phóng lệch payout nhất quán Gordon 1 − g/ROE quá bank_terminal.payout_consistency_tol: tăng trưởng "
            "terminal không khớp phần lợi nhuận giữ lại (Damodaran stable growth). Cờ cảnh báo, không kẹp."
        ),
    },
    "SEC_ROE_BELOW_COE": {
        "level": "warning",
        "message": "ROE bền vững của công ty chứng khoán thấp hơn COE — mô hình khẳng định doanh nghiệp không tạo giá trị trên vốn; tuyên bố mạnh, cần rà.",
    },
    "SEC_PB_FAR_BELOW_MARKET": {
        "level": "warning",
        "message": "P/B mục tiêu của chứng khoán thấp hơn nhiều P/B thị trường đang trả (≤ guardrails.pb_vs_market_min_ratio) — cần luận điểm rõ.",
    },
    "SEC_PB_FAR_ABOVE_MARKET": {
        "level": "warning",
        "message": "P/B mục tiêu của chứng khoán cao hơn nhiều P/B thị trường đang trả (≥ guardrails.pb_vs_market_max_ratio) — cần luận điểm rõ.",
    },
    "INS_PB_FAR_BELOW_MARKET": {
        "level": "warning",
        "message": "P/B mục tiêu của bảo hiểm thấp hơn nhiều P/B thị trường đang trả (≤ guardrails.pb_vs_market_min_ratio) — cần luận điểm rõ.",
    },
    "INS_PB_FAR_ABOVE_MARKET": {
        "level": "warning",
        "message": "P/B mục tiêu của bảo hiểm cao hơn nhiều P/B thị trường đang trả (≥ guardrails.pb_vs_market_max_ratio) — cần luận điểm rõ.",
    },
    "BANK_PB_FAR_BELOW_MARKET": {
        "level": "warning",
        "message": "P/B mục tiêu của ngân hàng thấp hơn nhiều P/B thị trường đang trả (≤ guardrails.pb_vs_market_min_ratio) — cần luận điểm rõ.",
    },
    "BANK_PB_FAR_ABOVE_MARKET": {
        "level": "warning",
        "message": "P/B mục tiêu của ngân hàng cao hơn nhiều P/B thị trường đang trả (≥ guardrails.pb_vs_market_max_ratio) — cần luận điểm rõ.",
    },
    "FV_FAR_BELOW_PRICE": {
        "level": "warning",
        "message": "Giá trị hợp lý thấp hơn thị giá quá guardrails.fv_below_price_alarm — phép thử độc lập với đồng thuận CTCK; cần rà giả định.",
    },
    "FV_FAR_ABOVE_PRICE": {
        "level": "warning",
        "message": "Giá trị hợp lý cao hơn thị giá quá guardrails.fv_above_price_alarm — phép thử độc lập với đồng thuận CTCK; cần rà giả định.",
    },
    "BANK_CREDIT_COST_SPIKE": {
        "level": "warning",
        "message": (
            "Chi phí tín dụng TTM vượt credit_cost_spike_multiple × trung vị chu kỳ — coi là trích lập đột biến một lần, "
            "dự phóng dùng trung vị chu kỳ thay vì phai từ mức TTM."
        ),
    },
    "BANK_LEVERAGE_ABOVE_HISTORY": {
        "level": "warning",
        "message": "VCSH/tổng tài sản dự phóng năm cuối thấp hơn trung vị lịch sử — ngân hàng dùng đòn bẩy cao hơn quá khứ, ROE dự phóng có thể bị thổi lên.",
    },
    "BANK_ROE_FORECAST_VS_HISTORY": {
        "level": "warning",
        "message": "ROE năm 5 của dự phóng driver (trước hội tụ) lệch trung vị ROE lịch sử quá bank_terminal.roe_history_tolerance — rà NIM/CIR/chi phí tín dụng.",
    },
    "BANK_G_CLAMPED_BELOW_COE": {
        "level": "warning",
        "message": "Tăng trưởng terminal ≥ COE (Gordon không xác định) — g bị hạ xuống dưới COE 0,5 điểm %; cần rà COE/g.",
    },
    "CREDIT_GROWTH_CAPPED": {
        "level": "info",
        "message": "Tăng trưởng tín dụng lịch sử nằm ngoài dải cấu hình (credit_growth_floor/cap) — dự phóng dùng giá trị đã kẹp.",
    },
    "DDM_SKIPPED_LOW_PAYOUT": {
        "level": "info",
        "message": "Tỷ lệ chi trả cổ tức dưới min_payout — không dùng DDM (cổ tức không đại diện dòng tiền cho cổ đông).",
    },
    "PE_DISABLED_TTM_LOSS": {
        "level": "warning",
        "message": "Doanh nghiệp (không chu kỳ) đang lỗ TTM — không dùng P/E (luật vàng #2); chân P/E bằng 0.",
    },
    "PE_ON_MIDCYCLE_EARNINGS_TTM_LOSS": {
        "level": "warning",
        "message": "Doanh nghiệp chu kỳ lỗ TTM — chân P/E áp lên lợi nhuận giữa chu kỳ, không phải lợi nhuận hiện tại; cần rà khả năng phục hồi.",
    },
}


def describe_flags(flags: List[str]) -> List[Dict[str, str]]:
    """Trả về danh sách {code, level, message} cho các cờ đã biết; cờ lạ dùng mô tả mặc định.
    Cờ mang chi tiết sau ':' (vd SOURCE_AUDIT_PARTIAL:2026Q3) tra theo mã trước ':'."""
    out = []
    for f in flags or []:
        info = (
            FLAG_DESCRIPTIONS.get(f)
            or FLAG_DESCRIPTIONS.get(str(f).upper())
            or FLAG_DESCRIPTIONS.get(str(f).split(":", 1)[0].strip().upper())
        )
        if info:
            out.append({"code": f, **info})
        else:
            out.append({"code": f, "level": "info", "message": f"Cờ hệ thống: {f} (chưa có mô tả chi tiết)."})
    return out
