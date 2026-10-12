import os
import json
import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ValidationError
from openai import OpenAI

logger = logging.getLogger(__name__)

# ==========================================
# PYDANTIC SCHEMAS CHO VALIDATION
# ==========================================

class ExtractedField(BaseModel):
    value: Optional[Any] = Field(None, description="Giá trị được trích xuất")
    source_quote: Optional[str] = Field(None, description="Câu văn gốc trong báo cáo chứa giá trị này")
    missing: bool = Field(False, description="True nếu thông tin này không xuất hiện trong báo cáo")

class RNAVProject(BaseModel):
    ten_du_an: ExtractedField
    dien_tich_san_thuong_pham_m2: ExtractedField
    he_so_su_dung_dat: ExtractedField
    gia_ban_tren_m2: ExtractedField
    chi_phi_tren_m2: ExtractedField
    bien_ln_rong: ExtractedField
    ty_le_so_huu: ExtractedField
    nam_mo_ban: ExtractedField
    nam_ban_giao: ExtractedField
    ty_le_da_ban: ExtractedField

class RNAVResult(BaseModel):
    ticker: str
    projects: List[RNAVProject]

class SOTPSegment(BaseModel):
    ten_mang: ExtractedField
    chi_tieu: ExtractedField
    gia_tri: ExtractedField
    phuong_phap_dinh_gia_mang: ExtractedField
    multiple_ky_vong: ExtractedField
    loai_gia_tri: ExtractedField
    ma_ck: ExtractedField
    ty_le_so_huu: ExtractedField
    thi_gia: ExtractedField

class SOTPResult(BaseModel):
    ticker: str
    segments: List[SOTPSegment]


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_openai_client() -> OpenAI:
    """Khởi tạo OpenAI client. Trỏ sang DeepSeek nếu có DEEPSEEK_API_KEY."""
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com") if os.getenv("DEEPSEEK_API_KEY") else None
    
    if not api_key:
        raise ValueError("Chưa cấu hình DEEPSEEK_API_KEY hoặc OPENAI_API_KEY.")
    
    return OpenAI(api_key=api_key, base_url=base_url)

def flatten_extracted_field(field_obj: ExtractedField) -> Dict:
    """Biến đổi nested object thành flat để tiện hiển thị trên st.data_editor."""
    return {
        "value": field_obj.value,
        "source": field_obj.source_quote,
        "missing": field_obj.missing
    }

def flatten_rnav_project(proj: RNAVProject) -> Dict:
    flat = {}
    for key, field_obj in proj.model_dump().items():
        flat[key] = field_obj['value']
        flat[f"{key}_source"] = field_obj['source_quote']
        flat[f"{key}_missing"] = field_obj['missing']
    return flat

def flatten_sotp_segment(seg: SOTPSegment) -> Dict:
    flat = {}
    for key, field_obj in seg.model_dump().items():
        flat[key] = field_obj['value']
        flat[f"{key}_source"] = field_obj['source_quote']
        flat[f"{key}_missing"] = field_obj['missing']
    return flat

# ==========================================
# MAIN EXTRACTOR FUNCTIONS
# ==========================================

def extract_rnav_projects(ticker: str, context_text: str) -> dict:
    """
    Bóc tách dữ liệu RNAV bằng AI, áp dụng strict validation và source quoting.
    """
    client = get_openai_client()
    
    prompt = f"""Bạn là một chuyên gia phân tích tài chính (Equity Analyst) chuyên về ngành Bất động sản tại Việt Nam.
Tôi sẽ cung cấp cho bạn một đoạn văn bản trích xuất từ Báo cáo phân tích hoặc Thuyết minh BCTC của mã {ticker}.
Nhiệm vụ của bạn là bóc tách các DỰ ÁN BẤT ĐỘNG SẢN và các con số tài chính liên quan để phục vụ định giá RNAV.

RÀNG BUỘC BẮT BUỘC (CHỐNG ẢO GIÁC - HALLUCINATION):
1. Chỉ trích xuất con số CÓ THẬT trong văn bản. TUYỆT ĐỐI KHÔNG SUY DIỄN, KHÔNG ƯỚC LƯỢNG.
2. Nếu một thông tin KHÔNG CÓ trong text, bạn phải trả về `value: null` và `missing: true`.
3. Mỗi con số/thông tin bóc ra PHẢI KÈM `source_quote` là CÂU VĂN GỐC CHỨA SỐ ĐÓ. Nếu không có câu gốc, coi như `missing: true`.
4. Quy ước đơn vị: Diện tích là m2 (nếu cho ha thì đổi ra m2 bằng cách nhân 10,000, hoặc trích ha và hệ số). Giá/Chi phí là đồng. Tỷ lệ %.

Bạn PHẢI trả về ĐÚNG định dạng JSON sau:
{{
    "ticker": "{ticker}",
    "projects": [
        {{
            "ten_du_an": {{"value": "...", "source_quote": "...", "missing": false}},
            "dien_tich_san_thuong_pham_m2": {{"value": số_thực_hoặc_null, "source_quote": "...", "missing": bool}},
            "he_so_su_dung_dat": {{"value": số_thực_hoặc_null, "source_quote": "...", "missing": bool}},
            "gia_ban_tren_m2": {{"value": số_thực_hoặc_null, "source_quote": "...", "missing": bool}},
            "chi_phi_tren_m2": {{"value": số_thực_hoặc_null, "source_quote": "...", "missing": bool}},
            "bien_ln_rong": {{"value": số_thực_hoặc_null, "source_quote": "...", "missing": bool}},
            "ty_le_so_huu": {{"value": số_thực_hoặc_null, "source_quote": "...", "missing": bool}},
            "nam_mo_ban": {{"value": số_nguyên_hoặc_null, "source_quote": "...", "missing": bool}},
            "nam_ban_giao": {{"value": số_nguyên_hoặc_null, "source_quote": "...", "missing": bool}},
            "ty_le_da_ban": {{"value": số_thực_hoặc_null, "source_quote": "...", "missing": bool}}
        }}
    ]
}}

ĐOẠN VĂN BẢN:
{context_text}
"""
    
    try:
        response = client.chat.completions.create(
            model=os.getenv("AI_MODEL_NAME", "deepseek-chat"),
            messages=[
                {"role": "system", "content": "You are a highly precise financial data extractor. Output strict JSON exactly as requested."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        if content.startswith("```json"):
            content = content.replace("```json\\n", "").replace("```json", "").replace("```", "").strip()
            
        data = json.loads(content)
        
        # Validate bằng Pydantic
        validated_data = RNAVResult.model_validate(data)
        
        # Flatten
        flat_projects = [flatten_rnav_project(p) for p in validated_data.projects]
        return {"projects": flat_projects}
        
    except json.JSONDecodeError as e:
        logger.error(f"Lỗi JSON Decode: {e}")
        return {"error": "AI trả về JSON không hợp lệ.", "projects": []}
    except ValidationError as e:
        logger.error(f"Lỗi Pydantic Validation: {e}")
        return {"error": f"Dữ liệu AI thiếu trường bắt buộc: {str(e)}", "projects": []}
    except Exception as e:
        logger.error(f"Lỗi API hoặc Không xác định: {e}")
        return {"error": str(e), "projects": []}


def extract_sotp_segments(ticker: str, context_text: str) -> dict:
    """
    Bóc tách dữ liệu SOTP bằng AI, áp dụng strict validation và source quoting.
    """
    client = get_openai_client()
    
    prompt = f"""Bạn là một chuyên gia phân tích tài chính (Equity Analyst) chuyên về định giá SOTP (Sum of The Parts).
Tôi sẽ cung cấp cho bạn một đoạn văn bản trích xuất từ Báo cáo phân tích của mã đa ngành {ticker}.
Nhiệm vụ của bạn là bóc tách các MẢNG KINH DOANH CON và các con số tài chính.

RÀNG BUỘC BẮT BUỘC (CHỐNG ẢO GIÁC - HALLUCINATION):
1. Chỉ trích xuất con số CÓ THẬT trong văn bản. KHÔNG SUY DIỄN, KHÔNG ƯỚC LƯỢNG.
2. Nếu một thông tin KHÔNG CÓ trong text, trả về `value: null` và `missing: true`.
3. Mỗi thông tin bóc ra PHẢI KÈM `source_quote` (câu văn gốc).
4. `loai_gia_tri` BẮT BUỘC phải là "EV" (nếu định giá ra Enterprise Value, ví dụ dùng EV/EBITDA, FCFF) hoặc "Equity" (nếu ra Equity Value, ví dụ P/E, P/B, FCFE).

Bạn PHẢI trả về ĐÚNG định dạng JSON sau:
{{
    "ticker": "{ticker}",
    "segments": [
        {{
            "ten_mang": {{"value": "...", "source_quote": "...", "missing": false}},
            "chi_tieu": {{"value": "...", "source_quote": "...", "missing": false}},
            "gia_tri": {{"value": số_thực_hoặc_null, "source_quote": "...", "missing": bool}},
            "phuong_phap_dinh_gia_mang": {{"value": "...", "source_quote": "...", "missing": bool}},
            "multiple_ky_vong": {{"value": số_thực_hoặc_null, "source_quote": "...", "missing": bool}},
            "loai_gia_tri": {{"value": "EV hoặc Equity", "source_quote": "...", "missing": bool}},
            "ma_ck": {{"value": "...", "source_quote": "...", "missing": true}},
            "ty_le_so_huu": {{"value": số_thực_hoặc_null, "source_quote": "...", "missing": true}},
            "thi_gia": {{"value": số_thực_hoặc_null, "source_quote": "...", "missing": true}}
        }}
    ]
}}

ĐOẠN VĂN BẢN:
{context_text}
"""
    
    try:
        response = client.chat.completions.create(
            model=os.getenv("AI_MODEL_NAME", "deepseek-chat"),
            messages=[
                {"role": "system", "content": "You are a highly precise financial data extractor. Output strict JSON exactly as requested."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        if content.startswith("```json"):
            content = content.replace("```json\\n", "").replace("```json", "").replace("```", "").strip()
            
        data = json.loads(content)
        
        validated_data = SOTPResult.model_validate(data)
        flat_segments = [flatten_sotp_segment(s) for s in validated_data.segments]
        return {"segments": flat_segments}
        
    except json.JSONDecodeError as e:
        logger.error(f"Lỗi JSON Decode: {e}")
        return {"error": "AI trả về JSON không hợp lệ.", "segments": []}
    except ValidationError as e:
        logger.error(f"Lỗi Pydantic Validation: {e}")
        return {"error": f"Dữ liệu AI thiếu trường bắt buộc: {str(e)}", "segments": []}
    except Exception as e:
        logger.error(f"Lỗi API hoặc Không xác định: {e}")
        return {"error": str(e), "segments": []}
