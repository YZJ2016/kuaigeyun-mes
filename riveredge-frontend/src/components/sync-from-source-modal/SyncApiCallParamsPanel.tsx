/**
 * 来源设置内嵌：编辑本次调用参数 + 按 pageSize 批量填入本系统物料编码
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Button, Checkbox, Input, Pagination, Select, Space, Spin, Switch, Tag, Typography } from 'antd';
import { CustomFieldJsonEditor } from '../custom-fields/CustomFieldJsonEditor';
import { getAPIByUuid } from '../../services/apiManagement';
import { materialApi } from '../../apps/master-data/services/material';
import {
  asJsonObject,
  collectLeafPaths,
  resolveCallPageSize,
  setByPath,
  suggestMaterialFillPath,
} from './syncCallParams';

export interface SyncApiCallParamsPanelProps {
  apiUuid?: string;
  requestBody?: Record<string, unknown>;
  requestParams?: Record<string, unknown>;
  persistOverride: boolean;
  batchFillPath?: string;
  batchFillValues?: string[];
  onChange: (next: {
    request_body?: Record<string, unknown>;
    request_params?: Record<string, unknown>;
    persist_request_override: boolean;
    batch_fill_path?: string;
    batch_fill_values?: string[];
  }) => void;
}

type MaterialFillStash = {
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
    const res = await materialApi.list({ skip, limit, isActive: true });
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

export const SyncApiCallParamsPanel: React.FC<SyncApiCallParamsPanelProps> = ({
  apiUuid,
  requestBody,
  requestParams,
  persistOverride,
  batchFillPath,
  batchFillValues,
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
  const [materialFillEnabled, setMaterialFillEnabled] = useState(
    () => Boolean(batchFillPath || batchFillValues?.length),
  );
  const materialFillStashRef = useRef<MaterialFillStash>({
    path: batchFillPath,
    values: batchFillValues,
  });
  const codePageSize = 20;
  const codes = batchFillValues ?? [];

  // 外部带回填充配置时打开开关；关闭由用户开关控制，避免空 stash 时被 props 回拨关掉
  useEffect(() => {
    if (!(batchFillPath || batchFillValues?.length)) return;
    setMaterialFillEnabled(true);
    materialFillStashRef.current = {
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

  const handleMaterialFillEnabledChange = (enabled: boolean) => {
    setMaterialFillEnabled(enabled);
    if (enabled) {
      const stash = materialFillStashRef.current;
      emit({
        batch_fill_path: stash.path,
        batch_fill_values: stash.values,
      });
      return;
    }
    materialFillStashRef.current = {
      path: batchFillPath,
      values: batchFillValues,
    };
    emit({
      batch_fill_path: undefined,
      batch_fill_values: undefined,
    });
  };

  useEffect(() => {
    if (!apiUuid) return;
    let cancelled = false;
    setLoading(true);
    void getAPIByUuid(apiUuid)
      .then((api) => {
        if (cancelled) return;
        const apiBody = asJsonObject(api.request_body);
        const apiParams = asJsonObject(api.request_params);
        setDefaultBody(apiBody);
        setDefaultParams(apiParams);
        setShowParams(Object.keys(apiParams).length > 0 || Boolean(requestParams));
        if (!requestBody) {
          emit({ request_body: apiBody, request_params: Object.keys(apiParams).length ? apiParams : undefined });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) return;
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
  const fillPath = batchFillPath || suggestMaterialFillPath(leafPaths);
  const pageSize = resolveCallPageSize(workingBody);
  const batchCount = codes.length === 0 ? 0 : Math.ceil(codes.length / pageSize);

  const filteredCodes = useMemo(() => {
    const keyword = codeFilter.trim().toLowerCase();
    if (!keyword) return codes;
    return codes.filter((code) => code.toLowerCase().includes(keyword));
  }, [codeFilter, codes]);

  const pagedCodes = filteredCodes.slice((codePage - 1) * codePageSize, codePage * codePageSize);

  const handleReset = () => {
    emit({
      request_body: asJsonObject(defaultBody),
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
      const next = await fetchAllLocalMaterialCodes();
      if (next.length === 0) {
        messageApi.warning(t('components.syncFromSource.materialCodesEmpty'));
        return;
      }
      const path = fillPath || suggestMaterialFillPath(leafPaths);
      emit({
        batch_fill_path: path,
        batch_fill_values: next,
        request_body: path
          ? setByPath(workingBody, path, next.slice(0, pageSize).join(','))
          : workingBody,
      });
      setCodePage(1);
      messageApi.success(
        t('components.syncFromSource.materialCodesLoaded', {
          count: next.length,
          pageSize,
          batches: Math.ceil(next.length / pageSize),
        }),
      );
    } catch (error: unknown) {
      messageApi.error(
        error instanceof Error ? error.message : t('components.syncFromSource.materialCodesLoadFailed'),
      );
    } finally {
      setCodesLoading(false);
    }
  };

  const handleRemoveCode = (code: string) => {
    const next = codes.filter((item) => item !== code);
    const path = fillPath;
    emit({
      batch_fill_values: next,
      request_body: path
        ? setByPath(workingBody, path, next.slice(0, pageSize).join(','))
        : workingBody,
    });
  };

  const handleRemoveFiltered = () => {
    const drop = new Set(filteredCodes);
    const next = codes.filter((item) => !drop.has(item));
    const path = fillPath;
    emit({
      batch_fill_values: next,
      request_body: path
        ? setByPath(workingBody, path, next.slice(0, pageSize).join(','))
        : workingBody,
    });
    setCodePage(1);
  };

  const handleFillPathChange = (path: string) => {
    emit({
      batch_fill_path: path,
      request_body:
        path && codes.length > 0
          ? setByPath(workingBody, path, codes.slice(0, pageSize).join(','))
          : workingBody,
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
              {t('components.syncFromSource.materialFillTitle')}
            </Typography.Title>
            <Space size="small">
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {t('components.syncFromSource.materialFillEnable')}
              </Typography.Text>
              <Switch checked={materialFillEnabled} onChange={handleMaterialFillEnabledChange} />
            </Space>
          </Space>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {materialFillEnabled
              ? t('components.syncFromSource.materialFillHint', { pageSize })
              : t('components.syncFromSource.materialFillEnableHint')}
          </Typography.Text>
          {materialFillEnabled ? (
            <>
              <Space wrap style={{ width: '100%' }}>
                <Select
                  style={{ minWidth: 240, flex: 1 }}
                  placeholder={t('components.syncFromSource.materialFillPathPlaceholder')}
                  options={leafPaths.map((item) => ({ label: item.label, value: item.path }))}
                  value={fillPath}
                  onChange={handleFillPathChange}
                  showSearch
                  optionFilterProp="label"
                />
                <Button loading={codesLoading} onClick={() => void handleLoadCodes()}>
                  {t('components.syncFromSource.loadMaterialCodes')}
                </Button>
              </Space>
              {codes.length > 0 ? (
                <>
                  <Typography.Text>
                    {t('components.syncFromSource.materialCodesSummary', {
                      count: codes.length,
                      pageSize,
                      batches: batchCount,
                      shown: Math.min(pageSize, codes.length),
                    })}
                  </Typography.Text>
                  <Space wrap style={{ width: '100%' }}>
                    <Input
                      allowClear
                      style={{ maxWidth: 280 }}
                      placeholder={t('components.syncFromSource.materialCodeFilter')}
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
                  <div>
                    {pagedCodes.map((code) => (
                      <Tag key={code} closable onClose={() => handleRemoveCode(code)} style={{ marginBottom: 6 }}>
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
