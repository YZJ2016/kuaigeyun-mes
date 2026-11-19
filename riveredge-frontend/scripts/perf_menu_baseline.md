# Top5 菜单性能基线（Network）

度量口径：浏览器 DevTools Network；同一租户暖库；记录关键 GET 的 Waiting (TTFB) + 总时长。

| 菜单 path | 进页关键 API | 详情关键 API | 重 Tab |
|-----------|-------------|-------------|--------|
| `/apps/kuaizhizao/sales-management/sales-orders` | `GET .../sales-orders` | `GET .../sales-orders/{id}` | `.../trace`、`.../attachment-center` |
| `/apps/kuaizhizao/production-execution/work-orders` | `GET .../work-orders` | `GET .../work-orders/{id}` | 同上（document-relations） |
| `/apps/kuaizhizao/purchase-management/purchase-orders` | `GET .../purchase-orders` | `GET .../purchase-orders/{id}` | 同上 |
| `/apps/kuaizhizao/sales-management/outbound` | 出库列表 API | 出库详情 | 同上 |
| `/apps/kuaizhizao/sales-management/quotations` | `GET .../quotations` | 报价详情 | 全链路（若有） |

## API 预算（暖库 p95 目标）

| 场景 | 预算 |
|------|------|
| 列表首屏 GET | &lt; 800ms |
| 详情 GET | &lt; 1500ms |
| trace / attachment-center（简单链） | &lt; 1500ms |
| trace / attachment-center（富链） | &lt; 3000ms |
| 进页 statistics（可延后） | 不阻塞列表首绘 |

## 复测日志

| 日期 | 结果 |
|------|------|
| 2026-11-10 | 误探 `8000`；实际健康检查 `8200/health=200`。鉴权采样脚本：`riveredge-backend/scripts/perf_top5_sample.py`（需 `E2E_PASSWORD` 等）。本会话环境变量未设 → **未写入新墙钟样本** |
| 2026-11-10 | 补测/门禁单测已绿；性能数值待设 `E2E_*` 后执行：`python scripts/perf_top5_sample.py` |
| 2026-11-10 | **墙钟样本（tenant=3，xiaofeng，BASE=8200，暖库第二轮）**：路径前缀已改为 `/api/v1/apps/kuaizhizao`。见下表「2026-11-10 墙钟」 |

## 2026-11-10 墙钟（`perf_top5_sample.py`，tenant=3）

预算：列表 &lt;800ms / 详情 &lt;1500ms。路径前缀 `/api/v1/apps/kuaizhizao`。

### 优化前（暖库）

| API | list | id | detail | 列表预算 | 详情预算 |
|-----|------|----|--------|----------|----------|
| sales-orders | 578ms / 200 | 4265 | 638ms / 200（`include_items`） | 过 | 过 |
| work-orders | 674ms / 200 | 57 | 457ms / 200 | 过 | 过 |
| purchase-orders | **820–917ms** / 200 | 1959 | **1262–1693ms** / 200 | **超** | **超** |
| sales-deliveries（outbound） | 401ms / 200 | 21 | 158ms / 200 | 过 | 过 |
| quotations | 343ms / 200 | 4 | 651ms / 200 | 过 | 过 |

### 优化后（PO：去读侧 sync + 列表/capabilities `gather`；暖库两轮）

| API | list | detail | 列表预算 | 详情预算 |
|-----|------|--------|----------|----------|
| purchase-orders | **506–672ms** | **414–549ms** | 过 | 过 |
| sales-orders | 525–979ms（抖动） | 551–1166ms | 偶超 / 过 | 过 |
| work-orders | 663–702ms | 396–459ms | 过 | 过 |
| sales-deliveries | 357–373ms | 168–171ms | 过 | 过 |
| quotations | 380–390ms | 802ms（重启后首轮曾冷启动 15s，勿当基线） | 过 | 过 |

PO 改前→改后：列表约 −30%～−45%，详情约 −60%～−75%。

## 已测样本（本机 2026-10-13，tenant≈18）

| API | 样例 | 改前 | 改后 |
|-----|------|------|------|
| sales-orders/{id} include_items | XS202610120002 | ~5338ms | ~1000ms |
| document-relations/.../trace | SO 1885 简单 | ~2000ms | ~900ms |
| document-relations/.../trace | SO 1873 富链 | ~10700ms | ~4600–6000ms |
| attachment-center | 随 trace | 略高于 trace | 接近 trace |

## 复测命令（后端墙钟，只读）

```powershell
$env:E2E_USERNAME='xiaofeng'
$env:E2E_PASSWORD='…'
$env:E2E_TENANT_ID='3'
cd D:\kuaigeyun-pro\kuaigeyun\riveredge-backend
$env:PYTHONPATH='D:\kuaigeyun-pro\kuaigeyun\riveredge-backend\src'
.\.venv\Scripts\python.exe scripts\perf_top5_sample.py
```

## Chunk 复测

```bash
cd riveredge-frontend && ANALYZE=1 npm run build:analyze
# 打开 dist/stats.html：确认 Top5 列表 chunk 未静态含 univer / libredwg / echarts / xlsx
```

## 自检清单

1. 进页：列表请求是否先于 statistics（`useDeferAfterPaint`；SO/WO/PO 已落地）
2. 详情：是否先开抽屉壳再取数；Tab 是否懒挂载（`DetailDrawerTemplate`）
3. 新建：报价/合同/SO 是否无 `loadMaterialFormReferenceList` 进页预拉
