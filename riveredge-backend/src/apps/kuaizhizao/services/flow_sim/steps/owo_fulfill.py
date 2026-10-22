"""场景 owo_fulfill：委外下达 → 补库 → 发料 → 收货。"""

OWO_FULFILL_STEPS = (
    {
        "key": "outsource",
        "service": "OutsourceMaterialIssueService|OutsourceMaterialReceiptService",
        "label": "委外发料收货",
    },
)
