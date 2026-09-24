"""KU-AI S3 单测：知识库管理面 REST + 服务（spec 136 契约 C，KR-D12）。

全部 mock Tortoise 查询，不需要真实数据库。覆盖：
- KB CRUD 全路径（create/get/update/delete/list 分页 {items,total} + keyword）
- 跨租户/软删/不存在一律 404
- options 只回 status=启用 行，且不回 tenant_id
- embedding_model_id 归属复核：跨租户/不存在 404，非 embed/停用 400
- chunk_size/chunk_overlap 非法 400（>0 且 overlap < chunk_size；显式 null=清空回落）
- 路由注册断言：契约 C 十二条路径/方法/权限码（options 先于 {kb_id}）

文档面（documents/chunks/parse）KnowledgeService 已由 S3 并行单元落地：
路由层顶层直接 import，本文件另含 DocumentListOut（m3）契约断言。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.routing import APIRoute

from apps.kuaiai.api.router import router
from apps.kuaiai.models.catalog import KuaiaiLlmModel
from apps.kuaiai.models.knowledge import KuaiaiKnowledgeBase
from apps.kuaiai.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
)
from apps.kuaiai.services import knowledge_base_service as kbs
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

TENANT = 7
OTHER_TENANT = 8
USER_ID = 5


def _user(uid: int = USER_ID):
    return SimpleNamespace(id=uid, full_name="测试用户", username="tester")


def _qs(rows=(), count=None):
    """伪 QuerySet：链式方法返回自身，终端方法为 AsyncMock。

    list_bases 等直接 ``await q.order_by().offset().limit(...)``（Tortoise
    QuerySet 自身可 await），故 limit 用 AsyncMock 返回 rows。
    """
    q = MagicMock()
    rows = list(rows)
    for m in ("filter", "order_by", "offset"):
        setattr(q, m, MagicMock(return_value=q))
    q.limit = AsyncMock(return_value=rows)
    q.all = AsyncMock(return_value=rows)
    q.first = AsyncMock(return_value=rows[0] if rows else None)
    q.count = AsyncMock(return_value=len(rows) if count is None else count)
    q.exists = AsyncMock(return_value=bool(rows))
    q.update = AsyncMock(return_value=len(rows))
    return q


def _self_updating(ns: SimpleNamespace) -> SimpleNamespace:
    """update_from_dict 回自身并对字段生效（对齐 Tortoise Model 行为）。"""

    def _upd(data):
        ns.__dict__.update(data)
        return ns

    ns.update_from_dict = MagicMock(side_effect=_upd)
    ns.save = AsyncMock()
    return ns


def _base(kbid=1, name="库1", status="启用", tenant=TENANT, **over):
    base = dict(
        id=kbid,
        uuid=f"uuid-kb{kbid}",
        tenant_id=tenant,
        name=name,
        description=None,
        embedding_model_id=None,
        chunk_size=None,
        chunk_overlap=None,
        expand_enabled=None,
        status=status,
        created_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
        updated_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )
    base.update(over)
    return _self_updating(SimpleNamespace(**base))


def _model(mid=1, mtype="embed", status="启用", tenant=TENANT):
    return SimpleNamespace(
        id=mid,
        tenant_id=tenant,
        provider_id=1,
        model_name="emb-model",
        model_type=mtype,
        status=status,
    )


# ------------------------------------------------------------ service: CRUD


class TestKnowledgeBaseCrud:
    @pytest.mark.asyncio
    async def test_create_happy_path(self):
        created = {}

        async def _create(**kw):
            created.update(kw)
            return _base(name=kw["name"])

        payload = KnowledgeBaseCreate(name="  工艺库  ", chunk_size=500, chunk_overlap=50)
        with (
            patch.object(
                KuaiaiKnowledgeBase, "get_or_none", new=AsyncMock(return_value=None)
            ),
            patch.object(
                KuaiaiKnowledgeBase, "create", new=AsyncMock(side_effect=_create)
            ),
        ):
            base = await kbs.create_base(TENANT, _user(), payload)
        assert created["tenant_id"] == TENANT
        assert created["name"] == "工艺库"  # strip
        assert created["status"] == "启用"  # 缺省启用
        assert created["chunk_size"] == 500
        assert created["created_by"] == USER_ID
        assert created["updated_by"] == USER_ID
        assert base.name == "工艺库"

    @pytest.mark.asyncio
    async def test_create_duplicate_name_400(self):
        with patch.object(
            KuaiaiKnowledgeBase,
            "get_or_none",
            new=AsyncMock(return_value=_base()),
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await kbs.create_base(TENANT, _user(), KnowledgeBaseCreate(name="库1"))
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_bad_status_400(self):
        with pytest.raises(BusinessLogicError):
            await kbs.create_base(
                TENANT, _user(), KnowledgeBaseCreate(name="x", status="冻结")
            )

    @pytest.mark.asyncio
    async def test_get_base_cross_tenant_404(self):
        with patch.object(
            KuaiaiKnowledgeBase, "get_or_none", new=AsyncMock(return_value=None)
        ) as mock_get:
            with pytest.raises(NotFoundError):
                await kbs.get_base(OTHER_TENANT, 1)
        assert mock_get.await_args.kwargs["tenant_id"] == OTHER_TENANT

    @pytest.mark.asyncio
    async def test_update_name_dup_excludes_self(self):
        base = _base(kbid=1, name="库1")
        other = _base(kbid=2, name="库2")
        # get_or_none 顺序：get_base 取本行 → 重名查询取到他人行 → 400
        with patch.object(
            KuaiaiKnowledgeBase,
            "get_or_none",
            new=AsyncMock(side_effect=[base, other]),
        ):
            with pytest.raises(BusinessLogicError):
                await kbs.update_base(
                    TENANT, _user(), 1, KnowledgeBaseUpdate(name="库2")
                )
        base.update_from_dict.assert_not_called()

        # 改回自己同名（dup.id == base.id）不算冲突
        base2 = _base(kbid=1, name="库1")
        with patch.object(
            KuaiaiKnowledgeBase,
            "get_or_none",
            new=AsyncMock(side_effect=[base2, base2]),
        ):
            await kbs.update_base(
                TENANT, _user(), 1, KnowledgeBaseUpdate(name="库1")
            )
        base2.update_from_dict.assert_called()

    @pytest.mark.asyncio
    async def test_update_name_null_400(self):
        base = _base()
        with patch.object(
            KuaiaiKnowledgeBase, "get_or_none", new=AsyncMock(return_value=base)
        ):
            with pytest.raises(BusinessLogicError):
                await kbs.update_base(TENANT, _user(), 1, KnowledgeBaseUpdate(name=None))
        base.update_from_dict.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_writes_audit_and_saves(self):
        base = _base()
        with patch.object(
            KuaiaiKnowledgeBase, "get_or_none", new=AsyncMock(return_value=base)
        ):
            await kbs.update_base(
                TENANT, _user(), 1, KnowledgeBaseUpdate(description="d", status="停用")
            )
        data = base.update_from_dict.call_args.args[0]
        assert data["status"] == "停用"
        assert data["updated_by"] == USER_ID
        base.save.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_soft_delete_only(self):
        """软删本行；档案 knowledge_ids JSONB 引用不级联（检索侧过滤）。"""
        base = _base()
        with patch.object(
            KuaiaiKnowledgeBase, "get_or_none", new=AsyncMock(return_value=base)
        ):
            await kbs.delete_base(TENANT, _user(), 1)
        assert base.deleted_at is not None
        assert base.update_from_dict.call_args.args[0]["updated_by"] == USER_ID
        base.save.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_cross_tenant_404(self):
        with patch.object(
            KuaiaiKnowledgeBase, "get_or_none", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(NotFoundError):
                await kbs.delete_base(OTHER_TENANT, _user(), 1)


class TestListAndOptions:
    @pytest.mark.asyncio
    async def test_list_bases_page_shape_and_keyword(self):
        q = _qs([_base(1), _base(2)], count=9)
        with patch.object(
            KuaiaiKnowledgeBase, "filter", MagicMock(return_value=q)
        ) as mock_filter:
            out = await kbs.list_bases(TENANT, page=2, page_size=2, keyword="工艺")
        assert set(out.keys()) == {"items", "total"}
        assert out["total"] == 9
        assert len(out["items"]) == 2
        # 租户过滤在类级 filter；keyword 走 name__icontains
        assert mock_filter.call_args.kwargs["tenant_id"] == TENANT
        q.filter.assert_called_with(name__icontains="工艺")
        q.offset.assert_called_with(2)
        q.limit.assert_called_with(2)

    @pytest.mark.asyncio
    async def test_list_bases_no_keyword_no_extra_filter(self):
        q = _qs([])
        with patch.object(KuaiaiKnowledgeBase, "filter", MagicMock(return_value=q)):
            out = await kbs.list_bases(TENANT)
        assert out == {"items": [], "total": 0}
        q.filter.assert_not_called()

    @pytest.mark.asyncio
    async def test_base_options_only_enabled(self):
        rows = [_base(1), _base(2, name="库2")]
        q = _qs(rows)
        with patch.object(
            KuaiaiKnowledgeBase, "filter", MagicMock(return_value=q)
        ) as mock_filter:
            options = await kbs.base_options(TENANT)
        assert mock_filter.call_args.kwargs["status"] == "启用"
        assert mock_filter.call_args.kwargs["tenant_id"] == TENANT
        assert [o["id"] for o in options] == [1, 2]
        for opt in options:
            assert set(opt.keys()) == {"id", "name", "description"}
            assert "tenant_id" not in opt


class TestEmbeddingModelBinding:
    @pytest.mark.asyncio
    async def test_embed_model_ok(self):
        created = {}

        async def _create(**kw):
            created.update(kw)
            return _base(embedding_model_id=kw["embedding_model_id"])

        payload = KnowledgeBaseCreate(name="k", embedding_model_id=3)
        with (
            patch.object(
                KuaiaiKnowledgeBase, "get_or_none", new=AsyncMock(return_value=None)
            ),
            patch.object(
                KuaiaiLlmModel,
                "get_or_none",
                new=AsyncMock(return_value=_model(mid=3, mtype="embed")),
            ),
            patch.object(
                KuaiaiKnowledgeBase, "create", new=AsyncMock(side_effect=_create)
            ),
        ):
            await kbs.create_base(TENANT, _user(), payload)
        assert created["embedding_model_id"] == 3

    @pytest.mark.asyncio
    async def test_cross_tenant_model_404(self):
        payload = KnowledgeBaseCreate(name="k", embedding_model_id=55)
        with (
            patch.object(
                KuaiaiKnowledgeBase, "get_or_none", new=AsyncMock(return_value=None)
            ),
            patch.object(
                KuaiaiLlmModel, "get_or_none", new=AsyncMock(return_value=None)
            ) as mock_get,
        ):
            with pytest.raises(NotFoundError):
                await kbs.create_base(TENANT, _user(), payload)
        # 归属查询带本租户过滤，查不到即跨租户/不存在 → 404
        assert mock_get.await_args.kwargs["tenant_id"] == TENANT

    @pytest.mark.asyncio
    async def test_non_embed_model_400(self):
        payload = KnowledgeBaseCreate(name="k", embedding_model_id=2)
        with (
            patch.object(
                KuaiaiKnowledgeBase, "get_or_none", new=AsyncMock(return_value=None)
            ),
            patch.object(
                KuaiaiLlmModel,
                "get_or_none",
                new=AsyncMock(return_value=_model(mid=2, mtype="chat")),
            ),
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await kbs.create_base(TENANT, _user(), payload)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_disabled_embed_model_400(self):
        payload = KnowledgeBaseCreate(name="k", embedding_model_id=2)
        with (
            patch.object(
                KuaiaiKnowledgeBase, "get_or_none", new=AsyncMock(return_value=None)
            ),
            patch.object(
                KuaiaiLlmModel,
                "get_or_none",
                new=AsyncMock(return_value=_model(mid=2, status="停用")),
            ),
        ):
            with pytest.raises(BusinessLogicError):
                await kbs.create_base(TENANT, _user(), payload)

    @pytest.mark.asyncio
    async def test_update_embed_null_clears_without_check(self):
        """显式 null = 清空回落默认 embed，不触发归属查询。"""
        base = _base(embedding_model_id=3)
        with (
            patch.object(
                KuaiaiKnowledgeBase, "get_or_none", new=AsyncMock(return_value=base)
            ),
            patch.object(
                KuaiaiLlmModel, "get_or_none", new=AsyncMock()
            ) as mock_model_get,
        ):
            await kbs.update_base(
                TENANT, _user(), 1, KnowledgeBaseUpdate(embedding_model_id=None)
            )
        mock_model_get.assert_not_called()
        assert base.embedding_model_id is None


class TestChunkParamValidation:
    @pytest.mark.asyncio
    async def test_overlap_ge_size_400(self):
        with pytest.raises(BusinessLogicError):
            await kbs.create_base(
                TENANT,
                _user(),
                KnowledgeBaseCreate(name="k", chunk_size=100, chunk_overlap=100),
            )
        with pytest.raises(BusinessLogicError):
            await kbs.create_base(
                TENANT,
                _user(),
                KnowledgeBaseCreate(name="k", chunk_size=100, chunk_overlap=200),
            )

    @pytest.mark.asyncio
    async def test_overlap_zero_400(self):
        """schema 层 ge=0 放行，服务层按 spec 要求 overlap>0 → 400。"""
        with pytest.raises(BusinessLogicError):
            await kbs.create_base(
                TENANT,
                _user(),
                KnowledgeBaseCreate(name="k", chunk_size=100, chunk_overlap=0),
            )

    @pytest.mark.asyncio
    async def test_update_merges_with_existing_values(self):
        """单侧更新与另一侧生效值合并校验。"""
        base = _base(chunk_size=100, chunk_overlap=10)
        with patch.object(
            KuaiaiKnowledgeBase, "get_or_none", new=AsyncMock(return_value=base)
        ):
            with pytest.raises(BusinessLogicError):
                await kbs.update_base(
                    TENANT, _user(), 1, KnowledgeBaseUpdate(chunk_overlap=100)
                )
        base.update_from_dict.assert_not_called()

        # 合法单侧更新通过
        with patch.object(
            KuaiaiKnowledgeBase, "get_or_none", new=AsyncMock(return_value=base)
        ):
            await kbs.update_base(
                TENANT, _user(), 1, KnowledgeBaseUpdate(chunk_overlap=50)
            )
        base.update_from_dict.assert_called()

    @pytest.mark.asyncio
    async def test_chunk_null_clears_to_fallback(self):
        """显式 null 清空回落租户配置，不再参与成对比较。"""
        base = _base(chunk_size=100, chunk_overlap=90)
        with patch.object(
            KuaiaiKnowledgeBase, "get_or_none", new=AsyncMock(return_value=base)
        ):
            await kbs.update_base(
                TENANT, _user(), 1, KnowledgeBaseUpdate(chunk_size=None)
            )
        assert base.chunk_size is None


class TestKnowledgeBaseOutContract:
    def test_out_has_no_tenant_id(self):
        out = KnowledgeBaseOut.model_validate(_base())
        dumped = out.model_dump()
        assert "tenant_id" not in dumped
        assert dumped["name"] == "库1"


def _doc_row(**over):
    """文档行伪 ORM 对象（model_validate(from_attributes) 可用）。"""
    base = dict(
        id=41,
        uuid="uuid-doc41",
        knowledge_id=1,
        title="文档",
        source_type="txt",
        file_uuid=None,
        raw_content="原文内容",
        status="ready",
        chunk_count=3,
        error_message=None,
        is_active=True,
        created_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
        updated_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestDocumentListOutContract:
    """m3：documents list 用 DocumentListOut（不回 raw_content），detail 保留。"""

    def test_list_schema_excludes_raw_content(self):
        from apps.kuaiai.schemas.knowledge import DocumentListOut

        assert "raw_content" not in DocumentListOut.model_fields
        dumped = DocumentListOut.model_validate(_doc_row()).model_dump()
        assert "raw_content" not in dumped
        assert dumped["title"] == "文档"

    def test_detail_schema_keeps_raw_content(self):
        from apps.kuaiai.schemas.knowledge import DocumentOut

        assert "raw_content" in DocumentOut.model_fields

    @pytest.mark.asyncio
    async def test_documents_list_route_strips_raw_content(self):
        """GET /knowledge-bases/{kb_id}/documents 返回项不含 raw_content。"""
        from apps.kuaiai.api.router import api_list_kb_documents
        from apps.kuaiai.services.knowledge_service import KnowledgeService

        with (
            patch.object(
                kbs, "get_base", AsyncMock(return_value=_base())
            ),
            patch.object(
                KnowledgeService,
                "list_documents",
                AsyncMock(
                    return_value={"items": [_doc_row()], "total": 1}
                ),
            ),
        ):
            result = await api_list_kb_documents(1, 1, 20, TENANT)
        assert result["total"] == 1
        item = result["items"][0]
        dumped = (
            item.model_dump() if hasattr(item, "model_dump") else dict(item)
        )
        assert "raw_content" not in dumped
        assert dumped["title"] == "文档"


# ------------------------------------------------------- 路由注册与权限码

_EXPECTED_KB_ROUTES = {
    ("GET", "/knowledge-bases"): {"kuaiai:knowledge:list"},
    ("POST", "/knowledge-bases"): {"kuaiai:knowledge:add"},
    ("GET", "/knowledge-bases/options"): {"kuaiai:knowledge:query"},
    ("GET", "/knowledge-bases/{kb_id}"): {"kuaiai:knowledge:query"},
    ("PUT", "/knowledge-bases/{kb_id}"): {"kuaiai:knowledge:edit"},
    ("DELETE", "/knowledge-bases/{kb_id}"): {"kuaiai:knowledge:remove"},
    ("GET", "/knowledge-bases/{kb_id}/documents"): {"kuaiai:knowledge:list"},
    ("POST", "/knowledge-bases/{kb_id}/documents"): {"kuaiai:knowledge:add"},
    ("GET", "/documents/{document_id}"): {"kuaiai:knowledge:query"},
    ("DELETE", "/documents/{document_id}"): {"kuaiai:knowledge:remove"},
    ("POST", "/documents/{document_id}/parse"): {"kuaiai:knowledge:edit"},
    ("GET", "/documents/{document_id}/chunks"): {"kuaiai:knowledge:query"},
}


def _required_permissions(route: APIRoute):
    """从 require_access 依赖闭包中取出 required_permissions。"""
    perms = set()
    for dep in route.dependencies or []:
        fn = getattr(dep, "dependency", None)
        closure = getattr(fn, "__closure__", None)
        if fn is None or closure is None:
            continue
        for name, cell in zip(fn.__code__.co_freevars, closure):
            if name == "required_permissions":
                perms.update(cell.cell_contents or [])
    return perms


class TestKnowledgeRouteRegistration:
    """契约 C 十二条 S3 路由：路径/方法/权限码。文档面仅断言注册存在性，
    不调 KnowledgeService 实现（由并行单元落地）。"""

    def test_all_s3_routes_registered_with_permission_codes(self):
        table = {}
        for r in router.routes:
            if not isinstance(r, APIRoute):
                continue
            for method in r.methods:
                table[(method, r.path)] = _required_permissions(r)
        for key, perms in _EXPECTED_KB_ROUTES.items():
            assert key in table, f"路由未注册: {key}"
            assert table[key] == perms, f"{key} 权限码不符: {table[key]}"

    def test_options_registered_before_kb_id(self):
        """/knowledge-bases/options 必须先于 /knowledge-bases/{kb_id} 注册。"""
        get_paths = [
            r.path
            for r in router.routes
            if isinstance(r, APIRoute) and "GET" in r.methods
        ]
        assert get_paths.index("/knowledge-bases/options") < get_paths.index(
            "/knowledge-bases/{kb_id}"
        )

    def test_document_routes_use_knowledge_service(self):
        """文档面 KnowledgeService 已就位：路由模块顶层直接 import
        （S3 并行单元交付后 lazy import seam 已移除）。"""
        import apps.kuaiai.api.router as r

        assert r.KnowledgeService is not None
        for fn in (
            "list_documents",
            "create_document",
            "get_document",
            "delete_document",
            "request_parse",
            "list_chunks",
        ):
            assert callable(getattr(r.KnowledgeService, fn, None)), fn
