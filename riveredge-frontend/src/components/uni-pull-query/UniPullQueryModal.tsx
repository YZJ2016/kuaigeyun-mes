import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Flex, Modal, Table, theme } from 'antd';
import type { TableColumnsType } from 'antd/es/table';
import { MODAL_CONFIG } from '../layout-templates/constants';
import { UniPullQueryFilterBar } from './UniPullQueryFilterBar';
import {
  UniPullQuerySelectionBar,
  type UniPullQueryCrossPageMode,
} from './UniPullQuerySelectionBar';
import { defaultPullRowLabel } from './defaultPullRowLabel';
import { resolvePullQueryModalFilterProps } from './resolvePullQueryModalFilterProps';
import { normalizePullKey, resolvePullRowKey } from './pullRowKey';
import { DocumentLineTotalStockProvider } from '../../apps/kuaizhizao/components/DocumentLineTotalStock';
import {
  buildPullQueryCurrentStockColumn,
  pullRowMaterialId,
} from './pullQueryCurrentStockColumn.tsx';
import {
  columnsHavePullMaterialFields,
  pullQueryColumnDataIndex,
  resolvePullCurrentStockInsertIndex,
} from './pullQueryColumnUtils';
import type { UniPullQueryModalProps } from './types';

function shouldAppendPullCurrentStockColumn(columns: UniPullQueryModalProps<object>['columns']): boolean {
  if (!columns?.length) return false;
  if (columns.some((col) => pullQueryColumnDataIndex(col) === 'current_stock')) return false;
  return columnsHavePullMaterialFields(columns as TableColumnsType<unknown>);
}

function withPullCurrentStockColumn<T extends object>(
  columns: TableColumnsType<T>,
  t: (key: string, defaultValue?: string) => string,
): TableColumnsType<T> {
  const stockRender = buildPullQueryCurrentStockColumn<T>(t).render;
  const mapped = columns.map((col) =>
    pullQueryColumnDataIndex(col) === 'current_stock' ? { ...col, render: stockRender } : col,
  );
  if (!shouldAppendPullCurrentStockColumn(columns)) return mapped;
  const stockCol = buildPullQueryCurrentStockColumn<T>(t);
  const insertAt = resolvePullCurrentStockInsertIndex(mapped as TableColumnsType<unknown>);
  const next = [...mapped];
  next.splice(insertAt, 0, stockCol);
  return next;
}

/**
 * 统一加载取单弹窗：筛选栏 + 可选表格 + 分页 + 确认创建。
 * 筛选区样式对齐 UniMaterialBatchPicker。
 */
export function UniPullQueryModal<T extends object>({
  open,
  title,
  onCancel,
  onOk,
  rowKey,
  columns,
  dataSource,
  loading = false,
  confirmLoading = false,
  selectionType = 'radio',
  defaultCrossPageMode: defaultCrossPageModeProp,
  selectedRowKeys,
  onSelectedRowKeysChange,
  isRowDisabled,
  onDisabledRowClick,
  searchDraft,
  onSearchDraftChange,
  onSearchApply,
  onSearchClear,
  appliedKeyword,
  dateDraftFrom,
  dateDraftTo,
  onDateDraftChange,
  onDateApply,
  onDateClear,
  appliedDateFrom,
  appliedDateTo,
  enableDateFilter = true,
  searchPlaceholder,
  emptyText,
  emptySearchText,
  page,
  pageSize,
  total,
  onPageChange,
  scopeOptions,
  scope,
  onScopeChange,
  leading,
  filterExtra,
  filterExtraPlacement,
  okText,
  cancelText,
  okButtonProps,
  footer,
  width = MODAL_CONFIG.EXTRA_LARGE_WIDTH,
  zIndex,
  destroyOnHidden = true,
  afterOpenChange,
  alert,
  footerHint,
  tableScroll = { y: 360 },
  selectedRows,
  getRowLabel,
  embedded = false,
  hideFooter = false,
  pullQuery,
}: UniPullQueryModalProps<T>) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const filterProps = resolvePullQueryModalFilterProps(pullQuery, {
    searchDraft,
    onSearchDraftChange,
    onSearchApply,
    onSearchClear,
    appliedKeyword,
    dateDraftFrom,
    dateDraftTo,
    onDateDraftChange,
    onDateApply,
    onDateClear,
    appliedDateFrom,
    appliedDateTo,
    enableDateFilter,
    scope,
    scopeOptions,
    onScopeChange,
    page,
    pageSize,
    total,
    onPageChange,
  });
  const resolvedSearchDraft = filterProps.searchDraft ?? searchDraft;
  const resolvedOnSearchDraftChange = filterProps.onSearchDraftChange ?? onSearchDraftChange;
  const resolvedOnSearchApply = filterProps.onSearchApply ?? onSearchApply;
  const resolvedOnSearchClear = filterProps.onSearchClear ?? onSearchClear;
  const resolvedAppliedKeyword = filterProps.appliedKeyword ?? appliedKeyword;
  const resolvedPage = filterProps.page ?? page;
  const resolvedPageSize = filterProps.pageSize ?? pageSize;
  const resolvedTotal = filterProps.total ?? total;
  const resolvedOnPageChange = filterProps.onPageChange ?? onPageChange;
  const isMultiSelect = selectionType === 'checkbox';
  const resolvedDefaultCrossPageMode: UniPullQueryCrossPageMode =
    defaultCrossPageModeProp ?? (isMultiSelect ? 'cross' : 'page');
  const [crossPageMode, setCrossPageMode] = useState<UniPullQueryCrossPageMode>(
    resolvedDefaultCrossPageMode,
  );

  const resolvedSearchPlaceholder = String(
    searchPlaceholder ?? t('components.uniPullQuery.searchPlaceholder'),
  );
  const resolvedEmptyText = emptyText ?? t('components.uniPullQuery.empty');
  const resolvedEmptySearchText = emptySearchText ?? t('components.uniPullQuery.emptySearch');
  const resolvedOkText = okText ?? t('common.confirm');
  const resolvedCancelText = cancelText ?? t('common.cancel');
  const resolvedColumns = useMemo(
    () => withPullCurrentStockColumn(columns, t),
    [columns, t],
  );
  const stockMaterialIds = useMemo(
    () =>
      dataSource
        .map((row) => pullRowMaterialId(row))
        .filter((id): id is number => id != null),
    [dataSource],
  );
  const selectedCount = selectedRowKeys.length;
  const resolveLabel = getRowLabel ?? ((record: T) => defaultPullRowLabel(record));

  useEffect(() => {
    if (!open) {
      setCrossPageMode('page');
      return;
    }
    setCrossPageMode(resolvedDefaultCrossPageMode);
  }, [open, resolvedDefaultCrossPageMode]);

  const tableRowKey = useCallback(
    (record: T) => resolvePullRowKey(record, rowKey),
    [rowKey],
  );

  const previewItems = useMemo(() => {
    const rowByKey = new Map<string, T>();
    for (const row of selectedRows ?? []) {
      rowByKey.set(resolvePullRowKey(row, rowKey), row);
    }
    for (const row of dataSource) {
      const key = resolvePullRowKey(row, rowKey);
      if (!rowByKey.has(key)) rowByKey.set(key, row);
    }
    const unlabeled = t('components.uniPullQuery.selectedUnlabeled');
    return selectedRowKeys.map((key) => {
      const nk = normalizePullKey(key);
      const row = rowByKey.get(nk);
      const label = row ? String(resolveLabel(row) ?? '').trim() : '';
      return { key: nk, label: label || unlabeled };
    });
  }, [dataSource, resolveLabel, rowKey, selectedRowKeys, selectedRows, t]);

  const handleRemoveSelected = useCallback(
    (key: React.Key) => {
      const target = normalizePullKey(key);
      const nextKeys = selectedRowKeys.filter((item) => normalizePullKey(item) !== target);
      const nextKeySet = new Set(nextKeys.map((item) => normalizePullKey(item)));
      const nextRows = (selectedRows ?? dataSource).filter((row) =>
        nextKeySet.has(resolvePullRowKey(row, rowKey)),
      );
      onSelectedRowKeysChange(nextKeys, nextRows);
    },
    [dataSource, onSelectedRowKeysChange, rowKey, selectedRowKeys, selectedRows],
  );

  const handleClearSelected = useCallback(() => {
    onSelectedRowKeysChange([], []);
  }, [onSelectedRowKeysChange]);

  const handleCrossPageModeChange = useCallback(
    (mode: UniPullQueryCrossPageMode) => {
      setCrossPageMode(mode);
      if (mode !== 'page') return;
      const pageKeys = new Set(dataSource.map((row) => resolvePullRowKey(row, rowKey)));
      const nextKeys = selectedRowKeys.filter((key) => pageKeys.has(normalizePullKey(key)));
      if (nextKeys.length === selectedRowKeys.length) return;
      const nextRows = dataSource.filter((row) =>
        nextKeys.some((key) => normalizePullKey(key) === resolvePullRowKey(row, rowKey)),
      );
      onSelectedRowKeysChange(nextKeys, nextRows);
    },
    [dataSource, onSelectedRowKeysChange, rowKey, selectedRowKeys],
  );

  const handlePageChange = useCallback(
    (nextPage: number) => {
      if (isMultiSelect && crossPageMode === 'page') {
        onSelectedRowKeysChange([], []);
      }
      resolvedOnPageChange(nextPage);
    },
    [crossPageMode, isMultiSelect, onSelectedRowKeysChange, resolvedOnPageChange],
  );

  const handleRowClick = useCallback(
    (record: T, event: React.MouseEvent<HTMLElement>) => {
      const target = event.target as HTMLElement;
      const hitControl = Boolean(
        target.closest(
          '.ant-checkbox-wrapper, .ant-checkbox, .ant-radio-wrapper, .ant-radio, button, a, input, textarea, select',
        ),
      );
      if (isRowDisabled?.(record)) {
        // 点禁用单选/勾选或行体：均提示不可选原因（禁用控件本身不会触发 rowSelection.onChange）
        onDisabledRowClick?.(record);
        return;
      }
      if (hitControl) {
        return;
      }
      const key = resolvePullRowKey(record, rowKey);
      if (selectionType === 'radio') {
        onSelectedRowKeysChange([key], [record]);
        return;
      }
      const selected = selectedRowKeys.some((item) => normalizePullKey(item) === key);
      const nextKeys = selected
        ? selectedRowKeys.filter((k) => normalizePullKey(k) !== key)
        : [...selectedRowKeys.map(normalizePullKey), key];
      const nextKeySet = new Set(nextKeys.map(normalizePullKey));
      const nextRows = dataSource.filter((row) =>
        nextKeySet.has(resolvePullRowKey(row, rowKey)),
      );
      onSelectedRowKeysChange(nextKeys, nextRows);
    },
    [
      dataSource,
      isRowDisabled,
      onDisabledRowClick,
      onSelectedRowKeysChange,
      rowKey,
      selectedRowKeys,
      selectionType,
    ],
  );

  const inner = (
    <>
      {leading}
      <UniPullQueryFilterBar
        searchDraft={resolvedSearchDraft}
        onSearchDraftChange={resolvedOnSearchDraftChange}
        onSearchApply={resolvedOnSearchApply}
        onSearchClear={resolvedOnSearchClear}
        searchPlaceholder={resolvedSearchPlaceholder}
        scopeOptions={filterProps.scopeOptions ?? scopeOptions}
        scope={filterProps.scope ?? scope}
        onScopeChange={filterProps.onScopeChange ?? onScopeChange}
        filterExtra={filterExtra}
        filterExtraPlacement={filterExtraPlacement}
        enableDateFilter={filterProps.enableDateFilter ?? enableDateFilter}
        dateDraftFrom={filterProps.dateDraftFrom ?? dateDraftFrom}
        dateDraftTo={filterProps.dateDraftTo ?? dateDraftTo}
        onDateDraftChange={filterProps.onDateDraftChange ?? onDateDraftChange}
        onDateApply={filterProps.onDateApply ?? onDateApply}
        onDateClear={filterProps.onDateClear ?? onDateClear}
      />
      <UniPullQuerySelectionBar
        showCrossPage={isMultiSelect}
        crossPageMode={crossPageMode}
        onCrossPageModeChange={handleCrossPageModeChange}
        items={previewItems}
        onRemove={handleRemoveSelected}
        onClear={handleClearSelected}
      />
      <DocumentLineTotalStockProvider materialIds={stockMaterialIds}>
      <Table<T>
        rowKey={tableRowKey}
        loading={loading}
        size="small"
        tableLayout="fixed"
        columns={resolvedColumns}
        dataSource={dataSource}
        locale={{
          emptyText:
            resolvedAppliedKeyword.trim() ||
            filterProps.appliedDateFrom ||
            filterProps.appliedDateTo
              ? resolvedEmptySearchText
              : resolvedEmptyText,
        }}
        rowSelection={{
          type: selectionType,
          selectedRowKeys: selectedRowKeys.map(normalizePullKey),
          preserveSelectedRowKeys: !isMultiSelect || crossPageMode === 'cross',
          onChange: (keys, rows) => {
            onSelectedRowKeysChange(keys.map(normalizePullKey), rows);
          },
          getCheckboxProps: (record) => ({
            disabled: isRowDisabled?.(record) ?? false,
          }),
        }}
        onRow={(record) => ({
          onClick: (event) => handleRowClick(record, event),
          style: { cursor: isRowDisabled?.(record) ? 'not-allowed' : 'pointer' },
        })}
        pagination={{
          current: resolvedPage,
          pageSize: resolvedPageSize,
          total: resolvedTotal,
          showSizeChanger: false,
          onChange: (nextPage) => handlePageChange(nextPage),
          showTotal: (tot) => (
            <Flex gap={16} align="center">
              <span style={{ color: token.colorTextSecondary, fontSize: 13 }}>
                {t('components.uniPullQuery.selectedCount', { count: selectedCount })}
              </span>
              <span style={{ color: token.colorTextSecondary, fontSize: 13 }}>
                {t('components.uniPullQuery.pageTotal', { total: tot })}
              </span>
            </Flex>
          ),
        }}
        scroll={tableScroll}
      />
      </DocumentLineTotalStockProvider>
      {footerHint ? <div style={{ marginTop: 12 }}>{footerHint}</div> : null}
      {alert ? <div style={{ marginTop: 12 }}>{alert}</div> : null}
    </>
  );

  const defaultFooterButtons = (
    <Flex justify="flex-end" gap={8}>
      <Button onClick={onCancel}>{resolvedCancelText}</Button>
      <Button
        type="primary"
        onClick={() => void onOk()}
        loading={confirmLoading}
        {...okButtonProps}
        disabled={selectedCount === 0 || okButtonProps?.disabled}
      >
        {resolvedOkText}
      </Button>
    </Flex>
  );
  const resolvedFooter = footer !== undefined ? footer : defaultFooterButtons;

  if (embedded) {
    if (!open) return null;
    return (
      <div style={{ paddingTop: 4 }}>
        {inner}
        {hideFooter ? null : <div style={{ marginTop: 16 }}>{resolvedFooter}</div>}
      </div>
    );
  }

  return (
    <Modal
      title={title}
      styles={{ header: { marginBottom: 0 }, body: { paddingTop: 12 } }}
      style={{ maxWidth: 'calc(100vw - 32px)' }}
      open={open}
      width={width}
      zIndex={zIndex}
      onCancel={onCancel}
      footer={hideFooter ? null : resolvedFooter}
      destroyOnHidden={destroyOnHidden}
      afterOpenChange={afterOpenChange}
    >
      {inner}
    </Modal>
  );
}
