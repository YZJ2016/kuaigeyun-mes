import React, { useCallback, useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { App, Button } from 'antd';
import { useTranslation } from 'react-i18next';
import { rowActionKind } from '../../../../../components/uni-action';
import { ListPageTemplate } from '../../../../../components/layout-templates';
import {
  CustomFieldsDetailSection,
  hasCustomFieldsDetailContent,
} from '../../../../../components/custom-fields';
import { UniTable, type UniTableRequestMeta } from '../../../../../components/uni-table';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { buildDetailDrawerEditExtra } from '../../equipment-management/shared/equipmentMasterDataDetail';
import {
  AFTER_SALES_ASSET_STATUS_COLOR,
  AFTER_SALES_CUSTOMER_NAME_COLUMN_DEFAULTS,
  renderAfterSalesStatusTag,
} from '../shared/afterSalesListPresentation';
import { serviceAssetApi, type ServiceAsset } from '../../../services/after-sales-service';
import ServiceAssetFormModal from './ServiceAssetFormModal';
import { ServiceAssetDetailDrawer } from './components/ServiceAssetDetailDrawer';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { pickListSearchKeyword, pickSearchString } from '../../../../../utils/tableQueryKey';

const RESOURCE = 'kuaizhizao:service-asset';
const CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_service_assets';

const ServiceAssetsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const perms = useResourcePermissions(RESOURCE);
  const actionRef = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ServiceAsset | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<ServiceAsset | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailRetryIdRef = useRef<number | null>(null);
  const {
    customFields: listCustomFields,
    customFieldValues: detailCustomFieldValues,
    generateCustomFieldColumns,
    enrichRecordsWithCustomFields,
    loadFieldValuesForDetail,
    resetDetailFieldValues,
  } = useCustomFieldsForList<ServiceAsset>({
    tableName: CUSTOM_FIELD_TABLE,
    hostResource: RESOURCE,
  });
  const customFieldColumns = generateCustomFieldColumns();
  const showDetailCustomFields = hasCustomFieldsDetailContent(
    listCustomFields,
    detailCustomFieldValues,
  );

  const openCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const openEdit = async (row: ServiceAsset) => {
    const full = await serviceAssetApi.get(row.id);
    setEditing(full);
    setModalOpen(true);
  };

  const loadDetail = useCallback(async (id: number) => {
    setDetailLoading(true);
    setDetailError(null);
    resetDetailFieldValues();
    try {
      setDetail(await serviceAssetApi.get(id));
      await loadFieldValuesForDetail(id);
    } catch (error) {
      setDetail(null);
      setDetailError(getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.detail.loadFailed')));
    } finally {
      setDetailLoading(false);
    }
  }, [loadFieldValuesForDetail, resetDetailFieldValues, t]);

  const openDetail = (row: ServiceAsset) => {
    detailRetryIdRef.current = row.id;
    setDetailOpen(true);
    setDetail(null);
    setDetailError(null);
    void loadDetail(row.id);
  };

  const columns: ProColumns<ServiceAsset>[] = useMemo(
    () =>
      alignProColumns<ServiceAsset>(
        [
          {
            title: t('app.kuaizhizao.afterSalesService.serviceAsset.field.assetCode'),
            dataIndex: 'asset_code',
            width: 188,
            minWidth: 188,
            uniTableKeepWidth: true,
            resizable: false,
            fixed: 'left',
            copyable: true,
          },
          {
            title: t('app.kuaizhizao.afterSalesService.serviceAsset.field.customerName'),
            dataIndex: 'customer_name',
            ...AFTER_SALES_CUSTOMER_NAME_COLUMN_DEFAULTS,
          },
          {
            // 产品名称长短不一：唯一 RemainderFlex；key 专用段位，避免 material_name 全局 79.3 把保修列挤到产品前
            title: t('app.kuaizhizao.afterSalesService.serviceAsset.field.materialName'),
            key: 'service_asset_material_name',
            dataIndex: 'material_name',
            minWidth: 160,
            uniTableRemainderFlex: true,
            uniTablePrimaryFlex: true,
            resizable: false,
            ellipsis: true,
          },
          {
            title: t('app.kuaizhizao.afterSalesService.serviceAsset.field.serialNumber'),
            dataIndex: 'serial_number',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            ellipsis: true,
            copyable: true,
          },
          {
            title: t('app.kuaizhizao.afterSalesService.serviceAsset.field.installAddress'),
            dataIndex: 'install_address',
            width: 160,
            minWidth: 160,
            uniTableKeepWidth: true,
            resizable: false,
            ellipsis: true,
            hideInSearch: true,
            render: (_, row) => {
              const text = String(row.install_address ?? '').trim();
              return text || '—';
            },
          },
          {
            title: t('app.kuaizhizao.afterSalesService.serviceAsset.field.warrantyMonths'),
            dataIndex: 'warranty_months',
            width: 100,
            minWidth: 100,
            uniTableKeepWidth: true,
            resizable: false,
            align: 'right',
            hideInSearch: true,
            render: (_, row) => (row.warranty_months != null ? row.warranty_months : '—'),
          },
          {
            title: t('app.kuaizhizao.afterSalesService.serviceAsset.field.warrantyPolicy'),
            dataIndex: 'warranty_policy',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            ellipsis: true,
            hideInSearch: true,
            render: (_, row) => {
              const text = String(row.warranty_policy ?? '').trim();
              return text || '—';
            },
          },
          ...customFieldColumns,
          {
            title: t('common.status'),
            key: 'lifecycle',
            dataIndex: 'status',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) =>
              renderAfterSalesStatusTag(row.status, AFTER_SALES_ASSET_STATUS_COLOR),
          },
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) => [
              <Button {...rowActionKind('read')} key="read" onClick={() => openDetail(row)} />,
              perms.canUpdate ? (
                <Button {...rowActionKind('update')} key="edit" onClick={() => void openEdit(row)} />
              ) : null,
            ],
          },
        ],
        SALES_DOC_LIST_FIELD_RANK,
      ),
    [customFieldColumns, perms.canUpdate, t],
  );

  return (
    <ListPageTemplate>
      <UniTable<ServiceAsset>
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.afterSalesServiceAsset)}
        actionRef={actionRef}
        columns={columns}
        columnPersistenceId="apps.kuaizhizao.pages.after-sales-service.service-assets.v9-cf"
        showAdvancedSearch
        skipFuzzyPinyinClientFilter
        rowKey="id"
        headerTitle={t('app.kuaizhizao.menu.after-sales-service.service-assets')}
        request={async (params, _sort, _filter, searchFormValues, meta?: UniTableRequestMeta) => {
          const res = await serviceAssetApi.list({
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize,
            keyword: pickListSearchKeyword(searchFormValues),
            status: pickSearchString(searchFormValues, 'status'),
          });
          const data =
            meta?.purpose === 'prefetch'
              ? res.items
              : await enrichRecordsWithCustomFields(res.items);
          return { data, total: res.total, success: true };
        }}
        showCreateButton={perms.canCreate}
        createButtonText={t('app.kuaizhizao.afterSalesService.serviceAsset.createTitle')}
        onCreate={openCreate}
        enableRowSelection={perms.canDelete}
        showDeleteButton={perms.canDelete}
        deleteButtonText={t('common.delete')}
        onDelete={async (keys) => {
          await Promise.all(keys.map((key) => serviceAssetApi.delete(Number(key))));
    messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
    actionRef.current?.reload();
        }}
      />

      <ServiceAssetFormModal
        open={modalOpen}
        editing={editing}
        onClose={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onSuccess={() => {
          actionRef.current?.reload();
        }}
      />

      <ServiceAssetDetailDrawer
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          setDetail(null);
          setDetailError(null);
          resetDetailFieldValues();
        }}
        record={detail}
        loading={detailLoading}
        error={detailError}
        onRetry={() => {
          const id = detailRetryIdRef.current;
          if (id != null) void loadDetail(id);
        }}
        supplementaryTitle={
          showDetailCustomFields
            ? t('app.master-data.customFields', { defaultValue: '自定义字段' })
            : undefined
        }
        supplementary={
          showDetailCustomFields ? (
            <CustomFieldsDetailSection
              customFields={listCustomFields}
              customFieldValues={detailCustomFieldValues}
            />
          ) : undefined
        }
        extra={buildDetailDrawerEditExtra(t, Boolean(detail && perms.canUpdate), () => {
          if (!detail) return;
          void openEdit(detail);
        })}
      />
    </ListPageTemplate>
  );
};

export default ServiceAssetsPage;
