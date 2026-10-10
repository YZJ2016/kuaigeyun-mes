---
title: API 写防护
slug: api-write-protection
status: active
domain: principle
when: 新公开写接口、审核/下推/确认路径、新客户端渠道、开放 API
keywords:
  - X-Client-Channel
  - Idempotency-Key
  - interactive_client_guard
  - integration
  - OPEN_API
standard: riveredge-backend/docs/api-write-protection-ops.md
---

# API 写防护

- 写入：2026-10-03
- 同步规则：`.cursor/rules/api-write-protection.mdc`
- 运维手册：`riveredge-backend/docs/api-write-protection-ops.md`

## 原则

全站 `/api/*` 的 POST/PUT/PATCH/DELETE 受中间件保护：渠道白名单、写限流、幂等、integration IP、开放 API 账套鉴权。

## 动手前

1. 新公开写接口加入 `interactive_client_guard.py` 豁免名单（若确需公开）
2. 新「审核/下推/确认」路径应能被 `write_path_policy._CRITICAL_PATH_RE` 匹配
3. 官方新端渠道改 `client_channel.py` 的 `CLIENT_CHANNEL_DEVICE_LABELS`，不要伪造 UA
4. 写请求带 `X-Client-Channel`：`pc|station|android|ios|mobile_h5|miniprogram|integration`

## 禁止

- integration 渠道用普通用户 JWT 做开放 API 写
- 靠 UA 冒充官方渠道

## 关联

- `.cursor/rules/api-write-protection.mdc`
- `riveredge-backend/docs/api-write-protection-ops.md`
