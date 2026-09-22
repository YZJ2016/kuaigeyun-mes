# 实时推送与 IM 契约

## 两种传输（可切换，业务不变）

| 方式 | 安装 | 运维 | 适用 |
|------|------|------|------|
| **python-socketio**（推荐） | `uv sync` 已有依赖，与 FastAPI **同进程** | 只跑后端即可 | 单机 / 常规部署 |
| **Centrifugo**（可选） | **独立 Go 容器/二进制**，不是 Python 库 | 多实例、百万连接 | 超大规模再考虑 |
| **noop** | 无 | 关开关 | 回退 HTTP 轮询 |

**Centrifugo 不能 `uv add`**，必须单独部署。默认推荐 **socketio**。

## 开关

| 环境变量 | 说明 | 默认 |
|----------|------|------|
| `REALTIME_BACKEND` | `noop` / **`socketio`** / `centrifugo` | **`socketio`** |
| `REALTIME_SOCKET_PATH` | Socket.IO 路径 | `/socket.io` |
| `CENTRIFUGO_*` | 仅 `centrifugo` 时需要 | — |

启用 socketio（无需额外服务）：

```
REALTIME_BACKEND=socketio
```

回退：`REALTIME_BACKEND=noop`。

## 频道 / 房间

- 用户私有：`personal:t{tenant_id}:u{user_id}`

## 事件

| event | 来源 |
|-------|------|
| `message.internal` | 站内信 |
| `approval.*` | 审批通知 |
| `ai.stream.start` / `ai.stream.done` | AI 流式 |
| `im.message` | IM |

## API

- `GET /api/v1/core/realtime/config` — `backend` / `socket_path` / `enabled`
- `GET /api/v1/core/realtime/token` — **仅 centrifugo**；socketio 用登录 access token
- `GET/POST /api/v1/personal/im/*` — IM（PG 真源）

## 前端

- `backend=socketio`：`socket.io-client` 连同源，`auth.token` = 现有 JWT
- `backend=centrifugo`：Centrifuge + `/realtime/token`
- 布局内 IM / 站内信 **短轮询保留** 作兜底（顶栏约 15s，打开会话约 5–10s）

## Caddy

`/socket.io` 与 `/api` 均反代到同一后端即可（模板已含 `/connection/*` 供 Centrifugo 可选）。
