"""行业扩展运行时：模块启停时 apply/revert profile。"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from loguru import logger

from core.config.industry_document_profiles import GENERIC_PROFILES_BY_KEY
from core.config.industry_extension_registry import (
    DOCUMENT_REPLACEMENTS_CONFIG_KEY,
    IndustryExtensionDecl,
    assert_no_replace_slot_conflict,
    document_replacement_payload,
    parse_industry_extensions,
    tenant_config_key_for_profile,
)
from core.config.extension_hooks_loader import (
    apply_standalone_via_hooks,
    host_capabilities_from_hooks,
    resolve_profile_seed_from_hooks,
    revert_standalone_via_hooks,
)
from core.config.extension_provider import is_extension_provider_app_code
from infra.exceptions.exceptions import ValidationError
from infra.services.tenant_service import TenantService


def _active_items(items: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    if not items:
        return []
    return [x for x in items if isinstance(x, dict) and x.get("active", True)]


class IndustryExtensionRuntimeService:
    """租户级扩展 profile 生命周期（行业插件与声明 extensions 的定制应用共用）。"""

    @staticmethod
    def _is_extension_provider(app_code: str) -> bool:
        return is_extension_provider_app_code(app_code)

    @staticmethod
    async def _active_extension_provider_codes(
        tenant_id: int, *, exclude_app_code: Optional[str] = None
    ) -> List[str]:
        from core.services.application.application_service import ApplicationService

        apps = await ApplicationService.list_applications(
            tenant_id=tenant_id,
            skip=0,
            limit=500,
            is_installed=True,
            is_active=True,
        )
        codes: List[str] = []
        for app in apps:
            code = str(app.get("code") or "")
            if exclude_app_code and code == exclude_app_code:
                continue
            if IndustryExtensionRuntimeService._is_extension_provider(code):
                codes.append(code)
        return codes

    @staticmethod
    def _load_module_manifest(app_code: str) -> Dict[str, Any]:
        from core.services.application.application_service import ApplicationService

        scan = getattr(ApplicationService, "_scan_plugin_manifests", None)
        if scan is None:
            raise ValidationError("应用清单扫描不可用")
        manifests = scan()
        for m in manifests:
            if str(m.get("code") or "") == app_code:
                return m
        raise ValidationError(f"未找到行业模块清单: {app_code}")

    @staticmethod
    def declarations_for_module(app_code: str) -> List[IndustryExtensionDecl]:
        manifest = IndustryExtensionRuntimeService._load_module_manifest(app_code)
        return parse_industry_extensions(app_code, manifest)

    @staticmethod
    async def _active_replace_decls_for_tenant(
        tenant_id: int, *, exclude_app_code: Optional[str] = None
    ) -> List[IndustryExtensionDecl]:
        """已启用行业模块的 replace 声明（用于跨模块槽位冲突校验）。"""
        from core.services.application.application_service import ApplicationService

        apps = await ApplicationService.list_applications(
            tenant_id=tenant_id,
            skip=0,
            limit=500,
            is_installed=True,
            is_active=True,
        )
        out: List[IndustryExtensionDecl] = []
        for app in apps:
            code = str(app.get("code") or "")
            if not IndustryExtensionRuntimeService._is_extension_provider(code):
                continue
            if exclude_app_code and code == exclude_app_code:
                continue
            out.extend(
                d
                for d in IndustryExtensionRuntimeService.declarations_for_module(code)
                if d.kind == "replace"
            )
        return out

    @staticmethod
    async def on_module_activated(tenant_id: int, app_code: str) -> None:
        if not IndustryExtensionRuntimeService._is_extension_provider(app_code):
            return
        decls = IndustryExtensionRuntimeService.declarations_for_module(app_code)
        replace_decls = [d for d in decls if d.kind == "replace"]
        others = await IndustryExtensionRuntimeService._active_replace_decls_for_tenant(
            tenant_id, exclude_app_code=app_code
        )
        try:
            assert_no_replace_slot_conflict(others + replace_decls)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        for decl in replace_decls:
            if decl.strategy != "profile" or not decl.profile_key:
                continue
            seed = decl.seed
            if seed is None:
                seed = IndustryExtensionRuntimeService._builtin_seed(app_code, decl.profile_key)
            if not seed:
                raise ValidationError(
                    f"扩展 {decl.id} 缺少 profile seed（manifest.seed 或内置种子）"
                )
            await IndustryExtensionRuntimeService._write_profile(
                tenant_id,
                decl.profile_key,
                {
                    "enabled": True,
                    "extension_id": decl.id,
                    "module_app_code": app_code,
                    "profile": copy.deepcopy(seed),
                },
                description=f"行业扩展 profile: {decl.id}",
            )
            logger.info(
                "industry_ext_profile_applied tenant={} module={} profile_key={}",
                tenant_id,
                app_code,
                decl.profile_key,
            )

        await IndustryExtensionRuntimeService._apply_standalone_seeds(tenant_id, app_code, decls)

        await IndustryExtensionRuntimeService._apply_document_replacements(
            tenant_id, app_code, replace_decls
        )

        from core.services.system.menu_takeover_service import MenuTakeoverService

        await MenuTakeoverService.apply_extension_pack_menu(
            tenant_id, app_code, replace_decls
        )

    @staticmethod
    async def _apply_document_replacements(
        tenant_id: int, app_code: str, replace_decls: List[IndustryExtensionDecl]
    ) -> None:
        from core.services.system.menu_takeover_service import MenuTakeoverService

        doc_decls = [
            d for d in replace_decls if d.strategy == "document" and d.menu_path and d.host_app
        ]
        if not doc_decls:
            return

        existing = await IndustryExtensionRuntimeService._read_document_replacements(tenant_id)
        by_id = {
            str(item.get("extension_id")): item
            for item in existing
            if isinstance(item, dict) and item.get("extension_id")
        }
        for decl in doc_decls:
            by_id[decl.id] = document_replacement_payload(decl)
            await MenuTakeoverService.tag_document_replacement(
                tenant_id,
                host_app=str(decl.host_app),
                menu_path=str(decl.menu_path),
                extension_id=decl.id,
            )
        await IndustryExtensionRuntimeService._write_document_replacements(
            tenant_id, list(by_id.values())
        )
        logger.info(
            "industry_ext_document_applied tenant={} module={} count={}",
            tenant_id,
            app_code,
            len(doc_decls),
        )

    @staticmethod
    async def _clear_document_replacements_for_module(tenant_id: int, app_code: str) -> None:
        from core.services.system.menu_takeover_service import MenuTakeoverService

        decls = IndustryExtensionRuntimeService.declarations_for_module(app_code)
        doc_decls = [d for d in decls if d.kind == "replace" and d.strategy == "document"]
        if not doc_decls:
            return
        existing = await IndustryExtensionRuntimeService._read_document_replacements(tenant_id)
        drop_ids = {d.id for d in doc_decls}
        kept = [
            item
            for item in existing
            if isinstance(item, dict) and str(item.get("extension_id")) not in drop_ids
        ]
        for decl in doc_decls:
            if decl.host_app and decl.menu_path:
                await MenuTakeoverService.clear_document_replacement(
                    tenant_id,
                    host_app=decl.host_app,
                    menu_path=decl.menu_path,
                    extension_id=decl.id,
                )
        await IndustryExtensionRuntimeService._write_document_replacements(tenant_id, kept)

    @staticmethod
    async def _read_document_replacements(tenant_id: int) -> List[Dict[str, Any]]:
        row = await TenantService().get_tenant_config(
            tenant_id, DOCUMENT_REPLACEMENTS_CONFIG_KEY
        )
        if not row or not isinstance(row.config_value, list):
            return []
        return [x for x in row.config_value if isinstance(x, dict)]

    @staticmethod
    async def _write_document_replacements(
        tenant_id: int, items: List[Dict[str, Any]]
    ) -> None:
        await TenantService().set_tenant_config(
            tenant_id,
            DOCUMENT_REPLACEMENTS_CONFIG_KEY,
            items,
            description="行业扩展 document 替代清单",
        )

    @staticmethod
    async def list_active_document_replacements(tenant_id: int) -> List[Dict[str, Any]]:
        """供宿主页 FE 解析：当前租户生效的 document 替代。"""
        return await IndustryExtensionRuntimeService._read_document_replacements(tenant_id)

    @staticmethod
    async def ensure_missing_profiles_for_module(tenant_id: int, app_code: str) -> int:
        """补写已启用模块仍缺失的 profile 键；已存在配置不覆盖。

        用于包内后增扩展（如先启样品再补 ECN）后，菜单同步即可补齐，无需停用再启用。
        """
        if not IndustryExtensionRuntimeService._is_extension_provider(app_code):
            return 0
        from infra.models.tenant_config import TenantConfig

        written = 0
        for decl in IndustryExtensionRuntimeService.declarations_for_module(app_code):
            if decl.kind != "replace" or decl.strategy != "profile" or not decl.profile_key:
                continue
            key = tenant_config_key_for_profile(decl.profile_key)
            exists = await TenantConfig.filter(tenant_id=tenant_id, config_key=key).exists()
            if exists:
                continue
            seed = decl.seed
            if seed is None:
                seed = IndustryExtensionRuntimeService._builtin_seed(app_code, decl.profile_key)
            if not seed:
                raise ValidationError(
                    f"扩展 {decl.id} 缺少 profile seed（manifest.seed 或内置种子）"
                )
            await IndustryExtensionRuntimeService._write_profile(
                tenant_id,
                decl.profile_key,
                {
                    "enabled": True,
                    "extension_id": decl.id,
                    "module_app_code": app_code,
                    "profile": copy.deepcopy(seed),
                },
                description=f"行业扩展 profile 补齐: {decl.id}",
            )
            written += 1
            logger.info(
                "industry_ext_profile_ensured tenant={} module={} profile_key={}",
                tenant_id,
                app_code,
                decl.profile_key,
            )
        return written

    @staticmethod
    async def reconcile_profiles_for_tenant(tenant_id: int) -> int:
        """对租户下已启用行业模块补齐缺失 profile。"""
        from core.services.application.application_service import ApplicationService

        apps = await ApplicationService.list_applications(
            tenant_id=tenant_id,
            skip=0,
            limit=500,
            is_installed=True,
            is_active=True,
        )
        total = 0
        for app in apps:
            code = str(app.get("code") or "")
            if not IndustryExtensionRuntimeService._is_extension_provider(code):
                continue
            total += await IndustryExtensionRuntimeService.ensure_missing_profiles_for_module(
                tenant_id, code
            )
            decls = IndustryExtensionRuntimeService.declarations_for_module(code)
            await IndustryExtensionRuntimeService._apply_standalone_seeds(tenant_id, code, decls)
            replace_decls = [d for d in decls if d.kind == "replace"]
            await IndustryExtensionRuntimeService._apply_document_replacements(
                tenant_id, code, replace_decls
            )
            from core.services.system.menu_takeover_service import MenuTakeoverService

            await MenuTakeoverService.apply_extension_pack_menu(
                tenant_id, code, replace_decls
            )
        return total

    @staticmethod
    async def on_module_deactivated(tenant_id: int, app_code: str) -> None:
        if not IndustryExtensionRuntimeService._is_extension_provider(app_code):
            return
        decls = IndustryExtensionRuntimeService.declarations_for_module(app_code)
        for decl in decls:
            if decl.strategy != "profile" or not decl.profile_key:
                continue
            await IndustryExtensionRuntimeService._clear_profile(tenant_id, decl.profile_key)
            logger.info(
                "industry_ext_profile_reverted tenant={} module={} profile_key={}",
                tenant_id,
                app_code,
                decl.profile_key,
            )
        await IndustryExtensionRuntimeService._revert_standalone_seeds(tenant_id, app_code, decls)
        await IndustryExtensionRuntimeService._clear_document_replacements_for_module(
            tenant_id, app_code
        )

        from core.services.system.menu_takeover_service import MenuTakeoverService

        replace_decls = [d for d in decls if d.kind == "replace"]
        await MenuTakeoverService.revert_extension_pack_menu(
            tenant_id, app_code, replace_decls
        )

    @staticmethod
    async def _apply_standalone_seeds(
        tenant_id: int, app_code: str, decls: List[IndustryExtensionDecl]
    ) -> None:
        for decl in decls:
            if decl.kind != "standalone":
                continue
            await apply_standalone_via_hooks(tenant_id, app_code, decl.id)
            logger.info(
                "industry_ext_standalone_applied tenant={} module={} extension={}",
                tenant_id,
                app_code,
                decl.id,
            )

    @staticmethod
    async def _revert_standalone_seeds(
        tenant_id: int, app_code: str, decls: List[IndustryExtensionDecl]
    ) -> None:
        for decl in decls:
            if decl.kind != "standalone":
                continue
            await revert_standalone_via_hooks(tenant_id, app_code, decl.id)
            logger.info(
                "industry_ext_standalone_reverted tenant={} module={} extension={}",
                tenant_id,
                app_code,
                decl.id,
            )

    @staticmethod
    def _builtin_seed(app_code: str, profile_key: str) -> Optional[Dict[str, Any]]:
        seed = resolve_profile_seed_from_hooks(app_code, profile_key)
        return copy.deepcopy(seed) if seed else None

    @staticmethod
    async def list_host_capabilities(tenant_id: int) -> List[Dict[str, Any]]:
        """已启用扩展模块向基础宿主页暴露的 capability（路径不含行业包硬编码）。"""
        active_ext_ids: set[str] = set()
        for module_code in await IndustryExtensionRuntimeService._active_extension_provider_codes(
            tenant_id
        ):
            for decl in IndustryExtensionRuntimeService.declarations_for_module(module_code):
                active_ext_ids.add(decl.id)

        items: List[Dict[str, Any]] = []
        for module_code in await IndustryExtensionRuntimeService._active_extension_provider_codes(
            tenant_id
        ):
            declared_ids = {
                d.id for d in IndustryExtensionRuntimeService.declarations_for_module(module_code)
            }
            for cap_key, spec in host_capabilities_from_hooks(module_code).items():
                if not isinstance(spec, dict):
                    continue
                ext_id = str(spec.get("extension_id") or "")
                if not ext_id or ext_id not in declared_ids or ext_id not in active_ext_ids:
                    continue
                base = f"/apps/{module_code}"
                entry: Dict[str, Any] = {
                    "capability": cap_key,
                    "module_app_code": module_code,
                    "extension_id": ext_id,
                }
                fetch_path = str(spec.get("fetch_path") or "").strip()
                if fetch_path:
                    entry["fetch_path"] = f"{base}{fetch_path}"
                nav_path = str(spec.get("navigation_path") or "").strip()
                if nav_path:
                    entry["navigation_path"] = f"{base}{nav_path}"
                post_paths = spec.get("post_paths")
                if isinstance(post_paths, dict):
                    entry["post_paths"] = {
                        k: f"{base}{str(v)}"
                        for k, v in post_paths.items()
                        if str(v).strip()
                    }
                items.append(entry)
        return items

    @staticmethod
    async def resolve_navigation_path_for_capability(
        tenant_id: int, capability: str, *, fallback: Optional[str] = None
    ) -> Optional[str]:
        for item in await IndustryExtensionRuntimeService.list_host_capabilities(tenant_id):
            if item.get("capability") == capability:
                path = item.get("navigation_path")
                if isinstance(path, str) and path.strip():
                    return path.strip()
        return fallback

    @staticmethod
    async def _write_profile(
        tenant_id: int,
        profile_key: str,
        value: Dict[str, Any],
        *,
        description: str,
    ) -> None:
        key = tenant_config_key_for_profile(profile_key)
        await TenantService().set_tenant_config(
            tenant_id, key, value, description=description
        )

    @staticmethod
    async def _clear_profile(tenant_id: int, profile_key: str) -> None:
        from infra.models.tenant_config import TenantConfig

        key = tenant_config_key_for_profile(profile_key)
        row = await TenantConfig.filter(tenant_id=tenant_id, config_key=key).first()
        if row:
            await row.delete()

    @staticmethod
    async def is_industry_profile_enabled(tenant_id: int, profile_key: str) -> bool:
        """租户是否已启用行业包写入的 profile（非通用默认）。"""
        key = tenant_config_key_for_profile(profile_key)
        row = await TenantService().get_tenant_config(tenant_id, key)
        if not row or not isinstance(row.config_value, dict):
            return False
        return bool(row.config_value.get("enabled"))

    @staticmethod
    async def resolve_profile(tenant_id: int, profile_key: str) -> Dict[str, Any]:
        """返回可消费的 profile 正文。无行业配置则通用默认。"""
        generic = GENERIC_PROFILES_BY_KEY.get(profile_key)
        if generic is None:
            raise ValidationError(f"未知 profile_key: {profile_key}")

        key = tenant_config_key_for_profile(profile_key)
        row = await TenantService().get_tenant_config(tenant_id, key)
        if not row or not isinstance(row.config_value, dict):
            return copy.deepcopy(generic)

        cfg = row.config_value
        if not cfg.get("enabled"):
            return copy.deepcopy(generic)
        profile = cfg.get("profile")
        if not isinstance(profile, dict):
            raise ValidationError(f"行业扩展 profile 损坏: {profile_key}")
        return copy.deepcopy(profile)

    @staticmethod
    def active_kind_codes(profile: Dict[str, Any]) -> frozenset[str]:
        return frozenset(
            str(x["code"])
            for x in _active_items(profile.get("request_kinds"))
            if x.get("code")
        )

    @staticmethod
    def active_attachment_codes(profile: Dict[str, Any]) -> frozenset[str]:
        return frozenset(
            str(x["code"])
            for x in _active_items(profile.get("attachment_types"))
            if x.get("code")
        )

    @staticmethod
    def _rule_matches_kind(rule: Dict[str, Any], kind: str) -> bool:
        when_kind = rule.get("when_kind_in") or []
        when_change = rule.get("when_change_kind_in") or []
        if when_change:
            return kind in when_change
        if when_kind:
            return kind in when_kind
        return False

    @staticmethod
    def require_fields_for_kind(profile: Dict[str, Any], kind: str) -> List[str]:
        required: List[str] = []
        for rule in profile.get("validation_rules") or []:
            if not isinstance(rule, dict):
                continue
            if IndustryExtensionRuntimeService._rule_matches_kind(rule, kind):
                for f in rule.get("require") or []:
                    required.append(str(f))
        return required

    @staticmethod
    def validation_message(profile: Dict[str, Any], kind: str) -> Optional[str]:
        for rule in profile.get("validation_rules") or []:
            if not isinstance(rule, dict):
                continue
            if IndustryExtensionRuntimeService._rule_matches_kind(rule, kind) and rule.get("message"):
                return str(rule["message"])
        return None
