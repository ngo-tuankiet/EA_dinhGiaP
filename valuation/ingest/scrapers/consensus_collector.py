import json
import datetime
import os
import re
from typing import Dict, Any, List, Optional
from pypdf import PdfReader
from openai import OpenAI
from sqlalchemy.dialects.postgresql import insert

from valuation.config import settings
from valuation.db.session import SessionLocalWrite
from valuation.db.models import Consensus
from valuation.ingest.vnstock_client import vnstock_client

def parse_vnstock_date(date_str: str) -> Optional[datetime.date]:
    """Parse date from formats like '18-May-26' or '2026-05-18'"""
    if not date_str:
        return None
    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    # Try Regex fallback
    match = re.search(r"(\d{1,2})-([A-Za-z]{3})-(\d{2,4})", date_str)
    if match:
        d, m, y = match.groups()
        # Convert month name to number
        months = {"jan":1, "feb":2, "mar":3, "apr":4, "may":5, "jun":6, "jul":7, "aug":8, "sep":9, "oct":10, "nov":11, "dec":12}
        m_num = months.get(m.lower())
        if m_num:
            y_full = 2000 + int(y) if len(y) == 2 else int(y)
            return datetime.date(y_full, m_num, int(d))
    return None

def import_vnstock_recommendations(ticker: str) -> List[Dict[str, Any]]:
    """
    Lấy khuyến nghị của VCI từ vnstock.api.company.overview và lưu vào DB.
    Trả về danh sách các records đã được import.
    """
    print(f"Fetching VCI recommendations from vnstock for {ticker}...")
    try:
        df = vnstock_client.get_company_overview(ticker)
        if df.empty:
            print(f"No company overview found for {ticker}")
            return []
            
        info = df.iloc[0]
        records = []
        
        # 1. Khuyến nghị hiện tại
        target_price = info.get("target_price")
        rating = info.get("rating")
        rating_as_of = info.get("rating_as_of")
        analyst = info.get("analyst") or "VCI Analyst"
        
        if target_price and rating_as_of:
            rep_date = parse_vnstock_date(str(rating_as_of))
            if rep_date:
                records.append({
                    "ticker": ticker,
                    "broker": f"VCI ({analyst})",
                    "report_date": rep_date,
                    "target_price": float(target_price),
                    "rating": str(rating),
                    "source_url": "vnstock://overview",
                    "raw_quote": f"Current VCI analyst recommendation: {rating} with target price {target_price:,.0f} VND"
                })
                
        # 2. Khuyến nghị cũ (prev_insight)
        prev = info.get("prev_insight")
        if isinstance(prev, str):
            try:
                # Nếu là string dạng dict
                prev = json.loads(prev.replace("'", "\""))
            except Exception:
                prev = None
                
        if isinstance(prev, dict):
            prev_tp = prev.get("targetPrice") or prev.get("target_price")
            prev_rat = prev.get("rating")
            prev_date_str = prev.get("ratingAsOf") or prev.get("rating_as_of")
            prev_analyst = prev.get("analyst") or analyst
            
            if prev_tp and prev_date_str:
                prev_date = parse_vnstock_date(str(prev_date_str))
                if prev_date:
                    records.append({
                        "ticker": ticker,
                        "broker": f"VCI ({prev_analyst})",
                        "report_date": prev_date,
                        "target_price": float(prev_tp),
                        "rating": str(prev_rat),
                        "source_url": "vnstock://prev_insight",
                        "raw_quote": f"Previous VCI analyst recommendation: {prev_rat} with target price {prev_tp:,.0f} VND"
                    })
                    
        if not records:
            return []
            
        # Lưu vào DB
        db = SessionLocalWrite()
        imported = []
        try:
            for rec in records:
                stmt = insert(Consensus).values(rec)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["ticker", "broker", "report_date"],
                    set_={
                        "target_price": stmt.excluded.target_price,
                        "rating": stmt.excluded.rating,
                        "source_url": stmt.excluded.source_url,
                        "raw_quote": stmt.excluded.raw_quote
                    }
                )
                db.execute(stmt)
                imported.append(rec)
            db.commit()
            print(f"Successfully imported {len(imported)} VCI recommendations for {ticker}")
        except Exception as e:
            db.rollback()
            print(f"Error saving VCI recommendations: {e}")
        finally:
            db.close()
            
        return imported
    except Exception as e:
        print(f"Failed to import vnstock recommendations for {ticker}: {e}")
        return []

def extract_consensus_from_pdf_text(text: str) -> Dict[str, Any]:
    """
    Gửi text thô trích xuất từ PDF qua DeepSeek API để trích xuất JSON.
    """
    if not settings.deepseek_api_key:
        print("Warning: DEEPSEEK_API_KEY is not set. Cannot run DeepSeek PDF extractor.")
        return {}

    client = OpenAI(
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com/v1"
    )

    prompt = f"""
    Bạn là một chuyên viên dữ liệu tài chính.
    Hãy đọc kỹ đoạn văn bản dưới đây được trích xuất từ báo cáo phân tích cổ phiếu của một công ty chứng khoán (CTCK).
    Trích xuất các thông tin định giá và khuyến nghị sau:
    1. broker: Tên công ty chứng khoán phát hành báo cáo (viết tắt ngắn gọn, ví dụ: SSI, VCI, HSC, MBS, VNDS, MAS, VCBS, BVSC...).
    2. report_date: Ngày phát hành báo cáo dạng YYYY-MM-DD (nếu có, ví dụ 2024-05-18).
    3. target_price: Giá mục tiêu khuyến nghị (số nguyên VND, ví dụ 125000). Cần phân biệt rõ đơn vị (nghìn đồng hoặc đồng).
    4. rating: Khuyến nghị (MUA, BÁN, THEO DÕI, KHẢ QUAN, TRUNG LẬP, BUY, HOLD, SELL, OUTPERFORM...).
    5. raw_quote: Câu hoặc đoạn văn chứa trực tiếp khuyến nghị và giá mục tiêu để đối chiếu.

    QUY TẮC NGHIÊM NGẶT (GUARDRAILS):
    - Chỉ trích xuất từ dữ liệu có thật trong văn bản.
    - Tuyệt đối không tự đoán, không tự bịa số hay giả định giá trị.
    - Nếu không tìm thấy target_price, trả về null cho tất cả các trường.
    - Chỉ trả về ĐÚNG MỘT JSON object hợp lệ, không kèm giải thích hay text nào khác ngoài JSON.

    Format JSON bắt buộc:
    {{
        "broker": <string hoặc null>,
        "report_date": <string dạng YYYY-MM-DD hoặc null>,
        "target_price": <int hoặc null>,
        "rating": <string hoặc null>,
        "raw_quote": <string hoặc null>
    }}
    
    --- VĂN BẢN BÁO CÁO ---
    {text[:8000]}  # Giới hạn 8000 ký tự đầu tiên để tránh quá tải token
    """

    try:
        response = client.chat.completions.create(
            # "deepseek-chat" — không dùng model suy luận "deepseek-v4-flash" vì
            # tốn token "suy nghĩ" ngẫu nhiên, đôi khi cắt cụt JSON (xem
            # valuation/analysis/ai_insight.py).
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a precise financial data extraction assistant. Always respond in pure JSON format without markdown code blocks."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        
        content = response.choices[0].message.content.strip()
        data = json.loads(content)
        return data
        
    except Exception as e:
        print(f"Error running DeepSeek PDF extractor: {e}")
        return {}

def process_pdf_report(pdf_path: str, ticker: str, source_url: str = "") -> Optional[Dict[str, Any]]:
    """
    Đọc PDF rời, trích xuất text và dùng DeepSeek API để lưu khuyến nghị vào DB.
    """
    print(f"Processing PDF report: {pdf_path} for {ticker}...")
    if not os.path.exists(pdf_path):
        print(f"PDF file does not exist: {pdf_path}")
        return None
        
    try:
        reader = PdfReader(pdf_path)
        text_content = ""
        # Đọc 3 trang đầu tiên (thường chứa đủ thông tin tóm tắt định giá)
        for page in reader.pages[:3]:
            text_content += page.extract_text() or ""
            
        if not text_content.strip():
            print("PDF has no readable text content.")
            return None
            
        data = extract_consensus_from_pdf_text(text_content)
        if not data or not data.get("target_price"):
            print("No target price extracted from PDF by DeepSeek.")
            return None
            
        # Lưu vào DB
        rec = {
            "ticker": ticker,
            "broker": data.get("broker") or "Unknown Broker",
            "report_date": parse_vnstock_date(data.get("report_date")) or datetime.date.today(),
            "target_price": float(data.get("target_price")),
            "rating": data.get("rating"),
            "source_url": source_url or pdf_path,
            "raw_quote": data.get("raw_quote")
        }
        
        db = SessionLocalWrite()
        try:
            stmt = insert(Consensus).values(rec)
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker", "broker", "report_date"],
                set_={
                    "target_price": stmt.excluded.target_price,
                    "rating": stmt.excluded.rating,
                    "source_url": stmt.excluded.source_url,
                    "raw_quote": stmt.excluded.raw_quote
                }
            )
            db.execute(stmt)
            db.commit()
            print(f"Successfully processed and saved PDF consensus: {rec['broker']} target price = {rec['target_price']:,.0f} VND")
            return rec
        except Exception as e:
            db.rollback()
            print(f"Error saving PDF consensus: {e}")
            return None
        finally:
            db.close()
            
    except Exception as e:
        print(f"Failed to process PDF report: {e}")
        return None
