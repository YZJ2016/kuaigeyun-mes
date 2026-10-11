/**
 * KU-Corpus 知识语料运营视图（/apps/kuaiai/corpus，spec 183；设计 §7）。
 *
 * 紧凑列表页（无大标题页头）：
 * - 筛选条：标题搜索（约 240px）、高级搜索折叠（知识库/类型/创建日期）、
 *   重置、索引状态快捷 Tag；全部筛选写入 URL search params（可分享）；
 * - 动作行：加载出厂 FAQ（知识库选择）、添加 FAQ（Modal 720px）、
 *   前往知识库添加文档（kuaiai:knowledge:display，缺失禁用+原因）、
 *   导出训练 JSONL（corpus:export，按当前筛选）、批量删除（红色描边 +
 *   二次确认 Modal）、批量操作下拉（索引/重试 → batch-index，corpus:update）；
 * - 表格固定列：选择/标题/所属知识库/类型/分块数/创建时间/索引状态/操作；
 *   行操作：详情→/knowledge（无权限禁用+原因）、删除（确认）；
 * - 页脚：左「共 N 条记录，显示 A-B 条」+ 右分页（默认 20）；
 * - 批量结果逐项透出（成功/失败明细）；空/403/失败态与空态严格区分；
 * - 文件上传与文本添加只在 /knowledge，本页不重复。
 */

import React, { useEffect, useMemo, useState } from 'react';
import {
  App,
  Button,
  Checkbox,
  DatePicker,
  Dropdown,
  Empty,
  Form,
  Input,
  Modal,
  Pagination,
  Popconfirm,
  Popover,
  Result,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
} from 'antd';
import {
  DownOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useQuery } from '@tanstack/react-query';
import dayjs, { type Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import { hasPermission } from '../../../../utils/permission';
import {
  batchDeleteCorpus,
  batchIndexCorpus,
  createCorpusFaq,
  downloadCorpusJsonl,
  listCorpus,
  listCorpusKnowledgeOptions,
  seedCorpusFaqs,
} from '../../services/operations';
import type {
  CorpusDocStatus,
  CorpusDocType,
  CorpusItemOut,
  CorpusQuery,
} from '../../types/operations';
import '../../ops.less';

const K = 'app.kuaiai.corpus';

const DEFAULT_PAGE_SIZE = 20;
const COLUMN_STORAGE_KEY = 'apps.kuaiai.pages.corpus.columns-v1';

const STATUS_ORDER: CorpusDocStatus[] = [
  'ready',
  'pending',
  'parsing',
  'failed',
];

const STATUS_TAG: Record<string, { color: string; labelKey: string; fallback: string }> = {
  pending: { color: 'default', labelKey: `${K}.status.pending`, fallback: '待索引' },
  parsing: { color: 'processing', labelKey: `${K}.status.parsing`, fallback: '索引中' },
  ready: { color: 'success', labelKey: `${K}.status.ready`, fallback: '已索引' },
  failed: { color: 'error', labelKey: `${K}.status.failed`, fallback: '索引失败' },
};

const TYPE_TAG: Record<string, { color: string; labelKey: string; fallback: string }> = {
  faq: { color: 'purple', labelKey: `${K}.type.faq`, fallback: 'FAQ' },
  text: { color: 'blue', labelKey: `${K}.type.text`, fallback: '文本' },
  file: { color: 'cyan', labelKey: `${K}.type.file`, fallback: '文件' },
};

/** 列设置可开关的列（标题/索引状态/操作恒显） */
const TOGGLEABLE_COLUMNS = [
  'knowledge_name',
  'type',
  'chunk_count',
  'created_at',
] as const;
type ToggleableColumn = (typeof TOGGLEABLE_COLUMNS)[number];

function fmtTime(v?: string | null) {
  return v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '—';
}

function statusTag(status: string, errorSummary: string | null, t: (k: string, o?: any) => string) {
  const conf = STATUS_TAG[status] || { color: 'default', labelKey: '', fallback: status };
  const tag = (
    <Tag color={conf.color}>{conf.labelKey ? t(conf.labelKey, { defaultValue: conf.fallback }) : conf.fallback}</Tag>
  );
  if (status === 'failed' && errorSummary) {
    return <Tooltip title={errorSummary}>{tag}</Tooltip>;
  }
  return tag;
}

function typeTag(type: string, t: (k: string, o?: any) => string) {
  const conf = TYPE_TAG[type];
  if (!conf) return <Tag>{type || '—'}</Tag>;
  return <Tag color={conf.color}>{t(conf.labelKey, { defaultValue: conf.fallback })}</Tag>;
}

function loadVisibleColumns(): ToggleableColumn[] {
  try {
    const raw = localStorage.getItem(COLUMN_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return parsed.filter((c): c is ToggleableColumn =>
          (TOGGLEABLE_COLUMNS as readonly string[]).includes(c),
        );
      }
    }
  } catch {
    /* 本地存储不可用时回落默认 */
  }
  return [...TOGGLEABLE_COLUMNS];
}

const CorpusPage: React.FC = () => {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const currentUser = useCurrentUser();

  const canCreate = hasPermission(currentUser, 'kuaiai:corpus:create');
  const canUpdate = hasPermission(currentUser, 'kuaiai:corpus:update');
  const canDelete = hasPermission(currentUser, 'kuaiai:corpus:delete');
  const canExport = hasPermission(currentUser, 'kuaiai:corpus:export');
  const canKnowledgeDisplay = hasPermission(currentUser, 'kuaiai:knowledge:display');

  // ---------------------------------------------------------- URL 筛选（可分享）
  const keyword = (searchParams.get('keyword') || '').trim();
  const knowledgeIdParam = Number(searchParams.get('knowledge_id'));
  const knowledgeId = Number.isFinite(knowledgeIdParam) && knowledgeIdParam > 0 ? knowledgeIdParam : undefined;
  const typeParam = searchParams.get('type');
  const docType = typeParam === 'faq' || typeParam === 'text' || typeParam === 'file' ? (typeParam as CorpusDocType) : undefined;
  const statusParam = searchParams.get('status');
  const docStatus = STATUS_ORDER.includes(statusParam as CorpusDocStatus)
    ? (statusParam as CorpusDocStatus)
    : undefined;
  const createdFrom = searchParams.get('created_from') || undefined;
  const createdTo = searchParams.get('created_to') || undefined;
  const page = Math.max(1, Number(searchParams.get('page')) || 1);
  const pageSize = Math.min(100, Math.max(1, Number(searchParams.get('page_size')) || DEFAULT_PAGE_SIZE));

  const [keywordInput, setKeywordInput] = useState(keyword);
  useEffect(() => setKeywordInput(keyword), [keyword]);

  const updateParams = (patch: Record<string, string | undefined>, resetPage = true) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(patch).forEach(([key, value]) => {
      if (value === undefined || value === '') next.delete(key);
      else next.set(key, value);
    });
    if (resetPage) next.delete('page');
    setSearchParams(next, { replace: true });
  };

  const resetFilters = () => {
    const next = new URLSearchParams();
    if (searchParams.get('page_size')) next.set('page_size', searchParams.get('page_size')!);
    setSearchParams(next, { replace: true });
    setKeywordInput('');
  };

  const query: CorpusQuery = useMemo(
    () => ({
      page,
      page_size: pageSize,
      keyword: keyword || undefined,
      knowledge_id: knowledgeId,
      type: docType,
      status: docStatus,
      created_from: createdFrom,
      created_to: createdTo,
    }),
    [page, pageSize, keyword, knowledgeId, docType, docStatus, createdFrom, createdTo],
  );

  const corpusQuery = useQuery({
    queryKey: ['kuaiai', 'corpus', query],
    queryFn: () => listCorpus(query),
    // pending/parsing 时每 4s 轮询直至终态（与 /knowledge 文档页同策略）
    refetchInterval: (q) =>
      (q.state.data?.items || []).some(
        (d) => d.status === 'pending' || d.status === 'parsing',
      )
        ? 4000
        : false,
  });

  const kbOptionsQuery = useQuery({
    queryKey: ['kuaiai', 'corpus', 'knowledge-options'],
    queryFn: () => listCorpusKnowledgeOptions(),
    staleTime: 60_000,
    retry: 1,
  });
  const kbOptions = kbOptionsQuery.data ?? [];

  // ---------------------------------------------------------- 本地 UI 状态
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [visibleColumns, setVisibleColumns] = useState<ToggleableColumn[]>(loadVisibleColumns);
  const [faqModalOpen, setFaqModalOpen] = useState(false);
  const [faqSubmitting, setFaqSubmitting] = useState(false);
  const [seedModalOpen, setSeedModalOpen] = useState(false);
  const [seedSubmitting, setSeedSubmitting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [batchRunning, setBatchRunning] = useState(false);
  const [faqForm] = Form.useForm();
  const [seedForm] = Form.useForm();

  const total = corpusQuery.data?.total ?? 0;
  const items = corpusQuery.data?.items ?? [];

  useEffect(() => {
    // 筛选/数据变化后清掉已不在本页的勾选
    setSelectedRowKeys((keys) => keys.filter((k) => items.some((i) => i.id === k)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  const refresh = () => {
    void corpusQuery.refetch();
  };

  const showBatchResult = (res: { items: { id: number; success: boolean; error: string | null }[] }, kind: 'index' | 'delete') => {
    const failed = res.items.filter((i) => !i.success);
    if (!failed.length) {
      message.success(
        kind === 'index'
          ? t(`${K}.batchIndexDone`, { defaultValue: '已提交 {{count}} 条索引任务', count: res.items.length })
          : t(`${K}.batchDeleteDone`, { defaultValue: '已删除 {{count}} 条记录', count: res.items.length }),
      );
      return;
    }
    const succeeded = res.items.length - failed.length;
    modal.warning({
      title:
        kind === 'index'
          ? t(`${K}.batchIndexPartial`, { defaultValue: '部分索引提交失败' })
          : t(`${K}.batchDeletePartial`, { defaultValue: '部分删除失败' }),
      content: (
        <div>
          <p>
            {t(`${K}.batchResultSummary`, {
              defaultValue: '成功 {{ok}} 条，失败 {{fail}} 条',
              ok: succeeded,
              fail: failed.length,
            })}
          </p>
          <ul style={{ paddingLeft: 18, margin: 0, maxHeight: 240, overflow: 'auto' }}>
            {failed.map((i) => (
              <li key={i.id}>
                #{i.id}：{i.error}
              </li>
            ))}
          </ul>
        </div>
      ),
    });
  };

  const handleBatchIndex = async () => {
    if (!selectedRowKeys.length) return;
    setBatchRunning(true);
    try {
      const res = await batchIndexCorpus(selectedRowKeys.map(Number));
      showBatchResult(res, 'index');
      refresh();
    } catch (error: any) {
      message.error(error?.message || t(`${K}.batchIndexFailed`, { defaultValue: '批量索引失败' }));
    } finally {
      setBatchRunning(false);
    }
  };

  const handleBatchDelete = () => {
    if (!selectedRowKeys.length) return;
    modal.confirm({
      title: t(`${K}.batchDeleteConfirm`, {
        defaultValue: '确认删除选中的 {{count}} 条语料？',
        count: selectedRowKeys.length,
      }),
      content: t(`${K}.batchDeleteConfirmHint`, {
        defaultValue: '删除后不可恢复，关联切块将一并移除',
      }),
      okText: t('common.confirm', { defaultValue: '确定' }),
      okButtonProps: { danger: true },
      cancelText: t('common.cancel', { defaultValue: '取消' }),
      onOk: async () => {
        setBatchRunning(true);
        try {
          const res = await batchDeleteCorpus(selectedRowKeys.map(Number));
          showBatchResult(res, 'delete');
          setSelectedRowKeys([]);
          refresh();
        } catch (error: any) {
          message.error(error?.message || t('common.deleteFailed', { defaultValue: '删除失败' }));
        } finally {
          setBatchRunning(false);
        }
      },
    });
  };

  const handleRowDelete = async (doc: CorpusItemOut) => {
    try {
      const res = await batchDeleteCorpus([doc.id]);
      const item = res.items[0];
      if (item?.success) {
        message.success(t('common.deleteSuccess', { defaultValue: '删除成功' }));
      } else {
        message.error(item?.error || t('common.deleteFailed', { defaultValue: '删除失败' }));
      }
      refresh();
    } catch (error: any) {
      message.error(error?.message || t('common.deleteFailed', { defaultValue: '删除失败' }));
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      await downloadCorpusJsonl({
        keyword: keyword || undefined,
        knowledge_id: knowledgeId,
        type: docType,
        status: docStatus,
        created_from: createdFrom,
        created_to: createdTo,
      });
      message.success(t(`${K}.exportStarted`, { defaultValue: '导出已开始下载' }));
    } catch (error: any) {
      message.error(error?.message || t(`${K}.exportFailed`, { defaultValue: '导出失败' }));
    } finally {
      setExporting(false);
    }
  };

  const handleSeedSubmit = async () => {
    try {
      const values = await seedForm.validateFields();
      setSeedSubmitting(true);
      const res = await seedCorpusFaqs(values.knowledge_id);
      message.success(
        t(`${K}.seedDone`, {
          defaultValue: '已写入 {{created}} 条出厂 FAQ，跳过 {{skipped}} 条',
          created: res.created,
          skipped: res.skipped,
        }),
      );
      setSeedModalOpen(false);
      refresh();
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error(error?.message || t(`${K}.seedFailed`, { defaultValue: '加载出厂 FAQ 失败' }));
    } finally {
      setSeedSubmitting(false);
    }
  };

  const handleFaqSubmit = async () => {
    try {
      const values = await faqForm.validateFields();
      setFaqSubmitting(true);
      await createCorpusFaq({
        knowledge_id: values.knowledge_id,
        question: values.question,
        answer: values.answer,
        is_active: values.is_active ?? true,
      });
      message.success(t('common.createSuccess', { defaultValue: '创建成功' }));
      setFaqModalOpen(false);
      refresh();
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error(error?.message || t('common.createFailed', { defaultValue: '创建失败' }));
    } finally {
      setFaqSubmitting(false);
    }
  };

  const toggleColumn = (col: ToggleableColumn, checked: boolean) => {
    setVisibleColumns((prev) => {
      const next = checked
        ? TOGGLEABLE_COLUMNS.filter((c) => prev.includes(c) || c === col)
        : prev.filter((c) => c !== col);
      try {
        localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(next));
      } catch {
        /* 本地存储不可用时仅会话内生效 */
      }
      return next;
    });
  };

  // ---------------------------------------------------------- 表格列
  const columns: ColumnsType<CorpusItemOut> = useMemo(() => {
    const cols: ColumnsType<CorpusItemOut> = [
      {
        title: t(`${K}.colTitle`, { defaultValue: '标题' }),
        dataIndex: 'title',
        ellipsis: true,
        render: (v: string, r) => (
          <Tooltip title={!r.is_active ? t(`${K}.inactiveHint`, { defaultValue: '已停用，不参与检索' }) : undefined}>
            <span style={!r.is_active ? { opacity: 0.55 } : undefined}>{v}</span>
          </Tooltip>
        ),
      },
    ];
    if (visibleColumns.includes('knowledge_name')) {
      cols.push({
        title: t(`${K}.colKnowledge`, { defaultValue: '所属知识库' }),
        dataIndex: 'knowledge_name',
        width: 140,
        ellipsis: true,
        render: (v: string | null) => v || '—',
      });
    }
    if (visibleColumns.includes('type')) {
      cols.push({
        title: t(`${K}.colType`, { defaultValue: '类型' }),
        dataIndex: 'type',
        width: 80,
        render: (v: string) => typeTag(v, t),
      });
    }
    if (visibleColumns.includes('chunk_count')) {
      cols.push({
        title: t(`${K}.colChunks`, { defaultValue: '分块数' }),
        dataIndex: 'chunk_count',
        width: 80,
        align: 'right',
      });
    }
    if (visibleColumns.includes('created_at')) {
      cols.push({
        title: t('common.createdAt', { defaultValue: '创建时间' }),
        dataIndex: 'created_at',
        width: 170,
        render: (v: string) => fmtTime(v),
      });
    }
    cols.push({
      title: t(`${K}.colStatus`, { defaultValue: '索引状态' }),
      dataIndex: 'status',
      width: 100,
      render: (_, r) => statusTag(r.status, r.error_summary, t),
    });
    cols.push({
      title: t('common.actions', { defaultValue: '操作' }),
      key: 'actions',
      width: 140,
      render: (_, r) => (
        <Space size={0}>
          <Tooltip
            title={
              canKnowledgeDisplay
                ? undefined
                : t(`${K}.noKnowledgePerm`, { defaultValue: '缺少知识库管理权限' })
            }
          >
            <Button
              type="link"
              size="small"
              disabled={!canKnowledgeDisplay}
              onClick={() => navigate('/apps/kuaiai/knowledge')}
            >
              {t(`${K}.detail`, { defaultValue: '详情' })}
            </Button>
          </Tooltip>
          <Tooltip
            title={
              canDelete
                ? undefined
                : t(`${K}.noDeletePerm`, { defaultValue: '缺少语料删除权限' })
            }
          >
            <Popconfirm
              title={t(`${K}.deleteConfirm`, { defaultValue: '确认删除该语料？' })}
              okText={t('common.confirm', { defaultValue: '确定' })}
              cancelText={t('common.cancel', { defaultValue: '取消' })}
              disabled={!canDelete}
              onConfirm={() => void handleRowDelete(r)}
            >
              <Button type="link" size="small" danger disabled={!canDelete}>
                {t('common.delete', { defaultValue: '删除' })}
              </Button>
            </Popconfirm>
          </Tooltip>
        </Space>
      ),
    });
    return cols;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleColumns, canKnowledgeDisplay, canDelete, t, navigate]);

  const columnSettingsContent = (
    <div className="kuaiai-ops-corpus-col-settings">
      {TOGGLEABLE_COLUMNS.map((col) => {
        const labelMap: Record<ToggleableColumn, string> = {
          knowledge_name: t(`${K}.colKnowledge`, { defaultValue: '所属知识库' }),
          type: t(`${K}.colType`, { defaultValue: '类型' }),
          chunk_count: t(`${K}.colChunks`, { defaultValue: '分块数' }),
          created_at: t('common.createdAt', { defaultValue: '创建时间' }),
        };
        return (
          <div key={col}>
            <Checkbox
              checked={visibleColumns.includes(col)}
              onChange={(e) => toggleColumn(col, e.target.checked)}
            >
              {labelMap[col]}
            </Checkbox>
          </div>
        );
      })}
    </div>
  );

  const advancedCount = (knowledgeId ? 1 : 0) + (docType ? 1 : 0) + (createdFrom || createdTo ? 1 : 0);

  // ---------------------------------------------------------- 错误态（403/整页失败）
  if (corpusQuery.isError && !corpusQuery.data) {
    const statusCode = (corpusQuery.error as any)?.response?.status as number | undefined;
    const is403 = statusCode === 403;
    return (
      <div className="kuaiai-ops-page">
        <div className="kuaiai-ops-corpus">
          <Result
            status={is403 ? '403' : 'error'}
            title={
              is403
                ? t('app.kuaiai.ops.forbidden', { defaultValue: '缺少功能权限' })
                : t(`${K}.loadFailed`, { defaultValue: '加载语料列表失败' })
            }
            subTitle={
              is403
                ? t('app.kuaiai.ops.forbiddenHint', {
                    defaultValue: '当前账号缺少对应页面权限，请联系管理员授权',
                  })
                : (corpusQuery.error as Error)?.message
            }
            extra={
              !is403 ? (
                <Button type="primary" onClick={refresh}>
                  {t('common.retry', { defaultValue: '重试' })}
                </Button>
              ) : undefined
            }
          />
        </div>
      </div>
    );
  }

  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(total, page * pageSize);

  return (
    <div className="kuaiai-ops-page">
      <div className="kuaiai-ops-corpus">
        {/* 筛选条 */}
        <div className="kuaiai-ops-corpus-filters">
          <Input.Search
            allowClear
            style={{ width: 240 }}
            placeholder={t(`${K}.searchPlaceholder`, { defaultValue: '按标题搜索' })}
            value={keywordInput}
            onChange={(e) => setKeywordInput(e.target.value)}
            onSearch={(v) => updateParams({ keyword: v.trim() || undefined })}
            aria-label={t(`${K}.searchPlaceholder`, { defaultValue: '按标题搜索' })}
          />
          <Button
            icon={<DownOutlined rotate={advancedOpen ? 180 : 0} />}
            onClick={() => setAdvancedOpen((v) => !v)}
          >
            {t(`${K}.advancedSearch`, { defaultValue: '高级搜索' })}
            {advancedCount ? ` (${advancedCount})` : ''}
          </Button>
          <Button onClick={resetFilters}>
            {t('common.reset', { defaultValue: '重置' })}
          </Button>
          <div className="kuaiai-ops-corpus-status-tags">
            {/* CheckableTag 不可键盘操作，改用 Segmented（单选 + 「全部」等价于清除筛选） */}
            <Segmented
              value={docStatus ?? 'all'}
              onChange={(v) =>
                updateParams({
                  status: v === 'all' ? undefined : (v as CorpusDocStatus),
                })
              }
              options={[
                {
                  value: 'all',
                  label: t('common.all', { defaultValue: '全部' }),
                },
                ...STATUS_ORDER.map((s) => ({
                  value: s,
                  label: t(STATUS_TAG[s].labelKey, {
                    defaultValue: STATUS_TAG[s].fallback,
                  }),
                })),
              ]}
            />
          </div>
          <div className="kuaiai-ops-corpus-filters-right">
            <Tooltip title={t(`${K}.helpTip`, { defaultValue: '跨知识库查看语料；文件与文本在知识库管理页添加' })}>
              <Button
                type="text"
                size="small"
                icon={<QuestionCircleOutlined />}
                aria-label={t(`${K}.help`, { defaultValue: '帮助' })}
              />
            </Tooltip>
          </div>
        </div>

        {/* 高级搜索折叠区 */}
        {advancedOpen ? (
          <div className="kuaiai-ops-corpus-advanced">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              style={{ minWidth: 200 }}
              placeholder={t(`${K}.filterKnowledge`, { defaultValue: '所属知识库' })}
              value={knowledgeId}
              onChange={(v) => updateParams({ knowledge_id: v ? String(v) : undefined })}
              options={kbOptions.map((kb) => ({ value: kb.id, label: kb.name }))}
            />
            <Select
              allowClear
              style={{ minWidth: 140 }}
              placeholder={t(`${K}.filterType`, { defaultValue: '类型' })}
              value={docType}
              onChange={(v) => updateParams({ type: v ?? undefined })}
              options={(['faq', 'text', 'file'] as CorpusDocType[]).map((v) => ({
                value: v,
                label: t(TYPE_TAG[v].labelKey, { defaultValue: TYPE_TAG[v].fallback }),
              }))}
            />
            <DatePicker.RangePicker
              value={
                createdFrom && createdTo
                  ? [dayjs(createdFrom), dayjs(createdTo)]
                  : createdFrom
                    ? [dayjs(createdFrom), null]
                    : createdTo
                      ? [null, dayjs(createdTo)]
                      : null
              }
              onChange={(vals: [Dayjs | null, Dayjs | null] | null) =>
                updateParams({
                  created_from: vals?.[0] ? vals[0].format('YYYY-MM-DD') : undefined,
                  created_to: vals?.[1] ? vals[1].format('YYYY-MM-DD') : undefined,
                })
              }
            />
          </div>
        ) : null}

        {/* 白色主面板 */}
        <div className="kuaiai-ops-corpus-panel">
          <div className="kuaiai-ops-corpus-actions">
            <Space size={8} wrap>
              {/* 未授权动作一律禁用 + Tooltip 原因，不隐藏（与 agent-library 约定一致） */}
              <Tooltip
                title={
                  canCreate
                    ? undefined
                    : t(`${K}.noCreatePerm`, { defaultValue: '缺少语料创建权限' })
                }
              >
                <Button disabled={!canCreate} onClick={() => setSeedModalOpen(true)}>
                  {t(`${K}.seedFaqs`, { defaultValue: '加载出厂 FAQ' })}
                </Button>
              </Tooltip>
              <Tooltip
                title={
                  canCreate
                    ? undefined
                    : t(`${K}.noCreatePerm`, { defaultValue: '缺少语料创建权限' })
                }
              >
                <Button
                  type="primary"
                  disabled={!canCreate}
                  onClick={() => {
                    faqForm.resetFields();
                    faqForm.setFieldsValue({ is_active: true });
                    setFaqModalOpen(true);
                  }}
                >
                  {t(`${K}.addFaq`, { defaultValue: '添加 FAQ' })}
                </Button>
              </Tooltip>
              <Tooltip
                title={
                  canKnowledgeDisplay
                    ? undefined
                    : t(`${K}.noKnowledgePerm`, { defaultValue: '缺少知识库管理权限' })
                }
              >
                <Button
                  disabled={!canKnowledgeDisplay}
                  onClick={() => navigate('/apps/kuaiai/knowledge')}
                >
                  {t(`${K}.gotoKnowledge`, { defaultValue: '前往知识库添加文档' })}
                </Button>
              </Tooltip>
              <Tooltip
                title={
                  canExport
                    ? undefined
                    : t(`${K}.noExportPerm`, { defaultValue: '缺少语料导出权限' })
                }
              >
                <Button
                  disabled={!canExport}
                  loading={exporting}
                  onClick={() => void handleExport()}
                >
                  {t(`${K}.exportJsonl`, { defaultValue: '导出训练 JSONL' })}
                </Button>
              </Tooltip>
              <Tooltip
                title={
                  canDelete
                    ? undefined
                    : t(`${K}.noDeletePerm`, { defaultValue: '缺少语料删除权限' })
                }
              >
                <Button
                  danger
                  disabled={!canDelete || !selectedRowKeys.length}
                  onClick={handleBatchDelete}
                  loading={batchRunning}
                >
                  {t(`${K}.batchDelete`, { defaultValue: '批量删除' })}
                </Button>
              </Tooltip>
              <Tooltip
                title={
                  canUpdate
                    ? undefined
                    : t(`${K}.noUpdatePerm`, { defaultValue: '缺少语料更新权限' })
                }
              >
                <Dropdown
                  disabled={!canUpdate}
                  menu={{
                    items: [
                      {
                        key: 'index',
                        label: t(`${K}.batchIndex`, { defaultValue: '索引' }),
                        disabled: !selectedRowKeys.length,
                        onClick: () => void handleBatchIndex(),
                      },
                      {
                        key: 'retry',
                        label: t('common.retry', { defaultValue: '重试' }),
                        disabled: !selectedRowKeys.length,
                        onClick: () => void handleBatchIndex(),
                      },
                    ],
                  }}
                >
                  <Button
                    disabled={!canUpdate || !selectedRowKeys.length || batchRunning}
                  >
                    {t(`${K}.batchOps`, { defaultValue: '批量操作' })} <DownOutlined />
                  </Button>
                </Dropdown>
              </Tooltip>
            </Space>
            <div className="kuaiai-ops-corpus-actions-right">
              <Tooltip title={t('common.refresh', { defaultValue: '刷新' })}>
                <Button
                  type="text"
                  icon={<ReloadOutlined spin={corpusQuery.isFetching} />}
                  onClick={refresh}
                  aria-label={t('common.refresh', { defaultValue: '刷新' })}
                />
              </Tooltip>
              <Popover
                content={columnSettingsContent}
                title={t(`${K}.columnSettings`, { defaultValue: '列设置' })}
                trigger="click"
                placement="bottomRight"
              >
                <Button
                  type="text"
                  icon={<SettingOutlined />}
                  aria-label={t(`${K}.columnSettings`, { defaultValue: '列设置' })}
                />
              </Popover>
            </div>
          </div>

          <Table<CorpusItemOut>
            rowKey="id"
            size="middle"
            loading={corpusQuery.isLoading}
            columns={columns}
            dataSource={items}
            pagination={false}
            scroll={{ x: 900 }}
            rowSelection={
              canDelete || canUpdate
                ? {
                    selectedRowKeys,
                    onChange: setSelectedRowKeys,
                    columnWidth: 48,
                    preserveSelectedRowKeys: false,
                  }
                : undefined
            }
            locale={{
              emptyText: (
                <Empty
                  description={t(`${K}.empty`, { defaultValue: '暂无语料记录' })}
                />
              ),
            }}
          />

          {/* 页脚 */}
          <div className="kuaiai-ops-corpus-footer">
            <span className="kuaiai-ops-corpus-footer-total">
              {t(`${K}.footerTotal`, {
                defaultValue: '共 {{total}} 条记录，显示 {{start}}-{{end}} 条',
                total,
                start: rangeStart,
                end: rangeEnd,
              })}
            </span>
            <Pagination
              current={page}
              pageSize={pageSize}
              total={total}
              showSizeChanger
              pageSizeOptions={[10, 20, 50, 100]}
              showQuickJumper
              onChange={(p, ps) => {
                const patch: Record<string, string | undefined> = {
                  page: p > 1 ? String(p) : undefined,
                  page_size: ps !== DEFAULT_PAGE_SIZE ? String(ps) : undefined,
                };
                updateParams(patch, false);
              }}
            />
          </div>
        </div>
      </div>

      {/* 加载出厂 FAQ */}
      <Modal
        open={seedModalOpen}
        title={t(`${K}.seedModalTitle`, { defaultValue: '加载出厂 FAQ' })}
        okText={t('common.confirm', { defaultValue: '确定' })}
        cancelText={t('common.cancel', { defaultValue: '取消' })}
        confirmLoading={seedSubmitting}
        onOk={() => void handleSeedSubmit()}
        onCancel={() => setSeedModalOpen(false)}
        destroyOnHidden
      >
        <p className="kuaiai-ops-corpus-modal-hint">
          {t(`${K}.seedModalHint`, {
            defaultValue: '为选中的启用知识库写入内置 FAQ；同题已存在（含人工 FAQ）自动跳过，不会覆盖。',
          })}
        </p>
        <Form form={seedForm} layout="vertical">
          <Form.Item
            name="knowledge_id"
            label={t(`${K}.form.knowledge`, { defaultValue: '知识库' })}
            rules={[
              {
                required: true,
                message: t(`${K}.form.knowledgeRequired`, { defaultValue: '请选择知识库' }),
              },
            ]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              placeholder={t(`${K}.form.knowledgePlaceholder`, { defaultValue: '请选择启用的知识库' })}
              options={kbOptions.map((kb) => ({ value: kb.id, label: kb.name }))}
              notFoundContent={
                kbOptionsQuery.isLoading
                  ? t('common.loading', { defaultValue: '加载中' })
                  : t(`${K}.noEnabledKb`, { defaultValue: '暂无启用的知识库' })
              }
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 添加 FAQ（720px） */}
      <Modal
        open={faqModalOpen}
        title={t(`${K}.faqModalTitle`, { defaultValue: '添加 FAQ' })}
        width={720}
        okText={t('common.save', { defaultValue: '保存' })}
        cancelText={t('common.cancel', { defaultValue: '取消' })}
        confirmLoading={faqSubmitting}
        onOk={() => void handleFaqSubmit()}
        onCancel={() => setFaqModalOpen(false)}
        destroyOnHidden
      >
        <Form form={faqForm} layout="vertical" initialValues={{ is_active: true }}>
          <Form.Item
            name="knowledge_id"
            label={t(`${K}.form.knowledge`, { defaultValue: '知识库' })}
            rules={[
              {
                required: true,
                message: t(`${K}.form.knowledgeRequired`, { defaultValue: '请选择知识库' }),
              },
            ]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              placeholder={t(`${K}.form.knowledgePlaceholder`, { defaultValue: '请选择启用的知识库' })}
              options={kbOptions.map((kb) => ({ value: kb.id, label: kb.name }))}
              notFoundContent={
                kbOptionsQuery.isLoading
                  ? t('common.loading', { defaultValue: '加载中' })
                  : t(`${K}.noEnabledKb`, { defaultValue: '暂无启用的知识库' })
              }
            />
          </Form.Item>
          <Form.Item
            name="question"
            label={t(`${K}.form.question`, { defaultValue: '问题' })}
            rules={[
              {
                required: true,
                whitespace: true,
                message: t(`${K}.form.questionRequired`, { defaultValue: '请输入问题' }),
              },
            ]}
          >
            <Input
              maxLength={300}
              showCount
              placeholder={t(`${K}.form.questionPlaceholder`, { defaultValue: '问题将作为语料标题（300 字以内）' })}
            />
          </Form.Item>
          <Form.Item
            name="answer"
            label={t(`${K}.form.answer`, { defaultValue: '答案' })}
            rules={[
              {
                required: true,
                whitespace: true,
                message: t(`${K}.form.answerRequired`, { defaultValue: '请输入答案' }),
              },
            ]}
          >
            <Input.TextArea
              rows={6}
              placeholder={t(`${K}.form.answerPlaceholder`, { defaultValue: '请输入标准答复内容' })}
            />
          </Form.Item>
          <Form.Item
            name="is_active"
            label={t(`${K}.form.isActive`, { defaultValue: '是否启用' })}
            valuePropName="checked"
            tooltip={t(`${K}.form.isActiveTip`, { defaultValue: '停用的 FAQ 不参与检索' })}
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default CorpusPage;
