"""企业微信 CorpId + AgentId 反查 RiverEdge 租户（唯一命中才返回）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.models.integration_config import IntegrationConfig
from core.services.integration.wecom_connector_guidance import (
    _normalize_corp_id,
    _parse_wecom_agent_id,
)
from infra.domain.tenant_context import unscoped
from infra.models.tenant import Tenant


@dataclass(frozen=True)
class WeComTenantResolveResult:
    tenant_id: int
    tenant_domain: str
    candidates_count: int = 1


async def resolve_tenant_by_wecom_corp_agent(
    *,
    corp_id: str,
    agent_id: int,
) -> WeComTenantResolveResult | None:
    corp = (corp_id or "").strip()
    if not corp:
        return None

    async with unscoped(
        reason="企业微信 CorpID+AgentId 跨组织反查租户（公开登录入口）",
        resource="IntegrationConfig",
    ):
        rows = await IntegrationConfig.filter(
            type="wecom",
            is_active=True,
            deleted_at__isnull=True,
        ).all()

    matched_tenant_ids: list[int] = []
    for row in rows:
        cfg = row.config if isinstance(row.config, dict) else {}
        if _normalize_corp_id(cfg) != corp:
            continue
        parsed_agent = _parse_wecom_agent_id(cfg)
        if parsed_agent != agent_id:
            continue
        matched_tenant_ids.append(int(row.tenant_id))

    unique_ids = sorted(set(matched_tenant_ids))
    if len(unique_ids) != 1:
        return None

    tid = unique_ids[0]
    tenant = await Tenant.get_or_none(id=tid)
    domain = (tenant.domain or "").strip() if tenant else ""
    return WeComTenantResolveResult(tenant_id=tid, tenant_domain=domain, candidates_count=1)


async def list_wecom_enabled_tenant_ids() -> list[int]:
    async with unscoped(
        reason="企业微信启用组织候选扫描（公开登录入口）",
        resource="IntegrationConfig",
    ):
        rows = await IntegrationConfig.filter(
            type="wecom",
            is_active=True,
            deleted_at__isnull=True,
        ).all()
    ids: list[int] = []
    seen: set[int] = set()
    for row in rows:
        cfg = row.config if isinstance(row.config, dict) else {}
        if not _normalize_corp_id(cfg) or _parse_wecom_agent_id(cfg) is None:
            continue
        tid = int(row.tenant_id)
        if tid in seen:
            continue
        seen.add(tid)
        ids.append(tid)
    return ids


@dataclass(frozen=True)
class WeComBootstrapSummary:
    """无 corp+agent 时的组织发现：同 Corp 多应用可先任选一租户发起 OAuth，再按绑定反查。"""

    tenant_id: int | None
    candidates_count: int
    tenant_domain: str | None = None
    shared_corp_id: str | None = None
    """全站启用连接器共用同一 CorpId 时填充；供前端走发现授权。"""
    bootstrap_tenant_id: int | None = None
    """发现授权用的租户（取其 Agent 换 code）；与 tenant_id 在唯一命中时相同。"""


async def summarize_wecom_bootstrap_without_entry() -> WeComBootstrapSummary:
    async with unscoped(
        reason="企业微信连接器候选组织发现（公开登录入口）",
        resource="IntegrationConfig",
    ):
        rows = await IntegrationConfig.filter(
            type="wecom",
            is_active=True,
            deleted_at__isnull=True,
        ).all()
    by_corp: dict[str, list[int]] = {}
    for row in rows:
        cfg = row.config if isinstance(row.config, dict) else {}
        corp = _normalize_corp_id(cfg)
        if not corp or _parse_wecom_agent_id(cfg) is None:
            continue
        by_corp.setdefault(corp, [])
        tid = int(row.tenant_id)
        if tid not in by_corp[corp]:
            by_corp[corp].append(tid)

    all_ids = sorted({tid for ids in by_corp.values() for tid in ids})
    if not all_ids:
        return WeComBootstrapSummary(tenant_id=None, candidates_count=0)

    if len(all_ids) == 1:
        tid = all_ids[0]
        tenant = await Tenant.get_or_none(id=tid)
        domain = (tenant.domain or "").strip() if tenant else ""
        return WeComBootstrapSummary(
            tenant_id=tid,
            candidates_count=1,
            tenant_domain=domain or None,
            shared_corp_id=next(iter(by_corp.keys())),
            bootstrap_tenant_id=tid,
        )

    if len(by_corp) == 1:
        corp = next(iter(by_corp.keys()))
        ids = sorted(by_corp[corp])
        boot = ids[0]
        return WeComBootstrapSummary(
            tenant_id=None,
            candidates_count=len(ids),
            shared_corp_id=corp,
            bootstrap_tenant_id=boot,
        )

    return WeComBootstrapSummary(
        tenant_id=None,
        candidates_count=len(all_ids),
    )
