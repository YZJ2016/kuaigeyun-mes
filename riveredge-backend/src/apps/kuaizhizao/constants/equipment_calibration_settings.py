"""设备校准到期提醒租户配置键与默认值。"""

EQUIPMENT_CALIBRATION_REMINDER_SETTINGS_KEY = "kuaizhizao.equipment_calibration_reminder"

DEFAULT_CALIBRATION_REMINDER_ADVANCE_DAYS = 30
MIN_CALIBRATION_REMINDER_ADVANCE_DAYS = 1
MAX_CALIBRATION_REMINDER_ADVANCE_DAYS = 365

# 消息渠道（与配置中心 rule.channels 语义一致：internal / email / sms）
DEFAULT_CALIBRATION_NOTIFY_CHANNELS: tuple[str, ...] = ("internal",)
ALLOWED_CALIBRATION_NOTIFY_CHANNELS = frozenset({"internal", "email", "sms"})
