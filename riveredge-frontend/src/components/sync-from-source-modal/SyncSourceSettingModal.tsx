/**
 * 单个同步来源：接口/数据集选择与字段映射（嵌套弹窗）
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  App,
  Button,
  Checkbox,
  Modal,
  Select,
  Space,
  Spin,
  Table,
  Typography,
} from 'antd';
import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  PlusOutlined,
  SyncOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { SyncApiCallParamsPanel } from './SyncApiCallParamsPanel';
import { ThemedSegmented } from '../themed-segmented/ThemedSegmented';
import { getAPIByUuid, testAPI } from '../../services/apiManagement';
import {
  collapseMaterialRowsToUniqueUnits,
  collectRowColumnKeys,
  expandNestedDetailRows,
  extractKingdeeFieldKeys,
  filterPreviewColumns,
  formatSyncErrorMessage,
  isInactiveSyncSourceError,
  mergeSuggestedMapping,
  normalizeApiBodyToRows,
  normalizeImportedTargetToSource,
  resolveImportSourceColumn,
  suggestTargetToSourceMapping,
  SYNC_PREVIEW_ROW_LIMIT,
  withKingdeePreviewLimit,
} from './syncSourceUtils';
import { executeDatasetQuery } from '../../services/dataset';
import {
  ensureCosmicListRequestData,
  resolveBatchFillChunkSize,
  setByPath,
} from './syncCallParams';
import { prepareJsonRequestBody } from '../custom-fields/jsonFieldDateShortcuts';
import type { SyncFromSourceConfig, SyncSourceType, SyncTargetField } from './types';
import type { SyncSourceDraft } from './syncSourcesDraft';

function resolveSyncTargetLabel(field: SyncTargetField, t: (key: string) => string): string {
  if (field.label?.trim()) return field.label.trim();
  if (field.labelKey) return t(field.labelKey);
  return field.value;
}

/** 与「选择数据集」等最长标签对齐，避免切换来源类型时左列宽度变化 */
const SYNC_FIELD_LABEL_COLUMN_WIDTH = 88;

const SYNC_FIELD_GRID_STYLE: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: `${SYNC_FIELD_LABEL_COLUMN_WIDTH}px minmax(0, 1fr)`,
  columnGap: 12,
  rowGap: 12,
  alignItems: 'center',
  width: '100%',
};

const SYNC_FIELD_LABEL_STYLE: React.CSSProperties = {
  whiteSpace: 'nowrap',
  lineHeight: '32px',
};

/** 分段项等宽，避免「数据接口 / 数据集」字数不同导致 thumb 宽度跳动 */
const SYNC_SOURCE_KIND_SEGMENTED_WIDTH = 200;

const SYNC_FIELD_CONTROL_STYLE: React.CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 12,
  alignItems: 'center',
  minWidth: 0,
};

export interface SyncSourceSettingModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (draft: SyncSourceDraft) => void;
  draft: SyncSourceDraft;
  config: SyncFromSourceConfig;
  apiOptions: { label: string; value: string }[];
  datasetOptions: { label: string; value: string }[];
  loadingOptions: boolean;
  loadedAvailableFields: SyncTargetField[];
  zIndex?: number;
}

export const SyncSourceSettingModal: React.FC<SyncSourceSettingModalProps> = ({
  open,
  onClose,
  onSave,
  draft,
  config,
  apiOptions,
  datasetOptions,
  loadingOptions,
  loadedAvailableFields,
  zIndex,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();

  const [kind, setKind] = useState<SyncSourceType>(draft.kind);
  const [apiUuid, setApiUuid] = useState<string | undefined>(draft.api_uuid);
  const [datasetUuid, setDatasetUuid] = useState<string | undefined>(draft.dataset_uuid);
  const [targetToSource, setTargetToSource] = useState<Record<string, string>>(draft.targetToSource);
  const [previewRows, setPreviewRows] = useState<Record<string, unknown>[]>([]);
  /** 预览表展示列（可按 preferredKeys 收窄） */
  const [previewColumns, setPreviewColumns] = useState<string[]>([]);
  /** 映射下拉 / 自动匹配用的完整来源列（不得被预览表收窄裁掉） */
  const [sourceColumns, setSourceColumns] = useState<string[]>([]);
  const [executing, setExecuting] = useState(false);
  const [addedTargetKeys, setAddedTargetKeys] = useState<string[]>([]);
  const [pendingAddTargetKeys, setPendingAddTargetKeys] = useState<string[]>([]);
  const [requestBody, setRequestBody] = useState<Record<string, unknown> | undefined>(
    draft.request_body,
  );
  const [requestParams, setRequestParams] = useState<Record<string, unknown> | undefined>(
    draft.request_params,
  );
  const [persistRequestOverride, setPersistRequestOverride] = useState(
    Boolean(draft.persist_request_override),
  );
  const [batchFillPath, setBatchFillPath] = useState<string | undefined>(draft.batch_fill_path);
  const [batchFillValues, setBatchFillValues] = useState<string[] | undefined>(draft.batch_fill_values);
  const [editingCallParams, setEditingCallParams] = useState(false);
  const mappingFileInputRef = useRef<React.ElementRef<'input'> | null>(null);

  const defaultTargetFieldValues = useMemo(
    () => new Set(config.targetFields.map((field) => field.value)),
    [config.targetFields],
  );

  const fieldCatalogByValue = useMemo(() => {
    const map = new Map<string, SyncTargetField>();
    for (const field of config.targetFields) map.set(field.value, field);
    for (const field of config.availableTargetFields ?? []) {
      if (!map.has(field.value)) map.set(field.value, field);
    }
    for (const field of loadedAvailableFields) {
      if (!map.has(field.value)) map.set(field.value, field);
    }
    return map;
  }, [config.targetFields, config.availableTargetFields, loadedAvailableFields]);

  const visibleTargetFields = useMemo(() => {
    const fields = [...config.targetFields];
    const seen = new Set(fields.map((field) => field.value));
    for (const key of addedTargetKeys) {
      if (seen.has(key)) continue;
      const field = fieldCatalogByValue.get(key);
      if (field) {
        fields.push(field);
        seen.add(key);
      } else {
        fields.push({ value: key, label: key });
        seen.add(key);
      }
    }
    return fields;
  }, [config.targetFields, addedTargetKeys, fieldCatalogByValue]);

  const targetFieldValues = useMemo(
    () => visibleTargetFields.map((field) => field.value),
    [visibleTargetFields],
  );

  const addableTargetOptions = useMemo(() => {
    const visible = new Set(targetFieldValues);
    return [...fieldCatalogByValue.values()]
      .filter((field) => !visible.has(field.value))
      .map((field) => ({
        value: field.value,
        label:
          field.kind === 'custom'
            ? `${resolveSyncTargetLabel(field, t)} (${t('components.syncFromSource.customFieldTag')})`
            : resolveSyncTargetLabel(field, t),
      }))
      .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));
  }, [fieldCatalogByValue, targetFieldValues, t]);

  const supportsAddMoreFields =
    (config.availableTargetFields?.length ?? 0) > 0 ||
    Boolean(config.loadAvailableTargetFields) ||
    Boolean(config.customFieldTableName);

  const mergeAddedKeysFromMapping = useCallback(
    (mapping: Record<string, string>) => {
      const extras = Object.keys(mapping).filter((key) => !defaultTargetFieldValues.has(key));
      if (extras.length === 0) return;
      setAddedTargetKeys((prev) => {
        const next = new Set(prev);
        extras.forEach((key) => next.add(key));
        return [...next];
      });
    },
    [defaultTargetFieldValues],
  );

  const resetPreview = useCallback(() => {
    setPreviewRows([]);
    setPreviewColumns([]);
    setSourceColumns([]);
  }, []);

  useEffect(() => {
    if (!open) return;
    setKind(draft.kind);
    setApiUuid(draft.api_uuid);
    setDatasetUuid(draft.dataset_uuid);
    const mapping = config.sanitizeMapping
      ? config.sanitizeMapping({ ...draft.targetToSource })
      : { ...draft.targetToSource };
    setTargetToSource(mapping);
    setRequestBody(draft.request_body ? { ...draft.request_body } : undefined);
    setRequestParams(draft.request_params ? { ...draft.request_params } : undefined);
    setPersistRequestOverride(Boolean(draft.persist_request_override));
    setBatchFillPath(draft.batch_fill_path);
    setBatchFillValues(draft.batch_fill_values);
    setEditingCallParams(false);
    setPreviewRows([]);
    setPreviewColumns([]);
    setSourceColumns([]);
    setPendingAddTargetKeys([]);
    const extras = Object.keys(mapping).filter(
      (key) => !defaultTargetFieldValues.has(key),
    );
    setAddedTargetKeys(extras);
  }, [open, draft, defaultTargetFieldValues]);

  const handlePreview = async () => {
    if (kind === 'api' && !apiUuid) {
      messageApi.warning(t('components.syncFromSource.selectApiFirst'));
      return;
    }
    if (kind === 'dataset' && !datasetUuid) {
      messageApi.warning(t('components.syncFromSource.selectDatasetFirst'));
      return;
    }

    setExecuting(true);
    resetPreview();
    try {
      let rows: Record<string, unknown>[] = [];
      if (kind === 'api' && apiUuid) {
        const apiDetail = await getAPIByUuid(apiUuid);
        const apiMeta = {
          path: String(apiDetail.path || ''),
          code: String(apiDetail.code || ''),
        };
        const apiBody = ensureCosmicListRequestData(
          apiDetail.request_body &&
            typeof apiDetail.request_body === 'object' &&
            !Array.isArray(apiDetail.request_body)
            ? (apiDetail.request_body as Record<string, unknown>)
            : {},
          apiMeta,
        );
        // 合并后来源覆盖优先；发送前解析 __NOW__ 并去掉空日期（避免苍穹 DateTime NumberFormatException）
        // 保留空 data{}：与本地/生产同一苍穹 getList 源设定
        let baseBody = ensureCosmicListRequestData(
          prepareJsonRequestBody({
            ...apiBody,
            ...(requestBody ?? {}),
          }) as Record<string, unknown>,
          apiMeta,
        );
        const dataObj = baseBody.data;
        const warehouseNumberInBody =
          dataObj &&
          typeof dataObj === 'object' &&
          !Array.isArray(dataObj) &&
          typeof (dataObj as Record<string, unknown>).warehouse_number === 'string'
            ? String((dataObj as Record<string, unknown>).warehouse_number).trim()
            : '';
        const needsWarehouseNumber =
          apiMeta.path.toLowerCase().includes('bd_warelocareference') ||
          apiMeta.code.toLowerCase().includes('query_warelocareference');
        if (
          needsWarehouseNumber &&
          !batchFillValues?.length &&
          !warehouseNumberInBody
        ) {
          messageApi.warning(t('components.syncFromSource.warehouseNumberRequiredForPreview'));
          setExecuting(false);
          return;
        }
        if (batchFillPath && batchFillValues?.length) {
          const chunkSize = resolveBatchFillChunkSize(baseBody, batchFillPath, apiMeta);
          const slice = batchFillValues.slice(0, chunkSize);
          const fillScalar = chunkSize === 1 ? slice[0] : slice.join(',');
          baseBody = setByPath(baseBody, batchFillPath, fillScalar);
        }
        const previewBody = withKingdeePreviewLimit(baseBody, SYNC_PREVIEW_ROW_LIMIT);
        const preparedParams = requestParams
          ? (prepareJsonRequestBody(requestParams) as Record<string, unknown>)
          : undefined;
        const result = await testAPI(apiUuid, {
          ...(previewBody ? { body: previewBody } : {}),
          ...(preparedParams ? { params: preparedParams } : {}),
        });
        if (result.status_code < 200 || result.status_code >= 300) {
          const detail =
            typeof result.body === 'object' && result.body && 'error' in result.body
              ? String((result.body as Record<string, unknown>).error)
              : `HTTP ${result.status_code}`;
          throw new Error(detail);
        }
        const columnNames = extractKingdeeFieldKeys(baseBody);
        rows = normalizeApiBodyToRows(result.body, columnNames);
      } else if (kind === 'dataset' && datasetUuid) {
        const res = await executeDatasetQuery(datasetUuid, {
          limit: SYNC_PREVIEW_ROW_LIMIT,
          offset: 0,
        });
        if (!res.success) throw new Error(res.error || t('components.syncFromSource.queryFailed'));
        rows = expandNestedDetailRows(
          ((res.data || []) as Record<string, unknown>[]),
        );
      }

      if (config.collapsePreviewToUniqueUnits) {
        rows = collapseMaterialRowsToUniqueUnits(rows);
      }
      rows = rows.slice(0, SYNC_PREVIEW_ROW_LIMIT);

      const allColumns = collectRowColumnKeys(rows);
      const displayColumns = filterPreviewColumns(
        allColumns,
        config.previewPreferredSourceKeys,
        Object.values(targetToSource),
      );
      const previewData =
        displayColumns.length && displayColumns.length < allColumns.length
          ? rows.map((row) => {
              const slim: Record<string, unknown> = {};
              for (const key of displayColumns) {
                if (key in row) slim[key] = row[key];
              }
              return slim;
            })
          : rows;
      setPreviewRows(previewData);
      setPreviewColumns(displayColumns);
      // 映射候选必须用全量列：收窄后税率/行备注等未映射列会从自动匹配与下拉里消失
      setSourceColumns(allColumns);

      if (rows.length === 0 || allColumns.length === 0) {
        messageApi.warning(t('components.syncFromSource.previewEmptyRows'));
      } else {
        const merged = mergeSuggestedMapping(
          allColumns,
          targetFieldValues,
          targetToSource,
          config.targetAliases,
        );
        mergeAddedKeysFromMapping(merged);
        setTargetToSource(merged);
        messageApi.success(t('components.syncFromSource.previewOk', { count: rows.length }));
      }
    } catch (error: unknown) {
      const detail = formatSyncErrorMessage(error, t('components.syncFromSource.queryFailed'));
      if (isInactiveSyncSourceError(error)) {
        messageApi.info(detail);
      } else {
        messageApi.error(detail);
      }
    } finally {
      setExecuting(false);
    }
  };

  const handleAutoMatch = useCallback(() => {
    // 预览列 + 当前行键并集，避免 sourceColumns 异常偏少时整表只命中 1 列
    const columnsForMatch = Array.from(
      new Set([...sourceColumns, ...collectRowColumnKeys(previewRows)]),
    );
    if (columnsForMatch.length === 0) {
      messageApi.warning(t('components.syncFromSource.autoMatchNeedPreview'));
      return;
    }
    // 整表重算：只保留本次建议命中；旧映射全部丢掉，配不上的清空
    const suggested = suggestTargetToSourceMapping(
      columnsForMatch,
      targetFieldValues,
      config.targetAliases,
    );
    mergeAddedKeysFromMapping(suggested);
    setTargetToSource(suggested);
    const hitCount = Object.keys(suggested).length;
    if (hitCount <= 1) {
      // 列很少或只有 status 等壳字段：多半是预览没拉到业务 rows
      const looksSparse =
        columnsForMatch.length <= 8 ||
        columnsForMatch.every((col) =>
          /^(status|success|error|errorcode|message|msg|code|data_)/i.test(col),
        );
      messageApi.warning(
        looksSparse
          ? t('components.syncFromSource.autoMatchSparsePreview')
          : t('components.syncFromSource.autoMatchAliasMiss', {
              columns: columnsForMatch.length,
            }),
      );
    } else {
      messageApi.success(t('components.syncFromSource.autoMatchDone', { count: hitCount }));
    }
  }, [
    config.targetAliases,
    mergeAddedKeysFromMapping,
    messageApi,
    previewRows,
    sourceColumns,
    t,
    targetFieldValues,
  ]);

  const handleExportMapping = useCallback(() => {
    if (Object.keys(targetToSource).length === 0) {
      messageApi.warning(t('components.syncFromSource.mappingExportEmpty'));
      return;
    }
    const payload = {
      version: 1,
      type: 'riveredge-sync-field-mapping',
      orientation: 'target_to_source',
      exported_at: new Date().toISOString(),
      mapping: targetToSource,
    };
    const blob = new window.Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    const fileName =
      (config.mappingExportFileName || '').trim() || 'sync-field-mapping.json';
    anchor.download = fileName.endsWith('.json') ? fileName : `${fileName}.json`;
    anchor.click();
    window.URL.revokeObjectURL(url);
    messageApi.success(t('components.syncFromSource.mappingExportSuccess'));
  }, [config.mappingExportFileName, messageApi, t, targetToSource]);

  const handleImportMapping = useCallback(
    async (event: React.ChangeEvent<React.ElementRef<'input'>>) => {
      const file = event.target.files?.[0];
      event.target.value = '';
      if (!file) return;
      try {
        const parsed: unknown = JSON.parse(await file.text());
        const rawMapping =
          parsed && typeof parsed === 'object' && 'mapping' in parsed
            ? (parsed as { mapping?: unknown }).mapping
            : parsed;
        if (!rawMapping || typeof rawMapping !== 'object' || Array.isArray(rawMapping)) {
          throw new Error('invalid');
        }
        const rawEntries = Object.fromEntries(
          Object.entries(rawMapping as Record<string, unknown>).filter(
            ([key, value]) =>
              typeof key === 'string' &&
              key.trim() &&
              typeof value === 'string' &&
              String(value).trim(),
          ),
        ) as Record<string, string>;
        if (Object.keys(rawEntries).length === 0) throw new Error('empty');

        const imported = normalizeImportedTargetToSource(rawEntries, targetFieldValues);
        if (Object.keys(imported).length === 0) throw new Error('empty');

        // 有预览列时宽松对齐列名；无预览则原样导入（保存后下次拉取仍可用）
        const usable: Record<string, string> = {};
        for (const [target, source] of Object.entries(imported)) {
          const resolved = resolveImportSourceColumn(source, sourceColumns);
          if (resolved) usable[target] = resolved;
        }
        if (Object.keys(usable).length === 0) throw new Error('unmatched');
        mergeAddedKeysFromMapping(usable);
        setTargetToSource((prev) => ({ ...prev, ...usable }));
        messageApi.success(
          t('components.syncFromSource.mappingImportSuccess', { count: Object.keys(usable).length }),
        );
      } catch {
        messageApi.error(t('components.syncFromSource.mappingImportFailed'));
      }
    },
    [mergeAddedKeysFromMapping, messageApi, sourceColumns, t, targetFieldValues],
  );

  const validateAndSave = async () => {
    const mapping = config.sanitizeMapping
      ? config.sanitizeMapping({ ...targetToSource })
      : targetToSource;
    if (mapping !== targetToSource) {
      setTargetToSource(mapping);
    }
    let validateCtx:
      | { connectionType?: string | null; apiPath?: string | null; apiCode?: string | null }
      | undefined;
    if (kind === 'api' && apiUuid && config.validateMapping) {
      try {
        const apiDetail = await getAPIByUuid(apiUuid);
        validateCtx = {
          connectionType: apiDetail.connection_type,
          apiPath: apiDetail.path,
          apiCode: apiDetail.code,
        };
      } catch (e: unknown) {
        const detail =
          e && typeof e === 'object' && 'message' in e
            ? String((e as { message?: unknown }).message || '')
            : '';
        messageApi.error(detail || t('components.syncFromSource.loadApiMetaFailed'));
        return;
      }
    }
    const mappingError = config.validateMapping
      ? config.validateMapping(mapping, t, validateCtx)
      : (() => {
          for (const required of config.requiredTargets) {
            if (!mapping[required]) {
              const field =
                fieldCatalogByValue.get(required) ||
                config.targetFields.find((item) => item.value === required);
              return t('components.syncFromSource.mappingRequired', {
                field: field ? resolveSyncTargetLabel(field, t) : required,
              });
            }
          }
          return null;
        })();
    if (mappingError) {
      messageApi.warning(mappingError);
      return;
    }
    if (kind === 'api' && !apiUuid) {
      messageApi.warning(t('components.syncFromSource.selectApiFirst'));
      return;
    }
    if (kind === 'dataset' && !datasetUuid) {
      messageApi.warning(t('components.syncFromSource.selectDatasetFirst'));
      return;
    }
    onSave({
      ...draft,
      kind,
      api_uuid: kind === 'api' ? apiUuid : undefined,
      dataset_uuid: kind === 'dataset' ? datasetUuid : undefined,
      targetToSource: mapping,
      request_body: kind === 'api' ? requestBody : undefined,
      request_params: kind === 'api' ? requestParams : undefined,
      persist_request_override: kind === 'api' ? persistRequestOverride : undefined,
      batch_fill_path: kind === 'api' ? batchFillPath : undefined,
      batch_fill_values: kind === 'api' ? batchFillValues : undefined,
    });
    onClose();
  };

  const mappingRows = visibleTargetFields.map((field) => ({
    key: field.value,
    target: field.value,
    label: resolveSyncTargetLabel(field, t),
    required: field.required ?? config.requiredTargets.includes(field.value),
    removable: !defaultTargetFieldValues.has(field.value),
  }));

  const handleConfirmAddTargets = () => {
    if (pendingAddTargetKeys.length === 0) return;
    setAddedTargetKeys((prev) => {
      const next = new Set(prev);
      pendingAddTargetKeys.forEach((key) => next.add(key));
      return [...next];
    });
    if (sourceColumns.length > 0) {
      setTargetToSource((prev) => ({
        ...suggestTargetToSourceMapping(
          sourceColumns,
          pendingAddTargetKeys,
          config.targetAliases,
        ),
        ...prev,
      }));
    }
    setPendingAddTargetKeys([]);
  };

  const handleRemoveTarget = (target: string) => {
    setAddedTargetKeys((prev) => prev.filter((key) => key !== target));
    setTargetToSource((prev) => {
      const next = { ...prev };
      delete next[target];
      return next;
    });
  };

  const previewTableColumns = previewColumns.map((col) => {
    const mappedTarget = Object.entries(targetToSource).find(([, source]) => source === col)?.[0];
    return {
      title: mappedTarget ?? col,
      dataIndex: col,
      key: col,
      ellipsis: true,
      width: 140,
    };
  });

  return (
    <>
    <Modal
      title={t('components.syncFromSource.sourceSettingTitle')}
      open={open}
      onCancel={onClose}
      width={880}
      zIndex={zIndex}
      destroyOnHidden
      footer={[
        <Button key="cancel" onClick={onClose}>
          {t('common.cancel')}
        </Button>,
        <Button key="preview" icon={<SyncOutlined />} loading={executing} onClick={() => void handlePreview()}>
          {t('components.syncFromSource.previewFetch')}
        </Button>,
        <Button key="save" type="primary" onClick={validateAndSave}>
          {t('common.save')}
        </Button>,
      ]}
    >
      <Space orientation="vertical" size="medium" style={{ width: '100%' }}>
        <div style={SYNC_FIELD_GRID_STYLE}>
          <Typography.Text type="secondary" style={SYNC_FIELD_LABEL_STYLE}>
            {t('components.syncFromSource.sourceKindField')}
          </Typography.Text>
          <div style={SYNC_FIELD_CONTROL_STYLE}>
            <ThemedSegmented
              block
              style={{ width: SYNC_SOURCE_KIND_SEGMENTED_WIDTH, maxWidth: '100%' }}
              value={kind}
              onChange={(value) => {
                const nextKind = value as SyncSourceType;
                setKind(nextKind);
                if (nextKind !== 'api') {
                  setRequestBody(undefined);
                  setRequestParams(undefined);
                  setPersistRequestOverride(false);
                  setBatchFillPath(undefined);
                  setBatchFillValues(undefined);
                  setEditingCallParams(false);
                }
                resetPreview();
              }}
              options={[
                { label: t('components.syncFromSource.sourceApi'), value: 'api' },
                { label: t('components.syncFromSource.sourceDataset'), value: 'dataset' },
              ]}
            />
          </div>

          {kind === 'api' ? (
            <>
              <Typography.Text type="secondary" style={SYNC_FIELD_LABEL_STYLE}>
                {t('components.syncFromSource.selectApi')}
              </Typography.Text>
              <div style={SYNC_FIELD_CONTROL_STYLE}>
                <Select
                  style={{ flex: 1, minWidth: 220, maxWidth: 520 }}
                  placeholder={t('components.syncFromSource.selectApiPlaceholder')}
                  loading={loadingOptions}
                  options={apiOptions}
                  value={apiUuid}
                  onChange={(value) => {
                    setApiUuid(value);
                    setRequestBody(undefined);
                    setRequestParams(undefined);
                    setPersistRequestOverride(false);
                    setBatchFillPath(undefined);
                    setBatchFillValues(undefined);
                    setEditingCallParams(false);
                    resetPreview();
                  }}
                  showSearch
                  optionFilterProp="label"
                  allowClear
                />
                <Button
                  icon={<EditOutlined />}
                  disabled={!apiUuid}
                  type={editingCallParams ? 'primary' : 'default'}
                  onClick={() => setEditingCallParams((prev) => !prev)}
                >
                  {t('components.syncFromSource.editCallParams')}
                </Button>
                <Checkbox
                  checked={persistRequestOverride}
                  disabled={!apiUuid}
                  onChange={(event) => setPersistRequestOverride(event.target.checked)}
                >
                  {t('components.syncFromSource.rememberCallParams')}
                </Checkbox>
                {requestBody || requestParams || batchFillValues?.length ? (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {persistRequestOverride
                      ? t('components.syncFromSource.callParamsRemembered')
                      : t('components.syncFromSource.callParamsSessionOnly')}
                  </Typography.Text>
                ) : null}
              </div>
            </>
          ) : (
            <>
              <Typography.Text type="secondary" style={SYNC_FIELD_LABEL_STYLE}>
                {t('components.syncFromSource.selectDataset')}
              </Typography.Text>
              <div style={SYNC_FIELD_CONTROL_STYLE}>
                <Select
                  style={{ width: '100%', maxWidth: 520 }}
                  placeholder={t('components.syncFromSource.selectDatasetPlaceholder')}
                  loading={loadingOptions}
                  options={datasetOptions}
                  value={datasetUuid}
                  onChange={(value) => {
                    setDatasetUuid(value);
                    resetPreview();
                  }}
                  showSearch
                  optionFilterProp="label"
                  allowClear
                />
              </div>
            </>
          )}
        </div>

        <Typography.Text type="secondary">
          {t(
            kind === 'api'
              ? config.apiRealtimeHintKey ?? 'components.syncFromSource.apiRealtimeHintDefault'
              : config.datasetBatchHintKey ?? 'components.syncFromSource.datasetBatchHintDefault',
          )}
        </Typography.Text>

        {kind === 'api' && editingCallParams && apiUuid ? (
          <SyncApiCallParamsPanel
            apiUuid={apiUuid}
            requestBody={requestBody}
            requestParams={requestParams}
            persistOverride={persistRequestOverride}
            batchFillPath={batchFillPath}
            batchFillValues={batchFillValues}
            localCodesLoader={config.syncCallParamsLocalCodes}
            onChange={(next) => {
              setRequestBody(next.request_body);
              setRequestParams(next.request_params);
              setPersistRequestOverride(next.persist_request_override);
              setBatchFillPath(next.batch_fill_path);
              setBatchFillValues(next.batch_fill_values);
              resetPreview();
            }}
          />
        ) : null}

        {executing ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin description={t('components.syncFromSource.fetching')} />
          </div>
        ) : null}

        {!executing && previewRows.length > 0 ? (
          <>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 8,
              }}
            >
              <Typography.Title level={5} style={{ margin: 0 }}>
                {t('components.syncFromSource.fieldMapping')}
              </Typography.Title>
              <Space wrap>
                <Button
                  size="small"
                  icon={<SyncOutlined />}
                  onClick={handleAutoMatch}
                  disabled={sourceColumns.length === 0 && previewRows.length === 0}
                >
                  {t('components.syncFromSource.autoMatch')}
                </Button>
                <Button
                  size="small"
                  icon={<UploadOutlined />}
                  onClick={() => mappingFileInputRef.current?.click()}
                >
                  {t('components.syncFromSource.mappingImport')}
                </Button>
                <input
                  ref={mappingFileInputRef}
                  type="file"
                  accept=".json,application/json"
                  style={{ display: 'none' }}
                  onChange={(event) => void handleImportMapping(event)}
                />
                <Button
                  size="small"
                  icon={<DownloadOutlined />}
                  onClick={handleExportMapping}
                  disabled={Object.keys(targetToSource).length === 0}
                >
                  {t('components.syncFromSource.mappingExport')}
                </Button>
              </Space>
            </div>
            <Table
              size="small"
              pagination={false}
              dataSource={mappingRows}
              columns={[
                {
                  title: t(config.targetFieldLabelKey ?? 'components.syncFromSource.targetFieldLabel'),
                  dataIndex: 'label',
                  width: 200,
                  render: (text, record) => (
                    <span>
                      {text}
                      {record.required ? <Typography.Text type="danger"> *</Typography.Text> : null}
                    </span>
                  ),
                },
                {
                  title: t('components.syncFromSource.sourceColumn'),
                  dataIndex: 'target',
                  render: (target: string) => (
                    <Select
                      style={{ width: '100%' }}
                      allowClear
                      showSearch
                      placeholder={t('components.syncFromSource.sourceColumnPlaceholder')}
                      options={sourceColumns.map((col) => ({ label: col, value: col }))}
                      value={targetToSource[target]}
                      onChange={(value) => {
                        setTargetToSource((prev) => {
                          const next = { ...prev };
                          // 允许同一来源列映多个目标（如 bizdate→订单日期+交货日期）
                          if (value) next[target] = value;
                          else delete next[target];
                          return next;
                        });
                      }}
                    />
                  ),
                },
                ...(supportsAddMoreFields
                  ? [
                      {
                        title: '',
                        key: 'actions',
                        width: 48,
                        render: (_: unknown, record: { target: string; removable: boolean }) =>
                          record.removable ? (
                            <Button
                              type="text"
                              size="small"
                              danger
                              icon={<DeleteOutlined />}
                              onClick={() => handleRemoveTarget(record.target)}
                              title={t('components.syncFromSource.removeMappingField')}
                              aria-label={t('components.syncFromSource.removeMappingField')}
                            />
                          ) : null,
                      },
                    ]
                  : []),
              ]}
            />
            {supportsAddMoreFields ? (
              <Space wrap style={{ width: '100%' }}>
                <Select
                  mode="multiple"
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  style={{ minWidth: 280, flex: 1 }}
                  placeholder={t('components.syncFromSource.addMappingFieldPlaceholder')}
                  options={addableTargetOptions}
                  value={pendingAddTargetKeys}
                  onChange={(values) => setPendingAddTargetKeys(values)}
                  disabled={addableTargetOptions.length === 0}
                />
                <Button
                  icon={<PlusOutlined />}
                  onClick={handleConfirmAddTargets}
                  disabled={pendingAddTargetKeys.length === 0}
                >
                  {t('components.syncFromSource.addMappingField')}
                </Button>
              </Space>
            ) : null}

            <Typography.Title level={5} style={{ margin: 0 }}>
              {t('components.syncFromSource.previewData', { count: previewRows.length })}
            </Typography.Title>
            <Table
              size="small"
              scroll={{ x: 'max-content', y: 240 }}
              pagination={{ pageSize: 5, showSizeChanger: false }}
              dataSource={previewRows.map((row, index) => ({ ...row, key: index }))}
              columns={previewTableColumns}
            />
          </>
        ) : null}

        {!executing && previewRows.length === 0 && Object.keys(targetToSource).length > 0 ? (
          <Typography.Text type="secondary">
            {t('components.syncFromSource.savedMappingReady')}
          </Typography.Text>
        ) : null}
      </Space>
    </Modal>
    </>
  );
};
