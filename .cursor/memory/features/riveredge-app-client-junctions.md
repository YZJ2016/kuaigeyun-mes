---
title: 主仓 riveredge-app 联接到私仓终端
slug: riveredge-app-client-junctions
status: delivered
domain: deploy
when: 组装 riveredge-app、工位/手机/TV/小程序源码位置、mklink
keywords:
  - riveredge-app
  - mklink
  - riveredge-app-tv
  - riveredge-app-mini-program
  - kuaigeyun-client
standard: 主仓 riveredge-app 下四端一律 Junction 到 kuaigeyun-client；禁止在主仓再放一份源码拷贝
---

# 主仓 riveredge-app 联接到私仓终端

## 目标

开源主仓 `riveredge-app/`（gitignore）只作组装路径；真源在私仓 `kuaigeyun-client`。

## 何时读 / 禁止另起

- 何时读：本机缺工位脚本、Caddy H5 路径、TV/小程序要不要进私仓
- 禁止：在主仓 `riveredge-app/station` 等目录再拷一份源码；不要把 `web-dist` 再挂到 `riveredge-app/` 根下

## 标准入口

| 主仓路径 | 私仓真源 |
|----------|----------|
| `riveredge-app/mobile` | `kuaigeyun-client/riveredge-app-mobile` |
| `riveredge-app/station` | `kuaigeyun-client/riveredge-app-station` |
| `riveredge-app/tv` | `kuaigeyun-client/riveredge-app-tv` |
| `riveredge-app/mini-program` | `kuaigeyun-client/riveredge-app-mini-program` |

说明：`kuaigeyun-client/README.md`。Windows：`mklink /J`。

## 关键文件

| 角色 | 路径 |
|------|------|
| 私仓说明 | `kuaigeyun-client/README.md` |
| H5 构建 | `fast-deploy/build.mobile.web.sh` → `riveredge-app/mobile/web-dist` |
| 主仓忽略 | `kuaigeyun/.gitignore` `riveredge-app/` |

## 扩展点

新终端：私仓 `riveredge-app-<name>/` + 主仓 `riveredge-app/<name>` Junction，并改 README 表。

## 踩坑

- 主仓残留普通目录会盖住联接（工位曾缺 `scripts/`）
- Caddy 只吃 `mobile/web-dist`，不要在 `riveredge-app/web-dist` 再放一份
- 工位 Vite `@riveredge` 另需本机 `kuaigeyun-client/riveredge-frontend` 联接，与四端无关

## 关联

- `features/fast-deploy-scripts.md`
- `principles/reuse-existing-patterns.md`
