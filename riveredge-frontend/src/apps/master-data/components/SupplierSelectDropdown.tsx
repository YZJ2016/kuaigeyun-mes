/**
 * 供应商选择下拉：快速新建 / 快速编辑 / 高级搜索
 *
 * 输入关键词走远端 display-search，避免仅预加载首页导致百名开外选不到（对齐 CustomerSelectDropdown）。
 * 选中时必须带回完整引用展示（含联系人），禁止因「不在本地缓存 / 高级搜索」而 onSupplierPick(null)。
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Form } from 'antd';
import { UniDropdown, type UniDropdownProps } from '../../../components/uni-dropdown';
import type { Supplier } from '../types/supply-chain';
import { SupplierFormModal } from './SupplierFormModal';
import { useCurrentUser } from '../../../hooks/useCurrentUser';
import {
  REFERENCE_DISPLAY_MAX_PAGE_SIZE,
  ReferenceDisplayAccessError,
  canReadReferenceResource,
  mapPartnerReferenceDisplayItem,
  referenceDisplayToIdOptions,
  resolveReferenceDisplay,
  searchReferenceDisplay,
  type ReferenceDisplayItem,
} from '../../../utils/referenceDisplay';

const INITIAL_PAGE_SIZE = 50;
const SEARCH_PAGE_SIZE = 100;
const SEARCH_DEBOUNCE_MS = 300;

function formatSupplierLabel(s: Supplier | Record<string, unknown>): string {
  const row = s as Record<string, unknown>;
  return (
    `${row.code ?? row.supplier_code ?? ''} - ${row.name ?? row.supplier_name ?? ''}`.trim() ||
    String(row.id ?? row.supplier_id)
  );
}

function getSupplierId(s: Supplier | Record<string, unknown>): number | undefined {
  const row = s as Record<string, unknown>;
  const id = row.id ?? row.supplier_id;
  return id != null ? Number(id) : undefined;
}

function mapDisplayItemsToSuppliers(items: ReferenceDisplayItem[]): Supplier[] {
  return items.map((item) => mapPartnerReferenceDisplayItem(item) as Supplier);
}

export type SupplierSelectDropdownProps = Omit<
  UniDropdownProps,
  'options' | 'quickCreate' | 'quickEdit' | 'advancedSearch' | 'loading'
> & {
  suppliers?: Supplier[];
  loading?: boolean;
  onSuppliersChange?: (suppliers: Supplier[]) => void;
  onSupplierPick?: (supplier: Supplier | null) => void;
  modalZIndex?: number;
  autoLoad?: boolean;
  hostResource?: string;
  /**
   * 与表单 supplier_name 快照字段联动，options 未就绪时用名称回显。
   * 设为 false 则不读取 Form。
   */
  snapshotNameField?: string | false;
};

export const SupplierSelectDropdown: React.FC<SupplierSelectDropdownProps> = ({
  suppliers: suppliersProp,
  loading: loadingProp,
  onSuppliersChange,
  onSupplierPick,
  modalZIndex,
  autoLoad = true,
  hostResource,
  snapshotNameField = 'supplier_name',
  onChange,
  value,
  ...rest
}) => {
  const { message: messageApi } = App.useApp();
  const currentUser = useCurrentUser();
  const form = Form.useFormInstance();
  const snapshotName =
    snapshotNameField === false ? undefined : Form.useWatch(snapshotNameField, form);
  const [internalSuppliers, setInternalSuppliers] = useState<Supplier[]>([]);
  const [internalLoading, setInternalLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [resolvedById, setResolvedById] = useState<Map<number, Supplier>>(new Map());
  const [resolvingId, setResolvingId] = useState<number | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editUuid, setEditUuid] = useState<string | null>(null);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchSeqRef = useRef(0);

  const suppliers = suppliersProp ?? internalSuppliers;
  const loading = (loadingProp ?? internalLoading) || searchLoading;

  const mergeSupplierList = useCallback((prev: Supplier[], supplier: Supplier) => {
    const matchKey = supplier.uuid ?? supplier.id;
    const idx = prev.findIndex((s) => (s.uuid ?? s.id) === matchKey);
    if (idx >= 0) {
      const next = [...prev];
      next[idx] = { ...next[idx], ...supplier };
      return next;
    }
    return [...prev, supplier];
  }, []);

  const applySupplierList = useCallback(
    (list: Supplier[]) => {
      if (suppliersProp == null) {
        setInternalSuppliers(list);
      }
      onSuppliersChange?.(list);
    },
    [onSuppliersChange, suppliersProp],
  );

  const fetchSuppliers = useCallback(
    async (keyword?: string, pageSize = INITIAL_PAGE_SIZE) => {
      const res = await searchReferenceDisplay({
        resource: 'master-data:supply-chain:supplier',
        hostResource,
        keyword: keyword?.trim() || undefined,
        pageSize,
      });
      return mapDisplayItemsToSuppliers(res.items);
    },
    [hostResource],
  );

  const refreshSuppliers = useCallback(async () => {
    setInternalLoading(true);
    try {
      const list = await fetchSuppliers(undefined, INITIAL_PAGE_SIZE);
      applySupplierList(list);
      return list;
    } catch (err) {
      if (err instanceof ReferenceDisplayAccessError) {
        messageApi.warning(err.message);
      }
      return [];
    } finally {
      setInternalLoading(false);
    }
  }, [applySupplierList, fetchSuppliers, messageApi]);

  useEffect(() => {
    if (autoLoad && suppliersProp == null) {
      void refreshSuppliers();
    }
  }, [autoLoad, refreshSuppliers, suppliersProp]);

  useEffect(
    () => () => {
      if (searchTimerRef.current) {
        clearTimeout(searchTimerRef.current);
      }
    },
    [],
  );

  const handleRemoteSearch = useCallback(
    (raw: string) => {
      if (suppliersProp != null) return;
      if (searchTimerRef.current) {
        clearTimeout(searchTimerRef.current);
      }
      const keyword = (raw || '').trim();
      searchTimerRef.current = setTimeout(() => {
        const seq = ++searchSeqRef.current;
        void (async () => {
          setSearchLoading(true);
          try {
            const list = keyword
              ? await fetchSuppliers(keyword, SEARCH_PAGE_SIZE)
              : await fetchSuppliers(undefined, INITIAL_PAGE_SIZE);
            if (seq !== searchSeqRef.current) return;
            applySupplierList(list);
          } catch (err) {
            if (seq !== searchSeqRef.current) return;
            if (err instanceof ReferenceDisplayAccessError) {
              messageApi.warning(err.message);
            }
          } finally {
            if (seq === searchSeqRef.current) {
              setSearchLoading(false);
            }
          }
        })();
      }, SEARCH_DEBOUNCE_MS);
    },
    [applySupplierList, fetchSuppliers, messageApi, suppliersProp],
  );

  const selectedId = value != null && value !== '' ? Number(value) : NaN;

  useEffect(() => {
    if (!Number.isFinite(selectedId)) return;
    if (suppliers.some((s) => getSupplierId(s) === selectedId)) return;
    if (resolvedById.has(selectedId)) return;

    let cancelled = false;
    setResolvingId(selectedId);
    void resolveReferenceDisplay({
      resource: 'master-data:supply-chain:supplier',
      recordIds: [selectedId],
      hostResource,
    })
      .then((items) => {
        if (cancelled || !items.length) return;
        const item = items[0];
        const id = item.id != null ? Number(item.id) : selectedId;
        setResolvedById((prev) => {
          if (prev.has(id)) return prev;
          const next = new Map(prev);
          next.set(id, mapPartnerReferenceDisplayItem(item) as Supplier);
          return next;
        });
      })
      .catch((err) => {
        if (err instanceof ReferenceDisplayAccessError) {
          messageApi.warning(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setResolvingId((cur) => (cur === selectedId ? null : cur));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedId, suppliers, hostResource, messageApi, resolvedById]);

  const allSuppliers = useMemo(() => {
    const seen = new Set<number>();
    const merged: Supplier[] = [];
    for (const s of suppliers) {
      const id = getSupplierId(s);
      if (id == null || seen.has(id)) continue;
      seen.add(id);
      merged.push(s);
    }
    for (const [id, s] of resolvedById) {
      if (!seen.has(id)) merged.push(s);
    }
    return merged;
  }, [suppliers, resolvedById]);

  const snapshotDisplayLabel = useMemo(() => {
    if (snapshotName == null || snapshotName === '') return undefined;
    const text = String(snapshotName).trim();
    return text || undefined;
  }, [snapshotName]);

  const options = useMemo(() => {
    const base = allSuppliers.map((s) => ({
      value: getSupplierId(s),
      label: formatSupplierLabel(s),
    }));
    if (!Number.isFinite(selectedId) || base.some((o) => o.value === selectedId)) {
      return base;
    }
    const resolved = resolvedById.get(selectedId);
    const label =
      (resolved ? formatSupplierLabel(resolved) : undefined) ??
      snapshotDisplayLabel ??
      (resolvingId === selectedId ? snapshotDisplayLabel ?? '\u00A0' : undefined);
    if (!label) return base;
    return [...base, { value: selectedId, label }];
  }, [allSuppliers, selectedId, resolvedById, snapshotDisplayLabel, resolvingId]);

  const handleChange = useCallback(
    (nextValue: number | undefined, option: unknown) => {
      onChange?.(nextValue, option as Parameters<NonNullable<UniDropdownProps['onChange']>>[1]);
      if (nextValue == null) {
        onSupplierPick?.(null);
        return;
      }
      const id = Number(nextValue);
      if (!Number.isFinite(id) || id <= 0) {
        onSupplierPick?.(null);
        return;
      }
      const cached = allSuppliers.find((x) => getSupplierId(x) === id);
      if (cached) {
        onSupplierPick?.(cached);
        return;
      }
      setResolvingId(id);
      void resolveReferenceDisplay({
        resource: 'master-data:supply-chain:supplier',
        recordIds: [id],
        hostResource,
      })
        .then((items) => {
          if (!items.length) {
            onSupplierPick?.(null);
            return;
          }
          const mapped = mapPartnerReferenceDisplayItem(items[0]) as Supplier;
          setResolvedById((prev) => {
            const next = new Map(prev);
            next.set(id, mapped);
            return next;
          });
          onSupplierPick?.(mapped);
        })
        .catch((err) => {
          if (err instanceof ReferenceDisplayAccessError) {
            messageApi.warning(err.message);
          }
          onSupplierPick?.(null);
        })
        .finally(() => {
          setResolvingId((cur) => (cur === id ? null : cur));
        });
    },
    [allSuppliers, hostResource, messageApi, onChange, onSupplierPick],
  );

  const openCreate = useCallback(() => {
    setEditUuid(null);
    setFormOpen(true);
  }, []);

  const openEdit = useCallback(
    (supplierId: unknown) => {
      const s = allSuppliers.find((x) => getSupplierId(x) === supplierId);
      const uuid = s?.uuid;
      if (!uuid) {
        messageApi.warning('无法编辑该供应商，请刷新供应商列表后重试');
        return;
      }
      setEditUuid(String(uuid));
      setFormOpen(true);
    },
    [allSuppliers, messageApi],
  );

  const handleSuccess = useCallback(
    (supplier: Supplier) => {
      const nextList = mergeSupplierList(allSuppliers, supplier);
      if (suppliersProp == null) {
        setInternalSuppliers(nextList);
      }
      onSuppliersChange?.(nextList);
      onSupplierPick?.(supplier);
      onChange?.(supplier.id, {
        value: supplier.id,
        label: formatSupplierLabel(supplier),
      });
      setFormOpen(false);
      setEditUuid(null);
    },
    [allSuppliers, mergeSupplierList, onChange, onSupplierPick, onSuppliersChange, suppliersProp],
  );

  const canManageSupplier = canReadReferenceResource(currentUser, 'master-data:supply-chain:supplier');

  const optionPending =
    Number.isFinite(selectedId) && !options.some((o) => o.value === selectedId);

  return (
    <>
      <UniDropdown
        {...rest}
        value={value}
        showSearch
        allowClear
        filterOption={false}
        onSearch={handleRemoteSearch}
        loading={loading || (optionPending && resolvingId === selectedId)}
        options={options}
        onChange={handleChange}
        quickCreate={
          canManageSupplier
            ? {
                label: '快速新建',
                onClick: openCreate,
              }
            : undefined
        }
        quickEdit={
          canManageSupplier
            ? {
                label: '编辑供应商',
                onEdit: openEdit,
              }
            : undefined
        }
        advancedSearch={{
          label: '高级搜索',
          fields: [{ name: 'keyword', label: '关键词' }],
          onSearch: async (values) => {
            try {
              const res = await searchReferenceDisplay({
                resource: 'master-data:supply-chain:supplier',
                hostResource,
                keyword: values.keyword,
                pageSize: REFERENCE_DISPLAY_MAX_PAGE_SIZE,
              });
              const mapped = mapDisplayItemsToSuppliers(res.items);
              let next = allSuppliers;
              for (const s of mapped) {
                next = mergeSupplierList(next, s);
              }
              if (suppliersProp == null) {
                setInternalSuppliers(mapped.length ? mapped : next);
              }
              onSuppliersChange?.(mapped.length ? mapped : next);
              return referenceDisplayToIdOptions(res.items);
            } catch (err) {
              if (err instanceof ReferenceDisplayAccessError) {
                messageApi.warning(err.message);
              }
              return [];
            }
          },
        }}
      />
      <SupplierFormModal
        open={formOpen}
        zIndex={modalZIndex}
        onClose={() => {
          setFormOpen(false);
          setEditUuid(null);
        }}
        editUuid={editUuid}
        onSuccess={handleSuccess}
      />
    </>
  );
};
