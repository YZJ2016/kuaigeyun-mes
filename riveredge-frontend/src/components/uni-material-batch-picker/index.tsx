/**
 * UniMaterialBatchPicker — 统一多选物料弹窗
 *
 * 内容区集成搜索 / 分类 / 来源筛选；选择规则对齐 UniPullQuery
 *（默认仅本页，筛选下已选预览，分段可开跨页）；请求序号防竞态。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Flex, Input, Modal, Select, Spin, Table, Tooltip, Tree, theme } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { DataNode } from 'antd/es/tree';
import { useTranslation } from 'react-i18next';
import {
  ReferenceDisplayAccessError,
  resolveReferenceDisplay,
  searchReferenceDisplay,
} from '../../utils/referenceDisplay';
import { referenceDisplayItemsToMaterials } from '../../utils/documentFormReferenceLoad';
import { materialGroupApi } from '../../apps/master-data/services/material';
import type { Material } from '../../apps/master-data/types/material';
import { SecureImage } from '../secure-image';
import { UniTableStackedPrimaryCell } from '../uni-table/stackedPrimaryColumn';
import type { UniMaterialBatchPickerProps } from './types';
import {
  buildMaterialBatchPickerGroupTree,
  fetchBatchMaterialHasBom,
  fetchBatchMaterialInventory,
  filterMaterialGroupTreeData,
  getMaterialField,
} from './utils';
import { apiRequest } from '../../services/api';
import {
  getMaterialSourceTypeLabel,
  getMaterialSourceTypeTagColor,
} from '../../apps/master-data/utils/materialSourceType';
import { MODAL_ISOLATE_POINTER_PROPS } from '../../utils/modalEventIsolation';
import { MarkerTag } from '../../constants/statusBadges';
import {
  UniPullQuerySelectionBar,
  type UniPullQueryCrossPageMode,
} from '../uni-pull-query';
import './index.less';

export type { UniMaterialBatchPickerProps } from './types';

const PAGE_SIZE = 20;
const DEFAULT_WIDTH = 1280;
const GROUP_PANEL_WIDTH = 312;
/** 与右侧表格 scroll.y 同一真源 */
const PICKER_TABLE_SCROLL_Y = 360;
/**
 * 左侧分组树滚动区高度：对齐右侧跨页选择条 + 表头 + 表体滚动 + 分页，使左右内容区下沿平齐
 */
const PICKER_LIST_VIEWPORT_HEIGHT = 52 + 12 + 39 + PICKER_TABLE_SCROLL_Y + 48;

function resolveMaterialImageFileUuid(raw: unknown): string | null {
  if (typeof raw === 'string') {
    const val = raw.trim();
    return /^[0-9a-fA-F-]{32,36}$/.test(val) ? val : null;
  }
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as { uuid?: unknown; uid?: unknown };
  const uuid = typeof obj.uuid === 'string' ? obj.uuid.trim() : '';
  if (/^[0-9a-fA-F-]{32,36}$/.test(uuid)) return uuid;
  const uid = typeof obj.uid === 'string' ? obj.uid.trim() : '';
  if (/^[0-9a-fA-F-]{32,36}$/.test(uid)) return uid;
  return null;
}

function materialPreviewLabel(record: Material): string {
  const rec = record as unknown as Record<string, unknown>;
  const code = String(getMaterialField(rec, 'mainCode') ?? record.code ?? '').trim();
  const name = String(record.name ?? '').trim();
  return code || name || '';
}

export const UniMaterialBatchPicker: React.FC<UniMaterialBatchPickerProps> = ({
  open,
  onCancel,
  onConfirm,
  zIndex,
  width = DEFAULT_WIDTH,
  hostResource,
  warehouseId,
  sourceType: fixedSourceType,
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const { token } = theme.useToken();
  const [searchDraft, setSearchDraft] = useState('');
  const [searchKeyword, setSearchKeyword] = useState('');
  const [groupId, setGroupId] = useState<number | undefined>(undefined);
  const [selectedGroupKey, setSelectedGroupKey] = useState<string>('all');
  const [sourceType, setSourceType] = useState<string | undefined>(undefined);
  const [groupTreeData, setGroupTreeData] = useState<DataNode[]>([]);
  const [groupTreeLoading, setGroupTreeLoading] = useState(false);
  const [groupTreeSearch, setGroupTreeSearch] = useState('');
  const [groupExpandedKeys, setGroupExpandedKeys] = useState<React.Key[]>(['all']);
  const [loading, setLoading] = useState(false);
  const [list, setList] = useState<Material[]>([]);
  const [page, setPage] = useState(1);
  const [totalHint, setTotalHint] = useState(0);
  const [selectedMap, setSelectedMap] = useState<Map<number, Material>>(() => new Map());
  const [crossPageMode, setCrossPageMode] = useState<UniPullQueryCrossPageMode>('page');
  const [bomMap, setBomMap] = useState<Record<number, boolean>>({});
  const [inventoryMap, setInventoryMap] = useState<Record<number, number>>({});
  const [indicatorsLoading, setIndicatorsLoading] = useState(false);

  const resolvedWarehouseId = useMemo(() => {
    if (warehouseId == null) return undefined;
    const n = Number(warehouseId);
    return Number.isFinite(n) && n > 0 ? n : undefined;
  }, [warehouseId]);

  const loadTree = useCallback(async () => {
    try {
      setGroupTreeLoading(true);
      const tree = await materialGroupApi.tree();
      setGroupTreeData(
        buildMaterialBatchPickerGroupTree(tree.items ?? [], t, {
          totalMaterialCount: tree.totalMaterialCount,
          ungroupedMaterialCount: tree.ungroupedMaterialCount,
        }),
      );
    } catch {
      setGroupTreeData([]);
      message.error(t('app.kuaizhizao.salesOrder.materialPickerLoadGroupFailed'));
    } finally {
      setGroupTreeLoading(false);
    }
  }, [message, t]);

  const fetchSeqRef = useRef(0);
  const indicatorSeqRef = useRef(0);

  const fetchList = useCallback(
    async (kw: string, gid: number | undefined, st: string | undefined, p: number) => {
      const seq = ++fetchSeqRef.current;
      setLoading(true);
      try {
        if (resolvedWarehouseId) {
          const balanceRes: any = await apiRequest('/apps/kuaizhizao/reports/inventory/material-balances', {
            method: 'GET',
            params: {
              warehouse_id: resolvedWarehouseId,
              include_zero_stock: false,
              keyword: kw.trim() || undefined,
              current: p,
              page_size: PAGE_SIZE,
            },
          });
          if (seq !== fetchSeqRef.current) return;
          const balanceRows = balanceRes?.items || balanceRes?.data || [];
          const materialIds = [
            ...new Set(
              (Array.isArray(balanceRows) ? balanceRows : [])
                .map((row: { material_id?: number }) => Number(row.material_id))
                .filter((id: number) => Number.isFinite(id) && id > 0),
            ),
          ] as number[];
          if (!materialIds.length) {
            setList([]);
            setTotalHint(Number(balanceRes?.total ?? 0) || 0);
            return;
          }
          const displayItems = await resolveReferenceDisplay({
            resource: 'master-data:material',
            recordIds: materialIds,
            hostResource,
          });
          if (seq !== fetchSeqRef.current) return;
          const order = new Map(materialIds.map((id, idx) => [id, idx]));
          let rows = [...referenceDisplayItemsToMaterials(displayItems)].sort(
            (a, b) => (order.get(Number(a.id)) ?? 0) - (order.get(Number(b.id)) ?? 0),
          );
          if (st) {
            rows = rows.filter(
              (m) => String((m as any).source_type ?? (m as any).sourceType ?? '') === String(st),
            );
          }
          if (gid != null) {
            rows = rows.filter(
              (m) => Number((m as any).group_id ?? (m as any).groupId) === Number(gid),
            );
          }
          setList(rows);
          setTotalHint(Number(balanceRes?.total ?? rows.length) || rows.length);
          return;
        }

        const res = await searchReferenceDisplay({
          resource: 'master-data:material',
          hostResource,
          keyword: kw.trim() || undefined,
          page: p,
          pageSize: PAGE_SIZE,
          groupId: gid,
          sourceType: st,
        });
        if (seq !== fetchSeqRef.current) return;
        const arr: Material[] = res.items.map((item) => {
          const rawImages = item.extra?.images;
          const images = Array.isArray(rawImages)
            ? (rawImages as Material['images'])
            : undefined;
          return {
            id: item.id as number,
            uuid: item.uuid ?? '',
            name: item.name ?? '',
            code: item.code ?? undefined,
            mainCode: (item.extra?.main_code as string) ?? item.code ?? '',
            specification: (item.extra?.specification as string) ?? undefined,
            baseUnit: (item.extra?.base_unit as string) ?? undefined,
            sourceType: (item.extra?.source_type as string) ?? undefined,
            groupId: item.extra?.group_id as number | undefined,
            images,
          } as Material;
        });
        setList(arr);
        setTotalHint(res.total);
      } catch (err) {
        if (seq !== fetchSeqRef.current) return;
        setList([]);
        setTotalHint(0);
        if (err instanceof ReferenceDisplayAccessError) {
          message.warning(err.message);
        } else {
          message.error(t('app.kuaizhizao.salesOrder.materialPickerLoadListFailed'));
        }
      } finally {
        if (seq === fetchSeqRef.current) {
          setLoading(false);
        }
      }
    },
    [hostResource, message, resolvedWarehouseId, t],
  );

  useEffect(() => {
    if (!open) return;
    void loadTree();
  }, [open, loadTree]);

  /** 打开弹窗：重置筛选与选中；关闭时取消在途请求 */
  useEffect(() => {
    if (!open) {
      fetchSeqRef.current += 1;
      indicatorSeqRef.current += 1;
      return;
    }
    setSearchDraft('');
    setSearchKeyword('');
    setGroupId(undefined);
    setSelectedGroupKey('all');
    setGroupTreeSearch('');
    setSourceType(fixedSourceType);
    setPage(1);
    setSelectedMap(new Map());
    setCrossPageMode('page');
  }, [open, fixedSourceType]);

  /** 筛选 / 分页变化时拉列表（open 纳入依赖，保证首次打开也会请求） */
  useEffect(() => {
    if (!open) return;
    void fetchList(searchKeyword, groupId, sourceType, page);
  }, [open, searchKeyword, groupId, sourceType, page, fetchList]);

  /** 当前页物料：批量拉取 BOM 与可用库存 */
  useEffect(() => {
    if (!open || list.length === 0) {
      setBomMap({});
      setInventoryMap({});
      setIndicatorsLoading(false);
      return;
    }
    const materialIds = list.map((m) => m.id).filter((id) => typeof id === 'number');
    if (materialIds.length === 0) return;

    const seq = ++indicatorSeqRef.current;
    setIndicatorsLoading(true);
    void Promise.all([
      fetchBatchMaterialHasBom(materialIds),
      fetchBatchMaterialInventory(materialIds, resolvedWarehouseId),
    ]).then(([bom, inventory]) => {
      if (seq !== indicatorSeqRef.current) return;
      setBomMap(bom);
      setInventoryMap(inventory);
      setIndicatorsLoading(false);
    });
  }, [open, list, resolvedWarehouseId]);

  const selectedCount = selectedMap.size;
  const selectedRowKeys = useMemo(() => Array.from(selectedMap.keys()), [selectedMap]);
  const previewItems = useMemo(
    () =>
      Array.from(selectedMap.values()).map((row) => ({
        key: row.id,
        label: materialPreviewLabel(row) || t('components.uniPullQuery.selectedUnlabeled'),
      })),
    [selectedMap, t],
  );

  const rowSelection = useMemo(
    () => ({
      selectedRowKeys,
      preserveSelectedRowKeys: crossPageMode === 'cross',
      onChange: (keys: React.Key[]) => {
        setSelectedMap((prev) => {
          const next = new Map<number, Material>();
          keys.forEach((k) => {
            const id = Number(k);
            const row = list.find((m) => m.id === id) ?? prev.get(id);
            if (row) next.set(id, row);
          });
          return next;
        });
      },
    }),
    [crossPageMode, list, selectedRowKeys],
  );

  const handleRemoveSelected = useCallback((key: React.Key) => {
    setSelectedMap((prev) => {
      const next = new Map(prev);
      next.delete(Number(key));
      return next;
    });
  }, []);

  const handleCrossPageModeChange = useCallback(
    (mode: UniPullQueryCrossPageMode) => {
      setCrossPageMode(mode);
      if (mode !== 'page') return;
      setSelectedMap((prev) => {
        const next = new Map<number, Material>();
        for (const row of list) {
          const existing = prev.get(row.id);
          if (existing) next.set(row.id, existing);
        }
        return next;
      });
    },
    [list],
  );

  const handlePageChange = useCallback(
    (nextPage: number) => {
      if (crossPageMode === 'page') {
        setSelectedMap(new Map());
      }
      setPage(nextPage);
    },
    [crossPageMode],
  );

  const clearSelection = useCallback(() => {
    setSelectedMap(new Map());
  }, []);

  const toggleMaterialRow = useCallback((record: Material) => {
    setSelectedMap((prev) => {
      const next = new Map(prev);
      if (next.has(record.id)) {
        next.delete(record.id);
      } else {
        next.set(record.id, record);
      }
      return next;
    });
  }, []);

  const handleMaterialRowClick = useCallback(
    (record: Material, event: React.MouseEvent<HTMLElement>) => {
      const target = event.target as HTMLElement;
      if (target.closest('.ant-checkbox-wrapper, .ant-checkbox, button, a, input, textarea, select')) {
        return;
      }
      toggleMaterialRow(record);
    },
    [toggleMaterialRow],
  );

  const columns: ColumnsType<Material> = useMemo(
    () => [
      {
        title: t('app.master-data.materials.productImage'),
        width: 64,
        render: (_, record) => {
          const images = (record as { images?: Array<{ uid?: string; uuid?: string } | string> }).images || [];
          if (images.length > 0) {
            const firstImage = images[0];
            const fileUuid = resolveMaterialImageFileUuid(firstImage);
            if (fileUuid) {
              return (
                <SecureImage fileUuid={fileUuid} width={40} height={40} lazyLoad thumbSize={64} />
              );
            }
          }
          return '-';
        },
      },
      {
        title: t('app.kuaizhizao.salesOrder.materialPickerMaterial'),
        ellipsis: true,
        render: (_, r) => {
          const rec = r as unknown as Record<string, unknown>;
          const code = String(
            getMaterialField(rec, 'mainCode') ?? (r as { code?: string }).code ?? '',
          );
          return (
            <UniTableStackedPrimaryCell
              primary={String((r as { name?: string }).name ?? '')}
              secondary={code}
            />
          );
        },
      },
      {
        title: t('app.kuaizhizao.salesOrder.materialPickerSpecModel'),
        width: 140,
        ellipsis: false,
        render: (_, r) => {
          const rec = r as unknown as Record<string, unknown>;
          const spec = String(getMaterialField(rec, 'specification') ?? '').trim();
          const model = String(getMaterialField(rec, 'model') ?? '').trim();
          if (!spec && !model) return '-';
          if (spec && model) {
            return (
              <UniTableStackedPrimaryCell
                primary={spec}
                secondary={model}
                secondaryCopyable={false}
              />
            );
          }
          return spec || model;
        },
      },
      {
        title: t('common.unit'),
        width: 64,
        render: (_, r) => {
          const val = String(getMaterialField(r as unknown as Record<string, unknown>, 'baseUnit') ?? '');
          return val || '-';
        },
      },
      {
        title: t('app.kuaizhizao.salesOrder.materialPickerHasBom'),
        width: 96,
        align: 'center',
        render: (_, r) => {
          const id = r.id;
          if (indicatorsLoading || !(id in bomMap)) {
            return (
              <span
                style={{
                  color: 'var(--ant-color-text-tertiary)',
                  fontSize: 12,
                  whiteSpace: 'nowrap',
                }}
              >
                —
              </span>
            );
          }
          const hasBom = bomMap[id];
          const text = hasBom
            ? t('app.kuaizhizao.salesOrder.materialPickerHasBomYes')
            : t('app.kuaizhizao.salesOrder.materialPickerHasBomNo');
          return (
            <Tooltip
              title={
                hasBom
                  ? t('app.kuaizhizao.salesOrder.materialPickerHasBomConfigured')
                  : t('app.kuaizhizao.salesOrder.materialPickerHasBomNone')
              }
            >
              <MarkerTag color={hasBom ? 'success' : 'default'} style={{ marginInlineEnd: 0 }}>
                {text}
              </MarkerTag>
            </Tooltip>
          );
        },
      },
      {
        title: t('app.kuaizhizao.salesOrder.materialPickerAvailableInventory'),
        width: 88,
        align: 'right',
        render: (_, r) => {
          const id = r.id;
          if (indicatorsLoading || !(id in inventoryMap)) {
            return (
              <span
                style={{
                  color: 'var(--ant-color-text-tertiary)',
                  fontSize: 12,
                  whiteSpace: 'nowrap',
                }}
              >
                —
              </span>
            );
          }
          const qty = inventoryMap[id];
          return qty ? Number(qty).toLocaleString() : '0';
        },
      },
      {
        title: t('app.kuaizhizao.salesOrder.materialPickerSourceType'),
        width: 88,
        render: (_, r) => {
          const rec = r as unknown as Record<string, unknown>;
          const val = (getMaterialField(rec, 'sourceType') ?? rec.source_type) as string;
          const label = getMaterialSourceTypeLabel(val, t);
          if (!val || label === '-') return '-';
          return (
            <MarkerTag color={getMaterialSourceTypeTagColor(val)} style={{ marginInlineEnd: 0 }}>
              {label}
            </MarkerTag>
          );
        },
      },
    ],
    [t, bomMap, inventoryMap, indicatorsLoading],
  );

  const handleOk = () => {
    if (selectedMap.size === 0) {
      message.warning(t('app.kuaizhizao.salesOrder.materialPickerNoneSelected'));
      return;
    }
    onConfirm(Array.from(selectedMap.values()));
    setSelectedMap(new Map());
    onCancel();
  };

  const handleCancel = () => {
    setSelectedMap(new Map());
    onCancel();
  };

  const popupContainer = (node: HTMLElement): HTMLElement =>
    (node.closest('.ant-modal-wrap') as HTMLElement | null) ?? document.body;

  const filteredGroupTreeData = useMemo(
    () => filterMaterialGroupTreeData(groupTreeData, groupTreeSearch),
    [groupTreeData, groupTreeSearch],
  );

  const collectGroupTreeKeys = useCallback((nodes: DataNode[]): React.Key[] => {
    const keys: React.Key[] = [];
    for (const node of nodes) {
      keys.push(node.key);
      if (node.children?.length) {
        keys.push(...collectGroupTreeKeys(node.children));
      }
    }
    return keys;
  }, []);

  useEffect(() => {
    if (!open || groupTreeData.length === 0) return;
    const kw = groupTreeSearch.trim();
    const roots =
      filteredGroupTreeData.length > 0 || !kw ? filteredGroupTreeData : groupTreeData;
    setGroupExpandedKeys(collectGroupTreeKeys(roots.length ? roots : groupTreeData));
  }, [open, groupTreeSearch, filteredGroupTreeData, groupTreeData, collectGroupTreeKeys]);

  const handleGroupTreeSelect = useCallback(
    (keys: React.Key[]) => {
      const key = keys[0] != null ? String(keys[0]) : 'all';
      setSelectedGroupKey(key);
      if (!key || key === 'all') {
        setGroupId(undefined);
      } else {
        const id = Number(key);
        setGroupId(Number.isFinite(id) && id > 0 ? id : undefined);
      }
      setPage(1);
      clearSelection();
    },
    [clearSelection],
  );

  const filterChromeStyle = useMemo(
    () => ({
      padding: 12,
      marginBottom: 12,
      background: token.colorFillAlter,
      borderRadius: token.borderRadius,
      border: `1px solid ${token.colorBorderSecondary}`,
      boxSizing: 'border-box' as const,
    }),
    [token],
  );

  const filterBar = (
    <div style={filterChromeStyle}>
      <Flex gap={8} align="center" style={{ width: '100%' }}>
        <Input.Search
          allowClear
          placeholder={t('app.kuaizhizao.common.materialBatchSearchPlaceholder')}
          style={{ flex: 1, minWidth: 0 }}
          value={searchDraft}
          onChange={(e) => setSearchDraft(e.target.value)}
          onSearch={(v) => {
            setSearchDraft(v);
            setSearchKeyword(v);
            setPage(1);
          }}
          onClear={() => {
            setSearchDraft('');
            setSearchKeyword('');
            setPage(1);
          }}
        />
        <Select
          allowClear={!fixedSourceType}
          disabled={Boolean(fixedSourceType)}
          placeholder={t('app.kuaizhizao.common.materialBatchSourcePlaceholder')}
          style={{ flex: 1, minWidth: 0 }}
          value={sourceType}
          onChange={(v) => {
            setSourceType(v);
            setPage(1);
            clearSelection();
          }}
          getPopupContainer={popupContainer}
          options={[
            { label: t('app.master-data.materialForm.sourceMake'), value: 'Make' },
            { label: t('app.master-data.materialForm.sourceBuy'), value: 'Buy' },
            { label: t('app.master-data.materialForm.sourceOutsource'), value: 'Outsource' },
            { label: t('app.master-data.materialForm.sourcePhantom'), value: 'Phantom' },
            { label: t('app.master-data.materialForm.sourceCustomerProvided'), value: 'CustomerProvided' },
            { label: t('app.master-data.materialForm.sourceGift'), value: 'Gift' },
            { label: t('app.master-data.materialForm.sourceService'), value: 'Service' },
          ]}
        />
      </Flex>
    </div>
  );

  return (
    <Modal
      title={t('app.kuaizhizao.salesOrder.materialPickerTitle')}
      styles={{ header: { marginBottom: 0 }, body: { paddingTop: 12 } }}
      open={open}
      onCancel={handleCancel}
      onOk={handleOk}
      zIndex={zIndex}
      width={width}
      destroyOnHidden
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      maskProps={{ ...MODAL_ISOLATE_POINTER_PROPS }}
      wrapProps={{ ...MODAL_ISOLATE_POINTER_PROPS }}
    >
      <div className="uni-material-batch-picker-body">
        <div
          className="uni-material-batch-picker-group-panel"
          style={{
            flex: `0 0 ${GROUP_PANEL_WIDTH}px`,
            width: GROUP_PANEL_WIDTH,
          }}
        >
          <div className="uni-material-batch-picker-group-column" style={filterChromeStyle}>
            <Input.Search
              allowClear
              placeholder={t('app.master-data.materials.searchGroup')}
              value={groupTreeSearch}
              onChange={(e) => setGroupTreeSearch(e.target.value)}
              onClear={() => setGroupTreeSearch('')}
              style={{ width: '100%', marginBottom: 12, flexShrink: 0 }}
            />
            <div
              className="uni-material-batch-picker-group-tree-scroll"
              style={{ height: PICKER_LIST_VIEWPORT_HEIGHT }}
            >
              <Spin spinning={groupTreeLoading} className="uni-material-batch-picker-group-spin">
                <Tree
                  className="uni-material-batch-picker-group-tree"
                  blockNode
                  showLine
                  selectedKeys={[selectedGroupKey]}
                  expandedKeys={groupExpandedKeys}
                  onExpand={(keys) => setGroupExpandedKeys(keys)}
                  onSelect={handleGroupTreeSelect}
                  treeData={
                    filteredGroupTreeData.length > 0 || !groupTreeSearch.trim()
                      ? filteredGroupTreeData
                      : groupTreeData
                  }
                  titleRender={(node) => {
                    const searchLabel = (node as DataNode & { searchLabel?: string }).searchLabel;
                    const display =
                      searchLabel ??
                      (typeof node.title === 'string' ? node.title : String(node.title ?? ''));
                    return <span className="material-group-tree-title-text">{display}</span>;
                  }}
                />
              </Spin>
            </div>
          </div>
        </div>
        <div className="uni-material-batch-picker-main">
          {filterBar}
          <UniPullQuerySelectionBar
            crossPageMode={crossPageMode}
            onCrossPageModeChange={handleCrossPageModeChange}
            items={previewItems}
            onRemove={handleRemoveSelected}
            onClear={clearSelection}
          />
          <Table<Material>
            className="uni-material-batch-picker-table"
            size="small"
            rowKey="id"
            loading={loading}
            tableLayout="fixed"
            columns={columns}
            dataSource={list}
            rowSelection={rowSelection}
            onRow={(record) => ({
              onClick: (event) => handleMaterialRowClick(record, event),
              style: { cursor: 'pointer' },
            })}
            pagination={{
              current: page,
              pageSize: PAGE_SIZE,
              total: totalHint,
              showSizeChanger: false,
              showLessItems: true,
              onChange: (p) => handlePageChange(p),
              itemRender: (_page, type, originalElement) => {
                if (type === 'jump-prev' || type === 'jump-next') {
                  return (
                    <a className="ant-pagination-item-link" style={{ whiteSpace: 'nowrap' }}>
                      …
                    </a>
                  );
                }
                return originalElement;
              },
              showTotal: (tot) => (
                <Flex gap={16} align="center" style={{ flexShrink: 0, whiteSpace: 'nowrap' }}>
                  <span style={{ color: token.colorTextSecondary, fontSize: 13 }}>
                    {t('app.kuaizhizao.salesOrder.materialPickerSelectedCount', { count: selectedCount })}
                  </span>
                  <span style={{ color: token.colorTextSecondary, fontSize: 13 }}>
                    {t('app.kuaizhizao.salesOrder.materialPickerPageTotal', { total: tot })}
                  </span>
                </Flex>
              ),
            }}
            scroll={{ y: PICKER_TABLE_SCROLL_Y }}
          />
        </div>
      </div>
    </Modal>
  );
};

export default UniMaterialBatchPicker;
