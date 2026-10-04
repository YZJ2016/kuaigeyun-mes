"""同一厂商不同角色可以有不同调用地址。"""

from core.utils.integration_settings import endpoint_for_role

_CHAT = "https://llm-example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
_RERANK = "https://llm-example.cn-beijing.maas.aliyuncs.com/compatible-api/v1/reranks"


def test_chat_and_embed_keep_compatible_mode_base():
    assert endpoint_for_role("chat", _CHAT) == _CHAT
    assert endpoint_for_role("embed", _CHAT + "/") == _CHAT


def test_aliyun_maas_rerank_uses_sibling_reranks_endpoint():
    assert endpoint_for_role("rerank", _CHAT) == _RERANK


def test_rerank_keeps_an_already_specific_endpoint():
    assert endpoint_for_role("rerank", _RERANK) == _RERANK


def test_dashscope_compatible_mode_is_not_rewritten():
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert endpoint_for_role("rerank", url) == url
