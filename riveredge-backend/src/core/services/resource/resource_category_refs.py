"""资源分类外键回显（列表/详情响应共用）。"""

from typing import Optional, Tuple
from uuid import UUID


def read_category_uuid_name(entity) -> Tuple[Optional[UUID], Optional[str]]:
    category = getattr(entity, "category", None)
    if category is not None:
        return UUID(str(category.uuid)), category.name
    return None, None
