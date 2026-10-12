import json
from valuation.analysis.macro_radar import get_macro_deltas

def test_macro_radar():
    sectors_to_test = ["Ngân hàng", "Tài nguyên Cơ bản", "Công nghệ Thông tin"]
    
    results = {}
    for sector in sectors_to_test:
        deltas = get_macro_deltas(sector)
        results[sector] = deltas
        
    print(json.dumps(results, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test_macro_radar()
