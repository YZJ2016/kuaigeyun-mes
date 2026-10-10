---
title: 备份下载走当前页面 origin
slug: data-backup-download-same-origin
status: delivered
domain: system
when: 下载备份 ERR_CONNECTION_REFUSED、Connection Failed、BASE_URL 与打开站点不一致
keywords:
  - data-backups
  - download-url
  - ERR_CONNECTION_REFUSED
  - BASE_URL
standard: download_url 只返回 /api/v1/... 相对路径；前端再剥绝对域名
---

# 备份下载走当前页面 origin

## 目标

浏览器点「下载备份」跟当前打开的站点同源，不跳到 `.env` 的 `BASE_URL`。

## 何时读 / 禁止另起

- 何时读：备份下载 Connection Failed / ERR_CONNECTION_REFUSED
- 禁止：再拼一套绝对下载域名或 blob 整包缓冲

## 标准入口

| 层 | 标准 |
|----|------|
| BE | `BackupDownloadService.build_download_url` 只返回相对路径 |
| FE | `getBackupDownloadUrl` → `toSameOriginBackupDownloadUrl` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 签发 | `riveredge-backend/src/core/services/system/backup_download_service.py` |
| 点击下载 | `riveredge-frontend/src/services/dataBackup.ts` |

## 踩坑

- 文件预览早已相对路径；备份下载仍拼 `BASE_URL`（如 `http://10.166.30.3:8080`），用户从 Vite / 别的 IP 打开页面就会拒连
- zip 不在当前 API 机器上是 404「备份文件已丢失」，不是 CONNECTION_REFUSED
