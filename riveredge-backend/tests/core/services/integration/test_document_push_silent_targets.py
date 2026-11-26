"""无感外推：action_apis 按动作门禁，避免确认时误推 revoke 行。"""

from core.services.integration.document_push_silent import _target_would_auto_push_on_action


def test_confirm_only_fires_confirm_action_api_row():
    binding_triggers = ["confirm", "update", "withdraw", "unsubmit", "delete"]
    confirm_row = {
        "target_profile": "kingdee_im_saloutbill",
        "push_enabled": True,
        "push_mode": "auto",
        "trigger_actions": [],
        "action_apis": {"confirm": "uuid-add"},
    }
    update_row = {
        "target_profile": "kingdee_im_saloutbill",
        "push_enabled": True,
        "push_mode": "auto",
        "trigger_actions": [],
        "action_apis": {"update": "uuid-update"},
    }
    withdraw_row = {
        "target_profile": "kingdee_im_saloutbill",
        "push_enabled": True,
        "push_mode": "auto",
        "trigger_actions": [],
        "action_apis": {"withdraw": "uuid-unaudit"},
    }
    assert _target_would_auto_push_on_action(
        confirm_row, act="confirm", binding_triggers=binding_triggers
    )
    assert not _target_would_auto_push_on_action(
        update_row, act="confirm", binding_triggers=binding_triggers
    )
    assert not _target_would_auto_push_on_action(
        withdraw_row, act="confirm", binding_triggers=binding_triggers
    )
    assert _target_would_auto_push_on_action(
        update_row, act="update", binding_triggers=binding_triggers
    )


def test_empty_action_apis_falls_back_to_binding_triggers():
    row = {
        "target_profile": "kingdee_im_saloutbill",
        "push_enabled": True,
        "push_mode": "auto",
        "trigger_actions": [],
        "action_apis": {},
    }
    assert _target_would_auto_push_on_action(
        row, act="confirm", binding_triggers=["confirm"]
    )
    assert not _target_would_auto_push_on_action(
        row, act="confirm", binding_triggers=["withdraw"]
    )
