"""CustomerResponse 须接受现行结算方式码（含 net_terms）。"""

from datetime import datetime

from apps.master_data.schemas.supply_chain_schemas import CustomerResponse


def test_customer_response_accepts_net_terms():
    row = {
        "id": 1,
        "uuid": "00000000-0000-0000-0000-000000000001",
        "tenant_id": 1,
        "code": "C001",
        "name": "测试客户",
        "is_active": True,
        "settlement_terms_code": "net_terms",
        "payment_terms_days": 30,
        "pool_status": "pool",
        "follow_status": "pending",
        "market_scope": "domestic",
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    resp = CustomerResponse.model_validate(row)
    assert resp.settlement_terms_code == "net_terms"
