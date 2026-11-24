"""快制造引用展示 Provider 注册自检。"""

from apps.kuaizhizao.reference_display.setup import register_kuaizhizao_reference_display_providers
from core.services.reference.reference_display_provider_registry import get_reference_display_provider


def test_receipt_notice_display_provider_registered():
    register_kuaizhizao_reference_display_providers()
    provider = get_reference_display_provider("kuaizhizao:receipt-notice")
    assert provider is not None
    assert provider.resource_key == "kuaizhizao:receipt-notice"