/**
 * 来源设置内嵌：编辑本次调用参数 + 按本系统编码分批填入
 * （物料编码，或仓库仓位关系的仓库编码）
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Button, Checkbox, Input, Pagination, Select, Space, Spin, Switch, Tag, Typography } from 'antd';
import { CustomFieldJsonEditor } from '../custom-fields/CustomFieldJsonEditor';
import { getAPIByUuid } from '../../services/apiManagement';
import { materialApi } from '../../apps/master-data/services/material';
import { warehouseApi } from '../../apps/master-data/services/warehouse';
import {
  asJsonObject,
  collectLeafPaths,
  ensureCosmicListRequestData,
  isWarehouseLocationReferenceApi,
  resolveBatchFillChunkSize,
  setByPath,
  suggestMaterialFillPath,
  suggestWarehouseFillPath,
} from './syncCallParams';

export interface SyncApiCallParamsPanelProps {
  apiUuid?: string;
  requestBody?: Record<string, unknown>;
  requestParams?: Record<string, unknown>;
  persistOverride: boolean;
  batchFillPath?: string;
  batchFillValues?: string[];
  localCodesLoader?: 'material' | 'warehouse';
  onChange: (next: {
    request_body?: Record<string, unknown>;
    request_params?: Record<string, unknown>;
    persist_request_override: boolean;
    batch_fill_path?: string;
    batch_fill_values?: string[];
  }) => void;
}

type BatchFillStash = {
  path?: string;
  values?: string[];
};

function materialCodeOf(row: { mainCode?: string; main_code?: string; code?: string }): string {
  return String(row.mainCode ?? row.main_code ?? row.code ?? '').trim();
}

async function fetchAllLocalMaterialCodes(): Promise<string[]> {
  const codes: string[] = [];
  const seen = new Set<string>();
  let skip = 0;
  const limit = 2000;
  for (let page = 0; page < 50; page += 1) {
    const res = await materialApi.list({ skip, limit, is_active: true });
    for (const item of res.items) {
      const code = materialCodeOf(item);
      if (!code || seen.has(code)) continue;
      seen.add(code);
      codes.push(code);
    }
    if (res.items.length < limit || (res.total > 0 && codes.length >= res.total)) break;
    skip += res.items.length;
  }
  return codes;
}

async function fetchAllLocalWarehouseCodes(): Promise<string[]> {
  const codes: string[] = [];
  const seen = new Set<string>();
  let skip = 0;
  const limit = 1000;
  for (let page = 0; page < 50; page += 1) {
    const res = await warehouseApi.list({ skip, limit, is_active: true });
    for (const item of res.items) {
      const code = String(item.code ?? '').trim();
      if (!code || seen.has(code)) continue;
      seen.add(code);
      codes.push(code);
    }
    if (res.items.length < limit || (res.total > 0 && codes.length >= res.total)) break;
    skip += res.items.length;
  }
  return codes;
}

export const SyncApiCallParamsPanel: React.FC<SyncApiCallParamsPanelProps> = ({
  apiUuid,
  requestBody,
  requestParams,
  persistOverride,
  batchFillPath,
  batchFillValues,
  localCodesLoader = 'material',
  onChange,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [codesLoading, setCodesLoading] = useState(false);
  const [defaultBody, setDefaultBody] = useState<Record<string, unknown>>({});
  const [defaultParams, setDefaultParams] = useState<Record<string, unknown>>({});
  const [showParams, setShowParams] = useState(false);
  const [codeFilter, setCodeFilter] = useState('');
  const [codePage, setCodePage] = useState(1);
  const [apiPathHint, setApiPathHint] = useState('');
  // 仓位关系接口即使父级未传 warehouse loader，也不得展示/走物料编码填充
  const isWarehouseFill =
    localCodesLoader === 'warehouse' || isWarehouseLocationReferenceApi(apiPathHint);
  const [batchFillEnabled, setBatchFillEnabled] = useState(
    () => Boolean(batchFillPath || batchFillValues?.length),
  );
  const batchFillStashRef = useRef<BatchFillStash>({
    path: batchFillPath,
    values: batchFillValues,
  });
  const codePageSize = 20;
  const codes = batchFillValues ?? [];

  // 外部带回填充配置时打开开关；关闭由用户开关控制，避免空 stash 时被 props 回弹关掉
  useEffect(() => {
    if (!(batchFillPath || batchFillValues?.length)) return;
    setBatchFillEnabled(true);
    batchFillStashRef.current = {
      path: batchFillPath,
      values: batchFillValues,
    };
  }, [batchFillPath, batchFillValues]);

  const emit = useCallback(
    (patch: Partial<{
      request_body?: Record<string, unknown>;
      request_params?: Record<string, unknown>;
      persist_request_override: boolean;
      batch_fill_path?: string;
      batch_fill_values?: string[];
    }>) => {
      onChange({
        request_body: 'request_body' in patch ? patch.request_body : requestBody,
        request_params: 'request_params' in patch ? patch.request_params : requestParams,
        persist_request_override:
          patch.persist_request_override ?? persistOverride,
        batch_fill_path: 'batch_fill_path' in patch ? patch.batch_fill_path : batchFillPath,
        batch_fill_values: 'batch_fill_values' in patch ? patch.batch_fill_values : batchFillValues,
      });
    },
    [onChange, requestBody, requestParams, persistOverride, batchFillPath, batchFillValues],
  );

  const handleBatchFillEnabledChange = (enabled: boolean) => {
    setBatchFillEnabled(enabled);
    if (enabled) {
      const stash = batchFillStashRef.current;
      emit({
        batch_fill_path: stash.path,
        batch_fill_values: stash.values,
      });
      return;
    }
    batchFillStashRef.current = {
      path: batchFillPath,
      values: batchFillValues,
    };
    emit({
      batch_fill_path: undefined,
      batch_fill_values: undefined,
    });
  };

  useEffect(() => {
    if (!apiUuid) {
      setApiPathHint('');
      return;
    }
    let cancelled = false;
    setLoading(true);
    void getAPIByUuid(apiUuid)
      .then((api) => {
        if (cancelled) return;
        const apiMeta = {
          path: String(api.path || ''),
          code: String(api.code || ''),
        };
        setApiPathHint(`${apiMeta.path} ${apiMeta.code}`);
        const apiBody = ensureCosmicListRequestData(asJsonObject(api.request_body), apiMeta);
        const apiParams = asJsonObject(api.request_params);
        setDefaultBody(apiBody);
        setDefaultParams(apiParams);
        setShowParams(Object.keys(apiParams).length > 0 || Boolean(requestParams));
        if (!requestBody) {
          emit({ request_body: apiBody, request_params: Object.keys(apiParams).length ? apiParams : undefined });
        } else {
          // 历史「记住调用参数」可能缺 data；与接口模板对齐同一契约，不另起源设定
          const healed = ensureCosmicListRequestData(requestBody, apiMeta);
          if (JSON.stringify(healed) !== JSON.stringify(requestBody)) {
            emit({
              request_body: healed,
              request_params: requestParams,
            });
          }
        }
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setApiPathHint('');
        messageApi.error(
          error instanceof Error ? error.message : t('components.syncFromSource.loadApiParamsFailed'),
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // 仅在切换接口时拉模板；覆盖体由父级保存
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUuid]);

  const workingBody = requestBody ?? defaultBody;
  const leafPaths = useMemo(() => collectLeafPaths(workingBody), [workingBody]);
  const fillPath =
    batchFillPath ||
    (isWarehouseFill ? suggestWarehouseFillPath(leafPaths) : suggestMaterialFillPath(leafPaths));
  const fillChunkSize = resolveBatchFillChunkSize(workingBody, fillPath, apiPathHint);
  const batchCount = codes.length === 0 ? 0 : Math.ceil(codes.length / fillChunkSize);

  const filteredCodes = useMemo(() => {
    const keyword = codeFilter.trim().toLowerCase();
    if (!keyword) return codes;
    return codes.filter((code) => code.toLowerCase().includes(keyword));
  }, [codeFilter, codes]);

  const pagedCodes = filteredCodes.slice((codePage - 1) * codePageSize, codePage * codePageSize);

  const handleReset = () => {
    emit({
      request_body: ensureCosmicListRequestData(defaultBody),
      request_params: Object.keys(defaultParams).length ? asJsonObject(defaultParams) : undefined,
      batch_fill_path: undefined,
      batch_fill_values: undefined,
    });
    setCodeFilter('');
    setCodePage(1);
  };

  const handleLoadCodes = async () => {
    setCodesLoading(true);
    try {
      const next = isWarehouseFill
        ? await fetchAllLocalWarehouseCodes()
        : await fetchAllLocalMaterialCodes();
      if (next.length === 0) {
        messageApi.warning(
          t(
            isWarehouseFill
              ? 'components.syncFromSource.warehouseCodesEmpty'
              : 'components.syncFromSource.materialCodesEmpty',
          ),
        );
        return;
      }
      const path =
        fillPath ||
        (isWarehouseFill ? suggestWarehouseFillPath(leafPaths) : suggestMaterialFillPath(leafPaths));
      const chunkSize = resolveBatchFillChunkSize(workingBody, path, apiPathHint);
      const previewVal =
        chunkSize === 1 ? next[0] : next.slice(0, chunkSize).join(',');
      emit({
        batch_fill_path: path,
        batch_fill_values: next,
        request_body: path ? setByPath(workingBody, path, previewVal) : workingBody,
      });
      setCodePage(1);
      messageApi.success(
        t(
          isWarehouseFill
            ? 'components.syncFromSource.warehouseCodesLoaded'
            : 'components.syncFromSource.materialCodesLoaded',
          {
            count: next.length,
            pageSize: chunkSize,
            batches: Math.ceil(next.length / chunkSize),
          },
        ),
      );
    } catch (error: unknown) {
      messageApi.error(
        error instanceof Error
          ? error.message
          : t(
              isWarehouseFill
                ? 'components.syncFromSource.warehouseCodesLoadFailed'
                : 'components.syncFromSource.materialCodesLoadFailed',
            ),
      );
    } finally {
      setCodesLoading(false);
    }
  };

  const handleRemoveCode = (code: string) => {
    const next = codes.filter((item) => item !== code);
    const path = fillPath;
    const chunkSize = resolveBatchFillChunkSize(workingBody, path, apiPathHint);
    const previewVal =
      path && next.length > 0
        ? chunkSize === 1
          ? next[0]
          : next.slice(0, chunkSize).join(',')
        : undefined;
    emit({
      batch_fill_values: next,
      request_body: previewVal !== undefined && path ? setByPath(workingBody, path, previewVal) : workingBody,
    });
  };

  const handleRemoveFiltered = () => {
    const drop = new Set(filteredCodes);
    const next = codes.filter((item) => !drop.has(item));
    const path = fillPath;
    const chunkSize = resolveBatchFillChunkSize(workingBody, path, apiPathHint);
    const previewVal =
      path && next.length > 0
        ? chunkSize === 1
          ? next[0]
          : next.slice(0, chunkSize).join(',')
        : undefined;
    emit({
      batch_fill_values: next,
      request_body: previewVal !== undefined && path ? setByPath(workingBody, path, previewVal) : workingBody,
    });
    setCodePage(1);
  };

  const handleFillPathChange = (path: string) => {
    const chunkSize = resolveBatchFillChunkSize(workingBody, path, apiPathHint);
    const previewVal =
      path && codes.length > 0
        ? chunkSize === 1
          ? codes[0]
          : codes.slice(0, chunkSize).join(',')
        : undefined;
    emit({
      batch_fill_path: path,
      request_body:
        previewVal !== undefined ? setByPath(workingBody, path, previewVal) : workingBody,
    });
  };

  return (
    <Space orientation="vertical" size="medium" style={{ width: '100%' }}>
      {loading ? (
        <div style={{ textAlign: 'center', padding: 16 }}>
          <Spin />
        </div>
      ) : (
        <>
          <Typography.Text type="secondary">{t('components.syncFromSource.callRequestBody')}</Typography.Text>
          <CustomFieldJsonEditor
            value={workingBody}
            onChange={(value) => emit({ request_body: asJsonObject(value) })}
          />
          {showParams ? (
            <>
              <Typography.Text type="secondary">{t('components.syncFromSource.callRequestParams')}</Typography.Text>
              <CustomFieldJsonEditor
                value={requestParams ?? defaultParams}
                onChange={(value) => emit({ request_params: asJsonObject(value) })}
              />
            </>
          ) : null}
          <Space wrap>
            <Button onClick={handleReset}>{t('components.syncFromSource.resetCallParams')}</Button>
            <Checkbox
              checked={persistOverride}
              onChange={(event) => emit({ persist_request_override: event.target.checked })}
            >
              {t('components.syncFromSource.rememberCallParams')}
            </Checkbox>
          </Space>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {t('components.syncFromSource.rememberCallParamsHint')}
          </Typography.Text>

          <Space align="center" style={{ width: '100%', justifyContent: 'space-between' }}>
            <Typography.Title level={5} style={{ margin: 0 }}>
              {t(
                isWarehouseFill
                  ? 'components.syncFromSource.warehouseFillTitle'
                  : 'components.syncFromSource.materialFillTitle',
              )}
            </Typography.Title>
            <Space size="small">
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t(
                  isWarehouseFill
                    ? 'components.syncFromSource.warehouseFillEnable'
                    : 'components.syncFromSource.materialFillEnable',
                )}
              </Typography.Text>
              <Switch checked={batchFillEnabled} onChange={handleBatchFillEnabledChange} />
            </Space>
          </Space>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {batchFillEnabled
              ? t(
                  isWarehouseFill
                    ? 'components.syncFromSource.warehouseFillHint'
                    : 'components.syncFromSource.materialFillHint',
                  { pageSize: fillChunkSize },
                )
              : t(
                  isWarehouseFill
                    ? 'components.syncFromSource.warehouseFillEnableHint'
                    : 'components.syncFromSource.materialFillEnableHint',
                )}
          </Typography.Text>
          {batchFillEnabled ? (
            <>
              <Space wrap style={{ width: '100%' }}>
                <Select
                  style={{ minWidth: 240, flex: 1 }}
                  placeholder={t(
                    isWarehouseFill
                      ? 'components.syncFromSource.warehouseFillPathPlaceholder'
                      : 'components.syncFromSource.materialFillPathPlaceholder',
                  )}
                  options={leafPaths.map((item) => ({ label: item.label, value: item.path }))}
                  value={fillPath}
                  onChange={handleFillPathChange}
                  showSearch
                  optionFilterProp="label"
                />
                <Button loading={codesLoading} onClick={() => void handleLoadCodes()}>
                  {t(
                    isWarehouseFill
                      ? 'components.syncFromSource.loadWarehouseCodes'
                      : 'components.syncFromSource.loadMaterialCodes',
                  )}
                </Button>
              </Space>
              {codes.length > 0 ? (
                <>
                  <Typography.Text>
                    {t(
                      isWarehouseFill
                        ? 'components.syncFromSource.warehouseCodesSummary'
                        : 'components.syncFromSource.materialCodesSummary',
                      {
                        count: codes.length,
                        pageSize: fillChunkSize,
                        batches: batchCount,
                        shown: Math.min(fillChunkSize, codes.length),
                      },
                    )}
                  </Typography.Text>
                  <Space wrap style={{ width: '100%' }}>
                    <Input
                      allowClear
                      style={{ maxWidth: 280 }}
                      placeholder={t(
                        isWarehouseFill
                          ? 'components.syncFromSource.warehouseCodeFilter'
                          : 'components.syncFromSource.materialCodeFilter',
                      )}
                      value={codeFilter}
                      onChange={(event) => {
                        setCodeFilter(event.target.value);
                        setCodePage(1);
                      }}
                    />
                    <Button danger disabled={filteredCodes.length === 0} onClick={handleRemoveFiltered}>
                      {t('components.syncFromSource.removeFilteredCodes')}
                    </Button>
                  </Space>
                  <div
                    style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      alignItems: 'center',
                      gap: 8,
                      marginBlock: '8px 12px',
                    }}
                  >
                    {pagedCodes.map((code) => (
                      <Tag key={code} variant="filled" closable onClose={() => handleRemoveCode(code)}>
                        {code}
                      </Tag>
                    ))}
                  </div>
                  <Pagination
                    size="small"
                    current={codePage}
                    pageSize={codePageSize}
                    total={filteredCodes.length}
                    onChange={setCodePage}
                    showSizeChanger={false}
                  />
                </>
              ) : null}
            </>
          ) : null}
        </>
      )}
    </Space>
  );
};
