"""Tenant-scoped durable submission results and transactional effect intents."""
from tortoise import fields

from core.models.base import BaseModel


class MobileSubmission(BaseModel):
    id = fields.IntField(pk=True)
    tenant_id = fields.IntField(db_index=True)
    user_id = fields.IntField()
    operation_key = fields.CharField(max_length=128)
    fingerprint = fields.CharField(max_length=64)
    method = fields.CharField(max_length=8)
    path = fields.CharField(max_length=512)
    response_body = fields.TextField(null=True)
    response_status = fields.IntField(default=200)
    entity_id = fields.IntField(null=True)

    class Meta:
        table = "core_mobile_submissions"
        unique_together = [("tenant_id", "user_id", "operation_key")]


class MobileSubmissionEffect(BaseModel):
    id = fields.IntField(pk=True)
    tenant_id = fields.IntField(db_index=True)
    submission_id = fields.IntField()
    effect_type = fields.CharField(max_length=64)
    entity_id = fields.IntField()
    acting_user_id = fields.IntField()
    payload = fields.JSONField()
    status = fields.CharField(max_length=24, default="pending")
    attempts = fields.IntField(default=0)
    next_attempt_at = fields.DatetimeField(null=True)
    claimed_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    last_error_code = fields.CharField(max_length=64, null=True)

    class Meta:
        table = "core_mobile_submission_effects"
        unique_together = [("tenant_id", "submission_id", "effect_type", "entity_id")]
        indexes = [("status", "next_attempt_at")]
