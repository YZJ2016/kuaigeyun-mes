"""汇率设置 CRUD、参考汇率拉取与按业务日 lookup。"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from apps.common.audit_actor import apply_create_audit, apply_update_audit
from apps.kuaicaiwu.models.gl_exchange_rate import GlExchangeRate
from apps.kuaicaiwu.services.gl.settings_service import GlSettingsService
from core.utils.timezone_utils import resolve_business_datetime, to_site_date
from infra.exceptions.exceptions import NotFoundError, ValidationError
from infra.infrastructure.http import get_http_client
from infra.models.user import User

# 制造业常见外币（相对本位币维护；本位币自身不入库）
COMMON_FOREIGN_CURRENCIES: Tuple[str, ...] = ("USD", "EUR", "JPY", "HKD", "GBP", "SGD")

_FRANKFURTER_V2 = "https://api.frankfurter.dev/v2/rates"
_RATE_QUANT = Decimal("0.000001")

# 参考汇率来源（国内优先默认 CFETS 人民币中间价）
REFERENCE_SOURCES: Dict[str, Dict[str, str]] = {
    "cfets": {
        "provider": "cfets",
        "label": "中国外汇交易中心（人民币中间价）",
        "notes": "参考汇率（中国外汇交易中心中间价）",
        "description": "中国人民银行授权、中国外汇交易中心每日发布的人民币汇率中间价，国内账务与结售汇普遍参照",
    },
    "ecb": {
        "provider": "ecb",
        "label": "欧洲央行",
        "notes": "参考汇率（欧洲央行）",
        "description": "欧洲中央银行（ECB）官方参考汇率，适用于跨境欧元区业务对照",
    },
}
DEFAULT_REFERENCE_SOURCE = "cfets"


class ExchangeRateService:
    _SORT_FIELDS = frozenset(
        {"currency_code", "effective_date", "rate", "created_at", "updated_at"}
    )

    @staticmethod
    def _normalize_currency(code: str) -> str:
        value = (code or "").strip().upper()
        if not value:
            raise ValidationError("币种不能为空")
        if len(value) > 10:
            raise ValidationError("币种代码过长")
        return value

    async def _base_currency(self, tenant_id: int) -> str:
        settings = await GlSettingsService().get_or_create(tenant_id)
        return self._normalize_currency(settings.base_currency or "CNY")

    def _site_today(self) -> date:
        return to_site_date(resolve_business_datetime())

    @classmethod
    def list_reference_sources(cls) -> List[Dict[str, str]]:
        return [
            {
                "code": code,
                "label": meta["label"],
                "description": meta["description"],
                "is_default": code == DEFAULT_REFERENCE_SOURCE,
            }
            for code, meta in REFERENCE_SOURCES.items()
        ]

    @classmethod
    def _resolve_source(cls, source: Optional[str]) -> Tuple[str, Dict[str, str]]:
        code = (source or DEFAULT_REFERENCE_SOURCE).strip().lower()
        meta = REFERENCE_SOURCES.get(code)
        if not meta:
            allowed = "、".join(REFERENCE_SOURCES.keys())
            raise ValidationError(f"不支持的参考汇率来源：{source}，可选：{allowed}")
        return code, meta

    async def validate_foreign_row(
        self,
        tenant_id: int,
        *,
        currency_code: str,
        rate: Decimal,
    ) -> str:
        code = self._normalize_currency(currency_code)
        base = await self._base_currency(tenant_id)
        if code == base:
            raise ValidationError("本位币无需维护汇率设置，单据汇率固定为 1")
        value = Decimal(str(rate))
        if value <= 0:
            raise ValidationError("汇率必须大于 0")
        return code

    async def lookup(
        self,
        tenant_id: int,
        *,
        currency_code: str,
        as_of_date: date,
    ) -> Optional[GlExchangeRate]:
        code = self._normalize_currency(currency_code)
        base = await self._base_currency(tenant_id)
        if code == base:
            return None
        return (
            await GlExchangeRate.filter(
                tenant_id=tenant_id,
                currency_code=code,
                effective_date__lte=as_of_date,
                deleted_at__isnull=True,
            )
            .order_by("-effective_date", "-id")
            .first()
        )

    async def lookup_rate(
        self,
        tenant_id: int,
        *,
        currency_code: str,
        as_of_date: date,
    ) -> Tuple[bool, Optional[Decimal], str]:
        """返回 (found, rate, normalized_currency)。本位币恒 found=True rate=1。"""
        code = self._normalize_currency(currency_code)
        base = await self._base_currency(tenant_id)
        if code == base:
            return True, Decimal("1"), code
        row = await self.lookup(tenant_id, currency_code=code, as_of_date=as_of_date)
        if not row:
            return False, None, code
        return True, Decimal(str(row.rate)), code

    async def fetch_reference_rates(
        self,
        *,
        base_currency: str,
        currency_codes: Sequence[str],
        as_of_date: date,
        source: Optional[str] = None,
    ) -> Tuple[Dict[str, Decimal], str, str]:
        """
        拉取参考汇率：1 单位外币 = rate 单位本位币。

        返回 (rates, source_code, notes)。失败即抛错，不猜数、不切换备用源。
        """
        source_code, source_meta = self._resolve_source(source)
        base = self._normalize_currency(base_currency)
        targets: List[str] = []
        seen = set()
        for raw in currency_codes:
            code = self._normalize_currency(raw)
            if code == base or code in seen:
                continue
            seen.add(code)
            targets.append(code)
        if not targets:
            return {}, source_code, source_meta["notes"]

        today = self._site_today()
        params: Dict[str, str] = {
            "base": base.lower(),
            "providers": source_meta["provider"],
            "quotes": ",".join(c.lower() for c in targets),
        }
        if as_of_date < today:
            # 取 [as_of-14d, as_of] 区间内不晚于 as_of 的最近牌价（节假日无中间价）
            start = as_of_date - timedelta(days=14)
            params["from"] = start.isoformat()
            params["to"] = as_of_date.isoformat()

        client = get_http_client()
        try:
            resp = await client.get(_FRANKFURTER_V2, params=params, timeout=15.0)
        except httpx.TimeoutException as exc:
            raise ValidationError(
                f"{source_meta['label']}接口超时，请稍后重试"
            ) from exc
        except httpx.RequestError as exc:
            raise ValidationError(
                f"{source_meta['label']}接口不可用：{exc}"
            ) from exc

        if resp.status_code == 404:
            raise ValidationError(
                f"{source_meta['label']}不支持本位币 {base} 或指定日期无牌价，请换来源或手工维护"
            )
        if resp.status_code >= 400:
            detail = (resp.text or "").strip()[:200]
            raise ValidationError(
                f"{source_meta['label']}返回错误（HTTP {resp.status_code}）"
                f"{(': ' + detail) if detail else ''}"
            )

        try:
            body = resp.json()
        except ValueError as exc:
            raise ValidationError(f"{source_meta['label']}返回非 JSON") from exc

        if not isinstance(body, list) or not body:
            raise ValidationError(f"{source_meta['label']}未返回可用牌价")

        # 每币种取不晚于 as_of_date 的最新一条；rate 为 1 本位币可兑外币数，取倒数
        best: Dict[str, Tuple[date, Decimal]] = {}
        for row in body:
            if not isinstance(row, dict):
                continue
            quote = str(row.get("quote") or "").strip().upper()
            if quote not in seen or quote == base:
                continue
            raw_date = row.get("date")
            try:
                row_date = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                continue
            if row_date > as_of_date:
                continue
            try:
                foreign_per_base = Decimal(str(row.get("rate")))
            except (InvalidOperation, TypeError, ValueError):
                continue
            if foreign_per_base <= 0:
                continue
            prev = best.get(quote)
            if prev is None or row_date > prev[0]:
                best[quote] = (row_date, foreign_per_base)

        result: Dict[str, Decimal] = {}
        missing: List[str] = []
        for code in targets:
            pair = best.get(code)
            if pair is None:
                missing.append(code)
                continue
            rate = (Decimal("1") / pair[1]).quantize(_RATE_QUANT, rounding=ROUND_HALF_UP)
            result[code] = rate
        if missing and not result:
            raise ValidationError(
                f"{source_meta['label']}未提供币种 {', '.join(missing)} 相对 {base} 的牌价"
            )
        return result, source_code, source_meta["notes"]

    async def _upsert_rate_row(
        self,
        tenant_id: int,
        *,
        currency_code: str,
        effective_date: date,
        rate: Decimal,
        notes: str,
        current_user: Optional[User],
        overwrite: bool,
    ) -> str:
        """返回 created | updated | skipped。"""
        code = await self.validate_foreign_row(
            tenant_id, currency_code=currency_code, rate=rate
        )
        existing = await GlExchangeRate.get_or_none(
            tenant_id=tenant_id,
            currency_code=code,
            effective_date=effective_date,
            deleted_at__isnull=True,
        )
        if existing:
            if not overwrite:
                return "skipped"
            existing.rate = Decimal(str(rate))
            existing.notes = notes
            apply_update_audit(existing, current_user)
            await existing.save()
            return "updated"
        payload: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "uuid": str(uuid.uuid4()),
            "currency_code": code,
            "effective_date": effective_date,
            "rate": Decimal(str(rate)),
            "notes": notes,
        }
        apply_create_audit(payload, current_user)
        await GlExchangeRate.create(**payload)
        return "created"

    async def preset_common_currencies(
        self,
        tenant_id: int,
        *,
        current_user: Optional[User] = None,
        effective_date: Optional[date] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """为常见外币写入当日参考汇率；已存在则跳过。"""
        base = await self._base_currency(tenant_id)
        day = effective_date or self._site_today()
        targets = [c for c in COMMON_FOREIGN_CURRENCIES if c != base]
        if not targets:
            raise ValidationError("常见货币列表均与本位币相同，无需预置")
        rates, source_code, notes = await self.fetch_reference_rates(
            base_currency=base,
            currency_codes=targets,
            as_of_date=day,
            source=source,
        )
        created = 0
        skipped = 0
        unavailable: List[str] = []
        for code in targets:
            rate = rates.get(code)
            if rate is None:
                unavailable.append(code)
                continue
            action = await self._upsert_rate_row(
                tenant_id,
                currency_code=code,
                effective_date=day,
                rate=rate,
                notes=notes,
                current_user=current_user,
                overwrite=False,
            )
            if action == "created":
                created += 1
            else:
                skipped += 1
        return {
            "effective_date": day.isoformat(),
            "base_currency": base,
            "source": source_code,
            "created": created,
            "skipped": skipped,
            "updated": 0,
            "unavailable": unavailable,
        }

    async def import_reference_rates(
        self,
        tenant_id: int,
        *,
        current_user: Optional[User] = None,
        effective_date: Optional[date] = None,
        currency_codes: Optional[Sequence[str]] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """按参考汇率写入/覆盖指定日汇率。"""
        base = await self._base_currency(tenant_id)
        day = effective_date or self._site_today()
        if currency_codes:
            targets = [self._normalize_currency(c) for c in currency_codes]
        else:
            existing = await GlExchangeRate.filter(
                tenant_id=tenant_id, deleted_at__isnull=True
            ).values_list("currency_code", flat=True)
            targets = list({*COMMON_FOREIGN_CURRENCIES, *existing})
        targets = [c for c in targets if c != base]
        if not targets:
            raise ValidationError("没有可拉取的外币币种")
        rates, source_code, notes = await self.fetch_reference_rates(
            base_currency=base,
            currency_codes=targets,
            as_of_date=day,
            source=source,
        )
        created = 0
        updated = 0
        unavailable: List[str] = []
        for code in targets:
            rate = rates.get(code)
            if rate is None:
                unavailable.append(code)
                continue
            action = await self._upsert_rate_row(
                tenant_id,
                currency_code=code,
                effective_date=day,
                rate=rate,
                notes=notes,
                current_user=current_user,
                overwrite=True,
            )
            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1
        return {
            "effective_date": day.isoformat(),
            "base_currency": base,
            "source": source_code,
            "created": created,
            "updated": updated,
            "skipped": 0,
            "unavailable": unavailable,
        }

    async def create(
        self,
        tenant_id: int,
        *,
        currency_code: str,
        effective_date: date,
        rate: Decimal,
        notes: Optional[str] = None,
        current_user: Optional[User] = None,
    ) -> GlExchangeRate:
        code = await self.validate_foreign_row(tenant_id, currency_code=currency_code, rate=rate)
        exists = await GlExchangeRate.filter(
            tenant_id=tenant_id,
            currency_code=code,
            effective_date=effective_date,
            deleted_at__isnull=True,
        ).exists()
        if exists:
            raise ValidationError(f"币种 {code} 在 {effective_date} 的汇率已存在")
        payload: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "uuid": str(uuid.uuid4()),
            "currency_code": code,
            "effective_date": effective_date,
            "rate": Decimal(str(rate)),
            "notes": (notes or "").strip() or None,
        }
        apply_create_audit(payload, current_user)
        return await GlExchangeRate.create(**payload)

    async def get_by_id(self, tenant_id: int, row_id: int) -> GlExchangeRate:
        row = await GlExchangeRate.get_or_none(
            tenant_id=tenant_id, id=row_id, deleted_at__isnull=True
        )
        if not row:
            raise NotFoundError(f"汇率记录不存在: {row_id}")
        return row

    async def update(
        self,
        tenant_id: int,
        row_id: int,
        data: Dict[str, Any],
        current_user: Optional[User] = None,
    ) -> GlExchangeRate:
        row = await self.get_by_id(tenant_id, row_id)
        if "currency_code" in data and data["currency_code"] is not None:
            row.currency_code = await self.validate_foreign_row(
                tenant_id,
                currency_code=str(data["currency_code"]),
                rate=Decimal(str(data.get("rate", row.rate))),
            )
        if "effective_date" in data and data["effective_date"] is not None:
            new_date = data["effective_date"]
            dup = await GlExchangeRate.filter(
                tenant_id=tenant_id,
                currency_code=row.currency_code,
                effective_date=new_date,
                deleted_at__isnull=True,
            ).exclude(id=row.id).exists()
            if dup:
                raise ValidationError(
                    f"币种 {row.currency_code} 在 {new_date} 的汇率已存在"
                )
            row.effective_date = new_date
        if "rate" in data and data["rate"] is not None:
            await self.validate_foreign_row(
                tenant_id, currency_code=row.currency_code, rate=Decimal(str(data["rate"]))
            )
            row.rate = Decimal(str(data["rate"]))
        if "notes" in data:
            notes = data["notes"]
            if notes is not None:
                row.notes = (notes or "").strip() or None
        apply_update_audit(row, current_user)
        await row.save()
        return row

    async def delete(self, tenant_id: int, row_id: int) -> None:
        row = await self.get_by_id(tenant_id, row_id)
        row.deleted_at = resolve_business_datetime()
        await row.save()

    async def list_rows(
        self,
        tenant_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
        currency_code: Optional[str] = None,
        effective_start: Optional[date] = None,
        effective_end: Optional[date] = None,
        keyword: Optional[str] = None,
        sort_field: Optional[str] = None,
        sort_order: Optional[str] = None,
    ) -> Tuple[List[GlExchangeRate], int]:
        q = GlExchangeRate.filter(tenant_id=tenant_id, deleted_at__isnull=True)
        if currency_code:
            q = q.filter(currency_code=self._normalize_currency(currency_code))
        if effective_start:
            q = q.filter(effective_date__gte=effective_start)
        if effective_end:
            q = q.filter(effective_date__lte=effective_end)
        if keyword:
            kw = keyword.strip()
            if kw:
                q = q.filter(currency_code__icontains=kw.upper())
        field = (sort_field or "effective_date").strip()
        if field not in self._SORT_FIELDS:
            field = "effective_date"
        descending = (sort_order or "descend").lower() in {"descend", "desc"}
        order = f"-{field}" if descending else field
        total = await q.count()
        rows = await q.order_by(order, "-id").offset(skip).limit(limit)
        return list(rows), total
