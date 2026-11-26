"""
装箱箱规配置（Packing Profile）

租户级或物料级：容量、混装、满箱策略、核销门禁。
"""

from tortoise import fields

from core.models.base import BaseModel


class PackingProfile(BaseModel):
    """装箱箱规配置。"""

    class Meta:
        table = "apps_kuaizhizao_packing_profiles"
        table_description = "快格轻制造 - 装箱箱规配置"
        indexes = [
            ("tenant_id", "profile_code"),
            ("tenant_id", "material_id"),
        ]

    id = fields.IntField(pk=True, description="主键ID")
    profile_code = fields.CharField(max_length=50, default="default", description="配置编码")
    material_id = fields.IntField(
        null=True,
        description="物料ID；空表示租户默认箱规",
    )
    pack_mode = fields.CharField(
        max_length=20,
        default="box_first",
        description="装箱模式 box_first/product_first",
    )
    mix_policy = fields.CharField(
        max_length=20,
        default="same_material",
        description="混装策略 same_material/same_product/mixed",
    )
    max_quantity = fields.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        description="单箱目标容量（件）；空表示不限制",
    )
    seal_policy = fields.CharField(
        max_length=20,
        default="manual",
        description="满箱策略 auto_on_full/manual",
    )
    refill_open_box = fields.BooleanField(
        default=False,
        description="是否允许对已封箱但未满的箱补装（主流默认禁止，仅 sealed 未满特殊场景）",
    )
    require_sealed_for_consume = fields.BooleanField(
        default=True,
        description="按箱核销是否必须已封箱",
    )
    allow_manual_box_code = fields.BooleanField(
        default=True,
        description="是否允许手输箱码",
    )
    is_active = fields.BooleanField(default=True, description="是否启用")
    deleted_at = fields.DatetimeField(null=True, description="软删除")

    def __str__(self) -> str:
        return f"PackingProfile({self.profile_code}, material={self.material_id})"
