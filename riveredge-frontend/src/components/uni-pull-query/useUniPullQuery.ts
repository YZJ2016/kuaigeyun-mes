import { useCallback, useMemo, useRef, useState } from 'react';
import { isPullableScope } from './pullScope';
import { normalizePullKey, resolvePullRowKey } from './pullRowKey';
import type { UniPullQueryLoadParams, UseUniPullQueryOptions } from './types';

const DEFAULT_PAGE_SIZE = 20;

/**
 * 加载取单弹窗状态：分段范围/打开/搜索/日期/分页/选中/加载/提交。
 */
export function useUniPullQuery<T extends object>(options: UseUniPullQueryOptions<T>) {
  const {
    rowKey,
    loadData,
    onConfirm,
    onConfirmFailed,
    isRowDisabled,
    selectionType = 'radio',
    pageSize: defaultPageSize = DEFAULT_PAGE_SIZE,
    scopeOptions,
    defaultScope,
    onOpen,
    onClose,
    enableDateFilter = true,
  } = options;

  const resolvedDefaultScope =
    defaultScope ?? scopeOptions?.[0]?.value ?? 'all';

  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [searchDraft, setSearchDraft] = useState('');
  const [appliedKeyword, setAppliedKeyword] = useState('');
  const [dateDraftFrom, setDateDraftFrom] = useState<string | undefined>();
  const [dateDraftTo, setDateDraftTo] = useState<string | undefined>();
  const [appliedDateFrom, setAppliedDateFrom] = useState<string | undefined>();
  const [appliedDateTo, setAppliedDateTo] = useState<string | undefined>();
  const [scope, setScope] = useState(resolvedDefaultScope);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [dataSource, setDataSource] = useState<T[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const selectedRowsByKeyRef = useRef<Map<React.Key, T>>(new Map());
  const [selectedRowsVersion, setSelectedRowsVersion] = useState(0);

  const fetchSeqRef = useRef(0);
  const hasScope = scopeOptions != null && scopeOptions.length > 0;

  const buildLoadParams = useCallback(
    (
      keyword: string,
      nextPage: number,
      dates?: { from?: string; to?: string },
    ): UniPullQueryLoadParams => ({
      keyword,
      page: nextPage,
      pageSize: defaultPageSize,
      ...(hasScope ? { scope } : {}),
      ...(enableDateFilter && dates?.from ? { dateFrom: dates.from } : {}),
      ...(enableDateFilter && dates?.to ? { dateTo: dates.to } : {}),
    }),
    [defaultPageSize, enableDateFilter, hasScope, scope],
  );

  const activeDates = useMemo(
    () => ({ from: appliedDateFrom, to: appliedDateTo }),
    [appliedDateFrom, appliedDateTo],
  );

  const load = useCallback(
    async (params: UniPullQueryLoadParams) => {
      const seq = ++fetchSeqRef.current;
      setLoading(true);
      try {
        const result = await loadData(params);
        if (seq !== fetchSeqRef.current) {
          return;
        }
        let nextData = result.data;
        let nextTotal = result.total;
        if (hasScope && isRowDisabled && isPullableScope(params.scope)) {
          const visible = nextData.filter((row) => !isRowDisabled(row));
          if (visible.length !== nextData.length) {
            nextTotal = Math.max(0, nextTotal - (nextData.length - visible.length));
            nextData = visible;
          }
        }
        setDataSource(nextData);
        setTotal(nextTotal);
      } catch {
        if (seq !== fetchSeqRef.current) {
          return;
        }
        setDataSource([]);
        setTotal(0);
      } finally {
        if (seq === fetchSeqRef.current) {
          setLoading(false);
        }
      }
    },
    [hasScope, isRowDisabled, loadData],
  );

  const reloadCurrent = useCallback(() => {
    void load(buildLoadParams(appliedKeyword, page, activeDates));
  }, [activeDates, appliedKeyword, buildLoadParams, load, page]);

  const openModal = useCallback(() => {
    setSearchDraft('');
    setAppliedKeyword('');
    setDateDraftFrom(undefined);
    setDateDraftTo(undefined);
    setAppliedDateFrom(undefined);
    setAppliedDateTo(undefined);
    setScope(resolvedDefaultScope);
    setPage(1);
    setTotal(0);
    setSelectedRowKeys([]);
    selectedRowsByKeyRef.current = new Map();
    setSelectedRowsVersion((v) => v + 1);
    setDataSource([]);
    setOpen(true);
    onOpen?.();
    void load(buildLoadParams('', 1, {}));
  }, [buildLoadParams, load, onOpen, resolvedDefaultScope]);

  const closeModal = useCallback(() => {
    fetchSeqRef.current += 1;
    setOpen(false);
    onClose?.();
  }, [onClose]);

  const handleSearchApply = useCallback(
    (keyword: string) => {
      const normalized = keyword.trim();
      setSearchDraft(keyword);
      setAppliedKeyword(normalized);
      setPage(1);
      void load(buildLoadParams(normalized, 1, activeDates));
    },
    [activeDates, buildLoadParams, load],
  );

  const handleSearchClear = useCallback(() => {
    setSearchDraft('');
    setAppliedKeyword('');
    setPage(1);
    void load(buildLoadParams('', 1, activeDates));
  }, [activeDates, buildLoadParams, load]);

  const handleDateDraftChange = useCallback((from?: string, to?: string) => {
    setDateDraftFrom(from);
    setDateDraftTo(to);
  }, []);

  const handleDateApply = useCallback(
    (from?: string, to?: string) => {
      setAppliedDateFrom(from);
      setAppliedDateTo(to);
      setPage(1);
      setSelectedRowKeys([]);
      selectedRowsByKeyRef.current = new Map();
      setSelectedRowsVersion((v) => v + 1);
      void load(buildLoadParams(appliedKeyword, 1, { from, to }));
    },
    [appliedKeyword, buildLoadParams, load],
  );

  const handleDateClear = useCallback(() => {
    setDateDraftFrom(undefined);
    setDateDraftTo(undefined);
    setAppliedDateFrom(undefined);
    setAppliedDateTo(undefined);
    setPage(1);
    void load(buildLoadParams(appliedKeyword, 1, {}));
  }, [appliedKeyword, buildLoadParams, load]);

  const handleScopeChange = useCallback(
    (nextScope: string) => {
      setScope(nextScope);
      setPage(1);
      setSelectedRowKeys([]);
      selectedRowsByKeyRef.current = new Map();
      setSelectedRowsVersion((v) => v + 1);
      void load({
        keyword: appliedKeyword,
        page: 1,
        pageSize: defaultPageSize,
        ...(hasScope ? { scope: nextScope } : {}),
        ...(enableDateFilter && appliedDateFrom ? { dateFrom: appliedDateFrom } : {}),
        ...(enableDateFilter && appliedDateTo ? { dateTo: appliedDateTo } : {}),
      });
    },
    [
      appliedDateFrom,
      appliedDateTo,
      appliedKeyword,
      defaultPageSize,
      enableDateFilter,
      hasScope,
      load,
    ],
  );

  const handlePageChange = useCallback(
    (nextPage: number) => {
      setPage(nextPage);
      void load(buildLoadParams(appliedKeyword, nextPage, activeDates));
    },
    [activeDates, appliedKeyword, buildLoadParams, load],
  );

  const handleSelectedRowKeysChange = useCallback(
    (keys: React.Key[], rows: T[]) => {
      const normalizedKeys = keys.map(normalizePullKey);
      const next = new Map<string, T>();
      const keySet = new Set(normalizedKeys);
      for (const [existing, row] of selectedRowsByKeyRef.current.entries()) {
        const nk = normalizePullKey(existing);
        if (keySet.has(nk)) next.set(nk, row);
      }
      for (const row of rows) {
        next.set(resolvePullRowKey(row, rowKey), row);
      }
      // antd 有时只回 keys、rows 不全：用当前页 dataSource 补齐，避免「已选预览有、确认 rows 空」
      for (const key of normalizedKeys) {
        if (next.has(key)) continue;
        const fromPage = dataSource.find(
          (row) => resolvePullRowKey(row, rowKey) === key,
        );
        if (fromPage) next.set(key, fromPage);
      }
      selectedRowsByKeyRef.current = next as Map<React.Key, T>;
      setSelectedRowKeys(normalizedKeys);
      setSelectedRowsVersion((v) => v + 1);
    },
    [dataSource, rowKey],
  );

  const removeSelectedKey = useCallback(
    (key: React.Key) => {
      const target = normalizePullKey(key);
      const nextKeys = selectedRowKeys.filter((item) => normalizePullKey(item) !== target);
      const next = new Map(selectedRowsByKeyRef.current);
      for (const existing of [...next.keys()]) {
        if (normalizePullKey(existing) === target) next.delete(existing);
      }
      selectedRowsByKeyRef.current = next;
      setSelectedRowKeys(nextKeys);
      setSelectedRowsVersion((v) => v + 1);
    },
    [selectedRowKeys],
  );

  const selectedRows = useMemo(
    () =>
      selectedRowKeys
        .map((key) => {
          const nk = normalizePullKey(key);
          return (
            selectedRowsByKeyRef.current.get(nk)
            ?? selectedRowsByKeyRef.current.get(key)
            ?? dataSource.find((row) => resolvePullRowKey(row, rowKey) === nk)
          );
        })
        .filter((row): row is T => row != null),
    [dataSource, rowKey, selectedRowKeys, selectedRowsVersion],
  );

  const hasDisabledSelection = useMemo(
    () => selectedRows.some((row) => isRowDisabled?.(row)),
    [isRowDisabled, selectedRows],
  );

  const handleConfirm = useCallback(async () => {
    setConfirmLoading(true);
    try {
      const resolvedRows = selectedRowKeys
        .map((key) => {
          const nk = normalizePullKey(key);
          return (
            selectedRowsByKeyRef.current.get(nk)
            ?? selectedRowsByKeyRef.current.get(key)
            ?? dataSource.find((row) => resolvePullRowKey(row, rowKey) === nk)
          );
        })
        .filter((row): row is T => row != null);
      await onConfirm(selectedRowKeys, resolvedRows);
    } catch (error) {
      onConfirmFailed?.(error);
    } finally {
      setConfirmLoading(false);
    }
  }, [dataSource, onConfirm, onConfirmFailed, rowKey, selectedRowKeys]);

  const pullQuery = useMemo(
    () => ({
      searchDraft,
      setSearchDraft,
      appliedKeyword,
      dateDraftFrom,
      dateDraftTo,
      appliedDateFrom,
      appliedDateTo,
      enableDateFilter,
      handleSearchApply,
      handleSearchClear,
      handleDateDraftChange,
      handleDateApply,
      handleDateClear,
      scope,
      scopeOptions,
      handleScopeChange,
      page,
      pageSize: defaultPageSize,
      total,
      handlePageChange,
    }),
    [
      appliedDateFrom,
      appliedDateTo,
      appliedKeyword,
      dateDraftFrom,
      dateDraftTo,
      defaultPageSize,
      enableDateFilter,
      handleDateApply,
      handleDateClear,
      handleDateDraftChange,
      handlePageChange,
      handleScopeChange,
      handleSearchApply,
      handleSearchClear,
      page,
      scope,
      scopeOptions,
      searchDraft,
      total,
    ],
  );

  return {
    pullQuery,
    open,
    openModal,
    closeModal,
    loading,
    confirmLoading,
    searchDraft,
    setSearchDraft,
    appliedKeyword,
    dateDraftFrom,
    dateDraftTo,
    appliedDateFrom,
    appliedDateTo,
    handleDateDraftChange,
    handleDateApply,
    handleDateClear,
    enableDateFilter,
    scope,
    scopeOptions,
    handleScopeChange,
    page,
    pageSize: defaultPageSize,
    total,
    dataSource,
    selectedRowKeys,
    selectedRows,
    selectedCount: selectedRowKeys.length,
    reloadCurrent,
    handleSearchApply,
    handleSearchClear,
    handlePageChange,
    handleSelectedRowKeysChange,
    removeSelectedKey,
    handleConfirm,
    selectionType,
    isRowDisabled,
    hasDisabledSelection,
  };
}
