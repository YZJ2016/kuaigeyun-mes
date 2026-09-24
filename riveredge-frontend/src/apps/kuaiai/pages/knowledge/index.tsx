import React, { useMemo, useRef, useState } from 'react';
import {
  App,
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from 'antd';
import { InboxOutlined, PlusOutlined } from '@ant-design/icons';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import type { ColumnsType } from 'antd/es/table';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import { hasPermission } from '../../../../utils/permission';
import { uploadFile } from '../../../../services/file';
import {
  createDocument,
  createKnowledgeBase,
  deleteDocument,
  deleteKnowledgeBase,
  DOCUMENT_RAW_SOURCE_TYPES,
  listChunks,
  listDocuments,
  listKnowledgeBases,
  parseDocument,
  sourceTypeFromFileName,
  updateKnowledgeBase,
  type ChunkOut,
  type DocumentListOut,
  type KnowledgeBaseOut,
} from '../../services/knowledge';
import { listModelOptions } from '../../services/models';
import { KUAI_AI_OPTION_KEYS, KUAI_AI_OPTIONS_PREFIX } from '../../constants';

const K = 'app.kuaiai.knowledge';

const STATUS_ENABLED = '启用';
const STATUS_DISABLED = '停用';

const FILE_ACCEPT = '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.md,.txt';

function fmtTime(v?: string | null) {
  return v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '—';
}

function docStatusTag(status: string, errorMessage: string | null | undefined, t: (k: string, o?: any) => string) {
  const map: Record<string, { color: string; label: string }> = {
    pending: { color: 'default', label: t(`${K}.doc.status.pending`, { defaultValue: '待解析' }) },
    parsing: { color: 'processing', label: t(`${K}.doc.status.parsing`, { defaultValue: '解析中' }) },
    ready: { color: 'success', label: t(`${K}.doc.status.ready`, { defaultValue: '已就绪' }) },
    failed: { color: 'error', label: t(`${K}.doc.status.failed`, { defaultValue: '解析失败' }) },
  };
  const conf = map[status] || { color: 'default', label: status };
  const tag = <Tag color={conf.color}>{conf.label}</Tag>;
  if (status === 'failed' && errorMessage) {
    return <Tooltip title={errorMessage}>{tag}</Tooltip>;
  }
  return tag;
}

export default function KuaiaiKnowledgePage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const currentUser = useCurrentUser();
  const canAdd = hasPermission(currentUser, 'kuaiai:knowledge:add');
  const canEdit = hasPermission(currentUser, 'kuaiai:knowledge:edit');
  const canRemove = hasPermission(currentUser, 'kuaiai:knowledge:remove');

  const actionRef = useRef<ActionType>(null);
  const queryClient = useQueryClient();
  const [kbForm] = Form.useForm();
  const [kbModalOpen, setKbModalOpen] = useState(false);
  const [editingKb, setEditingKb] = useState<KnowledgeBaseOut | null>(null);

  // 文档抽屉
  const [docKb, setDocKb] = useState<KnowledgeBaseOut | null>(null);
  const [docPage, setDocPage] = useState(1);
  const [docPageSize, setDocPageSize] = useState(10);
  const [docModalOpen, setDocModalOpen] = useState(false);
  const [docTab, setDocTab] = useState<'file' | 'raw'>('file');
  const [docFile, setDocFile] = useState<File | null>(null);
  const [docSubmitting, setDocSubmitting] = useState(false);
  const [fileForm] = Form.useForm();
  const [rawForm] = Form.useForm();

  // 切块抽屉
  const [chunksDoc, setChunksDoc] = useState<DocumentListOut | null>(null);
  const [chunkPage, setChunkPage] = useState(1);
  const [chunkPageSize, setChunkPageSize] = useState(20);

  const { data: embedOptions } = useQuery({
    queryKey: KUAI_AI_OPTION_KEYS.embedModels,
    queryFn: () => listModelOptions('embed'),
    // /llm-models/options 需 kuaiai:model:query；无权限不打 403，下拉恒空
    enabled: hasPermission(currentUser, 'kuaiai:model:query'),
    staleTime: 60_000,
  });

  const embedLabel = (id?: number | null) => {
    if (id === null || id === undefined) return '—';
    const m = (embedOptions || []).find((o) => o.id === id);
    if (!m) return `#${id}`;
    return m.provider_name ? `${m.provider_name} / ${m.model_name}` : m.model_name;
  };

  const embedSelectOptions = useMemo(
    () =>
      (embedOptions || []).map((o) => ({
        value: o.id,
        label: o.provider_name ? `${o.provider_name} / ${o.model_name}` : o.model_name,
      })),
    [embedOptions],
  );

  const docsQuery = useQuery({
    queryKey: ['kuaiai', 'documents', docKb?.id, docPage, docPageSize],
    queryFn: () => listDocuments(docKb!.id, { page: docPage, page_size: docPageSize }),
    enabled: !!docKb,
    // pending/parsing 时每 4s 轮询直至终态
    refetchInterval: (query) =>
      (query.state.data?.items || []).some((d) => d.status === 'parsing' || d.status === 'pending')
        ? 4000
        : false,
  });

  const chunksQuery = useQuery({
    queryKey: ['kuaiai', 'chunks', chunksDoc?.id, chunkPage, chunkPageSize],
    queryFn: () => listChunks(chunksDoc!.id, { page: chunkPage, page_size: chunkPageSize }),
    enabled: !!chunksDoc,
  });

  const openCreateKb = () => {
    setEditingKb(null);
    kbForm.resetFields();
    kbForm.setFieldsValue({ status: STATUS_ENABLED });
    setKbModalOpen(true);
  };

  const openEditKb = (kb: KnowledgeBaseOut) => {
    setEditingKb(kb);
    kbForm.resetFields();
    kbForm.setFieldsValue({
      name: kb.name,
      description: kb.description ?? undefined,
      embedding_model_id: kb.embedding_model_id ?? undefined,
      chunk_size: kb.chunk_size ?? undefined,
      chunk_overlap: kb.chunk_overlap ?? undefined,
      expand_enabled: kb.expand_enabled ?? undefined,
      status: kb.status,
    });
    setKbModalOpen(true);
  };

  const handleKbSubmit = async () => {
    try {
      const values = await kbForm.validateFields();
      const payload = {
        name: values.name,
        description: values.description || null,
        embedding_model_id: values.embedding_model_id ?? null,
        chunk_size: values.chunk_size ?? null,
        chunk_overlap: values.chunk_overlap ?? null,
        expand_enabled: values.expand_enabled ?? null,
        status: values.status,
      };
      if (editingKb) {
        await updateKnowledgeBase(editingKb.id, payload);
        message.success(t('common.updateSuccess'));
      } else {
        await createKnowledgeBase(payload);
        message.success(t('common.createSuccess'));
      }
      setKbModalOpen(false);
      // 知识库变化影响档案表单的 knowledge_ids 下拉缓存
      void queryClient.invalidateQueries({ queryKey: KUAI_AI_OPTIONS_PREFIX });
      actionRef.current?.reload();
    } catch (error: any) {
      if (error?.errorFields) return; // 表单校验错误已在界面上提示
      message.error(error?.message || t('common.saveFailed', { defaultValue: '保存失败' }));
    }
  };

  const openDocs = (kb: KnowledgeBaseOut) => {
    setDocKb(kb);
    setDocPage(1);
  };

  const openDocModal = () => {
    setDocTab('file');
    setDocFile(null);
    fileForm.resetFields();
    rawForm.resetFields();
    setDocModalOpen(true);
  };

  const handleCreateDocument = async () => {
    if (!docKb) return;
    setDocSubmitting(true);
    try {
      if (docTab === 'file') {
        const values = await fileForm.validateFields();
        if (!docFile) {
          message.warning(t(`${K}.doc.fileRequired`, { defaultValue: '请选择文件' }));
          return;
        }
        const sourceType = sourceTypeFromFileName(docFile.name);
        if (!sourceType) {
          message.error(
            t(`${K}.doc.unsupportedType`, { defaultValue: '不支持的文件类型' }),
          );
          return;
        }
        const uploaded = await uploadFile(docFile);
        await createDocument(docKb.id, {
          title: values.title,
          source_type: sourceType,
          file_uuid: uploaded.uuid,
        });
      } else {
        const values = await rawForm.validateFields();
        await createDocument(docKb.id, {
          title: values.title,
          source_type: values.source_type,
          raw_content: values.raw_content,
        });
      }
      message.success(t('common.createSuccess'));
      setDocModalOpen(false);
      void docsQuery.refetch();
    } catch (error: any) {
      if (error?.errorFields) return; // 表单校验错误已在界面上提示
      message.error(error?.message || t('common.createFailed'));
    } finally {
      setDocSubmitting(false);
    }
  };

  const handleParse = async (doc: DocumentListOut) => {
    try {
      await parseDocument(doc.id);
      message.success(t(`${K}.doc.parseSubmitted`, { defaultValue: '已提交解析任务' }));
      void docsQuery.refetch();
    } catch (error: any) {
      message.error(error?.message || t(`${K}.doc.parseFailed`, { defaultValue: '提交解析失败' }));
    }
  };

  const kbColumns: ProColumns<KnowledgeBaseOut>[] = useMemo(
    () => [
      {
        title: t(`${K}.name`, { defaultValue: '名称' }),
        dataIndex: 'name',
        width: 180,
        ellipsis: true,
        hideInSearch: true,
      },
      {
        title: t(`${K}.description`, { defaultValue: '描述' }),
        dataIndex: 'description',
        ellipsis: true,
        hideInSearch: true,
        render: (_, r) => r.description || '—',
      },
      {
        title: t(`${K}.embeddingModel`, { defaultValue: 'Embedding 模型' }),
        dataIndex: 'embedding_model_id',
        width: 180,
        ellipsis: true,
        hideInSearch: true,
        render: (_, r) => embedLabel(r.embedding_model_id),
      },
      {
        title: t(`${K}.chunkSize`, { defaultValue: '切块大小' }),
        dataIndex: 'chunk_size',
        width: 100,
        align: 'right',
        hideInSearch: true,
        render: (_, r) => r.chunk_size ?? t(`${K}.default`, { defaultValue: '默认' }),
      },
      {
        title: t(`${K}.chunkOverlap`, { defaultValue: '切块重叠' }),
        dataIndex: 'chunk_overlap',
        width: 100,
        align: 'right',
        hideInSearch: true,
        render: (_, r) => r.chunk_overlap ?? t(`${K}.default`, { defaultValue: '默认' }),
      },
      {
        title: t(`${K}.expandEnabled`, { defaultValue: '检索展开' }),
        dataIndex: 'expand_enabled',
        width: 100,
        hideInSearch: true,
        render: (_, r) =>
          r.expand_enabled === null || r.expand_enabled === undefined
            ? t(`${K}.default`, { defaultValue: '默认' })
            : r.expand_enabled
              ? t(`${K}.expandOn`, { defaultValue: '开启' })
              : t(`${K}.expandOff`, { defaultValue: '关闭' }),
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        width: 90,
        hideInSearch: true,
        render: (_, r) => (
          <Tag color={r.status === STATUS_ENABLED ? 'success' : 'default'}>{r.status}</Tag>
        ),
      },
      {
        title: t('common.createdAt'),
        dataIndex: 'created_at',
        width: 160,
        hideInSearch: true,
        render: (_, r) => fmtTime(r.created_at),
      },
      {
        title: t('common.actions'),
        valueType: 'option',
        width: 190,
        fixed: 'right',
        render: (_, r) => [
          <Button key="docs" type="link" size="small" onClick={() => openDocs(r)}>
            {t(`${K}.docs`, { defaultValue: '文档' })}
          </Button>,
          canEdit ? (
            <Button key="edit" type="link" size="small" onClick={() => openEditKb(r)}>
              {t('common.edit')}
            </Button>
          ) : null,
          canRemove ? (
            <Popconfirm
              key="del"
              title={t('common.confirmDelete')}
              onConfirm={async () => {
                try {
                  await deleteKnowledgeBase(r.id);
                  message.success(t('common.deleteSuccess'));
                  void queryClient.invalidateQueries({ queryKey: KUAI_AI_OPTIONS_PREFIX });
                  actionRef.current?.reload();
                } catch (error: any) {
                  message.error(error?.message || t('common.deleteFailed', { defaultValue: '删除失败' }));
                }
              }}
            >
              <Button type="link" size="small" danger>
                {t('common.delete')}
              </Button>
            </Popconfirm>
          ) : null,
        ],
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canEdit, canRemove, embedOptions, t, message],
  );

  const docColumns: ColumnsType<DocumentListOut> = useMemo(
    () => [
      {
        title: t(`${K}.doc.title`, { defaultValue: '标题' }),
        dataIndex: 'title',
        ellipsis: true,
      },
      {
        title: t(`${K}.doc.sourceType`, { defaultValue: '来源类型' }),
        dataIndex: 'source_type',
        width: 100,
        render: (v: string) => <Tag>{v}</Tag>,
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        width: 110,
        render: (_, r) => docStatusTag(r.status, r.error_message, t),
      },
      {
        title: t(`${K}.doc.chunkCount`, { defaultValue: '切块数' }),
        dataIndex: 'chunk_count',
        width: 90,
        align: 'right',
      },
      {
        title: t('common.createdAt'),
        dataIndex: 'created_at',
        width: 150,
        render: (v: string) => fmtTime(v),
      },
      {
        title: t('common.actions'),
        key: 'actions',
        width: 200,
        render: (_, r) => {
          const parsing = r.status === 'parsing';
          const parseLabel =
            r.status === 'ready' || r.status === 'failed'
              ? t(`${K}.doc.reparse`, { defaultValue: '重新解析' })
              : t(`${K}.doc.parse`, { defaultValue: '解析' });
          return (
            <Space size={0} wrap>
              {canEdit ? (
                <Tooltip title={parsing ? t(`${K}.doc.parsingTip`, { defaultValue: '解析进行中' }) : undefined}>
                  <Button
                    type="link"
                    size="small"
                    disabled={parsing}
                    onClick={() => void handleParse(r)}
                  >
                    {parseLabel}
                  </Button>
                </Tooltip>
              ) : null}
              <Button
                type="link"
                size="small"
                onClick={() => {
                  setChunksDoc(r);
                  setChunkPage(1);
                }}
              >
                {t(`${K}.doc.chunks`, { defaultValue: '切块' })}
              </Button>
              {canRemove ? (
                <Popconfirm
                  title={t('common.confirmDelete')}
                  onConfirm={async () => {
                    try {
                      await deleteDocument(r.id);
                      message.success(t('common.deleteSuccess'));
                      void docsQuery.refetch();
                    } catch (error: any) {
                      message.error(error?.message || t('common.deleteFailed', { defaultValue: '删除失败' }));
                    }
                  }}
                >
                  <Button type="link" size="small" danger>
                    {t('common.delete')}
                  </Button>
                </Popconfirm>
              ) : null}
            </Space>
          );
        },
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [canEdit, canRemove, t, message, docsQuery],
  );

  const chunkColumns: ColumnsType<ChunkOut> = useMemo(
    () => [
      {
        title: '#',
        dataIndex: 'chunk_index',
        width: 70,
        align: 'right',
      },
      {
        title: t(`${K}.chunk.content`, { defaultValue: '内容' }),
        dataIndex: 'content',
        render: (v: string) => (
          <Typography.Paragraph
            ellipsis={{ rows: 3, expandable: true, symbol: t(`${K}.chunk.expand`, { defaultValue: '展开' }) }}
            style={{ marginBottom: 0 }}
          >
            {v}
          </Typography.Paragraph>
        ),
      },
      {
        title: t(`${K}.chunk.charCount`, { defaultValue: '字符数' }),
        dataIndex: 'char_count',
        width: 90,
        align: 'right',
      },
      {
        title: t('common.createdAt'),
        dataIndex: 'created_at',
        width: 150,
        render: (v: string) => fmtTime(v),
      },
    ],
    [t],
  );

  return (
    <ListPageTemplate>
      <UniTable<KnowledgeBaseOut>
        actionRef={actionRef}
        rowKey="id"
        columns={kbColumns}
        columnPersistenceId="apps.kuaiai.pages.knowledge.list-v1"
        viewTypes={['table']}
        showAdvancedSearch={false}
        showImportButton={false}
        showExportButton={false}
        fuzzySearchPlaceholder={t(`${K}.searchPlaceholder`, { defaultValue: '按名称搜索' })}
        request={async (params, _sort, _filter, searchFormValues) => {
          try {
            const res = await listKnowledgeBases({
              page: params.current,
              page_size: params.pageSize,
              keyword: searchFormValues?.keyword || undefined,
            });
            return { data: res.items, total: res.total, success: true };
          } catch (error: any) {
            message.error(error?.message || t(`${K}.loadFailed`, { defaultValue: '加载失败' }));
            return { data: [], total: 0, success: false };
          }
        }}
        toolBarActions={
          canAdd
            ? [
                <Button key="create" type="primary" icon={<PlusOutlined />} onClick={openCreateKb}>
                  {t(`${K}.create`, { defaultValue: '新建知识库' })}
                </Button>,
              ]
            : []
        }
      />

      {/* 知识库 新建/编辑 */}
      <Modal
        open={kbModalOpen}
        title={
          editingKb
            ? t(`${K}.editTitle`, { defaultValue: '编辑知识库' })
            : t(`${K}.createTitle`, { defaultValue: '新建知识库' })
        }
        onCancel={() => setKbModalOpen(false)}
        onOk={() => void handleKbSubmit()}
      >
        <Form form={kbForm} layout="vertical" initialValues={{ status: STATUS_ENABLED }}>
          <Form.Item
            name="name"
            label={t(`${K}.name`, { defaultValue: '名称' })}
            rules={[{ required: true, message: t(`${K}.nameRequired`, { defaultValue: '请输入名称' }) }]}
          >
            <Input maxLength={200} />
          </Form.Item>
          <Form.Item name="description" label={t(`${K}.description`, { defaultValue: '描述' })}>
            <Input.TextArea rows={2} maxLength={500} />
          </Form.Item>
          <Form.Item
            name="embedding_model_id"
            label={t(`${K}.embeddingModel`, { defaultValue: 'Embedding 模型' })}
            tooltip={t(`${K}.embeddingTip`, { defaultValue: '留空则回落租户默认配置' })}
          >
            <Select allowClear options={embedSelectOptions} showSearch optionFilterProp="label" />
          </Form.Item>
          <Form.Item
            name="chunk_size"
            label={t(`${K}.chunkSize`, { defaultValue: '切块大小' })}
            tooltip={t(`${K}.chunkSizeTip`, { defaultValue: '留空则回落租户默认配置' })}
          >
            <InputNumber min={1} precision={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="chunk_overlap"
            label={t(`${K}.chunkOverlap`, { defaultValue: '切块重叠' })}
            dependencies={['chunk_size']}
            rules={[
              {
                validator: (_, value) => {
                  if (value === undefined || value === null) return Promise.resolve();
                  const size = kbForm.getFieldValue('chunk_size');
                  if (value <= 0) {
                    return Promise.reject(
                      new Error(t(`${K}.overlapGtZero`, { defaultValue: '切块重叠须大于 0' })),
                    );
                  }
                  if (typeof size === 'number' && value >= size) {
                    return Promise.reject(
                      new Error(
                        t(`${K}.overlapLtSize`, { defaultValue: '切块重叠须小于切块大小' }),
                      ),
                    );
                  }
                  return Promise.resolve();
                },
              },
            ]}
          >
            <InputNumber min={0} precision={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="expand_enabled"
            label={t(`${K}.expandEnabled`, { defaultValue: '检索展开' })}
            tooltip={t(`${K}.expandTip`, { defaultValue: '留空则回落租户默认配置' })}
          >
            <Select
              allowClear
              placeholder={t(`${K}.default`, { defaultValue: '默认' })}
              options={[
                { value: true, label: t(`${K}.expandOn`, { defaultValue: '开启' }) },
                { value: false, label: t(`${K}.expandOff`, { defaultValue: '关闭' }) },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="status"
            label={t('common.status')}
            rules={[{ required: true, message: t(`${K}.statusRequired`, { defaultValue: '请选择状态' }) }]}
          >
            <Select
              options={[
                { value: STATUS_ENABLED, label: t('common.enabled') },
                { value: STATUS_DISABLED, label: t('common.disabled') },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 文档抽屉 */}
      <Drawer
        open={!!docKb}
        onClose={() => setDocKb(null)}
        width={960}
        destroyOnHidden
        title={
          docKb
            ? t(`${K}.docsTitle`, { defaultValue: '文档 - {{name}}', name: docKb.name })
            : t(`${K}.docs`, { defaultValue: '文档' })
        }
        extra={
          canAdd ? (
            <Button type="primary" icon={<PlusOutlined />} onClick={openDocModal}>
              {t(`${K}.doc.create`, { defaultValue: '新建文档' })}
            </Button>
          ) : null
        }
      >
        <Table<DocumentListOut>
          rowKey="id"
          size="small"
          loading={docsQuery.isLoading}
          dataSource={docsQuery.data?.items || []}
          columns={docColumns}
          pagination={{
            current: docPage,
            pageSize: docPageSize,
            total: docsQuery.data?.total || 0,
            showSizeChanger: true,
            showTotal: (total) => t('common.total', { defaultValue: '共 {{total}} 条', total }),
            onChange: (p, ps) => {
              setDocPage(ps !== docPageSize ? 1 : p);
              setDocPageSize(ps);
            },
          }}
        />
      </Drawer>

      {/* 新建文档 */}
      <Modal
        open={docModalOpen}
        title={t(`${K}.doc.createTitle`, { defaultValue: '新建文档' })}
        onCancel={() => setDocModalOpen(false)}
        onOk={() => void handleCreateDocument()}
        confirmLoading={docSubmitting}
        destroyOnHidden
      >
        <Tabs
          activeKey={docTab}
          onChange={(k) => setDocTab(k as 'file' | 'raw')}
          items={[
            {
              key: 'file',
              label: t(`${K}.doc.tabFile`, { defaultValue: '文件上传' }),
              children: (
                <Form form={fileForm} layout="vertical" preserve={false}>
                  <Form.Item
                    name="title"
                    label={t(`${K}.doc.title`, { defaultValue: '标题' })}
                    rules={[
                      {
                        required: true,
                        message: t(`${K}.doc.titleRequired`, { defaultValue: '请输入标题' }),
                      },
                    ]}
                  >
                    <Input maxLength={300} />
                  </Form.Item>
                  <Form.Item
                    label={t(`${K}.doc.file`, { defaultValue: '文件' })}
                    required
                    extra={t(`${K}.doc.fileHint`, {
                      defaultValue: '支持 pdf / doc / docx / ppt / pptx / xls / xlsx / md / txt',
                    })}
                  >
                    <Upload.Dragger
                      accept={FILE_ACCEPT}
                      maxCount={1}
                      fileList={
                        docFile
                          ? [{ uid: '-1', name: docFile.name, status: 'done' as const }]
                          : []
                      }
                      beforeUpload={(file) => {
                        if (!sourceTypeFromFileName(file.name)) {
                          message.error(
                            t(`${K}.doc.unsupportedType`, { defaultValue: '不支持的文件类型' }),
                          );
                          return Upload.LIST_IGNORE;
                        }
                        setDocFile(file);
                        if (!fileForm.getFieldValue('title')) {
                          fileForm.setFieldValue('title', file.name.replace(/\.[^.]+$/, ''));
                        }
                        return false;
                      }}
                      onRemove={() => setDocFile(null)}
                    >
                      <p className="ant-upload-drag-icon">
                        <InboxOutlined />
                      </p>
                      <p className="ant-upload-text">
                        {t(`${K}.doc.uploadText`, { defaultValue: '点击或拖拽文件到此处上传' })}
                      </p>
                    </Upload.Dragger>
                  </Form.Item>
                </Form>
              ),
            },
            {
              key: 'raw',
              label: t(`${K}.doc.tabRaw`, { defaultValue: '文本录入' }),
              children: (
                <Form
                  form={rawForm}
                  layout="vertical"
                  preserve={false}
                  initialValues={{ source_type: 'txt' }}
                >
                  <Form.Item
                    name="title"
                    label={t(`${K}.doc.title`, { defaultValue: '标题' })}
                    rules={[
                      {
                        required: true,
                        message: t(`${K}.doc.titleRequired`, { defaultValue: '请输入标题' }),
                      },
                    ]}
                  >
                    <Input maxLength={300} />
                  </Form.Item>
                  <Form.Item
                    name="source_type"
                    label={t(`${K}.doc.format`, { defaultValue: '格式' })}
                    rules={[{ required: true }]}
                    extra={t(`${K}.doc.rawHint`, { defaultValue: '文本直存仅支持 txt / md' })}
                  >
                    <Select
                      options={DOCUMENT_RAW_SOURCE_TYPES.map((s) => ({ value: s, label: s }))}
                    />
                  </Form.Item>
                  <Form.Item
                    name="raw_content"
                    label={t(`${K}.doc.rawContent`, { defaultValue: '内容' })}
                    rules={[
                      {
                        required: true,
                        message: t(`${K}.doc.rawRequired`, { defaultValue: '请输入内容' }),
                      },
                    ]}
                  >
                    <Input.TextArea rows={8} maxLength={200000} showCount />
                  </Form.Item>
                </Form>
              ),
            },
          ]}
        />
      </Modal>

      {/* 切块抽屉（只读） */}
      <Drawer
        open={!!chunksDoc}
        onClose={() => setChunksDoc(null)}
        width={720}
        destroyOnHidden
        title={
          chunksDoc
            ? t(`${K}.chunksTitle`, { defaultValue: '切块 - {{title}}', title: chunksDoc.title })
            : t(`${K}.doc.chunks`, { defaultValue: '切块' })
        }
      >
        <Table<ChunkOut>
          rowKey="id"
          size="small"
          loading={chunksQuery.isLoading}
          dataSource={chunksQuery.data?.items || []}
          columns={chunkColumns}
          pagination={{
            current: chunkPage,
            pageSize: chunkPageSize,
            total: chunksQuery.data?.total || 0,
            showTotal: (total) => t('common.total', { defaultValue: '共 {{total}} 条', total }),
            onChange: (p, ps) => {
              setChunkPage(ps !== chunkPageSize ? 1 : p);
              setChunkPageSize(ps);
            },
          }}
        />
      </Drawer>
    </ListPageTemplate>
  );
}
