"""KU-AI S3 单测：search_knowledge Tool 接线 + 路径 A 请求级 knowledge_id。

全部 mock ORM / retrieval facade / LLM，不需要真实端点与数据库。覆盖：
- search_knowledge 闭包：无 ctx / 无档案 / 档案无库 / 无命中文案
- 命中拼 file_name+片段，总长截断 ~2000
- 路径 A：knowledge_id 校验（跨租户 404 / 停用 400）+ 命中注入 SystemMessage
- AC4：档案路径（assembled 非空）携带 knowledge_id → BusinessLogicError(400)
- AiBusinessContext.knowledge_id 经 to_broker_dict 透传
- m6：档案 status!=启用 → 停用文案；m8：路径 A 注入总长截断 ~2000
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import apps.kuaiai.services.chat_service as cs
import apps.kuaiai.services.chat_tools as chat_tools
from apps.kuaiai.models.agent import KuaiaiAgentProfile
from apps.kuaiai.models.knowledge import KuaiaiKnowledgeBase
from core.ai.runtime.context import AiRuntimeContext, reset_ai_context, set_ai_context
from core.ai.schemas.context import AiBusinessContext
from infra.exceptions.exceptions import BusinessLogicError, NotFoundError

TENANT = 7
USER_ID = 5


def _user(uid=USER_ID):
    return SimpleNamespace(id=uid, full_name="测试", username="tester")


def _ctx(agent_id=None, uid=USER_ID):
    return AiRuntimeContext(tenant_id=TENANT, user=_user(uid), agent_id=agent_id)


def _profile(**kw):
    base = dict(
        id=3,
        tenant_id=TENANT,
        knowledge_ids=[9],
        status="启用",
        deleted_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _kb(**kw):
    base = dict(id=9, tenant_id=TENANT, status="启用", deleted_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _patch_profile(profile):
    qs = MagicMock()
    qs.first = AsyncMock(return_value=profile)
    return patch.object(
        KuaiaiAgentProfile, "filter", MagicMock(return_value=qs)
    )


class TestSearchKnowledgeTool:
    @pytest.mark.asyncio
    async def test_no_context(self):
        result = await chat_tools.search_knowledge("问题")
        assert result == chat_tools._ERR_NO_CONTEXT

    @pytest.mark.asyncio
    async def test_no_agent_id(self):
        result = await chat_tools.search_knowledge("问题", ctx=_ctx())
        assert result == chat_tools._ERR_NO_AGENT_PROFILE

    @pytest.mark.asyncio
    async def test_profile_not_found(self):
        """档案不存在/跨租户（filter 已带 tenant）→ 未绑定档案文案。"""
        with _patch_profile(None):
            result = await chat_tools.search_knowledge(
                "问题", ctx=_ctx(agent_id=3)
            )
        assert result == chat_tools._ERR_NO_AGENT_PROFILE

    @pytest.mark.asyncio
    async def test_profile_without_knowledge(self):
        with _patch_profile(_profile(knowledge_ids=[])):
            result = await chat_tools.search_knowledge(
                "问题", ctx=_ctx(agent_id=3)
            )
        assert result == chat_tools._ERR_NO_KNOWLEDGE

    @pytest.mark.asyncio
    async def test_no_hits(self):
        with (
            _patch_profile(_profile()),
            patch(
                "apps.kuaiai.services.retrieval.retrieve",
                new=AsyncMock(return_value=[]),
            ) as mock_retrieve,
        ):
            result = await chat_tools.search_knowledge(
                "如何报工", ctx=_ctx(agent_id=3)
            )
        assert result == chat_tools._ERR_NO_HIT
        mock_retrieve.assert_awaited_once_with(TENANT, "如何报工", [9])

    @pytest.mark.asyncio
    async def test_hits_formatted_with_file_name(self):
        hits = [
            {
                "content": "报工步骤片段",
                "file_name": "生产手册.pdf",
                "document_id": 10,
                "chunk_index": 0,
            }
        ]
        with (
            _patch_profile(_profile()),
            patch(
                "apps.kuaiai.services.retrieval.retrieve",
                new=AsyncMock(return_value=hits),
            ),
        ):
            result = await chat_tools.search_knowledge(
                "如何报工", ctx=_ctx(agent_id=3)
            )
        assert "生产手册.pdf" in result
        assert "报工步骤片段" in result

    @pytest.mark.asyncio
    async def test_result_truncated_at_limit(self):
        hits = [
            {
                "content": "x" * 1500,
                "file_name": "a.txt",
                "document_id": 1,
                "chunk_index": 0,
            },
            {
                "content": "y" * 1500,
                "file_name": "b.txt",
                "document_id": 2,
                "chunk_index": 0,
            },
        ]
        with (
            _patch_profile(_profile()),
            patch(
                "apps.kuaiai.services.retrieval.retrieve",
                new=AsyncMock(return_value=hits),
            ),
        ):
            result = await chat_tools.search_knowledge(
                "q", ctx=_ctx(agent_id=3)
            )
        assert len(result) <= chat_tools._KNOWLEDGE_RESULT_MAX_CHARS + 32

    @pytest.mark.asyncio
    async def test_disabled_agent_profile(self):
        """m6：档案 status!=启用 → 停用文案，不进入检索。"""
        expected = getattr(
            chat_tools, "_ERR_AGENT_DISABLED", "该 Agent 档案已停用"
        )
        mock_retrieve = AsyncMock(return_value=[])
        with (
            _patch_profile(_profile(status="停用")),
            patch(
                "apps.kuaiai.services.retrieval.retrieve",
                new=mock_retrieve,
            ),
        ):
            result = await chat_tools.search_knowledge(
                "q", ctx=_ctx(agent_id=3)
            )
        assert result == expected
        mock_retrieve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_retrieve_exception_returns_error_text(self):
        with (
            _patch_profile(_profile()),
            patch(
                "apps.kuaiai.services.retrieval.retrieve",
                new=AsyncMock(side_effect=RuntimeError("facade boom")),
            ),
        ):
            result = await chat_tools.search_knowledge(
                "q", ctx=_ctx(agent_id=3)
            )
        assert "失败" in result
        assert "facade boom" not in result

    @pytest.mark.asyncio
    async def test_via_contextvar(self):
        """ctx 缺省时经 get_ai_context() 取（tool_bridge 注入路径）。"""
        token = set_ai_context(_ctx(agent_id=3))
        try:
            with (
                _patch_profile(_profile()),
                patch(
                    "apps.kuaiai.services.retrieval.retrieve",
                    new=AsyncMock(return_value=[]),
                ),
            ):
                result = await chat_tools.search_knowledge("q")
            assert result == chat_tools._ERR_NO_HIT
        finally:
            reset_ai_context(token)


class _FakeChat:
    """路径 A 假 chat 模型（ainvoke 捕获注入后的消息序列）。"""

    def __init__(self):
        self.model_name = "fake-model"
        self.invoked_with = []

    def bind(self, **kw):
        return self

    async def ainvoke(self, messages):
        self.invoked_with.append(list(messages))
        return SimpleNamespace(
            content="答复",
            id="chatcmpl-fake",
            usage_metadata={
                "input_tokens": 1,
                "output_tokens": 1,
                "total_tokens": 2,
            },
            response_metadata={"finish_reason": "stop"},
        )


def _config():
    return SimpleNamespace(
        chat_api_key="fake-key",
        chat_base_url="https://llm.example.invalid",
        chat_model="fake-model",
        custom_system_prompt=None,
        stream_enabled=True,
    )


def _path_a_patches(chat, kb, hits):
    """路径 A 公共 patch：目录未命中 → IntegrationConfig 兜底；KB/检索 mock。

    返回 (patches, mocks)：mocks 持有各 AsyncMock 供断言。
    """
    mocks = SimpleNamespace(
        catalog=AsyncMock(return_value=None),
        config=AsyncMock(return_value=_config()),
        build=AsyncMock(return_value=chat),
        kb=AsyncMock(return_value=kb),
        retrieve=AsyncMock(return_value=hits),
    )
    patches = (
        patch.object(cs, "_resolve_catalog_source", mocks.catalog),
        patch.object(cs.AiRuntimeConfig, "load", mocks.config),
        patch.object(cs, "build_chat_model", mocks.build),
        patch.object(cs.KuaiaiKnowledgeBase, "get_or_none", mocks.kb),
        patch.object(cs, "retrieve", mocks.retrieve),
    )
    return patches, mocks


class TestPathAKnowledgeInjection:
    @pytest.mark.asyncio
    async def test_hit_injects_system_message(self):
        chat = _FakeChat()
        hits = [
            {
                "content": "报工片段内容",
                "file_name": "手册.pdf",
                "document_id": 1,
                "chunk_index": 0,
            }
        ]
        patches, mocks = _path_a_patches(chat, _kb(), hits)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "怎么报工"}],
                user=_user(),
                context={"knowledge_id": 9},
            )
        assert result["choices"][0]["message"]["content"] == "答复"
        mocks.retrieve.assert_awaited_once_with(TENANT, "怎么报工", [9])
        messages = chat.invoked_with[0]
        sys_msgs = [m for m in messages if m.__class__.__name__ == "SystemMessage"]
        assert any("手册.pdf" in m.content for m in sys_msgs)
        assert any("报工片段内容" in m.content for m in sys_msgs)

    @pytest.mark.asyncio
    async def test_no_hit_plain_chat(self):
        chat = _FakeChat()
        patches, _ = _path_a_patches(chat, _kb(), [])
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "怎么报工"}],
                user=_user(),
                context={"knowledge_id": 9},
            )
        assert result["choices"][0]["message"]["content"] == "答复"
        sys_msgs = [
            m for m in chat.invoked_with[0]
            if m.__class__.__name__ == "SystemMessage"
        ]
        assert not any("知识库内容" in m.content for m in sys_msgs)

    @pytest.mark.asyncio
    async def test_cross_tenant_kb_404_before_upstream(self):
        chat = _FakeChat()
        patches, mocks = _path_a_patches(chat, None, [])
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            with pytest.raises(NotFoundError):
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                    context={"knowledge_id": 9},
                )
            mocks.build.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_kb_400(self):
        """m2：路径 A 停用库业务拒绝 BusinessLogicError（400）。"""
        chat = _FakeChat()
        patches, _ = _path_a_patches(chat, _kb(status="停用"), [])
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            with pytest.raises(BusinessLogicError) as exc:
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                    context={"knowledge_id": 9},
                )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_agent_path_rejects_request_knowledge_id(self):
        """AC4：assembled 非空（选中档案）携带 knowledge_id → 400
        （m2：BusinessLogicError，注释与 400 现实对齐）。"""
        assembled = SimpleNamespace(
            profile=SimpleNamespace(id=3, default_model_id=11),
            model_name="agent-model",
            agent=MagicMock(),
        )
        with (
            patch.object(
                cs, "assemble", AsyncMock(return_value=assembled)
            ),
            patch.object(
                cs.KuaiaiKnowledgeBase,
                "get_or_none",
                AsyncMock(return_value=_kb()),
            ),
        ):
            with pytest.raises(BusinessLogicError) as exc:
                await cs.create_chat_completion(
                    TENANT,
                    [{"role": "user", "content": "hi"}],
                    user=_user(),
                    context={"agent_id": 3, "knowledge_id": 9},
                )
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_knowledge_injection_truncated(self):
        """m8：路径 A 知识注入片段总长截断 ~2000（与 Tool 侧上限同口径）。"""
        chat = _FakeChat()
        hits = [
            {
                "content": "x" * 1500,
                "file_name": "a.txt",
                "document_id": 1,
                "chunk_index": 0,
            },
            {
                "content": "y" * 1500,
                "file_name": "b.txt",
                "document_id": 2,
                "chunk_index": 0,
            },
        ]
        patches, _ = _path_a_patches(chat, _kb(), hits)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "怎么报工"}],
                user=_user(),
                context={"knowledge_id": 9},
            )
        sys_msgs = [
            m for m in chat.invoked_with[0]
            if m.__class__.__name__ == "SystemMessage"
        ]
        injected = next(
            m for m in sys_msgs if "知识库内容" in m.content
        )
        # 第一片命中保留；第二片被截断；总长 = 引导语 + ~2000 上限
        assert "x" * 500 in injected.content
        assert "y" * 1500 not in injected.content
        assert len(injected.content) <= 2200

    @pytest.mark.asyncio
    async def test_knowledge_id_via_extra_nesting(self):
        """_context_value 口径：extra 嵌套同样生效。"""
        chat = _FakeChat()
        patches, mocks = _path_a_patches(chat, _kb(), [])
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            await cs.create_chat_completion(
                TENANT,
                [{"role": "user", "content": "hi"}],
                user=_user(),
                context={"extra": {"knowledge_id": 9}},
            )
        mocks.kb.assert_awaited_once()


class TestContextSchema:
    def test_knowledge_id_field_passes_broker_dict(self):
        ctx = AiBusinessContext(knowledge_id=9, screen="/apps/kuaiai/chat")
        payload = ctx.to_broker_dict()
        assert payload["knowledge_id"] == 9
        assert payload["screen"] == "/apps/kuaiai/chat"

    def test_knowledge_id_via_extra_flattened(self):
        ctx = AiBusinessContext(extra={"knowledge_id": 9})
        assert ctx.to_broker_dict()["knowledge_id"] == 9


class TestManifestDescription:
    def test_search_knowledge_description_updated(self):
        manifest_path = (
            Path(chat_tools.__file__).resolve().parents[1] / "manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tool = next(
            t for t in manifest["ai_tools"] if t["name"] == "search_knowledge"
        )
        assert "暂未启用" not in tool["description"]
        defn = next(
            d for d in chat_tools.CHAT_TOOL_DEFINITIONS
            if d["function"]["name"] == "search_knowledge"
        )
        assert "暂未启用" not in defn["function"]["description"]
