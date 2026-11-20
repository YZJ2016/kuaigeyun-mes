/**
 * 接口管理列表页面
 *
 * 用于系统管理员查看和管理组织内的接口。
 * 支持接口的 CRUD 操作和接口测试功能。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ActionType,
  ProColumns,
  ProDescriptionsItemProps,
} from '@ant-design/pro-components'
import {
  App,
  Popconfirm,
  Button,
  Progress,
  Tag,
  Space,
} from 'antd'
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../utils/uniTableLayoutColumns'
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../../../apps/kuaizhizao/pages/sales-management/shared/documentFieldAlignment'
import { renderSystemActiveTag, renderSystemTypeMarker } from '../../utils/systemListPresentation'
import {
  ClearOutlined,
  DatabaseOutlined,
} from '@ant-design/icons'
import { UniTable } from '../../../../components/uni-table'
import { SystemMasterDetailDrawer } from '../../shared/systemMasterDetailDrawer'
import { getApiErrorMessage } from '../../../../utils/errorHandler'
import {
  getAPIList,
  getAPIListAllMatching,
  getAPIByUuid,
  createAPI,
  updateAPI,
  deleteAPI,
  API,
  CreateAPIData,
  UpdateAPIData,
} from '../../../../services/apiManagement'
import { CODE_FONT_FAMILY } from '../../../../constants/fonts'
import {
  extractProTableSort,
  mapApiListSortField,
  pickListSearchKeywordOrFields,
  pickSearchString,
  pickSearchTriStateBoolean,
} from '../../../../utils/tableQueryKey'
import { rowActionKind, rowActionLabelKeep } from '../../../../components/uni-action'
import {
  buildApiImportTemplate,
  dedupeApisByNormalizedCode,
  exportApisToXlsx,
  importApisFromSpreadsheet,
  planApiCodeDedup,
} from '../../../../utils/apiImportExport'
import { ImportResultModalContent } from '../../../../utils/importResultModalContent';
import { todaySiteDateString } from '../../../../utils/format';
import { buildListPageHelpViewConfig } from '../../../../components/page-help-wiki';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import {
  getBusinessSystemConnectionsForApi,
  type DataConnectionGroupOption,
  type IntegrationConfig,
} from '../../../../services/integrationConfig';
import { useResourceCategoryPanel } from '../../shared/useResourceCategoryPanel';
import { RESOURCE_CATEGORY_UNCATEGORIZED_KEY, type ResourceCategoryListFilter } from '../../../../services/resourceCategory';
import { ApiLibraryModal } from '../ApiLibraryModal';
import { ApiTestDrawer } from '../ApiTestDrawer';
import { ApiFormModal, normalizeApiFormInitialValues, type ApiFormSubmitValues } from '../ApiFormModal';
import { DEFAULT_API_REQUEST_PAGE_SIZE } from '../apiFormUtils';
import { TwoColumnLayout } from '../../../../components/layout-templates';


/**
 * 接口管理列表页面组件
 */
const APIListPage: React.FC = () => {
  const { t } = useTranslation()
  const { message: messageApi, modal: modalApi } = App.useApp()
  const connectionPerms = useResourcePermissions('system:application-connection')
  const apiPerms = useResourcePermissions('system:api')
  const actionRef = useRef<ActionType>(null)
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [dedupeLoading, setDedupeLoading] = useState(false)

  const reloadList = useCallback(() => {
    actionRef.current?.reload()
  }, [])

  const categoryListFilterRef = useRef<ResourceCategoryListFilter>({})

  const handleCategorySelectionChange = useCallback(
    (nextFilter: ResourceCategoryListFilter) => {
      categoryListFilterRef.current = nextFilter
      reloadList()
    },
    [reloadList],
  )

  const {
    leftPanel: categoryLeftPanel,
    listFilter: categoryListFilter,
    selectedCategoryKey,
    categorySelectOptions,
    reloadCategories,
    categoryFormModal,
  } = useResourceCategoryPanel({
    resourceType: 'api',
    onSelectionChange: handleCategorySelectionChange,
  })

  categoryListFilterRef.current = categoryListFilter

  // Modal 相关状态（创建/编辑接口）
  const [libraryModalOpen, setLibraryModalOpen] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [isEdit, setIsEdit] = useState(false)
  const [currentApiUuid, setCurrentApiUuid] = useState<string | null>(null)
  const [formLoading, setFormLoading] = useState(false)
  const [formInitialValues, setFormInitialValues] = useState<Record<string, any> | undefined>(
    undefined
  )

  // Drawer 相关状态（详情查看）
  const [drawerVisible, setDrawerVisible] = useState(false)
  const [detailData, setDetailData] = useState<API | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const detailRetryUuidRef = useRef<string | null>(null)

  // 测试接口状态
  const [testDrawerVisible, setTestDrawerVisible] = useState(false)
  const [testingApiUuid, setTestingApiUuid] = useState<string | null>(null)
  const [connectionGroups, setConnectionGroups] = useState<DataConnectionGroupOption[]>([])
  const [connectionItems, setConnectionItems] = useState<IntegrationConfig[]>([])

  useEffect(() => {
    if (!connectionPerms.canRead) return
    void getBusinessSystemConnectionsForApi()
      .then(({ groups, items }) => {
        setConnectionGroups(groups)
        setConnectionItems(items)
      })
      .catch(() => {
        // 无连接器读权限或列表为空时不阻断接口管理
      })
  }, [connectionPerms.canRead])

  /**
   * 处理新建接口
   */
  const handleCreate = () => {
    setIsEdit(false)
    setCurrentApiUuid(null)
    const presetCategoryUuid =
      selectedCategoryKey !== 'all' && selectedCategoryKey !== RESOURCE_CATEGORY_UNCATEGORIZED_KEY
        ? selectedCategoryKey
        : undefined
    setFormInitialValues({
      method: 'GET',
      sync_direction: 'pull',
      api_interface_type: 'custom',
      is_active: true,
      is_system: false,
      category_uuid: presetCategoryUuid,
      request_headers: [],
      request_params: [],
      request_body: { pageNo: 1, pageSize: DEFAULT_API_REQUEST_PAGE_SIZE },
    })
    setModalVisible(true)
  }

  /**
   * 处理编辑接口
   */
  const handleEdit = async (record: API) => {
    try {
      setIsEdit(true)
      setCurrentApiUuid(record.uuid)

      // 获取接口详情
      const detail = await getAPIByUuid(record.uuid)
      setFormInitialValues(normalizeApiFormInitialValues(detail))
      setModalVisible(true)
    } catch (error: any) {
      messageApi.error(error.message || t('pages.system.apis.getDetailFailed'))
    }
  }

  /**
   * 处理查看详情
   */
  const loadDetail = async (uuid: string) => {
    setDetailLoading(true)
    setDetailError(null)
    try {
      const detail = await getAPIByUuid(uuid)
      setDetailData(detail)
    } catch (error) {
      setDetailData(null)
      setDetailError(getApiErrorMessage(error, t('pages.system.apis.getDetailFailed')))
    } finally {
      setDetailLoading(false)
    }
  }

  const handleView = async (record: API) => {
    detailRetryUuidRef.current = record.uuid
    setDrawerVisible(true)
    setDetailData(null)
    setDetailError(null)
    void loadDetail(record.uuid)
  }

  const apiDetailDescColumns = useMemo<ProDescriptionsItemProps<API>[]>(
    () => [
      { title: t('pages.system.apis.detailColumnName'), dataIndex: 'name' },
      { title: t('pages.system.apis.detailColumnCode'), dataIndex: 'code' },
      { title: t('common.remark'), dataIndex: 'description' },
      {
        title: t('pages.system.apis.detailColumnMethod'),
        dataIndex: 'method',
        render: (_dom, entity: API) => <Tag color="blue">{entity.method}</Tag>,
      },
      {
        title: t('pages.system.apis.columnSyncDirection'),
        dataIndex: 'sync_direction',
        render: (_dom, entity: API) => {
          const direction = entity.sync_direction || 'pull'
          const colors: Record<string, string> = {
            pull: 'processing',
            push: 'warning',
            bidirectional: 'purple',
          }
          return renderSystemTypeMarker(
            t(`pages.system.apis.syncDirection.${direction}`),
            colors[direction] || 'default',
          )
        },
      },
      { title: t('pages.system.apis.detailColumnPath'), dataIndex: 'path' },
      {
        title: t('pages.system.apis.detailColumnConnection'),
        dataIndex: 'connection_name',
        render: (_dom, entity: API) =>
          entity.connection_name
            ? `${entity.connection_name}${entity.connection_type ? ` (${entity.connection_type})` : ''}`
            : '-',
      },
      {
        title: t('pages.system.apis.detailColumnRequestHeaders'),
        dataIndex: 'request_headers',
        render: (_dom, entity: API) => (
          <pre
            style={{
              margin: 0,
              padding: '8px',
              backgroundColor: '#f5f5f5',
              borderRadius: '4px',
              overflow: 'auto',
              maxHeight: '200px',
              fontSize: 12,
            }}
          >
            {JSON.stringify(entity.request_headers || {}, null, 2)}
          </pre>
        ),
      },
      {
        title: t('pages.system.apis.detailColumnRequestParams'),
        dataIndex: 'request_params',
        render: (_dom, entity: API) => (
          <pre
            style={{
              margin: 0,
              padding: '8px',
              backgroundColor: '#f5f5f5',
              borderRadius: '4px',
              overflow: 'auto',
              maxHeight: '200px',
              fontSize: 12,
            }}
          >
            {JSON.stringify(entity.request_params || {}, null, 2)}
          </pre>
        ),
      },
      {
        title: t('pages.system.apis.detailColumnRequestBody'),
        dataIndex: 'request_body',
        render: (_dom, entity: API) => (
          <pre
            style={{
              margin: 0,
              padding: '8px',
              backgroundColor: '#f5f5f5',
              borderRadius: '4px',
              overflow: 'auto',
              maxHeight: '200px',
              fontSize: 12,
            }}
          >
            {JSON.stringify(entity.request_body || {}, null, 2)}
          </pre>
        ),
      },
      {
        title: t('pages.system.apis.detailColumnResponseFormat'),
        dataIndex: 'response_format',
        render: (_dom, entity: API) => (
          <pre
            style={{
              margin: 0,
              padding: '8px',
              backgroundColor: '#f5f5f5',
              borderRadius: '4px',
              overflow: 'auto',
              maxHeight: '200px',
              fontSize: 12,
            }}
          >
            {JSON.stringify(entity.response_format || {}, null, 2)}
          </pre>
        ),
      },
      {
        title: t('pages.system.apis.detailColumnResponseExample'),
        dataIndex: 'response_example',
        render: (_dom, entity: API) => (
          <pre
            style={{
              margin: 0,
              padding: '8px',
              backgroundColor: '#f5f5f5',
              borderRadius: '4px',
              overflow: 'auto',
              maxHeight: '200px',
              fontSize: 12,
            }}
          >
            {JSON.stringify(entity.response_example || {}, null, 2)}
          </pre>
        ),
      },
      {
        title: t('pages.system.apis.detailColumnActive'),
        dataIndex: 'is_active',
        render: (_dom, entity: API) =>
          renderSystemActiveTag(t, entity.is_active, 'common.enabled', 'common.disabled'),
      },
      {
        title: t('pages.system.apis.detailColumnSystem'),
        dataIndex: 'is_system',
        render: (_dom, entity: API) =>
          renderSystemTypeMarker(
            entity.is_system ? t('pages.system.apis.systemTag') : t('pages.system.apis.customTag'),
            entity.is_system ? 'purple' : 'default',
          ),
      },
      { title: t('common.createdAt'), dataIndex: 'created_at', valueType: 'dateTime' },
      { title: t('common.updatedAt'), dataIndex: 'updated_at', valueType: 'dateTime' },
    ],
    [t]
  )

  /**
   * 处理删除接口
   */
  const handleDelete = async (record: API) => {
    try {
      await deleteAPI(record.uuid)
      messageApi.success(t('common.deleteSuccess'))
      actionRef.current?.reload()
      void reloadCategories()
    } catch (error: any) {
      messageApi.error(error.message || t('common.deleteFailed'))
    }
  }

  /**
   * 批量删除接口（系统接口会由后端拒绝）
   */
  const handleBatchDelete = async (keys: React.Key[]) => {
    try {
      let done = 0
      let fail = 0
      for (const uuid of keys) {
        try {
          await deleteAPI(String(uuid))
          done++
        } catch {
          fail++
        }
      }
      if (fail > 0) {
        messageApi.warning(t('pages.system.apis.batchDeleteDone', { done, fail }))
      } else {
        messageApi.success(t('pages.system.apis.batchDeleteSuccessCount', { count: done }))
      }
      setSelectedRowKeys([])
      actionRef.current?.reload()
      void reloadCategories()
    } catch (error: any) {
      messageApi.error(error.message || t('pages.system.apis.batchDeleteFailed'))
    }
  }

  /**
   * 处理测试接口
   */
  const handleTest = (record: API) => {
    setTestingApiUuid(record.uuid)
    setTestDrawerVisible(true)
  }

  /**
   * 处理提交表单（创建/更新接口）
   */
  const handleSubmit = async (values: ApiFormSubmitValues): Promise<void> => {
    try {
      setFormLoading(true)

      if (isEdit && currentApiUuid) {
        await updateAPI(currentApiUuid, {
          name: values.name,
          code: values.code,
          description: values.description,
          connection_uuid: values.connection_uuid ?? null,
          category_uuid: values.category_uuid ?? null,
          path: values.path,
          method: values.method,
          sync_direction: values.sync_direction,
          request_headers: values.request_headers,
          request_params: values.request_params,
          request_body: values.request_body,
          response_format: values.response_format,
          response_example: values.response_example,
          source_type_conversion_map: values.source_type_conversion_map ?? null,
          is_active: values.is_active,
        } as UpdateAPIData)
        messageApi.success(t('common.updateSuccess'))
      } else {
        await createAPI({
          name: values.name,
          code: values.code,
          description: values.description,
          connection_uuid: values.connection_uuid || undefined,
          category_uuid: values.category_uuid || undefined,
          path: values.path,
          method: values.method,
          sync_direction: values.sync_direction,
          request_headers: values.request_headers,
          request_params: values.request_params,
          request_body: values.request_body,
          response_format: values.response_format,
          response_example: values.response_example,
          source_type_conversion_map: values.source_type_conversion_map ?? null,
          is_active: values.is_active,
          is_system: values.is_system || false,
        } as CreateAPIData)
        messageApi.success(t('common.createSuccess'))
      }

      setModalVisible(false)
      setFormInitialValues(undefined)
      actionRef.current?.reload()
      void reloadCategories()
    } catch (error: any) {
      messageApi.error(error.message || t('common.operationFailed'))
      throw error
    } finally {
      setFormLoading(false)
    }
  }

  /** 按规范化 code 清理导入产生的重复接口 */
  const handleDedupeByCode = async () => {
    if (dedupeLoading) return
    setDedupeLoading(true)
    try {
      const all = await getAPIListAllMatching()
      const plan = planApiCodeDedup(all)
      if (plan.removeCount === 0) {
        messageApi.info(
          plan.skippedSystemCount > 0
            ? t('pages.system.apis.dedupeOnlySystemLeft', { count: plan.skippedSystemCount })
            : t('pages.system.apis.dedupeNoDuplicates'),
        )
        return
      }
      modalApi.confirm({
        title: t('pages.system.apis.dedupeConfirmTitle'),
        content: t('pages.system.apis.dedupeConfirmContent', {
          groups: plan.groups.length,
          remove: plan.removeCount,
          skipped: plan.skippedSystemCount,
        }),
        okText: t('pages.system.apis.dedupeConfirmOk'),
        cancelText: t('common.cancel'),
        onOk: async () => {
          const hide = messageApi.loading(t('pages.system.apis.dedupeRunning'), 0)
          try {
            const result = await dedupeApisByNormalizedCode()
            hide()
            if (result.failed > 0) {
              messageApi.warning(
                t('pages.system.apis.dedupeDonePartial', {
                  deleted: result.deleted,
                  failed: result.failed,
                  groups: result.groupCount,
                }),
              )
            } else {
              messageApi.success(
                t('pages.system.apis.dedupeDone', {
                  deleted: result.deleted,
                  groups: result.groupCount,
                }),
              )
            }
            setSelectedRowKeys([])
            actionRef.current?.reload()
            void reloadCategories()
          } catch (error: unknown) {
            hide()
            messageApi.error(
              getApiErrorMessage(error) || t('pages.system.apis.dedupeFailed'),
            )
          }
        },
      })
    } catch (error: unknown) {
      messageApi.error(getApiErrorMessage(error) || t('pages.system.apis.dedupeFailed'))
    } finally {
      setDedupeLoading(false)
    }
  }

  const apiImportTemplate = useMemo(() => buildApiImportTemplate(t), [t])

  const columns = useMemo<ProColumns<API>[]>(() => alignProColumns<API>([
    {
      title: t('pages.system.apis.columnName'),
      dataIndex: 'name',
      width: 180,
      minWidth: 180,
      uniTableKeepWidth: true,
      resizable: false,
      ellipsis: true,
      sorter: true,
    },
    {
      title: t('pages.system.apis.columnCode'),
      dataIndex: 'code',
      width: 140,
      minWidth: 140,
      uniTableKeepWidth: true,
      resizable: false,
      ellipsis: true,
      hideInSearch: true,
    },
    {
      title: t('pages.system.apis.columnMethod'),
      dataIndex: 'method',
      width: 100,
      minWidth: 100,
      uniTableKeepWidth: true,
      resizable: false,
      valueType: 'select',
      valueEnum: {
        GET: { text: 'GET', status: 'Success' },
        POST: { text: 'POST', status: 'Processing' },
        PUT: { text: 'PUT', status: 'Warning' },
        DELETE: { text: 'DELETE', status: 'Error' },
        PATCH: { text: 'PATCH', status: 'Default' },
      },
      render: (_, record) => {
        const methodColors: Record<string, string> = {
          GET: 'success',
          POST: 'processing',
          PUT: 'warning',
          DELETE: 'error',
          PATCH: 'default',
        }
        return renderSystemTypeMarker(record.method, methodColors[record.method] || 'default')
      },
    },
    {
      title: t('pages.system.apis.columnSyncDirection'),
      dataIndex: 'sync_direction',
      ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
      valueType: 'select',
      valueEnum: {
        pull: { text: t('pages.system.apis.syncDirection.pull') },
        push: { text: t('pages.system.apis.syncDirection.push') },
        bidirectional: { text: t('pages.system.apis.syncDirection.bidirectional') },
      },
      render: (_, record) => {
        const direction = record.sync_direction || 'pull'
        const colors: Record<string, string> = {
          pull: 'processing',
          push: 'warning',
          bidirectional: 'purple',
        }
        return renderSystemTypeMarker(
          t(`pages.system.apis.syncDirection.${direction}`),
          colors[direction] || 'default',
        )
      },
    },
    {
      title: t('pages.system.apis.columnRelatedDocument'),
      dataIndex: 'related_document_code',
      width: 120,
      minWidth: 120,
      uniTableKeepWidth: true,
      resizable: false,
      hideInSearch: true,
      render: (_, record) => {
        const code = record.related_document_code?.trim()
        if (!code) return '-'
        return t(`pages.system.apis.relatedDocument.${code}`, code)
      },
    },
    {
      title: t('pages.system.apis.columnApiInterfaceType'),
      dataIndex: 'api_interface_type',
      width: 112,
      minWidth: 112,
      uniTableKeepWidth: true,
      resizable: false,
      hideInSearch: true,
      render: (_, record) =>
        t(`pages.system.apis.apiInterfaceType.${record.api_interface_type || 'custom'}`),
    },
    {
      title: t('pages.system.apis.columnConnection'),
      dataIndex: 'connection_name',
      width: 180,
      minWidth: 180,
      uniTableKeepWidth: true,
      resizable: false,
      ellipsis: true,
      hideInSearch: true,
      render: (_, record) =>
        record.connection_name
          ? `${record.connection_name}${record.connection_type ? ` (${record.connection_type})` : ''}`
          : '-',
    },
    {
      // 备注长短不一：唯一 RemainderFlex
      title: t('common.remark'),
      dataIndex: 'description',
      minWidth: 140,
      uniTableRemainderFlex: true,
      uniTablePrimaryFlex: true,
      resizable: false,
      ellipsis: true,
      hideInSearch: true,
    },
    {
      title: t('pages.system.apis.columnActive'),
      dataIndex: 'is_active',
      ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
      valueType: 'select',
      valueEnum: {
        true: { text: t('common.enabled'), status: 'Success' },
        false: { text: t('common.disabled'), status: 'Default' },
      },
      render: (_, record) =>
        renderSystemActiveTag(t, record.is_active, 'common.enabled', 'common.disabled'),
    },
    {
      title: t('pages.system.apis.columnSystem'),
      dataIndex: 'is_system',
      ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
      hideInSearch: true,
      render: (_, record) =>
        renderSystemTypeMarker(
          record.is_system ? t('pages.system.apis.systemTag') : t('pages.system.apis.customTag'),
          record.is_system ? 'purple' : 'default',
        ),
    },
    {
      title: t('common.createdAt'),
      dataIndex: 'created_at',
      width: 180,
      minWidth: 180,
      uniTableKeepWidth: true,
      resizable: false,
      valueType: 'dateTime',
      hideInSearch: true,
      sorter: true,
    },
    {
      title: t('common.actions'),
      key: 'action',
      fixed: 'right',
      hideInSearch: true,
      render: (_, record) => {
        const actions: React.ReactNode[] = [
          <Button key="view" {...rowActionKind('read')} onClick={() => handleView(record)} />,
          <Button key="edit" {...rowActionKind('update')} onClick={() => handleEdit(record)} />,
          <Button key="test" {...rowActionKind('skip')} {...rowActionLabelKeep()} onClick={() => handleTest(record)}>
            {t('pages.system.apis.test')}
          </Button>,
        ]
        if (!record.is_system) {
          actions.push(
            <Popconfirm key="delete" title={t('pages.system.apis.deleteConfirmTitle')} onConfirm={() => handleDelete(record)}>
              <Button {...rowActionKind('delete')} />
            </Popconfirm>,
          )
        }
        return actions
      },
    },
  ], GLOBAL_DOC_LIST_FIELD_RANK), [t, handleView, handleEdit, handleTest, handleDelete])

  return (
    <>
      <TwoColumnLayout
        style={{ height: '100%' }}
        layoutPersistenceId="pages.system.apis.list"
        leftPanel={categoryLeftPanel}
        rightPanel={{
          content: (
            <UniTable<API>
        viewTypes={['table', 'help']}
          helpViewConfig={buildListPageHelpViewConfig('system.apis')}
          columnPersistenceId="pages.system.apis.list-v7"
          tanstackQuery={{ queryKeyPrefix: ['pages.system.apis.list', selectedCategoryKey] }}
          actionRef={actionRef}
          columns={columns}
          request={async (params, sort, _filter, searchFormValues) => {
            const { sortBy, sortOrder } = extractProTableSort(sort)
            const categoryFilter = categoryListFilterRef.current
            // 处理搜索参数
            const apiParams: any = {
              page: params.current || 1,
              page_size: params.pageSize || 20,
              sort_by: mapApiListSortField(sortBy),
              sort_order: sortOrder,
              ...categoryFilter,
            }

            const search = pickListSearchKeywordOrFields(searchFormValues, 'search')
            if (search) {
              apiParams.search = search
            }

            const method = pickSearchString(searchFormValues, 'method')
            if (method) {
              apiParams.method = method
            }

            const syncDirection = pickSearchString(searchFormValues, 'sync_direction')
            if (syncDirection) {
              apiParams.sync_direction = syncDirection
            }

            const isActive = pickSearchTriStateBoolean(searchFormValues, 'is_active')
            if (isActive !== undefined) {
              apiParams.is_active = isActive
            }

            try {
              const result = await getAPIList(apiParams)
              return {
                data: result.items,
                success: true,
                total: result.total,
              }
            } catch (error: any) {
              console.error('获取接口列表失败:', error)
              messageApi.error(error?.message || t('pages.system.apis.loadListFailed'))
              return {
                data: [],
                success: false,
                total: 0,
              }
            }
          }}
          rowKey="uuid"
          showAdvancedSearch={true}
          enableRowSelection
          onRowSelectionChange={setSelectedRowKeys}
          rowSelection={{ selectedRowKeys, onChange: setSelectedRowKeys }}
          showDeleteButton
          onDelete={handleBatchDelete}
          deleteButtonText={t('common.batchDelete')}
          deleteConfirmTitle={t('pages.system.apis.batchDeleteTitle')}
          deleteConfirmDescription={(c) => t('pages.system.apis.batchDeleteDescription', { count: c })}
          toolBarActionsAfterDelete={
            apiPerms.canCreate || apiPerms.canDelete
              ? [
                  ...(apiPerms.canCreate
                    ? [
                        <Button
                          key="api-library"
                          icon={<DatabaseOutlined />}
                          onClick={() => setLibraryModalOpen(true)}
                        >
                          {t('pages.system.apis.libraryButton')}
                        </Button>,
                      ]
                    : []),
                  ...(apiPerms.canDelete
                    ? [
                        <Button
                          key="api-dedupe"
                          icon={<ClearOutlined />}
                          loading={dedupeLoading}
                          onClick={() => void handleDedupeByCode()}
                        >
                          {t('pages.system.apis.dedupeButton')}
                        </Button>,
                      ]
                    : []),
                ]
              : undefined
          }
          showCreateButton
          onCreate={handleCreate}
          createButtonText={t('pages.system.apis.createButton')}
          showImportButton
          importHeaders={apiImportTemplate.importHeaders}
          importExampleRow={apiImportTemplate.importExampleRow}
          importFieldMap={apiImportTemplate.importHeaderMap}
          onImport={async data => {
            if (!data || data.length < 2) {
              messageApi.warning(t('pages.system.apis.fillImportData'))
              return
            }
            const progressModal = modalApi.info({
              title: t('pages.system.apis.importProgressTitle'),
              content: (
                <div>
                  <Progress percent={0} status="active" />
                  <p style={{ marginTop: 16 }}>{t('pages.system.apis.importProgressPreparing')}</p>
                </div>
              ),
              okButtonProps: { style: { display: 'none' } },
              closable: false,
              mask: { closable: false },
              keyboard: false,
            })
            try {
              const result = await importApisFromSpreadsheet({
                t,
                data,
                connections: connectionItems,
                onProgress: (done, totalRows, partial) => {
                  const percent =
                    totalRows > 0 ? Math.min(100, Math.round((done / totalRows) * 100)) : 0
                  progressModal.update({
                    content: (
                      <div>
                        <Progress percent={percent} status="active" />
                        <p style={{ marginTop: 16 }}>
                          {t('pages.system.apis.importProgressLine', {
                            done,
                            total: totalRows,
                          })}
                        </p>
                        <p style={{ marginTop: 8, color: 'rgba(0,0,0,0.65)' }}>
                          {t('pages.system.apis.importProgressCounts', {
                            created: partial.created,
                            updated: partial.updated,
                            failed: partial.failed,
                          })}
                        </p>
                      </div>
                    ),
                  })
                },
              })
              progressModal.destroy()
              const successCount = result.created + result.updated
              if (successCount === 0 && result.failed === 0) {
                messageApi.warning(t('pages.system.apis.fillImportData'))
                return
              }
              if (result.failed > 0) {
                modalApi.warning({
                  title: t('pages.system.apis.importResultTitle'),
                  width: 720,
                  content: (
                    <ImportResultModalContent
                      successCount={successCount}
                      failureCount={result.failed}
                      errors={result.errors.map(e => ({
                        row: e.row,
                        error: e.code ? `[${e.code}] ${e.error}` : e.error,
                      }))}
                    />
                  ),
                })
              } else {
                messageApi.success(
                  t('pages.system.apis.importBackupResult', {
                    created: result.created,
                    updated: result.updated,
                    failed: result.failed,
                  }),
                )
              }
              actionRef.current?.reload()
              reloadCategories()
            } catch (error: any) {
              progressModal.destroy()
              messageApi.error(getApiErrorMessage(error) || t('pages.system.apis.importFailed'))
            }
          }}
          showExportButton
          onExport={async (type, keys, pageData) => {
            try {
              const count = await exportApisToXlsx({
                t,
                type,
                keys: keys as Array<string | number> | undefined,
                pageData: pageData as API[] | undefined,
                connections: connectionItems,
                fileName: `apis-${todaySiteDateString()}.xlsx`,
              })
              if (count === 0) {
                messageApi.warning(t('common.exportNoData'))
                return
              }
              messageApi.success(t('pages.system.apis.exportSuccessCount', { count }))
            } catch (error: any) {
              messageApi.error(getApiErrorMessage(error) || t('pages.system.apis.exportFailed'))
            }
          }}
          pagination={{
            defaultPageSize: 20,
            showSizeChanger: true,
          }}
        />
          ),
        }}
      />

      {categoryFormModal}

      <ApiLibraryModal
        open={libraryModalOpen}
        onClose={() => setLibraryModalOpen(false)}
        onInstalled={() => {
          reloadList()
          void reloadCategories()
        }}
      />

      <ApiFormModal
        open={modalVisible}
        onClose={() => {
          setModalVisible(false)
          setFormInitialValues(undefined)
        }}
        onFinish={handleSubmit}
        isEdit={isEdit}
        initialValues={formInitialValues}
        loading={formLoading}
        connectionGroups={connectionGroups}
        connectionItems={connectionItems}
        categorySelectOptions={categorySelectOptions}
        canReadConnection={connectionPerms.canRead}
      />

      {/* 查看详情 Drawer */}
      <SystemMasterDetailDrawer
        title={t('pages.system.apis.detailTitle')}
        open={drawerVisible}
        basicColumn={1}
        onClose={() => {
          setDrawerVisible(false)
          setDetailData(null)
          setDetailError(null)
        }}
        detail={detailData}
        detailColumns={apiDetailDescColumns}
        loading={detailLoading}
        error={detailError}
        onRetry={() => {
          const uuid = detailRetryUuidRef.current
          if (uuid) void loadDetail(uuid)
        }}
      />

      <ApiTestDrawer
        open={testDrawerVisible}
        apiUuid={testingApiUuid}
        onClose={() => {
          setTestDrawerVisible(false)
          setTestingApiUuid(null)
        }}
      />
    </>
  )
}

export default APIListPage
