/**
 * 总账期末结账
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  App,
  Alert,
  Button,
  Card,
  Descriptions,
  InputNumber,
  Popconfirm,
  Space,
  Table,
  Typography,
} from 'antd';
import { ProFormDigit, ProFormSelect, ProFormText } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import {
  FormModalTemplate,
  ListPageTemplate,
  MODAL_CONFIG,
} from '../../../../../components/layout-templates';
import { rowActionKind } from '../../../../../components/uni-action';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { formatAmount } from '../../../../../utils/format';
import { glService } from '../../../services/gl';

const NS = 'app.kuaicaiwu.gl.periodClose';

type PeriodRow = {
  period_year: number;
  period_month: number;
  status: string;
  closed_at?: string | null;
};

type PeriodStatus = {
  initialized?: boolean;
  current_year?: number;
  current_month?: number;
  periods?: PeriodRow[];
};

type CheckResult = {
  ok?: boolean;
  errors?: string[];
  unposted_count?: number;
  checks?: Array<{
    name: string;
    business_balance?: number;
    gl_balance?: number;
    diff?: number;
    ok?: boolean;
  }>;
  message?: string;
};

type TransferTemplateLine = {
  side?: string;
  account_code?: string;
  amount_mode?: string;
  amount?: number;
  ratio?: number;
  summary?: string;
};

type TransferTemplate = {
  id: number;
  template_code: string;
  template_name: string;
  template_type: string;
  lines?: TransferTemplateLine[];
  is_active?: boolean;
};

type AccrualRow = Record<string, unknown>;

function buildCustomTemplateLines(values: Record<string, unknown>): TransferTemplateLine[] {
  const amountMode = String(values.amount_mode || 'period_balance');
  const amount = values.amount;
  const ratio = values.ratio || 1;
  const summary = String(values.template_name || '');
  return [
    {
      side: 'debit',
      account_code: String(values.debit_account_code || ''),
      amount_mode: amountMode,
      amount: amount as number | undefined,
      ratio: ratio as number,
      summary,
    },
    {
      side: 'credit',
      account_code: String(values.credit_account_code || ''),
      amount_mode: amountMode,
      amount: amount as number | undefined,
      ratio: ratio as number,
      summary,
    },
  ];
}

function templateFormInitialValues(tpl: TransferTemplate | null): Record<string, unknown> {
  if (!tpl) {
    return { amount_mode: 'period_balance', ratio: 1 };
  }
  const debit = (tpl.lines || []).find((l) => l.side === 'debit');
  const credit = (tpl.lines || []).find((l) => l.side === 'credit');
  return {
    template_code: tpl.template_code,
    template_name: tpl.template_name,
    debit_account_code: debit?.account_code,
    credit_account_code: credit?.account_code,
    amount_mode: debit?.amount_mode || credit?.amount_mode || 'period_balance',
    amount: debit?.amount ?? credit?.amount,
    ratio: debit?.ratio ?? credit?.ratio ?? 1,
  };
}

const PeriodClosePage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [status, setStatus] = useState<PeriodStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [preCheck, setPreCheck] = useState<CheckResult | null>(null);
  const [monthEnd, setMonthEnd] = useState<CheckResult | null>(null);
  const [templates, setTemplates] = useState<TransferTemplate[]>([]);
  const [accruals, setAccruals] = useState<AccrualRow[]>([]);
  const [tplOpen, setTplOpen] = useState(false);
  const [editingTpl, setEditingTpl] = useState<TransferTemplate | null>(null);
  const [accrualOpen, setAccrualOpen] = useState(false);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const [res, tplRes, accrualRes] = await Promise.all([
        glService.periodStatus() as Promise<PeriodStatus>,
        glService.listTransferTemplates(),
        glService.listAccruals(),
      ]);
      setStatus(res);
      if (res.current_year) setYear(res.current_year);
      if (res.current_month) setMonth(res.current_month);
      setTemplates((Array.isArray(tplRes) ? tplRes : []) as TransferTemplate[]);
      setAccruals(Array.isArray(accrualRes) ? (accrualRes as AccrualRow[]) : []);
    } catch (error) {
      messageApi.error(getApiErrorMessage(error, t('common.loadFailed', { defaultValue: '加载失败' })));
    } finally {
      setLoading(false);
    }
  }, [messageApi, t]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const withAction = async (key: string, fn: () => Promise<void>) => {
    setActionLoading(key);
    try {
      await fn();
      await loadStatus();
    } catch (error) {
      messageApi.error(getApiErrorMessage(error, t('common.operationFailed', { defaultValue: '操作失败' })));
    } finally {
      setActionLoading(null);
    }
  };

  const handlePreCheck = () =>
    void withAction('pre', async () => {
      const res = (await glService.preCloseChecks(year, month)) as CheckResult;
      setPreCheck(res);
      if (res.ok) {
        messageApi.success(t(`${NS}.preCheckOk`, { defaultValue: '结账前检查通过' }));
      } else {
        messageApi.warning(t(`${NS}.preCheckFail`, { defaultValue: '结账前检查未通过' }));
      }
    });

  const handleCarry = () =>
    void withAction('carry', async () => {
      await glService.carryProfitLoss(year, month);
      messageApi.success(t(`${NS}.carrySuccess`, { defaultValue: '损益结转完成' }));
    });

  const handleClose = () =>
    void withAction('close', async () => {
      await glService.closePeriod(year, month);
      messageApi.success(t(`${NS}.closeSuccess`, { defaultValue: '结账成功' }));
    });

  const handleReopen = () =>
    void withAction('reopen', async () => {
      await glService.reopenPeriod(year, month);
      messageApi.success(t(`${NS}.reopenSuccess`, { defaultValue: '反结账成功' }));
    });

  const handleMonthEnd = () =>
    void withAction('monthEnd', async () => {
      const res = (await glService.monthEndChecks(year, month)) as CheckResult;
      setMonthEnd(res);
      messageApi.success(t(`${NS}.monthEndDone`, { defaultValue: '业财月结对账已完成' }));
    });

  const handleRunTemplate = (tpl: TransferTemplate) =>
    void withAction(`tpl-${tpl.id}`, async () => {
      await glService.runTransferTemplate(tpl.id, year, month);
      messageApi.success(
        t(`${NS}.runTemplateSuccess`, {
          defaultValue: '转账模板 {{name}} 已执行',
          name: tpl.template_name,
        }),
      );
    });

  const openCreateTemplate = () => {
    setEditingTpl(null);
    setTplOpen(true);
  };

  const openEditTemplate = (tpl: TransferTemplate) => {
    setEditingTpl(tpl);
    setTplOpen(true);
  };

  const closeTemplateModal = () => {
    setTplOpen(false);
    setEditingTpl(null);
  };

  const handleDeleteTemplate = (tpl: TransferTemplate) =>
    void withAction(`tpl-del-${tpl.id}`, async () => {
      await glService.deleteTransferTemplate(tpl.id);
      messageApi.success(t('common.deleteSuccess', { defaultValue: '删除成功' }));
    });

  const tplInitialValues = useMemo(() => templateFormInitialValues(editingTpl), [editingTpl]);
  const editingProfitLoss = editingTpl?.template_type === 'profit_loss';

  const periodColumns = [
    {
      title: t(`${NS}.col.period`, { defaultValue: '期间' }),
      key: 'period',
      render: (_: unknown, r: PeriodRow) =>
        `${r.period_year}-${String(r.period_month).padStart(2, '0')}`,
    },
    {
      title: t('common.status', { defaultValue: '状态' }),
      dataIndex: 'status',
      render: (v: string) =>
        v === 'closed'
          ? t(`${NS}.status.closed`, { defaultValue: '已结账' })
          : t(`${NS}.status.open`, { defaultValue: '打开' }),
    },
    {
      title: t(`${NS}.col.closedAt`, { defaultValue: '结账时间' }),
      dataIndex: 'closed_at',
      render: (v: string | null | undefined) => v || '—',
    },
  ];

  const monthEndColumns = [
    { title: t(`${NS}.col.checkName`, { defaultValue: '检查项' }), dataIndex: 'name' },
    {
      title: t(`${NS}.col.business`, { defaultValue: '业务余额' }),
      dataIndex: 'business_balance',
      align: 'right' as const,
      render: (v: number) => formatAmount(v ?? 0),
    },
    {
      title: t(`${NS}.col.gl`, { defaultValue: '总账余额' }),
      dataIndex: 'gl_balance',
      align: 'right' as const,
      render: (v: number) => formatAmount(v ?? 0),
    },
    {
      title: t(`${NS}.col.diff`, { defaultValue: '差异' }),
      dataIndex: 'diff',
      align: 'right' as const,
      render: (v: number) => formatAmount(v ?? 0),
    },
    {
      title: t(`${NS}.col.result`, { defaultValue: '结果' }),
      dataIndex: 'ok',
      render: (v: boolean) =>
        v ? (
          <Typography.Text type="success">{t(`${NS}.ok`, { defaultValue: '通过' })}</Typography.Text>
        ) : (
          <Typography.Text type="danger">{t(`${NS}.fail`, { defaultValue: '差异' })}</Typography.Text>
        ),
    },
  ];

  const templateColumns = [
    {
      title: t(`${NS}.col.templateCode`, { defaultValue: '模板编码' }),
      dataIndex: 'template_code',
      width: 140,
    },
    {
      title: t(`${NS}.col.templateName`, { defaultValue: '模板名称' }),
      dataIndex: 'template_name',
      ellipsis: true,
    },
    {
      title: t(`${NS}.col.templateType`, { defaultValue: '类型' }),
      dataIndex: 'template_type',
      width: 120,
    },
    {
      title: t('common.action', { defaultValue: '操作' }),
      key: 'action',
      width: 220,
      render: (_: unknown, r: TransferTemplate) => (
        <Space size="small">
          <Button
            type="link"
            size="small"
            disabled={r.is_active === false}
            loading={actionLoading === `tpl-${r.id}`}
            onClick={() => handleRunTemplate(r)}
          >
            {t(`${NS}.runTemplate`, { defaultValue: '执行' })}
          </Button>
          <Button key="edit" {...rowActionKind('update')} onClick={() => openEditTemplate(r)} />
          <Popconfirm
            title={t(`${NS}.deleteTemplateConfirm`, {
              defaultValue: '确认删除转账模板「{{name}}」？',
              name: r.template_name,
            })}
            onConfirm={() => handleDeleteTemplate(r)}
          >
            <Button {...rowActionKind('delete')} loading={actionLoading === `tpl-del-${r.id}`} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const accrualColumns = [
    { title: t('common.code', { defaultValue: '编码' }), dataIndex: 'item_code', width: 120 },
    { title: t('common.name', { defaultValue: '名称' }), dataIndex: 'item_name', ellipsis: true },
    {
      title: t(`${NS}.col.remaining`, { defaultValue: '剩余' }),
      dataIndex: 'remaining',
      align: 'right' as const,
      render: (v: number) => formatAmount(v ?? 0),
    },
    {
      title: t('common.action', { defaultValue: '操作' }),
      key: 'action',
      width: 100,
      render: (_: unknown, r: AccrualRow) => (
        <Button
          type="link"
          size="small"
          loading={actionLoading === `acc-${r.id}`}
          onClick={() =>
            void withAction(`acc-${r.id}`, async () => {
              await glService.runAccrual(Number(r.id), year, month);
              messageApi.success(t(`${NS}.runAccrualOk`, { defaultValue: '摊销预提已生成凭证' }));
            })
          }
        >
          {t(`${NS}.runAccrual`, { defaultValue: '本期执行' })}
        </Button>
      ),
    },
  ];

  return (
    <ListPageTemplate>
      <Space orientation="vertical" size="medium" style={{ width: '100%' }}>
        <Card
          loading={loading}
          title={t(`${NS}.statusTitle`, { defaultValue: '账期状态' })}
          style={{ width: '100%' }}
        >
          <Descriptions bordered size="small" column={{ xs: 1, sm: 2, lg: 3 }}>
            <Descriptions.Item label={t(`${NS}.initialized`, { defaultValue: '已开账' })}>
              {status?.initialized
                ? t('common.yes', { defaultValue: '是' })
                : t('common.no', { defaultValue: '否' })}
            </Descriptions.Item>
            <Descriptions.Item label={t(`${NS}.currentYear`, { defaultValue: '当前年' })}>
              {status?.current_year ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label={t(`${NS}.currentMonth`, { defaultValue: '当前月' })}>
              {status?.current_month ?? '—'}
            </Descriptions.Item>
          </Descriptions>
        </Card>

        <Card
          title={t(`${NS}.actionsTitle`, { defaultValue: '期末处理' })}
          style={{ width: '100%' }}
          extra={
            <Button onClick={() => void loadStatus()} loading={loading}>
              {t('common.refresh', { defaultValue: '刷新' })}
            </Button>
          }
        >
          <Space orientation="vertical" size="medium" style={{ width: '100%' }}>
            <Space wrap size="medium">
              <Space.Compact>
                <InputNumber
                  size="medium"
                  precision={0}
                  value={year}
                  onChange={(v) => setYear(Number(v) || now.getFullYear())}
                  prefix={t(`${NS}.year`, { defaultValue: '年' })}
                  style={{ width: 140 }}
                />
                <InputNumber
                  size="medium"
                  min={1}
                  max={12}
                  precision={0}
                  value={month}
                  onChange={(v) => setMonth(Number(v) || 1)}
                  prefix={t(`${NS}.month`, { defaultValue: '月' })}
                  style={{ width: 120 }}
                />
              </Space.Compact>
              <Button loading={actionLoading === 'pre'} onClick={handlePreCheck}>
                {t(`${NS}.preCheck`, { defaultValue: '结账前检查' })}
              </Button>
              <Button loading={actionLoading === 'carry'} onClick={handleCarry}>
                {t(`${NS}.carry`, { defaultValue: '结转损益' })}
              </Button>
              <Button type="primary" loading={actionLoading === 'close'} onClick={handleClose}>
                {t(`${NS}.close`, { defaultValue: '结账' })}
              </Button>
              <Button danger loading={actionLoading === 'reopen'} onClick={handleReopen}>
                {t(`${NS}.reopen`, { defaultValue: '反结账' })}
              </Button>
              <Button loading={actionLoading === 'monthEnd'} onClick={handleMonthEnd}>
                {t(`${NS}.monthEnd`, { defaultValue: '业财月结对账' })}
              </Button>
            </Space>

            {preCheck ? (
              <Alert
                showIcon
                type={preCheck.ok ? 'success' : 'error'}
                title={
                  preCheck.ok
                    ? t(`${NS}.preCheckOk`, { defaultValue: '结账前检查通过' })
                    : t(`${NS}.preCheckFail`, { defaultValue: '结账前检查未通过' })
                }
                description={
                  (preCheck.errors || []).length
                    ? (preCheck.errors || []).join('；')
                    : t(`${NS}.unpostedCount`, {
                        defaultValue: '未记账凭证 {{count}} 张',
                        count: preCheck.unposted_count ?? 0,
                      })
                }
              />
            ) : null}
          </Space>
        </Card>

        <Card title={t(`${NS}.periodListTitle`, { defaultValue: '期间列表' })} style={{ width: '100%' }}>
          <Table
            rowKey={(r) => `${r.period_year}-${r.period_month}`}
            loading={loading}
            columns={periodColumns}
            dataSource={status?.periods || []}
            size="small"
            pagination={false}
          />
        </Card>

        <Card
          title={t(`${NS}.transferTemplates`, { defaultValue: '自定义转账' })}
          style={{ width: '100%' }}
          extra={
            <Button onClick={openCreateTemplate}>
              {t(`${NS}.newTemplate`, { defaultValue: '新建转账模板' })}
            </Button>
          }
        >
          <Table
            rowKey="id"
            loading={loading}
            columns={templateColumns}
            dataSource={templates}
            size="small"
            pagination={false}
            locale={{
              emptyText: t(`${NS}.noTemplates`, { defaultValue: '暂无自定义转账模板' }),
            }}
          />
        </Card>

        <Card
          title={t(`${NS}.accruals`, { defaultValue: '摊销预提' })}
          style={{ width: '100%' }}
          extra={
            <Button onClick={() => setAccrualOpen(true)}>
              {t(`${NS}.newAccrual`, { defaultValue: '新建摊销预提' })}
            </Button>
          }
        >
          <Table
            rowKey="id"
            loading={loading}
            columns={accrualColumns}
            dataSource={accruals}
            size="small"
            pagination={false}
          />
        </Card>

        {monthEnd?.checks ? (
          <Card title={t(`${NS}.monthEndResult`, { defaultValue: '业财月结对账结果' })} style={{ width: '100%' }}>
            <Table
              rowKey={(r) => r.name}
              columns={monthEndColumns}
              dataSource={monthEnd.checks}
              size="small"
              pagination={false}
            />
          </Card>
        ) : null}
      </Space>

      <FormModalTemplate
        key={editingTpl ? `edit-tpl-${editingTpl.id}` : 'create-tpl'}
        title={
          editingTpl
            ? t(`${NS}.editTemplate`, { defaultValue: '编辑转账模板' })
            : t(`${NS}.newTemplate`, { defaultValue: '新建转账模板' })
        }
        open={tplOpen}
        onClose={closeTemplateModal}
        width={MODAL_CONFIG.LARGE_WIDTH}
        initialValues={tplInitialValues}
        onFinish={async (values) => {
          try {
            if (editingTpl) {
              if (editingProfitLoss) {
                await glService.updateTransferTemplate(editingTpl.id, {
                  template_code: editingTpl.template_code,
                  template_name: values.template_name,
                  is_active: editingTpl.is_active !== false,
                });
              } else {
                await glService.updateTransferTemplate(editingTpl.id, {
                  template_code: editingTpl.template_code,
                  template_name: values.template_name,
                  template_type: 'custom',
                  lines: buildCustomTemplateLines(values),
                  is_active: true,
                });
              }
            } else {
              await glService.upsertTransferTemplate({
                template_code: values.template_code,
                template_name: values.template_name,
                template_type: 'custom',
                lines: buildCustomTemplateLines(values),
                is_active: true,
              });
            }
            messageApi.success(t('common.saveSuccess', { defaultValue: '保存成功' }));
            closeTemplateModal();
            await loadStatus();
          } catch (error) {
            messageApi.error(
              getApiErrorMessage(error, t('common.saveFailed', { defaultValue: '保存失败' })),
            );
          }
        }}
      >
        <ProFormText
          name="template_code"
          label={t(`${NS}.col.templateCode`, { defaultValue: '模板编码' })}
          rules={[{ required: true }]}
          disabled={Boolean(editingTpl)}
        />
        <ProFormText
          name="template_name"
          label={t(`${NS}.col.templateName`, { defaultValue: '模板名称' })}
          rules={[{ required: true }]}
        />
        {editingProfitLoss ? (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            title={t(`${NS}.profitLossEditHint`, {
              defaultValue: '结转损益模板由系统按全部损益科目生成分录，此处仅可修改名称。',
            })}
          />
        ) : (
          <>
            <ProFormText
              name="debit_account_code"
              label={t(`${NS}.debitAccount`, { defaultValue: '借方科目编码' })}
              rules={[{ required: true }]}
            />
            <ProFormText
              name="credit_account_code"
              label={t(`${NS}.creditAccount`, { defaultValue: '贷方科目编码' })}
              rules={[{ required: true }]}
            />
            <ProFormSelect
              name="amount_mode"
              label={t(`${NS}.amountMode`, { defaultValue: '取数方式' })}
              initialValue="period_balance"
              options={[
                {
                  label: t(`${NS}.amountMode.periodBalance`, { defaultValue: '本期净发生' }),
                  value: 'period_balance',
                },
                {
                  label: t(`${NS}.amountMode.periodDebit`, { defaultValue: '本期借方' }),
                  value: 'period_debit',
                },
                {
                  label: t(`${NS}.amountMode.periodCredit`, { defaultValue: '本期贷方' }),
                  value: 'period_credit',
                },
                {
                  label: t(`${NS}.amountMode.endingBalance`, { defaultValue: '期末余额' }),
                  value: 'ending_balance',
                },
                {
                  label: t(`${NS}.amountMode.fixed`, { defaultValue: '固定金额' }),
                  value: 'fixed',
                },
              ]}
            />
            <ProFormDigit name="amount" label={t(`${NS}.fixedAmount`, { defaultValue: '固定金额' })} min={0} />
            <ProFormDigit name="ratio" label={t(`${NS}.ratio`, { defaultValue: '比例' })} min={0} initialValue={1} />
          </>
        )}
      </FormModalTemplate>

      <FormModalTemplate
        title={t(`${NS}.newAccrual`, { defaultValue: '新建摊销预提' })}
        open={accrualOpen}
        onClose={() => setAccrualOpen(false)}
        width={MODAL_CONFIG.LARGE_WIDTH}
        onFinish={async (values) => {
          try {
            await glService.upsertAccrual({
              ...values,
              start_year: year,
              start_month: month,
            });
            messageApi.success(t('common.saveSuccess', { defaultValue: '保存成功' }));
            setAccrualOpen(false);
            await loadStatus();
          } catch (error) {
            messageApi.error(
              getApiErrorMessage(error, t('common.saveFailed', { defaultValue: '保存失败' })),
            );
          }
        }}
        initialValues={{ accrual_type: 'accrual', periods: 12 }}
      >
        <ProFormText name="item_code" label={t('common.code', { defaultValue: '编码' })} rules={[{ required: true }]} />
        <ProFormText name="item_name" label={t('common.name', { defaultValue: '名称' })} rules={[{ required: true }]} />
        <ProFormSelect
          name="accrual_type"
          label={t(`${NS}.accrualType`, { defaultValue: '类型' })}
          options={[
            { label: '预提', value: 'accrual' },
            { label: '待摊', value: 'deferred' },
          ]}
        />
        <ProFormDigit name="total_amount" label={t(`${NS}.totalAmount`, { defaultValue: '总额' })} min={0} rules={[{ required: true }]} />
        <ProFormDigit name="periods" label={t(`${NS}.periods`, { defaultValue: '期数' })} min={1} />
        <ProFormText name="debit_account_code" label={t(`${NS}.debitAccount`, { defaultValue: '借方科目' })} rules={[{ required: true }]} />
        <ProFormText name="credit_account_code" label={t(`${NS}.creditAccount`, { defaultValue: '贷方科目' })} rules={[{ required: true }]} />
        <ProFormText name="summary" label={t(`${NS}.summary`, { defaultValue: '摘要' })} />
      </FormModalTemplate>
    </ListPageTemplate>
  );
};

export default PeriodClosePage;
