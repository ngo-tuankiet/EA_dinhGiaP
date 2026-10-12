import os
import sys
import pandas as pd
from datetime import datetime

sys.path.append(os.getcwd())
from valuation.db.session import SessionLocalRead
from valuation.engine.batch import value_all
from valuation.models.macro_env import MacroEnvironment

def generate_pdf():
    print("--- Bắt đầu định giá toàn bộ VN100 để xuất PDF ---")
    db = SessionLocalRead()
    try:
        # Cùng nguồn vĩ mô với UI (CPI/TPCP/lãi suất trong DB), không hardcode lạm phát.
        macro_env = MacroEnvironment.from_db(db)
        print("Đang định giá... (Quá trình này có thể mất 1-2 phút)")
        results = value_all(db, macro_env=macro_env)
    finally:
        db.close()

    # Chuyển đổi kết quả thành DataFrame
    df = pd.DataFrame(results)
    
    # Lọc bỏ các cột không cần thiết và xử lý dữ liệu
    df['Giá HT (VND)'] = df['price'].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) else "")
    df['Giá Hợp Lý (VND)'] = df['fair_value'].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) else "")
    
    def format_upside(u):
        if pd.isnull(u): return ""
        return f"{u*100:,.1f}%"
        
    df['Upside (%)'] = df['upside'].apply(format_upside)
    
    # Khuyến nghị: mã chuẩn từ decision_engine (PDF font Helvetica không có dấu tiếng Việt).
    df['Khuyến nghị'] = df['recommendation'].fillna("")
    
    # Cập nhật error thành ghi chú
    df['Ghi chú'] = df.apply(lambda row: row['error'] if pd.notnull(row.get('error')) else ", ".join(row.get('flags', [])), axis=1)

    # Đổi tên và sắp xếp cột
    df = df.rename(columns={
        'ticker': 'Mã CP',
        'group': 'Ngành',
        'method': 'Phương pháp'
    })
    
    cols = ['Mã CP', 'Ngành', 'Phương pháp', 'Giá HT (VND)', 'Giá Hợp Lý (VND)', 'Upside (%)', 'Khuyến nghị', 'Ghi chú']
    # Giữ lại các cột tồn tại
    cols = [c for c in cols if c in df.columns]
    df = df[cols]

    desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop', 'DinhGia_VN100.pdf')
    print(f"Đang tạo file PDF bằng reportlab tại {desktop_path}...")
    
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    
    doc = SimpleDocTemplate(desktop_path, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], alignment=1, textColor=colors.HexColor('#1f497d'))
    date_style = ParagraphStyle('DateStyle', parent=styles['Normal'], alignment=1, textColor=colors.gray)
    
    elements.append(Paragraph("BÁO CÁO ĐỊNH GIÁ DANH MỤC VN100", title_style))
    elements.append(Paragraph(f"Cập nhật ngày: {datetime.now().strftime('%d/%m/%Y %H:%M')}", date_style))
    elements.append(Spacer(1, 20))
    
    # Chuẩn bị dữ liệu cho bảng
    data = [cols] # Header
    for idx, row in df.iterrows():
        data.append([str(row[c]) for c in cols])
        
    # Tạo bảng
    col_widths = [45, 80, 80, 70, 90, 65, 75, 230] # Tổng = 735
    t = Table(data, colWidths=col_widths, repeatRows=1)
    
    # Style cơ bản cho bảng
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f497d')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 1), (2, -1), 'LEFT'), # Mã, Ngành, PP canh trái
        ('ALIGN', (3, 1), (5, -1), 'RIGHT'), # Giá, Upside canh phải
        ('ALIGN', (7, 1), (7, -1), 'LEFT'), # Ghi chú canh trái
        ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])
    
    # Thêm màu xen kẽ
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.add('BACKGROUND', (0, i), (-1, i), colors.whitesmoke)
            
    # Thêm màu cho Khuyến nghị
    rec_col_idx = cols.index('Khuyến nghị')
    for i in range(1, len(data)):
        val = data[i][rec_col_idx]
        if val == "BUY":
            style.add('TEXTCOLOR', (rec_col_idx, i), (rec_col_idx, i), colors.green)
            style.add('FONTNAME', (rec_col_idx, i), (rec_col_idx, i), 'Helvetica-Bold')
        elif val == "SELL":
            style.add('TEXTCOLOR', (rec_col_idx, i), (rec_col_idx, i), colors.red)
            style.add('FONTNAME', (rec_col_idx, i), (rec_col_idx, i), 'Helvetica-Bold')
        elif val in ("HOLD", "TRIM"):
            style.add('TEXTCOLOR', (rec_col_idx, i), (rec_col_idx, i), colors.orange)
            style.add('FONTNAME', (rec_col_idx, i), (rec_col_idx, i), 'Helvetica-Bold')
            
    t.setStyle(style)
    elements.append(t)
    
    doc.build(elements)
    print(f"✅ Hoàn tất! File đã được lưu tại: {desktop_path}")

if __name__ == "__main__":
    generate_pdf()
