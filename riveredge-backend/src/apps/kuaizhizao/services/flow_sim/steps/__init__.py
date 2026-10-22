"""场景步骤适配器：一步对应现有业务 Service 调用面。"""

from apps.kuaizhizao.services.flow_sim.steps.mrp_push import MRP_PUSH_STEPS
from apps.kuaizhizao.services.flow_sim.steps.owo_fulfill import OWO_FULFILL_STEPS
from apps.kuaizhizao.services.flow_sim.steps.purchase_inbound import PURCHASE_INBOUND_STEPS
from apps.kuaizhizao.services.flow_sim.steps.ship import SHIP_STEPS
from apps.kuaizhizao.services.flow_sim.steps.wo_complete import WO_COMPLETE_STEPS

SCENARIO_STEP_CATALOG = {
    "mrp_push": MRP_PUSH_STEPS,
    "purchase_inbound": PURCHASE_INBOUND_STEPS,
    "wo_complete": WO_COMPLETE_STEPS,
    "owo_fulfill": OWO_FULFILL_STEPS,
    "ship": SHIP_STEPS,
}

__all__ = ["SCENARIO_STEP_CATALOG"]
