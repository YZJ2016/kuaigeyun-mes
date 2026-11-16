"""单据行「物料附件」汇总（Material.images + 工程图纸）。"""

from typing import Literal, Optional

from pydantic import Field

from core.schemas.base import BaseSchema


class DocumentLineMaterialAttachmentSourceItem(BaseSchema):
    key: str = Field(..., description="列表唯一键")
    source: Literal["material_image", "engineering_drawing"] = Field(
        ..., description="来源类型"
    )
    file_uuid: str = Field(..., description="文件 UUID")
    name: str = Field(..., description="展示名称")
    content_type: Optional[str] = Field(None, description="MIME 类型（若已知）")
    drawing_code: Optional[str] = Field(None, description="工程图纸编码")
    drawing_revision: Optional[str] = Field(None, description="工程图纸版本")


class DocumentLineMaterialAttachmentSourcesResponse(BaseSchema):
    material_id: int = Field(..., description="物料 ID")
    items: list[DocumentLineMaterialAttachmentSourceItem] = Field(
        default_factory=list, description="可勾选复制到行附件的候选"
    )
