---
title: 工位 API 走服务器设置
slug: station-settings-api-origin
status: delivered
domain: mes-station
when: npm run dev 工单不是设置里的服务器、ECONNREFUSED 127.0.0.1:8200、station_server_host
keywords:
  - station_server_host
  - X-Station-Api-Origin
  - resolveStationApiOrigin
  - useViteSameOriginApi
standard: DEV 下 /api 仍同源，Vite 按 X-Station-Api-Origin 转到设置 origin；打包后 rewrite 到设置 origin。
---

# 工位 API 走服务器设置

## 目标

工位工单/登录数据来自「服务器设置」，开发态不能写死 127.0.0.1:8200。

## 何时读 / 禁止另起

- 何时读：工位列表和 PC 派工不是同一套库
- 禁止：再给工位写第二套 axios baseURL

## 标准入口

| 层 | 标准 |
|----|------|
| 设置 | `setStationServerHost` / `app:setServerHost` |
| 请求 | `installStationApiProxy` + `X-Station-Api-Origin` |
| 开发 | `vite.config.ts` `stationSettingsApiProxy` |

## 踩坑

- `import.meta.env.DEV` 为 true 时原先 `rewriteUrlString` 不改写 URL，Vite `proxy.target` 固定 8200
- 改 vite.config 必须重启 `npm run dev`
