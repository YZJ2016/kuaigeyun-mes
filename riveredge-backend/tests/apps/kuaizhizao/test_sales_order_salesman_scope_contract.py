"""销售订单本部门数据范围依赖经办人 salesman_id；建单须回落到当前操作人。"""


def _apply_salesman_fallback(order_dict: dict, *, created_by: int, operator_name: str) -> None:
    """与 SalesOrderService 建单路径一致的 salesman 回落（契约抽检，不连库）。"""
    if not order_dict.get("salesman_id"):
        order_dict["salesman_id"] = created_by
        if not order_dict.get("salesman_name"):
            order_dict["salesman_name"] = operator_name


def test_sales_order_create_defaults_salesman_to_operator():
    order_dict: dict = {}
    _apply_salesman_fallback(order_dict, created_by=1001, operator_name="业务员甲")
    assert order_dict["salesman_id"] == 1001
    assert order_dict["salesman_name"] == "业务员甲"


def test_sales_order_create_keeps_explicit_salesman():
    order_dict = {"salesman_id": 2002, "salesman_name": "业务员乙"}
    _apply_salesman_fallback(order_dict, created_by=1001, operator_name="业务员甲")
    assert order_dict["salesman_id"] == 2002
    assert order_dict["salesman_name"] == "业务员乙"