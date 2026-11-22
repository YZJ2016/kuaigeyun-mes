"""单据关系通用打印必须把当前用户传给 print_document，采购/销售才走字段脱敏。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("document_type", ["purchase_order", "sales_order"])
async def test_generic_document_print_passes_current_user_as_viewer(document_type):
    from apps.kuaizhizao.api.productions.document_relations_legacy import (
        print_document as generic_print,
    )

    printed = AsyncMock(return_value={"success": True, "content": ""})
    with patch(
        "apps.kuaizhizao.api.productions.document_relations_legacy.ensure_document_print_access",
        new=AsyncMock(),
    ), patch(
        "apps.kuaizhizao.api.productions.document_relations_legacy.DocumentPrintService"
    ) as service_cls:
        service_cls.return_value.print_document = printed
        await generic_print(
            request=SimpleNamespace(),
            document_type=document_type,
            document_id=9,
            template_code=None,
            template_uuid=None,
            output_format="html",
            response_format="json",
            auth=SimpleNamespace(),
            current_user=SimpleNamespace(id=15),
            tenant_id=1,
        )

    assert printed.await_args.kwargs["viewer_user_id"] == 15
    assert printed.await_args.kwargs["document_type"] == document_type
    assert printed.await_args.kwargs["document_id"] == 9
