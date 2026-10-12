import os
import json
import pytest
from unittest.mock import patch, MagicMock
from valuation.engine.ai_extractor import extract_rnav_projects, extract_sotp_segments

@patch.dict('os.environ', {'OPENAI_API_KEY': 'fake_key'})
@patch('valuation.engine.ai_extractor.OpenAI')
def test_extract_rnav_projects_success(mock_openai):
    """Test bóc đúng số đã biết, kiểm tra schema có missing=False."""
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    
    # Giả lập response từ LLM
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "ticker": "VHM",
        "projects": [
            {
                "ten_du_an": {"value": "Vinhomes Royal", "source_quote": "Dự án Vinhomes Royal", "missing": False},
                "dien_tich_san_thuong_pham_m2": {"value": 50000.0, "source_quote": "diện tích sàn 50.000 m2", "missing": False},
                "he_so_su_dung_dat": {"value": None, "source_quote": None, "missing": True},
                "gia_ban_tren_m2": {"value": 100000000.0, "source_quote": "giá bán 100tr/m2", "missing": False},
                "chi_phi_tren_m2": {"value": 40000000.0, "source_quote": "chi phí xây dựng 40tr/m2", "missing": False},
                "bien_ln_rong": {"value": None, "source_quote": None, "missing": True},
                "ty_le_so_huu": {"value": 100.0, "source_quote": "sở hữu 100%", "missing": False},
                "nam_mo_ban": {"value": 2024, "source_quote": "mở bán 2024", "missing": False},
                "nam_ban_giao": {"value": 2026, "source_quote": "bàn giao 2026", "missing": False},
                "ty_le_da_ban": {"value": 30.0, "source_quote": "đã bán 30%", "missing": False}
            }
        ]
    })
    mock_client.chat.completions.create.return_value = mock_response

    text = "Dự án Vinhomes Royal mở bán 2024, bàn giao 2026, đã bán 30%. Có diện tích sàn 50.000 m2, sở hữu 100%, giá bán 100tr/m2, chi phí xây dựng 40tr/m2."
    result = extract_rnav_projects("VHM", text)
    
    assert "error" not in result
    assert len(result["projects"]) == 1
    p = result["projects"][0]
    
    assert p["ten_du_an"] == "Vinhomes Royal"
    assert p["dien_tich_san_thuong_pham_m2"] == 50000.0
    assert p["dien_tich_san_thuong_pham_m2_source"] == "diện tích sàn 50.000 m2"
    assert p["dien_tich_san_thuong_pham_m2_missing"] is False
    assert p["he_so_su_dung_dat_missing"] is True
    assert p["he_so_su_dung_dat"] is None

@patch.dict('os.environ', {'OPENAI_API_KEY': 'fake_key'})
@patch('valuation.engine.ai_extractor.OpenAI')
def test_extract_rnav_projects_missing(mock_openai):
    """Test chống bịa số: Khi văn bản thiếu thông tin (không có tỷ lệ đã bán)."""
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "ticker": "VHM",
        "projects": [
            {
                "ten_du_an": {"value": "Vinhomes Royal", "source_quote": "Dự án Vinhomes Royal", "missing": False},
                "dien_tich_san_thuong_pham_m2": {"value": 50000.0, "source_quote": "diện tích sàn 50.000 m2", "missing": False},
                "he_so_su_dung_dat": {"value": None, "source_quote": None, "missing": True},
                "gia_ban_tren_m2": {"value": 100000000.0, "source_quote": "giá bán 100tr/m2", "missing": False},
                "chi_phi_tren_m2": {"value": 40000000.0, "source_quote": "chi phí xây dựng 40tr/m2", "missing": False},
                "bien_ln_rong": {"value": None, "source_quote": None, "missing": True},
                "ty_le_so_huu": {"value": 100.0, "source_quote": "sở hữu 100%", "missing": False},
                "nam_mo_ban": {"value": 2024, "source_quote": "mở bán 2024", "missing": False},
                "nam_ban_giao": {"value": 2026, "source_quote": "bàn giao 2026", "missing": False},
                "ty_le_da_ban": {"value": None, "source_quote": None, "missing": True}
            }
        ]
    })
    mock_client.chat.completions.create.return_value = mock_response

    # Trong text không hề có thông tin tỷ lệ đã bán!
    text = "Dự án Vinhomes Royal mở bán 2024, bàn giao 2026. Có diện tích sàn 50.000 m2, sở hữu 100%, giá bán 100tr/m2, chi phí xây dựng 40tr/m2."
    result = extract_rnav_projects("VHM", text)
    
    p = result["projects"][0]
    assert p["ty_le_da_ban"] is None
    assert p["ty_le_da_ban_source"] is None
    assert p["ty_le_da_ban_missing"] is True

@patch.dict('os.environ', {'OPENAI_API_KEY': 'fake_key'})
@patch('valuation.engine.ai_extractor.OpenAI')
def test_extract_invalid_json(mock_openai):
    """Test xử lý khi AI trả về JSON hỏng."""
    mock_client = MagicMock()
    mock_openai.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "This is not JSON"
    mock_client.chat.completions.create.return_value = mock_response

    result = extract_rnav_projects("VHM", "Một số text")
    assert "error" in result
    assert result["projects"] == []
