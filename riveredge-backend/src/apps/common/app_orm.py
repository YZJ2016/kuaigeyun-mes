"""应用 ORM 就绪判定。

应用中心未启用（或 ORM 未按启用集重建）时，包可导入但 ``Model.filter`` 会报
``default_connection ... cannot be None``。跨应用/核心层读写路径须用本模块门禁。

对应上游 ``apps.common.optional_pro`` 的就绪分支：本 fork 各应用均为跟踪内建包，
无需 import_pro_module 间接层，仅保留 ORM 绑定判定。
"""

from __future__ import annotations

from infra.exceptions.exceptions import BusinessLogicError

_FINANCE_MODEL_MARKERS = (
    "payable",
    "receivable",
    "purchase_invoice",
    "invoice",
    "payment",
    "receipt",
    "settlement",
)


def app_orm_ready(app_code: str) -> bool:
    """应用包 Tortoise 模型已绑定 default 连接。

    无自有 Tortoise 模型的服务型应用在 Tortoise 已 init 时视为就绪；
    检测到该应用有模型但均未绑定时判未就绪。
    """
    from tortoise import Tortoise

    if not getattr(Tortoise, "_inited", False):
        return False
    pkg = app_code.replace("-", "_")
    prefix = f"apps.{pkg}."
    exact = f"apps.{pkg}"
    saw_package_model = False
    for app_models in (Tortoise.apps or {}).values():
        for model in app_models.values():
            module_name = getattr(model, "__module__", "") or ""
            if not (module_name == exact or module_name.startswith(prefix)):
                continue
            saw_package_model = True
            meta = getattr(model, "_meta", None)
            if meta is not None and getattr(meta, "default_connection", None) is not None:
                return True
    if saw_package_model:
        return False
    return True


def require_app_orm(app_code: str, label: str | None = None) -> None:
    """写路径门禁：应用 ORM 未就绪时明确报错，禁止继续查库。"""
    if app_orm_ready(app_code):
        return
    name = label or app_code
    raise BusinessLogicError(f"应用「{name}」未启用或 ORM 未就绪，无法使用该功能。")


def finance_orm_ready() -> bool:
    """kuaicaiwu 财务 ORM 可查（应付/应收/发票/收付款/核销任一核心模型已绑定连接）。"""
    from tortoise import Tortoise

    if not getattr(Tortoise, "_inited", False):
        return False
    prefix = "apps.kuaicaiwu.models."
    for app_models in (Tortoise.apps or {}).values():
        for model in app_models.values():
            module_name = getattr(model, "__module__", "") or ""
            if not module_name.startswith(prefix):
                continue
            tail = module_name[len(prefix) :]
            if tail.split(".")[0] not in _FINANCE_MODEL_MARKERS:
                continue
            meta = getattr(model, "_meta", None)
            if meta is not None and getattr(meta, "default_connection", None) is not None:
                return True
    return False


def require_finance_orm() -> None:
    """写路径门禁：财务 ORM 未就绪时明确报错。"""
    if finance_orm_ready():
        return
    raise BusinessLogicError(
        "轻财务未启用或财务 ORM 未就绪，无法使用该功能。"
        "请在应用中心启用轻财务后重试。"
    )
