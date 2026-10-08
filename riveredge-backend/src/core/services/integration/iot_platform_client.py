"""ThingsBoard 4.4 / JetLinks Community 2.10.0 REST 适配。地址与认证来自 core。"""
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import httpx

from infra.exceptions.exceptions import ValidationError


class PlatformClient:
    def __init__(self, kind: str, config: dict):
        self.kind = kind
        self.config = config
        self.base_url = str(config.get("base_url") or "").rstrip("/")
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValidationError("平台 Base URL 无效")
        self.client = httpx.AsyncClient(timeout=20, follow_redirects=False)

    async def __aenter__(self):
        try:
            if self.kind == "thingsboard":
                token = self.config.get("token")
                if not token:
                    response = await self.client.post(f"{self.base_url}/api/auth/login", json={"username": self.config.get("username"), "password": self.config.get("password")})
                    response.raise_for_status()
                    token = response.json().get("token")
                if not token:
                    raise ValidationError("平台认证失败")
                self.client.headers["X-Authorization"] = f"Bearer {token}"
            elif self.kind == "jetlinks":
                token = self.config.get("token")
                if not token:
                    raise ValidationError("平台缺少 Access Token")
                self.client.headers["X-Access-Token"] = str(token)
            else:
                raise ValidationError("平台类型不支持")
            return self
        except Exception:
            await self.client.aclose()
            raise ValidationError("平台认证失败") from None

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def request(self, method: str, path: str, **kwargs):
        try:
            response = await self.client.request(method, f"{self.base_url}{path}", **kwargs)
            response.raise_for_status()
            result = response.json()
            if self.kind == "jetlinks" and isinstance(result, dict) and "status" in result:
                if result.get("status") != 200:
                    raise ValidationError("平台请求失败")
                return result.get("result")
            return result
        except Exception:
            raise ValidationError("平台请求失败（检查认证、权限和设备）") from None

    async def telemetry(self, external_device_id: str) -> list[dict]:
        device = quote(external_device_id, safe="")
        if self.kind == "thingsboard":
            data = await self.request("GET", f"/api/plugins/telemetry/DEVICE/{device}/values/timeseries")
            rows = [{"tag_key": key, "value": point.get("value"), "timestamp": point.get("ts")}
                    for key, points in data.items() for point in points] if isinstance(data, dict) else []
        else:
            data = await self.request("GET", f"/device/instance/{device}/properties/latest")
            rows = [{"tag_key": item.get("property"), "value": item.get("value"), "timestamp": item.get("timestamp")}
                    for item in data if isinstance(item, dict)] if isinstance(data, list) else []
        return [row for row in rows if row["tag_key"] and isinstance(row["timestamp"], (int, float)) and not isinstance(row["timestamp"], bool)]

    async def device_page(self, page: int = 0) -> dict:
        """分页读取设备目录，只返回绑定所需标识与名称，不返回原始平台资料。"""
        if self.kind == "thingsboard":
            result = await self.request("GET", "/api/tenant/devices", params={"page": page, "pageSize": 100})
        elif self.kind == "jetlinks":
            # JetLinks 官方 QueryDeviceRequest 使用 POST 查询，无写入副作用。
            result = await self.request("POST", "/device/instance/_query", json={"pageIndex": page, "pageSize": 100})
        else:
            raise ValidationError("该连接不支持平台设备查询")
        if not isinstance(result, dict) or not isinstance(result.get("data"), list):
            raise ValidationError("平台设备列表响应格式不正确")
        items = []
        seen = set()
        for row in result["data"]:
            if not isinstance(row, dict):
                continue
            raw_id = row.get("id")
            identifier = raw_id.get("id") if isinstance(raw_id, dict) else raw_id
            if not isinstance(identifier, str) or not identifier.strip() or len(identifier.strip()) > 100:
                continue
            identifier = identifier.strip()
            if identifier in seen:
                continue
            seen.add(identifier)
            name = row.get("name")
            items.append({"external_device_id": identifier, "name": name[:100] if isinstance(name, str) else identifier})
        total = result.get("totalElements") if self.kind == "thingsboard" else result.get("total")
        if isinstance(result.get("hasNext"), bool):
            has_more = result["hasNext"]
        elif isinstance(total, int) and not isinstance(total, bool):
            has_more = (page + 1) * 100 < total
        else:
            has_more = len(result["data"]) >= 100
        return {"items": items, "has_more": has_more}

    async def command(self, device_id: str, function_key: str, params: dict, command_uuid: str):
        device = quote(device_id, safe="")
        if self.kind == "thingsboard":
            return await self.request("POST", f"/api/rpc/twoway/{device}", json={"method": function_key, "params": params, "requestUUID": command_uuid})
        result = await self.request("POST", f"/device/instance/{device}/function/{quote(function_key, safe='')}", json=params)
        replies = result if isinstance(result, list) else [result]
        if any(isinstance(reply, dict) and reply.get("success") is False for reply in replies):
            raise ValidationError("平台设备指令执行失败")
        return result

    async def probe(self):
        path = "/api/auth/user" if self.kind == "thingsboard" else "/device/instance/_query?pageSize=1"
        await self.request("GET", path)
        return {"message": "平台认证及只读访问通过，未验证设备指令", "verification_level": "authenticated"}


def sample_timestamp(milliseconds: float) -> str:
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat()
