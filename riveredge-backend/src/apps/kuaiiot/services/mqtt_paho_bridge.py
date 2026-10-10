"""Windows 安全的 MQTT 客户端：paho 独立线程，避开 aiomqtt + ProactorEventLoop。"""

from __future__ import annotations

import asyncio
import os
import ssl
import threading
import uuid
from typing import Any, Optional

import paho.mqtt.client as mqtt
from loguru import logger


class IncomingMqttMessage:
    __slots__ = ("topic", "payload", "qos", "retain")

    def __init__(self, topic: str, payload: bytes, qos: int, retain: bool) -> None:
        self.topic = topic
        self.payload = payload
        self.qos = qos
        self.retain = retain


def _reason_failed(reason_code: Any) -> bool:
    if reason_code is None:
        return True
    if hasattr(reason_code, "is_failure"):
        return bool(reason_code.is_failure)
    try:
        return int(reason_code) != 0
    except (TypeError, ValueError):
        return True


def build_paho_client(settings: dict[str, Any], *, client_id: str) -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        protocol=mqtt.MQTTv311,
        clean_session=True,
    )
    username = settings.get("username")
    password = settings.get("password")
    if username:
        client.username_pw_set(str(username), None if password is None else str(password))
    if settings.get("use_tls"):
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    return client


def probe_broker_sync(settings: dict[str, Any], timeout: float = 8.0) -> bool:
    """同步探测 Broker（可在线程池调用）。"""
    done = threading.Event()
    result: dict[str, Any] = {"ok": False, "error": None}
    base = str(settings.get("client_id") or "kuaiiot")
    client_id = f"{base}-probe-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    client = build_paho_client(settings, client_id=client_id)

    def on_connect(_client, _userdata, _flags, reason_code, _properties=None):
        if _reason_failed(reason_code):
            result["error"] = str(reason_code)
            result["ok"] = False
        else:
            result["ok"] = True
        done.set()

    client.on_connect = on_connect
    client.loop_start()
    try:
        client.connect_async(settings["host"], int(settings["port"]), keepalive=30)
        if not done.wait(timeout):
            logger.warning("kuaiiot mqtt probe timeout host={}", settings.get("host"))
            return False
        if not result["ok"]:
            logger.warning("kuaiiot mqtt probe refused host={} rc={}", settings.get("host"), result["error"])
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("kuaiiot mqtt probe connect failed host={}: {}", settings.get("host"), exc)
        return False
    finally:
        try:
            client.on_connect = None
            client.disconnect()
        finally:
            client.loop_stop()


class PahoMqttSession:
    """paho loop_start 会话：把消息丢进 asyncio.Queue。"""

    def __init__(self, settings: dict[str, Any]) -> None:
        self.settings = settings
        self._client: Optional[mqtt.Client] = None
        self._stopping = False
        self._connected = False
        self._session_token = uuid.uuid4().hex

    def start(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        base = str(self.settings.get("client_id") or "kuaiiot-subscriber")
        # 每次会话唯一 ID，避免重连时与未释放的旧连接互踢
        client_id = f"{base}-{os.getpid()}-{self._session_token[:8]}"
        client = build_paho_client(self.settings, client_id=client_id)
        connected = threading.Event()
        connect_error: dict[str, str] = {}
        token = self._session_token

        def on_connect(_client, _userdata, _flags, reason_code, _properties=None):
            if self._stopping or token != self._session_token:
                return
            if _reason_failed(reason_code):
                connect_error["error"] = str(reason_code)
                connected.set()
                return
            self._connected = True
            _client.subscribe(self.settings["topic_filter"], qos=int(self.settings.get("qos") or 1))
            connected.set()
            logger.info(
                "kuaiiot mqtt paho connected client_id={} topic={}",
                client_id,
                self.settings.get("topic_filter"),
            )

        def on_disconnect(_client, _userdata, _flags, reason_code, _properties=None):
            # 连接完成前 / 主动 stop 时的 disconnect 忽略，避免误杀刚建好的会话
            if self._stopping or not self._connected or token != self._session_token:
                return
            self._connected = False
            logger.warning(
                "kuaiiot mqtt unexpected disconnect client_id={} rc={}",
                client_id,
                reason_code,
            )

            def _signal() -> None:
                if self._stopping or token != self._session_token:
                    return
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass

            loop.call_soon_threadsafe(_signal)

        def on_message(_client, _userdata, msg):
            if self._stopping or token != self._session_token:
                return
            incoming = IncomingMqttMessage(
                topic=str(msg.topic),
                payload=bytes(msg.payload or b""),
                qos=int(msg.qos or 0),
                retain=bool(msg.retain),
            )

            def _enqueue() -> None:
                if self._stopping or token != self._session_token:
                    return
                try:
                    queue.put_nowait(incoming)
                except asyncio.QueueFull:
                    logger.warning("kuaiiot mqtt inbound queue full, drop topic={}", incoming.topic)

            loop.call_soon_threadsafe(_enqueue)

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        client.loop_start()
        try:
            client.connect_async(self.settings["host"], int(self.settings["port"]), keepalive=60)
            if not connected.wait(15):
                raise TimeoutError("MQTT CONNACK 超时")
            if connect_error:
                raise ConnectionError(f"MQTT 连接被拒绝: {connect_error['error']}")
        except Exception:
            self._stopping = True
            client.on_connect = None
            client.on_disconnect = None
            client.on_message = None
            try:
                client.disconnect()
            finally:
                client.loop_stop()
            raise
        self._client = client

    def stop(self) -> None:
        self._stopping = True
        self._connected = False
        client = self._client
        self._client = None
        if not client:
            return
        client.on_connect = None
        client.on_disconnect = None
        client.on_message = None
        try:
            client.disconnect()
        finally:
            client.loop_stop()
