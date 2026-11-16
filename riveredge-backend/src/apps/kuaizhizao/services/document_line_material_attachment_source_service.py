"""按物料 ID 汇总 images + 已发布工程图纸，供单据行「物料附件」快捷弹窗。"""

from __future__ import annotations

from typing import Any, List, Optional

from infra.exceptions.exceptions import NotFoundError
from infra.models.user import User

from apps.kuaizhizao.schemas.document_line_material_attachments import (
    DocumentLineMaterialAttachmentSourceItem,
    DocumentLineMaterialAttachmentSourcesResponse,
)
from apps.master_data.models.material import Material
from apps.master_data.services.drawing_service import DrawingService


def _file_uuid_from_attachment(file: Any) -> Optional[str]:
    if isinstance(file, str):
        uid = file.strip()
        return uid or None
    if not isinstance(file, dict):
        return None
    for key in ("uid", "uuid", "file_uuid", "fileUuid"):
        raw = file.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return None


def _name_from_attachment(file: Any, index: int) -> str:
    if isinstance(file, dict):
        for key in ("name", "original_name", "originalName", "file_name", "filename"):
            raw = file.get(key)
            if raw is not None and str(raw).strip():
                return str(raw).strip()
    return f"附件{index + 1}"


def _content_type_from_attachment(file: Any) -> Optional[str]:
    if not isinstance(file, dict):
        return None
    for key in ("content_type", "contentType", "mime_type", "mimeType", "type"):
        raw = file.get(key)
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return None


class DocumentLineMaterialAttachmentSourceService:
    async def list_sources_for_material(
        self,
        tenant_id: int,
        material_id: int,
        *,
        current_user: Optional[User] = None,
    ) -> DocumentLineMaterialAttachmentSourcesResponse:
        material = await Material.get_or_none(
            tenant_id=tenant_id, id=material_id, deleted_at__isnull=True
        )
        if not material:
            raise NotFoundError(f"物料不存在: {material_id}")

        items: List[DocumentLineMaterialAttachmentSourceItem] = []

        images = material.images if isinstance(material.images, list) else []
        for i, img in enumerate(images):
            file_uuid = _file_uuid_from_attachment(img)
            if not file_uuid:
                continue
            items.append(
                DocumentLineMaterialAttachmentSourceItem(
                    key=f"material_image-{file_uuid}",
                    source="material_image",
                    file_uuid=file_uuid,
                    name=_name_from_attachment(img, i),
                    content_type=_content_type_from_attachment(img),
                )
            )

        material_uuid = str(getattr(material, "uuid", "") or "").strip()
        if material_uuid:
            drawings = await DrawingService.list_by_context(
                tenant_id,
                material_uuid=material_uuid,
                current_user=current_user,
            )
            for d in drawings:
                file_uuid = str(getattr(d, "file_uuid", "") or "").strip()
                if not file_uuid and getattr(d, "file", None):
                    file_uuid = str(getattr(d.file, "uuid", "") or "").strip()
                if not file_uuid:
                    continue
                file_brief = getattr(d, "file", None)
                name = (
                    (getattr(file_brief, "original_name", None) if file_brief else None)
                    or f"{d.code}-{d.name}"
                )
                content_type = (
                    getattr(file_brief, "content_type", None) if file_brief else None
                )
                items.append(
                    DocumentLineMaterialAttachmentSourceItem(
                        key=f"engineering_drawing-{d.uuid}",
                        source="engineering_drawing",
                        file_uuid=file_uuid,
                        name=str(name),
                        content_type=str(content_type).strip() if content_type else None,
                        drawing_code=d.code,
                        drawing_revision=d.revision,
                    )
                )
                for j, supp in enumerate(getattr(d, "supplementary_files", None) or []):
                    suuid = str(getattr(supp, "uuid", "") or "").strip()
                    if not suuid:
                        continue
                    supp_name = str(
                        getattr(supp, "original_name", None) or f"{d.code}-附加{j + 1}"
                    )
                    supp_ct = getattr(supp, "content_type", None)
                    items.append(
                        DocumentLineMaterialAttachmentSourceItem(
                            key=f"engineering_drawing-{d.uuid}-supp-{j}",
                            source="engineering_drawing",
                            file_uuid=suuid,
                            name=supp_name,
                            content_type=str(supp_ct).strip() if supp_ct else None,
                            drawing_code=d.code,
                            drawing_revision=d.revision,
                        )
                    )

        return DocumentLineMaterialAttachmentSourcesResponse(
            material_id=material_id,
            items=items,
        )
