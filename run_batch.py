import os
import sys

# Đảm bảo đường dẫn project đúng
sys.path.append(os.getcwd())

from valuation.db.session import SessionLocalRead
from valuation.engine.batch import value_all
from valuation.models.macro_env import MacroEnvironment
from valuation.output.gsheets_exporter import export_vn100_valuations_to_gsheets
import logging

logging.basicConfig(level=logging.INFO)

def run():
    print("--- Khởi chạy định giá VN100 Batch ---")
    
    db = SessionLocalRead()
    try:
        # Sử dụng môi trường vĩ mô mặc định (Normal) cho định giá chuẩn
        normal_env = MacroEnvironment(inflation_rate=0.03, sbv_stance="Neutral")
        
        print("Đang định giá 100 mã (chế độ Normal)...")
        results = value_all(db, macro_env=normal_env)
        
        print("Xuất dữ liệu lên Google Sheets (VN100_Valuations)...")
        res_export = export_vn100_valuations_to_gsheets(results, sheet_name="VN100_Valuations")
        
        if res_export.get("status") == "success":
            print(f"Cập nhật thành công {res_export.get('rows')} mã lên Google Sheets.")
        else:
            print(f"Có lỗi khi cập nhật: {res_export}")
            
    finally:
        db.close()

if __name__ == "__main__":
    run()
