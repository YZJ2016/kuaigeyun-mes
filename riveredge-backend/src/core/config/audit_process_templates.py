"""内置审核流程模板（manifest.audit.template 真源）。

单据启用审核时按模板生成 ApprovalProcess.nodes；禁止按 node_key 硬编码流程图。
租户在审批设计器绑定角色/人员后启用；空审批人默认 block，不得静默跳过。
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

# 与 audit_registry.VALID_TEMPLATES 保持一致（注册表校验用那边；本模块负责构图）
TEMPLATE_SIMPLE = "simple"
TEMPLATE_SME = "sme"
TEMPLATE_RD_FILE_CHANGE = "rd_file_change"
TEMPLATE_SAMPLE_SMT = "sample_smt"
TEMPLATE_STRUCTURE_DRAWING = "structure_drawing"
TEMPLATE_COMPLAINT_IQC = "complaint_iqc"
TEMPLATE_COMPLAINT_LINE = "complaint_line"
TEMPLATE_COMPLAINT_PQC = "complaint_pqc"
TEMPLATE_COMPLAINT_OQC = "complaint_oqc"
TEMPLATE_COMPLAINT_CUSTOMER = "complaint_customer"
TEMPLATE_INVENTORY_VERIFY = "inventory_verify"

# 研发文件下发变更（#31 / L34）：发起后五级签审
RD_FILE_CHANGE_APPROVAL_STEPS: Tuple[str, ...] = (
    "经理审核",
    "项目经理审核",
    "采购审核",
    "生产审核",
    "总监审核",
)

# 样品阶段钢网/SMT（L36）：经理 → 仓库 → 采购 → COB
SAMPLE_SMT_APPROVAL_STEPS: Tuple[str, ...] = (
    "经理审核",
    "仓库确认",
    "采购审核",
    "COB审核",
)

# 结构 3D / CAD / PDF（L42、L43）：组长审核 → 经理批准，8 小时
STRUCTURE_DRAWING_APPROVAL_STEPS: Tuple[str, ...] = (
    "组长审核",
    "经理批准",
)

# 质量投诉：按业务类型串行，岗位在审批中心绑定，不写具体人名
COMPLAINT_IQC_STEPS: Tuple[str, ...] = ("计划会签", "采购会签")
COMPLAINT_LINE_STEPS: Tuple[str, ...] = ("责任部门确认",)
COMPLAINT_PQC_STEPS: Tuple[str, ...] = ("生产确认", "责任经理", "PQC主管", "质量经理")
COMPLAINT_OQC_STEPS: Tuple[str, ...] = ("PQC分发", "责任主管", "PQC主管", "质量负责人")
COMPLAINT_CUSTOMER_STEPS: Tuple[str, ...] = ("责任人回复", "客服审核", "负责人批准")

# 库存验证返工：质量、制造、负责人、采购、计划
INVENTORY_VERIFY_STEPS: Tuple[str, ...] = ("质量", "制造", "负责人", "采购", "计划")


def build_serial_approval_flow(
    *,
    step_labels: Sequence[str],
    default_approver_type: str = "role",
    empty_approver_policy: str = "block",
    timeout_hours: int | None = 24,
    y_step: int = 140,
) -> Dict[str, Any]:
    """串行多级审批：开始 → N 个 approval → 结束。"""
    labels = [str(x).strip() for x in step_labels if str(x).strip()]
    if not labels:
        raise ValueError("串行审核模板至少需要一个审批节点标签")

    nodes: List[Dict[str, Any]] = [
        {
            "id": "start",
            "type": "start",
            "position": {"x": 250, "y": 40},
            "data": {"label": "开始", "layoutDirection": "vertical"},
        }
    ]
    edges: List[Dict[str, str]] = []
    prev = "start"
    for index, step_label in enumerate(labels, start=1):
        node_id = f"approval_{index}"
        data: Dict[str, Any] = {
            "label": step_label,
            "approverType": default_approver_type,
            "approvalType": "OR",
            "layoutDirection": "vertical",
            "emptyApproverPolicy": empty_approver_policy,
            "approverIds": [],
        }
        if timeout_hours is not None and int(timeout_hours) > 0:
            data["timeoutHours"] = int(timeout_hours)
        nodes.append(
            {
                "id": node_id,
                "type": "approval",
                "position": {"x": 250, "y": 40 + index * y_step},
                "data": data,
            }
        )
        edges.append({"source": prev, "target": node_id})
        prev = node_id
    nodes.append(
        {
            "id": "end",
            "type": "end",
            "position": {"x": 250, "y": 40 + (len(labels) + 1) * y_step},
            "data": {"label": "结束", "layoutDirection": "vertical"},
        }
    )
    edges.append({"source": prev, "target": "end"})
    return {"nodes": nodes, "edges": edges}


def build_simple_audit_flow(label: str) -> Dict[str, Any]:
    """单级审核：开始 → 直属主管 → 结束。"""
    title = (label or "审核").strip() or "审核"
    return {
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "position": {"x": 250, "y": 50},
                "data": {"label": "开始", "layoutDirection": "vertical"},
            },
            {
                "id": "approval_1",
                "type": "approval",
                "position": {"x": 250, "y": 200},
                "data": {
                    "label": title,
                    "approverType": "manager",
                    "approvalType": "OR",
                    "layoutDirection": "vertical",
                    "emptyApproverPolicy": "block",
                },
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 250, "y": 350},
                "data": {"label": "结束", "layoutDirection": "vertical"},
            },
        ],
        "edges": [
            {"source": "start", "target": "approval_1"},
            {"source": "approval_1", "target": "end"},
        ],
    }


def build_rd_file_change_flow() -> Dict[str, Any]:
    """研发文件下发变更内置链（五级签审，节点待租户绑定角色）。"""
    return build_serial_approval_flow(
        step_labels=RD_FILE_CHANGE_APPROVAL_STEPS,
        default_approver_type="role",
        empty_approver_policy="block",
        timeout_hours=24,
    )


def build_sample_smt_flow() -> Dict[str, Any]:
    """样品钢网/SMT 内置链（四级签审，节点待租户绑定角色）。"""
    return build_serial_approval_flow(
        step_labels=SAMPLE_SMT_APPROVAL_STEPS,
        default_approver_type="role",
        empty_approver_policy="block",
        timeout_hours=24,
    )


def build_structure_drawing_flow() -> Dict[str, Any]:
    """结构图纸内置链（组长、经理，8 小时）。"""
    return build_serial_approval_flow(
        step_labels=STRUCTURE_DRAWING_APPROVAL_STEPS,
        default_approver_type="role",
        empty_approver_policy="block",
        timeout_hours=8,
    )


def _build_role_serial(steps: Sequence[str]) -> Dict[str, Any]:
    """岗位串行。超时留给单据自己的期限字段，不在节点上再写小时数。"""
    return build_serial_approval_flow(
        step_labels=steps,
        default_approver_type="role",
        empty_approver_policy="block",
        timeout_hours=None,
    )


def build_flow_from_template(template: str, label: str) -> Dict[str, Any]:
    """按 manifest.audit.template 构图。"""
    code = str(template or "").strip().lower()
    role_chains = {
        TEMPLATE_COMPLAINT_IQC: COMPLAINT_IQC_STEPS,
        TEMPLATE_COMPLAINT_LINE: COMPLAINT_LINE_STEPS,
        TEMPLATE_COMPLAINT_PQC: COMPLAINT_PQC_STEPS,
        TEMPLATE_COMPLAINT_OQC: COMPLAINT_OQC_STEPS,
        TEMPLATE_COMPLAINT_CUSTOMER: COMPLAINT_CUSTOMER_STEPS,
        TEMPLATE_INVENTORY_VERIFY: INVENTORY_VERIFY_STEPS,
    }
    if code in role_chains:
        return _build_role_serial(role_chains[code])
    if code == TEMPLATE_STRUCTURE_DRAWING:
        return build_structure_drawing_flow()
    if code == TEMPLATE_SAMPLE_SMT:
        return build_sample_smt_flow()
    if code == TEMPLATE_RD_FILE_CHANGE:
        return build_rd_file_change_flow()
    if code in {TEMPLATE_SIMPLE, TEMPLATE_SME}:
        return build_simple_audit_flow(label)
    raise ValueError(f"未知审核流程模板: {template!r}")


def is_pristine_simple_default(nodes: Any, *, label: str) -> bool:
    """是否仍为「单级 manager」默认图（可安全按新模板升级）。"""
    if not isinstance(nodes, dict):
        return False
    node_list = nodes.get("nodes") or []
    if not isinstance(node_list, list):
        return False
    approvals = [n for n in node_list if isinstance(n, dict) and n.get("type") == "approval"]
    if len(approvals) != 1:
        return False
    data = approvals[0].get("data") if isinstance(approvals[0].get("data"), dict) else {}
    approver_type = str(data.get("approverType") or data.get("approver_type") or "").strip()
    node_label = str(data.get("label") or "").strip()
    expected = (label or "").strip()
    return approver_type == "manager" and (not expected or node_label == expected)
