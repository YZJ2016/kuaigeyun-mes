"""可选专业包导入（开源主仓无 compose 时不得在宿主模块顶层硬 import pro 应用）。"""

from __future__ import annotations

import importlib
import importlib.util
from types import ModuleType
from typing import Any, Optional

from infra.exceptions.exceptions import BusinessLogicError

_PRO_APPS = frozenset(
    {
        "kuaicaiwu",
        "kuaiplm",
        "kuaioa",
        "kuaipd",
        "kuaiai",
        "kuaiiot",
        "kuaireport",
        "kuaiconnect",
    }
)
_PRO_APP_PREFIXES = ("ind_", "spoke_")
_HOST_FINANCE_MODULE_PREFIX = "apps.kuaizhizao.finance."


def _normalize_pro_app(app_code: str) -> str:
    return (app_code or "").strip().replace("-", "_")


def _is_known_pro_app(app: str) -> bool:
    if app in _PRO_APPS:
        return True
    return any(app.startswith(p) for p in _PRO_APP_PREFIXES)


def pro_app_available(app_code: str) -> bool:
    """专业包应用源码是否可导入（compose / 安装后为 True）。"""
    mod = _normalize_pro_app(app_code)
    if not mod:
        return False
    return importlib.util.find_spec(f"apps.{mod}") is not None


def host_finance_orm_ready() -> bool:
    """快制造宿主财务管理 ORM 已就绪：FINANCE_MANAGEMENT 清单内每个模块均已注册并绑定连接。"""
    from tortoise import Tortoise

    from apps.kuaizhizao.finance.orm_models_finance_management import (
        FINANCE_MANAGEMENT_ORM_MODEL_MODULES,
    )

    if not getattr(Tortoise, "_inited", False):
        return False

    bound_modules: set[str] = set()
    prefix = "apps.kuaizhizao.finance.models."
    for app_models in (Tortoise.apps or {}).values():
        for model in app_models.values():
            module_name = getattr(model, "__module__", "") or ""
            if not module_name.startswith(prefix):
                continue
            meta = getattr(model, "_meta", None)
            if meta is not None and getattr(meta, "default_connection", None) is not None:
                bound_modules.add(module_name)

    for required in FINANCE_MANAGEMENT_ORM_MODEL_MODULES:
        if required not in bound_modules:
            return False
    return bool(FINANCE_MANAGEMENT_ORM_MODEL_MODULES)


def finance_orm_ready() -> bool:
    """应收应付/收付款/发票等财务管理 ORM 可查（宿主真源；兼容旧版仍注册在 kuaicaiwu 的部署）。"""
    if host_finance_orm_ready():
        return True
    if not pro_app_available("kuaicaiwu"):
        return False
    from tortoise import Tortoise

    if not getattr(Tortoise, "_inited", False):
        return False
    legacy_prefix = "apps.kuaicaiwu.models."
    finance_markers = (
        "payable",
        "receivable",
        "purchase_invoice",
        "payment",
        "receipt",
    )
    for app_models in (Tortoise.apps or {}).values():
        for model in app_models.values():
            module_name = getattr(model, "__module__", "") or ""
            if not module_name.startswith(legacy_prefix):
                continue
            tail = module_name[len(legacy_prefix) :]
            if tail.split(".")[0] not in finance_markers:
                continue
            meta = getattr(model, "_meta", None)
            if meta is not None and getattr(meta, "default_connection", None) is not None:
                return True
    return False


def pro_orm_ready(app_code: str) -> bool:
    """专业包可导入，且其 Tortoise 模型已绑定 default 连接。

    磁盘已 compose 但应用中心未启用（或 ORM 未按启用集重建）时，
    ``pro_app_available`` 仍为 True，直接 ``Model.filter`` 会报
    ``default_connection ... cannot be None``。列表/只读增强须用本函数门禁。

    无自有 Tortoise 模型的专业包（如 ``kuaiconnect``，仅 services/api）在
    Tortoise 已 init 且包可导入时视为就绪；勿误报「已组装但 ORM 未就绪」。
    """
    if not pro_app_available(app_code):
        return False
    from tortoise import Tortoise

    if not getattr(Tortoise, "_inited", False):
        return False
    pkg = _normalize_pro_app(app_code)
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
    # 服务型专业包：无 ORM 声明，就绪条件 = 可导入 + Tortoise 已初始化
    return True


def require_finance_orm() -> None:
    """写路径门禁：宿主财务管理 ORM 未就绪时明确报错。"""
    if finance_orm_ready():
        return
    raise BusinessLogicError(
        "财务管理 ORM 未就绪，无法使用该功能。"
        "请确认快制造已启用，或重启服务后再试。"
    )


def require_pro_orm(app_code: str) -> None:
    """写路径门禁：专业包 ORM 未就绪时明确报错，禁止继续查库。"""
    app = _normalize_pro_app(app_code)
    if pro_orm_ready(app):
        return
    label = app.replace("_", "-")
    if pro_app_available(app):
        raise BusinessLogicError(
            f"专业包应用「{label}」已组装但 ORM 未就绪，无法使用该功能。"
            "请确认宿主应用（如快制造）已启用，或重启服务后再试。"
        )
    raise BusinessLogicError(
        f"当前环境未安装专业包应用「{label}」，无法使用该功能。"
        "请通过扩展应用/compose 安装后再试。"
    )


def _is_host_finance_module(path: str) -> bool:
    return (path or "").startswith(_HOST_FINANCE_MODULE_PREFIX)


def import_pro_module(module_path: str) -> ModuleType:
    """
    导入专业包模块，或快制造宿主财务管理（apps.kuaizhizao.finance.*）。
    缺失时抛 BusinessLogicError（明确能力缺口），禁止静默降级为假实现。
    """
    path = (module_path or "").strip()
    if not path.startswith("apps."):
        raise ValueError(f"invalid pro module path: {module_path!r}")
    if _is_host_finance_module(path):
        require_finance_orm()
        try:
            return importlib.import_module(path)
        except ImportError as exc:
            raise BusinessLogicError(
                "快制造财务管理模块加载失败，请确认快制造已启用并重启服务后再试。"
            ) from exc
    parts = path.split(".")
    app = parts[1] if len(parts) > 1 else ""
    if not _is_known_pro_app(app):
        raise ValueError(f"not a known pro app module: {module_path!r}")
    try:
        return importlib.import_module(path)
    except ImportError as exc:
        # 包本身可导入、仅缺子模块时勿报「未安装专业包」（易误导成 compose 问题）
        if pro_app_available(app):
            raise BusinessLogicError(
                f"专业包应用「{app}」已安装，但模块加载失败：{path}。"
                f"请确认 compose/镜像包含该文件，或联系实施同步专业包后再试。（{exc}）"
            ) from exc
        raise BusinessLogicError(
            f"当前环境未安装专业包应用「{app}」，无法使用该功能。请通过扩展应用/compose 安装后再试。"
        ) from exc


def import_pro_attr(module_path: str, attr: str) -> Any:
    mod = import_pro_module(module_path)
    try:
        return getattr(mod, attr)
    except AttributeError as exc:
        raise BusinessLogicError(
            f"专业包模块 {module_path} 缺少符号 {attr}"
        ) from exc


def try_import_pro_module(module_path: str) -> Optional[ModuleType]:
    """仅用于「无专业包则跳过该分支」的只读探测；不得用于掩盖业务错误。"""
    path = (module_path or "").strip()
    if _is_host_finance_module(path):
        if not finance_orm_ready():
            return None
        try:
            return importlib.import_module(path)
        except ImportError:
            return None
    parts = path.split(".")
    app = parts[1] if len(parts) > 1 else ""
    if not _is_known_pro_app(app) or not pro_app_available(app):
        return None
    try:
        return importlib.import_module(path)
    except ImportError:
        return None
