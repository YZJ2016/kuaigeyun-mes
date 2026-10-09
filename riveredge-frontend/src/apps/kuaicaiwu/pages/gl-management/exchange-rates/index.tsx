/**
 * 总账汇率设置：按币种与生效日维护相对本位币汇率。
 */
import { rowActionKind } from '../../../../../components/uni-action';
import { UniBatchDeleteButton, UniBatchMenuButton } from '../../../../../components/uni-batch';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import React, { useCallback, useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { ProFormDatePicker, ProFormDigit, ProFormTextArea } from '@ant-design/pro-components';
import { App, Button, Dropdown, Popconfirm, Row, Col } from 'antd';
import type { MenuProps } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { DictionarySelect } from '../../../../../components/dictionary-select';
import { DictionaryLabel } from '../../../../../components/dictionary-label';
import {
  FormModalTemplate,
  ListPageTemplate,
  MODAL_CONFIG,
} from '../../../../../components/layout-templates';
import { UniTable } from '../../../../../components/uni-table';
import { pickSearchString } from '../../../../../utils/tableQueryKey';
import {
  exchangeRateService,
  type GlExchangeRate,
  type GlExchangeRateBatchResult,
} from '../../../services/exchange-rate';
import { glService } from '../../../services/gl';
import { financeDocCreatedUpdatedColumns } from '../../../utils/financeListCore';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { toApiDateString } from '../../../../../utils/formDate';

const NS = 'app.kuaicaiwu.gl.exchangeRate';

const GlExchangeRatesPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi, modal } = App.useApp();
  const { canDelete } = useResourcePermissions('kuaicaiwu:gl');
  const actionRef = useRef<ActionType>();
  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<GlExchangeRate | null>(null);
  const [presetLoading, setPresetLoading] = useState(false);
  const [fetchLoading, setFetchLoading] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const tableRowsRef = useRef<GlExchangeRate[]>([]);

  const { data: glSettings } = useQuery({
    queryKey: ['kuaicaiwu-gl-book-settings'],
    queryFn: () => glService.getSettings(),
    staleTime: 10 * 60 * 1000,
  });
  const baseCurrency = String(glSettings?.base_currency || 'CNY')
    .trim()
    .toUpperCase();

  const { data: sourceCatalog } = useQuery({
    queryKey: ['kuaicaiwu-gl-exchange-rate-sources'],
    queryFn: () => exchangeRateService.listReferenceSources(),
    staleTime: 30 * 60 * 1000,
  });
  const referenceSources = sourceCatalog?.items ?? [];
  const defaultSource = sourceCatalog?.default || 'cfets';

  const openCreate = useCallback(() => {
    setEditing(null);
    setModalVisible(true);
  }, []);

  const sourceLabel = useCallback(
    (code?: string) => {
      const found = referenceSources.find((s) => s.code === code);
      return found?.label || code || defaultSource;
    },
    [defaultSource, referenceSources],
  );

  const notifyBatchResult = useCallback(
    (result: GlExchangeRateBatchResult, mode: 'preset' | 'fetch') => {
      const unavailable =
        result.unavailable?.length > 0
          ? t(`${NS}.batchUnavailable`, { codes: result.unavailable.join(', ') })
          : '';
      const sourceText = sourceLabel(result.source);
      if (mode === 'preset') {
        messageApi.success(
          t(`${NS}.presetSuccess`, {
            created: result.created,
            skipped: result.skipped,
            date: result.effective_date,
            source: sourceText,
          }) + (unavailable ? ` ${unavailable}` : ''),
        );
      } else {
        messageApi.success(
          t(`${NS}.fetchSuccess`, {
            created: result.created,
            updated: result.updated,
            date: result.effective_date,
            source: sourceText,
          }) + (unavailable ? ` ${unavailable}` : ''),
        );
      }
      actionRef.current?.reload();
    },
    [messageApi, sourceLabel, t],
  );

  const handlePresetCommon = useCallback(
    async (source?: string) => {
      setPresetLoading(true);
      try {
        const result = await exchangeRateService.presetCommon({
          source: source || defaultSource,
        });
        notifyBatchResult(result, 'preset');
      } catch (error: unknown) {
        const err = error as { message?: string };
        messageApi.error(err?.message || t(`${NS}.presetFailed`));
      } finally {
        setPresetLoading(false);
      }
    },
    [defaultSource, messageApi, notifyBatchResult, t],
  );

  const handleFetchReference = useCallback(
    async (source?: string, currencyCodes?: string[]) => {
      setFetchLoading(true);
      try {
        const result = await exchangeRateService.fetchReference({
          source: source || defaultSource,
          currency_codes: currencyCodes,
        });
        notifyBatchResult(result, 'fetch');
        if (currencyCodes?.length) {
          setSelectedRowKeys([]);
        }
      } catch (error: unknown) {
        const err = error as { message?: string };
        messageApi.error(err?.message || t(`${NS}.fetchFailed`));
      } finally {
        setFetchLoading(false);
      }
    },
    [defaultSource, messageApi, notifyBatchResult, t],
  );

  const confirmFetchWithSource = useCallback(
    (source: string, currencyCodes?: string[]) => {
      const label = sourceLabel(source);
      modal.confirm({
        title: t(`${NS}.fetchConfirmTitle`),
        content: t(`${NS}.fetchConfirmContent`, { source: label }),
        onOk: () => handleFetchReference(source, currencyCodes),
      });
    },
    [handleFetchReference, modal, sourceLabel, t],
  );

  const handleBatchDelete = useCallback(
    async (keys: React.Key[]) => {
      for (const key of keys) {
        await exchangeRateService.delete(Number(key));
      }
      messageApi.success(t(`${NS}.batchDeleteSuccess`, { count: keys.length }));
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    },
    [messageApi, t],
  );

  const handleBatchFetchSelected = useCallback(
    (keys: React.Key[]) => {
      const codes = tableRowsRef.current
        .filter((row) => keys.includes(row.id))
        .map((row) => row.currency_code)
        .filter(Boolean);
      const unique = Array.from(new Set(codes));
      if (unique.length === 0) {
        messageApi.warning(t(`${NS}.batchFetchNoCurrency`));
        return;
      }
      confirmFetchWithSource(defaultSource, unique);
    },
    [confirmFetchWithSource, defaultSource, messageApi, t],
  );

  const sourceMenuItems = useMemo<MenuProps['items']>(
    () =>
      referenceSources.map((s) => ({
        key: s.code,
        label: s.label,
        title: s.description,
      })),
    [referenceSources],
  );

  const fetchMenu: MenuProps = useMemo(
    () => ({
      items: sourceMenuItems,
      onClick: ({ key }) => confirmFetchWithSource(String(key)),
    }),
    [confirmFetchWithSource, sourceMenuItems],
  );

  const columns: ProColumns<GlExchangeRate>[] = useMemo(
    () =>
      alignProColumns<GlExchangeRate>(
        [
          {
            title: t(`${NS}.col.currencyCode`),
            key: 'gl_fx_currency_code',
            dataIndex: 'currency_code',
            width: 108,
            minWidth: 108,
            uniTableKeepWidth: true,
            resizable: false,
            ellipsis: true,
            sorter: true,
            copyable: true,
          },
          {
            title: t(`${NS}.col.currencyName`),
            key: 'gl_fx_currency_name',
            dataIndex: 'currency_name',
            width: 108,
            minWidth: 108,
            uniTableKeepWidth: true,
            resizable: false,
            ellipsis: true,
            hideInSearch: true,
            render: (_, r) => (
              <DictionaryLabel
                dictionaryCode="CURRENCY"
                value={r.currency_code}
                notFoundPlaceholder={r.currency_code || '—'}
              />
            ),
          },
          {
            title: t(`${NS}.col.rate`),
            key: 'gl_fx_rate',
            dataIndex: 'rate',
            align: 'right',
            width: 112,
            minWidth: 112,
            uniTableKeepWidth: true,
            resizable: false,
            sorter: true,
            hideInSearch: true,
            render: (_, r) => Number(r.rate).toFixed(4),
          },
          {
            title: t(`${NS}.col.effectiveDate`),
            key: 'gl_fx_effective_date',
            dataIndex: 'effective_date',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            sorter: true,
            hideInSearch: true,
          },
          {
            title: t(`${NS}.col.notes`),
            dataIndex: 'notes',
            ellipsis: true,
            minWidth: 160,
            uniTableRemainderFlex: true,
            hideInSearch: true,
          },
          ...financeDocCreatedUpdatedColumns<GlExchangeRate>(t),
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right',
            hideInSearch: true,
            render: (_, record) => [
              <Button
                key="edit"
                type="link"
                size="small"
                {...rowActionKind('update')}
                onClick={() => {
                  setEditing(record);
                  setModalVisible(true);
                }}
              />,
              <Popconfirm
                key="delete"
                title={t(`${NS}.deleteConfirm`)}
                onConfirm={async () => {
                  await exchangeRateService.delete(record.id);
                  messageApi.success(t('common.deleteSuccess'));
                  actionRef.current?.reload();
                }}
              >
                <Button type="link" size="small" {...rowActionKind('delete')} />
              </Popconfirm>,
            ],
          },
        ],
        SALES_DOC_LIST_FIELD_RANK,
      ),
    [t, messageApi],
  );

  const modalInitialValues = useMemo(() => {
    if (editing) {
      return {
        currency_code: editing.currency_code,
        effective_date: editing.effective_date,
        rate: Number(editing.rate),
        notes: editing.notes ?? undefined,
      };
    }
    return {};
  }, [editing]);

  return (
    <ListPageTemplate>
      <UniTable<GlExchangeRate>
        actionRef={actionRef}
        rowKey="id"
        columns={columns}
        columnPersistenceId="kuaicaiwu-gl-exchange-rates-v4"
        showCreateButton
        createButtonText={t(`${NS}.createButton`)}
        onCreate={openCreate}
        enableRowSelection
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        onTableDataChange={(rows) => {
          tableRowsRef.current = rows;
        }}
        toolBarActionsAfterCreate={[
          ...(canDelete
            ? [
                <UniBatchDeleteButton
                  key="batch-delete"
                  selectedRowKeys={selectedRowKeys}
                  onConfirm={handleBatchDelete}
                  confirmTitle={t(`${NS}.batchDeleteTitle`)}
                  confirmDescription={(count) => t(`${NS}.batchDeleteDesc`, { count })}
                />,
              ]
            : []),
          <UniBatchMenuButton
            key="exchange-rate-batch-actions"
            selectedRowKeys={selectedRowKeys}
            buttonText={t(`${NS}.batchActions`)}
            menuItems={[
              {
                key: 'batch-fetch-reference',
                label: t(`${NS}.batchFetchReference`),
                onClick: handleBatchFetchSelected,
              },
            ]}
          />,
          <Popconfirm
            key="preset-common"
            title={t(`${NS}.presetConfirmContent`, {
              source: sourceLabel(defaultSource),
            })}
            onConfirm={() => handlePresetCommon(defaultSource)}
          >
            <Button loading={presetLoading}>{t(`${NS}.presetCommon`)}</Button>
          </Popconfirm>,
          <Dropdown.Button
            key="fetch-reference"
            menu={fetchMenu}
            loading={fetchLoading}
            icon={<DownOutlined />}
            onClick={() => confirmFetchWithSource(defaultSource)}
          >
            {t(`${NS}.fetchReference`)}
          </Dropdown.Button>,
        ]}
        request={async (params, sort, _filter, searchFormValues) => {
          const sortField = sort && Object.keys(sort)[0];
          const sortOrder = sortField ? sort[sortField] : undefined;
          const { current = 1, pageSize = 20 } = params;
          const res = await exchangeRateService.list({
            skip: (current - 1) * pageSize,
            limit: pageSize,
            sort_field: sortField,
            sort_order: sortOrder,
            currency_code: pickSearchString(searchFormValues, 'currency_code'),
          });
          return { data: res.items, success: true, total: res.total };
        }}
        toolBarActionsEnd={[
          <span key="base-hint" style={{ color: 'rgba(0,0,0,0.45)', fontSize: 13 }}>
            {t(`${NS}.baseCurrencyHint`, { code: baseCurrency })}
          </span>,
        ]}
      />

      <FormModalTemplate
        title={editing ? t(`${NS}.editTitle`) : t(`${NS}.createTitle`)}
        open={modalVisible}
        onOpenChange={setModalVisible}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        grid={false}
        initialValues={modalInitialValues}
        modalProps={{ destroyOnHidden: true }}
        onFinish={async (values) => {
          const currency = String(values.currency_code).trim().toUpperCase();
          if (currency === baseCurrency) {
            messageApi.error(t(`${NS}.baseCurrencyForbidden`));
            return false;
          }
          const payload = {
            currency_code: currency,
            effective_date: toApiDateString(values.effective_date)!,
            rate: Number(values.rate),
            notes: values.notes,
          };
          if (editing) {
            await exchangeRateService.update(editing.id, payload);
            messageApi.success(t('common.updateSuccess'));
          } else {
            await exchangeRateService.create(payload);
            messageApi.success(t('common.createSuccess'));
          }
          setModalVisible(false);
          actionRef.current?.reload();
          return true;
        }}
      >
        <Row gutter={16}>
          <Col span={12}>
            <DictionarySelect
              dictionaryCode="CURRENCY"
              name="currency_code"
              label={t(`${NS}.col.currencyCode`)}
              rules={[{ required: true, message: t(`${NS}.currencyRequired`) }]}
            />
          </Col>
          <Col span={12}>
            <ProFormDatePicker
              name="effective_date"
              label={t(`${NS}.col.effectiveDate`)}
              rules={[{ required: true, message: t(`${NS}.effectiveDateRequired`) }]}
              fieldProps={{ style: { width: '100%' } }}
            />
          </Col>
          <Col span={12}>
            <ProFormDigit
              name="rate"
              label={t(`${NS}.col.rate`)}
              tooltip={t(`${NS}.rateHint`, { code: baseCurrency })}
              min={0.000001}
              max={999999999999}
              fieldProps={{ precision: 6 }}
              rules={[{ required: true, message: t(`${NS}.rateRequired`) }]}
            />
          </Col>
          <Col span={24}>
            <ProFormTextArea name="notes" label={t('common.remark')} fieldProps={{ rows: 3 }} />
          </Col>
        </Row>
      </FormModalTemplate>
    </ListPageTemplate>
  );
};

export default GlExchangeRatesPage;
