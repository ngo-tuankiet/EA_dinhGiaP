"""
Module field_mapping: Chứa các hằng số và danh sách các chỉ tiêu quan trọng
để đối chiếu hoặc chuẩn hóa từ vnstock.
Do vnstock đã trả item_id dưới dạng snake_case (VD: cash_and_cash_equivalents), 
chúng ta dùng trực tiếp item_id làm line_item trong DB.
Tuy nhiên, module này lưu trữ danh sách các trường quan trọng để validation.
"""

CRITICAL_BS_FIELDS = [
    "cash_and_cash_equivalents",
    "short_term_investments",
    "total_assets",
    "total_liabilities",
    "equity",
    "tangible_fixed_assets",
    "inventory",
]

CRITICAL_IS_FIELDS = [
    "net_sales",
    "cost_of_sales",
    "gross_profit",
    "net_profit_loss_after_tax",
    "net_profit_loss_before_tax",
]

CRITICAL_CF_FIELDS = [
    "net_cash_from_operating_activities",
    "net_cash_from_investing_activities",
    "net_cash_from_financing_activities",
]

BANK_CRITICAL_FIELDS = [
    "cash_and_precious_metals",
    "customer_loans",
    "customer_deposits",
    "provision_for_credit_losses",
    "net_interest_income"
]
