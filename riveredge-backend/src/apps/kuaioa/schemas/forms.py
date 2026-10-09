"""审批表单 schemas。"""

from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator


class FormTemplateCreate(BaseModel):
    template_code: str = Field(..., max_length=50)
    template_name: str = Field(..., max_length=200)
    category: str = Field(default="general", max_length=50)
    business_type: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    fields_schema: List[Any] = Field(default_factory=list)
    is_active: bool = True
    show_in_menu: bool = False


class FormTemplateUpdate(BaseModel):
    template_name: Optional[str] = Field(None, max_length=200)
    category: Optional[str] = Field(None, max_length=50)
    business_type: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    fields_schema: Optional[List[Any]] = None
    is_active: Optional[bool] = None
    show_in_menu: Optional[bool] = None


class FormRequestCreate(BaseModel):
    template_id: Optional[int] = None
    template_code: Optional[str] = None
    title: str = Field(..., max_length=200)
    form_data: dict[str, Any] = Field(default_factory=dict)
    department_name: Optional[str] = None
    notes: Optional[str] = None


class FormRequestUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    form_data: Optional[dict[str, Any]] = None
    department_name: Optional[str] = None
    notes: Optional[str] = None


class FormRequestCapabilities(BaseModel):
    uploaded: bool = False
    approved: bool = False
    issued: bool = False
    can_download: bool = False
    responded: bool = False
    countersign_selected: bool = False


class FormRequestConfirmationReply(BaseModel):
    confirmation_result: str = Field(..., min_length=1, max_length=50)


class FormRequestIssueGrantInput(BaseModel):
    target_type: str = Field(..., description="user|role|department")
    target_id: int = Field(..., ge=1)
    target_label: Optional[str] = Field(None, max_length=200)


class FormRequestIssueRequest(BaseModel):
    user_ids: List[int] = Field(default_factory=list, description="下发用户 id")
    role_uuids: List[str] = Field(default_factory=list, description="下发角色 uuid")
    department_ids: List[int] = Field(default_factory=list, description="下发部门 id")

    def normalized_grants(self) -> List[FormRequestIssueGrantInput]:
        out: List[FormRequestIssueGrantInput] = []
        for uid in self.user_ids:
            out.append(FormRequestIssueGrantInput(target_type="user", target_id=int(uid)))
        for rid in self.department_ids:
            out.append(FormRequestIssueGrantInput(target_type="department", target_id=int(rid)))
        return out

    @model_validator(mode="after")
    def _require_targets(self) -> "FormRequestIssueRequest":
        if not self.user_ids and not self.role_uuids and not self.department_ids:
            raise ValueError("须至少选择一个下发对象")
        return self
