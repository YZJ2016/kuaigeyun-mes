# 单公网 IP + 双机（Windows / Ubuntu）Caddy 反向代理

适用于：VMware ESXi（或同类虚拟化）上创建 **两台独立虚拟机**，外网只有 **一个公网 IP**，需要分别对外提供服务（例如一台 Windows 部署金蝶，一台 Ubuntu 部署 RiverEdge / 快格云制造）。

---

## 1. 结论速览

| 问题 | 结论 |
| --- | --- |
| 一个公网 IP，域名能分别「解析到两台服务器」吗？ | **不能**靠 DNS 指到两个不同公网地址。两条 A 记录也只能指向**同一个**公网 IP。 |
| 怎么分流到两台机？ | **反向代理（推荐）** 或 **端口转发**。 |
| 反向代理装哪台？ | 任意一台均可；公网 80/443 必须转到「装了边缘代理」的那台。 |
| Windows + Ubuntu 混用？ | **支持**，代理只转发 HTTP/HTTPS，与对端操作系统无关。 |
| Ubuntu 已按部署脚本装了 Caddy，Windows 再装一层？ | **可以**，少改脚本；内网多一跳，延迟通常可忽略。 |
| 边缘代理推荐软件 | **Caddy**（自动 HTTPS、配置短）；要图形界面可用 Nginx Proxy Manager。 |

---

## 2. 推荐架构

```text
互联网用户
    │
    ▼
公网 IP（路由器 / 防火墙）
    │  端口映射 80、443 → Windows 内网 IP
    ▼
Windows Server（边缘 Caddy）
    ├─ kd.example.com  ──► 本机金蝶（127.0.0.1:金蝶端口）
    └─ app.example.com ──► Ubuntu 内网 IP:本项目端口
                              │
                              ▼
                         Ubuntu Server
                         （按官方部署指南正常安装，可保留机内 Caddy）
```

要点：

1. DNS：`kd.example.com`、`app.example.com` 的 **A 记录都指向同一公网 IP**。
2. 路由器：**仅**把公网 80/443 转到 Windows（边缘 Caddy）。
3. Ubuntu：**不要**再做公网 80/443 映射，避免冲突。

---

## 3. Windows 安装 Caddy

1. 打开 [Caddy 下载页](https://caddyserver.com/download)，选择 **Windows amd64**。
2. 解压到例如 `C:\caddy\`，同目录创建 `Caddyfile`（见下一节）。
3. 管理员 PowerShell 试运行：

```powershell
cd C:\caddy
.\caddy.exe run --config C:\caddy\Caddyfile
```

4. 正式环境建议用 NSSM、WinSW 或计划任务，将 `caddy.exe` 注册为开机自启服务。

> Caddy **官方没有**完整图形设置端，以 `Caddyfile` 文本配置为主。若必须用网页点选配置，可改用 Nginx Proxy Manager（底层为 Nginx）。

---

## 4. Windows `Caddyfile` 示例

将域名、内网 IP、端口换成现场实际值。

```caddyfile
{
    admin localhost:2019
}

# ---------- 金蝶（本机 Windows）----------
kd.example.com {
    # 金蝶实际监听端口请按产品修改（常见 80 / 8080 / 443 / 自定义口）
    reverse_proxy 127.0.0.1:8080
}

# ---------- RiverEdge / 快格云制造（Ubuntu 虚拟机）----------
# 少改部署脚本：直接指到 Ubuntu 上已对外提供的 HTTP 端口（常见为本机 Caddy 的 80）
app.example.com {
    reverse_proxy 192.168.1.10:80
}

# 若 Ubuntu 侧仅提供 HTTPS，可改用（内网校验证书可关闭）：
# app.example.com {
#     reverse_proxy https://192.168.1.10 {
#         transport http {
#             tls_insecure_skip_verify
#         }
#     }
# }
```

### 必须修改的项

| 配置项 | 说明 |
| --- | --- |
| `kd.example.com` / `app.example.com` | 真实域名；DNS A 记录 → 公网 IP |
| `127.0.0.1:8080` | 金蝶在 Windows 上的监听地址与端口 |
| `192.168.1.10:80` | Ubuntu 内网 IP + RiverEdge 对外端口 |

### 金蝶侧建议

- Windows 防火墙放行金蝶端口（本机回环一般已可访问）。
- 若金蝶有「站点 URL / 外网地址」类配置，改为 `https://kd.example.com`，避免回调仍写内网 IP。

---

## 5. Ubuntu（本项目）怎么装

1. 按仓库 [`docs/部署指南.md`](./部署指南.md) 与 `fast-deploy` **正常安装**，尽量不改部署脚本。
2. 确认内网可访问，例如从 Windows 上：

```powershell
curl http://192.168.1.10/
```

3. Ubuntu 机内若已有 Caddy：可保留，但应只服务内网；**公网入口仍走 Windows 边缘 Caddy**。

### 双层代理与速度

```text
用户 → Windows Caddy → Ubuntu Caddy/应用 → 业务
```

同一台 ESXi、内网转发时，多一跳通常仅增加约 **1～数毫秒**，对页面与 API 体感影响可忽略。瓶颈一般在公网带宽、磁盘与应用本身，而不是这一跳。

更省事的 HTTPS 方式：证书只在 **Windows Caddy** 终结，内网用 `http://Ubuntu内网IP:端口` 转发。

---

## 6. 路由器 / 防火墙端口映射

| 外网端口 | 目标 |
| --- | --- |
| TCP 80 | Windows 内网 IP:80（Caddy） |
| TCP 443 | Windows 内网 IP:443（Caddy） |

不要把同一公网 80/443 再映射到 Ubuntu。

---

## 7. 备选：纯端口转发（不用反向代理）

适合临时联调；用户需带端口访问，体验较差。

示例：

| 用途 | 公网访问 | 映射到 |
| --- | --- | --- |
| Ubuntu / 本项目 | `https://域名`（443） | `Ubuntu内网:443` 或应用端口 |
| 金蝶 / Windows | `https://域名:8443` | `Windows内网:443` |

域名 A 记录仍只指向这一台公网 IP，靠**端口**区分机器。

正式对外站点更建议第 2～4 节的 **Caddy + 子域名（均走 443）**。

---

## 8. 上线检查清单

- [ ] 两台虚拟机均为静态内网 IP，且互通
- [ ] 两个（或以上）子域名 A 记录均指向同一公网 IP
- [ ] 公网 80/443 仅转发到 Windows（边缘 Caddy）
- [ ] Windows `Caddyfile` 中金蝶、Ubuntu 地址与端口正确
- [ ] 外网或手机流量访问：`https://kd.…`、`https://app.…` 分别打开正确系统
- [ ] 金蝶 / 本项目中的外网回调地址已改为对应 HTTPS 域名

---

## 9. 常见问题

**Q：边缘 Caddy 必须装在 Windows 吗？**  
A：不是。装在 Ubuntu 也可以，只要公网 80/443 转到「装边缘代理」的那台，再反代到另一台内网地址。本文按「Windows 跑金蝶、少改 Ubuntu 部署脚本」推荐装在 Windows。

**Q：Ubuntu 还要不要再装一层对外 Caddy？**  
A：不需要第二层**公网**入口。部署脚本自带的机内 Caddy 可保留，由 Windows 指过去即可。

**Q：Caddy 有图形界面吗？**  
A：官方无完整图形控制台。要 GUI 可用 Nginx Proxy Manager；要简单自动证书继续用 Caddy 文本配置。

---

## 10. 相关文档

- [RiverEdge 部署指南](./部署指南.md)
