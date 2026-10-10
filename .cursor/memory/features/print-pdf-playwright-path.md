---
title: 打印/追溯 PDF Playwright 浏览器路径
slug: print-pdf-playwright-path
status: active
keywords:
  - 打印 PDF
  - 追溯报告
  - Playwright
  - PLAYWRIGHT_BROWSERS_PATH
  - cursor-sandbox-cache
  - chromium-1243
updated: 2026-10-09
---

## 何时读

单据打印 PDF、追溯管理「导出追溯报告」失败：未找到 Chromium、路径在 `cursor-sandbox-cache`、或升级 Playwright 后 revision 对不上。

## 原因

1. Cursor 注入空的 `PLAYWRIGHT_BROWSERS_PATH=.../cursor-sandbox-cache/.../playwright`
2. `load_deploy_env` 的 `${VAR:-default}` 不会覆盖已有错误值
3. Playwright 大版本升级后浏览器目录需对应 revision（如 1.63 → `chromium-1243`）

## 标准入口

- 引擎回退：`riveredge-backend/src/core/services/pdf/playwright_engine.py` → `apply_usable_playwright_browsers_path`
- 打印子进程：`print_service._run_html_to_pdf_subprocess` 启动前同样调用
- 部署：`fast-deploy/lib/common.sh` `resolve_playwright_browsers_path` / `playwright_export_env`；`common.ps1` `Resolve-PlaywrightBrowsersPath` / `Set-PlaywrightEnv`
- Ubuntu 新版本宿主平台：同文件 `playwright_apply_host_platform`

## 禁止

- 手动 `playwright install` 时不要省略 `PLAYWRIGHT_BROWSERS_PATH`（须与 API 一致）
- 不要把 sandbox 缓存目录当正式浏览器路径

## 踩坑

- 系统 Temp `EPERM`：安装前设 `TEMP/TMP` 到 `.playwright-browsers/.tmp`，或依赖 `apply_writable_playwright_tmpdir`
- 国内下载慢：`PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright`（USE_MIRROR=1 时部署脚本默认）
- 静态 HTML 用 `set_content(wait_until=load)`，避免 `networkidle` 挂起
