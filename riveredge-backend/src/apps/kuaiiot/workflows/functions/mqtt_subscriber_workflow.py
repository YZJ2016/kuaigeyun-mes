"""已注册的 MQTT 订阅对齐。不新注册 cron，不内置 Broker。

订阅主题读连接 config 的 topic。不读取口令，不连接 Broker。
"""

from apps.kuaiiot.services.mqtt_subscriber_service import MqttSubscriberService


async def run_kuaiiot_mqtt_reload(force_restart: bool = False) -> dict:
    return await MqttSubscriberService.reload(force_restart=force_restart)
