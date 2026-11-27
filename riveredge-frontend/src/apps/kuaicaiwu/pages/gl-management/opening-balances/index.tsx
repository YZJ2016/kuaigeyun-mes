/**
 * 总账期初余额（科目 + 辅助）
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Alert, Button, InputNumber, Select, Space, Table, Tabs, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useNumericPrecisionPlaces } from '../../../../../hooks/useNumericPrecision';
import { ListPageTemplate } from '../../../../../components/layout-templates';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { formatAmount } from '../../../../../utils/format';
import {
  glService,
  type GlAccount,
  type GlOpeningBalanceResidual,
} from '../../../services/gl';
const NS = 'app.kuaicaiwu.gl.openingBalances';

const asList = <T,>(res: unknown): T[] => {
  if (Array.isArray(res)) return res as T[];
  const obj = res as { data?: T[]; items?: T[] } | null;
  return obj?.data ?? obj?.items ?? [];
};

type BalanceRow = {
  key: string;
  account_id: number;
  account_code: string;
  account_name: string;
  customer_id?: number;
  supplier_id?: number;
  department_id?: number;
  opening_debit: number;
  opening_credit: number;
  isAux: boolean;
  isLeaf?: boolean;
};

type TrialInfo = {
  balanced?: boolean;
  opening_debit?: number;
  opening_credit?: number;
  ending_debit?: number;
  ending_credit?: number;
};

const OpeningBalancesPage: React.FC = () => {
  const { t } = useTranslation();
  const amountDecimals = useNumericPrecisionPlaces('amount');
  const { message: messageApi } = App.useApp();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [activeTab, setActiveTab] = useState<'account' | 'aux'>('account');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [accountRows, setAccountRows] = useState<BalanceRow[]>([]);
  const [auxRows, setAuxRows] = useState<BalanceRow[]>([]);
  const [accounts, setAccounts] = useState<GlAccount[]>([]);
  const [trial, setTrial] = useState<TrialInfo | null>(null);
  const [residuals, setResiduals] = useState<GlOpeningBalanceResidual[]>([]);
  const [clearingResidual, setClearingResidual] = useState(false);
  const dirtyAccountIdsRef = useRef<Set<number>>(new Set());
  const dirtyAuxKeysRef = useRef<Set<string>>(new Set());

  const loadData = useCallback(async () => {
    setLoading(true);
    dirtyAccountIdsRef.current = new Set();
    dirtyAuxKeysRef.current = new Set();
    try {
      const [accountsRes, balancesRes, trialRes, diagRes] = await Promise.all([
        glService.listAccounts({ is_active: true }),
        glService.getOpeningBalances(year, month),
        glService.trialBalance({ year, month, include_unposted: false }),
        glService.getOpeningBalanceDiagnostics(year, month),
      ]);
      const allAccounts = asList<GlAccount>(accountsRes);
      setAccounts(allAccounts);
      const leafAccounts = allAccounts.filter((a) => a.is_leaf);
      const balances = asList<{
        account_id: number;
        opening_debit?: number;
        opening_credit?: number;
        customer_id?: number | null;
        supplier_id?: number | null;
        department_id?: number | null;
      }>(balancesRes);
      const accountById = new Map(leafAccounts.map((a) => [a.id, a]));
      const plainBalances = balances.filter(
        (b) => !b.customer_id && !b.supplier_id && !b.department_id,
      );
      const byId = new Map(plainBalances.map((b) => [b.account_id, b]));
      setAccountRows(
        allAccounts
          .slice()
          .sort((a, b) => String(a.account_code).localeCompare(String(b.account_code)))
          .map((a) => {
            const bal = byId.get(a.id);
            return {
              key: `a-${a.id}`,
              account_id: a.id,
              account_code: a.account_code,
              account_name: a.is_leaf
                ? a.account_name
                : `${a.account_name}${t(`${NS}.nonLeafHint`, { defaultValue: '（汇总，不可录入）' })}`,
              opening_debit: Number(bal?.opening_debit || 0),
              opening_credit: Number(bal?.opening_credit || 0),
              isAux: false,
              isLeaf: a.is_leaf,
            };
          }),
      );
      const auxFromApi = balances
        .filter((b) => b.customer_id || b.supplier_id || b.department_id)
        .map((b) => {
          const acc = accountById.get(b.account_id);
          return {
            key: `x-${b.account_id}-${b.customer_id || 0}-${b.supplier_id || 0}-${b.department_id || 0}`,
            account_id: b.account_id,
            account_code: acc?.account_code || String(b.account_id),
            account_name: acc?.account_name || '',
            customer_id: b.customer_id || undefined,
            supplier_id: b.supplier_id || undefined,
            department_id: b.department_id || undefined,
            opening_debit: Number(b.opening_debit || 0),
            opening_credit: Number(b.opening_credit || 0),
            isAux: true,
          };
        });
      setAuxRows(auxFromApi);
      setTrial((trialRes || {}) as TrialInfo);
      setResiduals(diagRes?.items ?? []);
    } catch (error) {
      messageApi.error(getApiErrorMessage(error, t('common.loadFailed', { defaultValue: '加载失败' })));
    } finally {
      setLoading(false);
    }
  }, [year, month, messageApi, t]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleClearResidual = useCallback(async () => {
    setClearingResidual(true);
    try {
      const res = await glService.clearNonLeafOpeningResidual({
        period_year: year,
        period_month: month,
      });
      messageApi.success(
        t(`${NS}.residualCleared`, {
          defaultValue: '已清零 {{count}} 个非末级残留期初',
          count: res.cleared ?? 0,
        }),
      );
      if (res.trial) {
        setTrial(res.trial as TrialInfo);
      }
      await loadData();
    } catch (error) {
      messageApi.error(
        getApiErrorMessage(error, t('common.operationFailed', { defaultValue: '操作失败' })),
      );
    } finally {
      setClearingResidual(false);
    }
  }, [year, month, loadData, messageApi, t]);

  const residualSummary = useMemo(
    () =>
      residuals
        .map((item) => {
          const code = item.account_code || '';
          const od = Number(item.opening_debit || 0);
          const oc = Number(item.opening_credit || 0);
          const sideText =
            od > 0
              ? `${t(`${NS}.col.openingDebit`, { defaultValue: '期初借方' })}${formatAmount(od)}`
              : `${t(`${NS}.col.openingCredit`, { defaultValue: '期初贷方' })}${formatAmount(oc)}`;
          return `${code} ${item.account_name || ''} ${sideText}`.trim();
        })
        .join('；'),
    [residuals, t],
  );

  const auxAccountOptions = useMemo(
    () =>
      accounts
        .filter((a) => a.is_leaf && (a.aux_customer || a.aux_supplier || a.aux_department))
        .map((a) => ({
          label: `${a.account_code} ${a.account_name}`,
          value: a.id,
        })),
    [accounts],
  );

  const updateAccountCell = (
    accountId: number,
    field: 'opening_debit' | 'opening_credit',
    value: number | null,
  ) => {
    dirtyAccountIdsRef.current.add(accountId);
    setAccountRows((prev) =>
      prev.map((r) =>
        r.account_id === accountId ? { ...r, [field]: Number(value || 0) } : r,
      ),
    );
  };

  const updateAuxCell = (
    key: string,
    field: keyof Pick<
      BalanceRow,
      'opening_debit' | 'opening_credit' | 'customer_id' | 'supplier_id' | 'department_id' | 'account_id'
    >,
    value: number | null,
  ) => {
    dirtyAuxKeysRef.current.add(key);
    setAuxRows((prev) =>
      prev.map((r) => {
        if (r.key !== key) return r;
        if (field === 'account_id') {
          const acc = accounts.find((a) => a.id === Number(value || 0));
          return {
            ...r,
            account_id: Number(value || 0),
            account_code: acc?.account_code || '',
            account_name: acc?.account_name || '',
          };
        }
        if (field === 'opening_debit' || field === 'opening_credit') {
          return { ...r, [field]: Number(value || 0) };
        }
        return { ...r, [field]: value ? Number(value) : undefined };
      }),
    );
  };

  const handleAddAuxRow = () => {
    const first = accounts.find(
      (a) => a.is_leaf && (a.aux_customer || a.aux_supplier || a.aux_department),
    );
    if (!first) {
      messageApi.warning(
        t(`${NS}.noAuxAccount`, { defaultValue: '请先在科目中启用辅助核算' }),
      );
      return;
    }
    setAuxRows((prev) => [
      ...prev,
      {
        key: `new-${Date.now()}`,
        account_id: first.id,
        account_code: first.account_code,
        account_name: first.account_name,
        customer_id: undefined,
        opening_debit: 0,
        opening_credit: 0,
        isAux: true,
      },
    ]);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const dirtyAccounts = dirtyAccountIdsRef.current;
      const dirtyAux = dirtyAuxKeysRef.current;
      const accountItems = accountRows
        .filter((r) => r.isLeaf)
        .filter((r) => dirtyAccounts.has(r.account_id) || r.opening_debit > 0 || r.opening_credit > 0)
        .map((r) => ({
          account_id: r.account_id,
          opening_debit: r.opening_debit,
          opening_credit: r.opening_credit,
        }));
      const auxItems = auxRows
        .filter(
          (r) =>
            Boolean(r.account_id) &&
            (dirtyAux.has(r.key) || r.opening_debit > 0 || r.opening_credit > 0),
        )
        .map((r) => {
          if (!r.customer_id && !r.supplier_id && !r.department_id) {
            throw new Error(
              t(`${NS}.auxRequired`, { defaultValue: '辅助期初须填写客户/供应商/部门之一' }),
            );
          }
          return {
            account_id: r.account_id,
            opening_debit: r.opening_debit,
            opening_credit: r.opening_credit,
            customer_id: r.customer_id || null,
            supplier_id: r.supplier_id || null,
            department_id: r.department_id || null,
          };
        });
      const items = [...accountItems, ...auxItems];
      if (items.length === 0) {
        messageApi.warning(
          t(`${NS}.nothingToSave`, { defaultValue: '没有需要保存的期初变更' }),
        );
        return;
      }
      const res = (await glService.setOpeningBalances({
        period_year: year,
        period_month: month,
        items,
      })) as { saved?: number; trial?: TrialInfo };
      setTrial(res.trial || null);
      messageApi.success(
        t('common.saveSuccess', {
          defaultValue: '期初已保存（{{count}} 条）',
          count: res.saved ?? items.length,
        }),
      );
      await loadData();
    } catch (error) {
      messageApi.error(
        error instanceof Error
          ? error.message
          : getApiErrorMessage(error, t('common.saveFailed', { defaultValue: '保存失败' })),
      );
    } finally {
      setSaving(false);
    }
  };

  const accountColumns = useMemo(
    () => [
      {
        title: t(`${NS}.col.accountCode`, { defaultValue: '科目编码' }),
        dataIndex: 'account_code',
        width: 140,
      },
      {
        title: t(`${NS}.col.accountName`, { defaultValue: '科目名称' }),
        dataIndex: 'account_name',
        ellipsis: true,
      },
      {
        title: t(`${NS}.col.openingDebit`, { defaultValue: '期初借方' }),
        dataIndex: 'opening_debit',
        width: 160,
        align: 'right' as const,
        render: (_: unknown, record: BalanceRow) => (
          <InputNumber
            size="medium"
            min={0}
            precision={amountDecimals}
            style={{ width: '100%' }}
            value={record.opening_debit}
            disabled={!record.isLeaf}
            onChange={(v) => updateAccountCell(record.account_id, 'opening_debit', v)}
          />
        ),
      },
      {
        title: t(`${NS}.col.openingCredit`, { defaultValue: '期初贷方' }),
        dataIndex: 'opening_credit',
        width: 160,
        align: 'right' as const,
        render: (_: unknown, record: BalanceRow) => (
          <InputNumber
            size="medium"
            min={0}
            precision={amountDecimals}
            style={{ width: '100%' }}
            value={record.opening_credit}
            disabled={!record.isLeaf}
            onChange={(v) => updateAccountCell(record.account_id, 'opening_credit', v)}
          />
        ),
      },
    ],
    [amountDecimals, t],
  );

  const auxColumns = useMemo(
    () => [
      {
        title: t(`${NS}.col.account`, { defaultValue: '科目' }),
        dataIndex: 'account_id',
        width: 220,
        render: (_: unknown, record: BalanceRow) => (
          <Select
            size="medium"
            showSearch
            optionFilterProp="label"
            style={{ width: '100%' }}
            options={auxAccountOptions}
            value={record.account_id || undefined}
            onChange={(v) => updateAuxCell(record.key, 'account_id', v)}
          />
        ),
      },
      {
        title: t(`${NS}.col.customer`, { defaultValue: '客户ID' }),
        dataIndex: 'customer_id',
        width: 110,
        render: (_: unknown, record: BalanceRow) => (
          <InputNumber
            size="medium"
            min={1}
            precision={0}
            style={{ width: '100%' }}
            value={record.customer_id}
            onChange={(v) => updateAuxCell(record.key, 'customer_id', v)}
          />
        ),
      },
      {
        title: t(`${NS}.col.supplier`, { defaultValue: '供应商ID' }),
        dataIndex: 'supplier_id',
        width: 110,
        render: (_: unknown, record: BalanceRow) => (
          <InputNumber
            size="medium"
            min={1}
            precision={0}
            style={{ width: '100%' }}
            value={record.supplier_id}
            onChange={(v) => updateAuxCell(record.key, 'supplier_id', v)}
          />
        ),
      },
      {
        title: t(`${NS}.col.department`, { defaultValue: '部门ID' }),
        dataIndex: 'department_id',
        width: 110,
        render: (_: unknown, record: BalanceRow) => (
          <InputNumber
            size="medium"
            min={1}
            precision={0}
            style={{ width: '100%' }}
            value={record.department_id}
            onChange={(v) => updateAuxCell(record.key, 'department_id', v)}
          />
        ),
      },
      {
        title: t(`${NS}.col.openingDebit`, { defaultValue: '期初借方' }),
        dataIndex: 'opening_debit',
        width: 140,
        align: 'right' as const,
        render: (_: unknown, record: BalanceRow) => (
          <InputNumber
            size="medium"
            min={0}
            precision={amountDecimals}
            style={{ width: '100%' }}
            value={record.opening_debit}
            onChange={(v) => updateAuxCell(record.key, 'opening_debit', v)}
          />
        ),
      },
      {
        title: t(`${NS}.col.openingCredit`, { defaultValue: '期初贷方' }),
        dataIndex: 'opening_credit',
        width: 140,
        align: 'right' as const,
        render: (_: unknown, record: BalanceRow) => (
          <InputNumber
            size="medium"
            min={0}
            precision={amountDecimals}
            style={{ width: '100%' }}
            value={record.opening_credit}
            onChange={(v) => updateAuxCell(record.key, 'opening_credit', v)}
          />
        ),
      },
      {
        title: t('common.action', { defaultValue: '操作' }),
        key: 'action',
        width: 80,
        render: (_: unknown, record: BalanceRow) => (
          <Button
            type="link"
            danger
            size="small"
            onClick={() => setAuxRows((prev) => prev.filter((r) => r.key !== record.key))}
          >
            {t('common.delete', { defaultValue: '删除' })}
          </Button>
        ),
      },
    ],
    [t, auxAccountOptions, accounts],
  );

  return (
    <ListPageTemplate>
      <Space orientation="vertical" size="medium" style={{ width: '100%' }}>
        <Space wrap>
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
          <Button onClick={() => void loadData()} loading={loading}>
            {t('common.refresh', { defaultValue: '刷新' })}
          </Button>
          {activeTab === 'aux' ? (
            <Button onClick={handleAddAuxRow}>
              {t(`${NS}.addAux`, { defaultValue: '添加辅助期初' })}
            </Button>
          ) : null}
          <Button type="primary" loading={saving} onClick={() => void handleSave()}>
            {t(`${NS}.save`, { defaultValue: '保存期初' })}
          </Button>
        </Space>

        {residuals.length > 0 ? (
          <Alert
            showIcon
            type="warning"
            title={t(`${NS}.residualTitle`, { defaultValue: '存在非末级科目残留期初' })}
            description={
              <Space orientation="vertical" size={8}>
                <Typography.Text>
                  {t(`${NS}.residualDetail`, {
                    defaultValue:
                      '以下科目已有下级，自身余额行仍有期初，科目余额表会轧卷显示但不可在此录入。请将金额迁到末级科目后清零残留：{{list}}',
                    list: residualSummary,
                  })}
                </Typography.Text>
                <Button loading={clearingResidual} onClick={() => void handleClearResidual()}>
                  {t(`${NS}.residualClear`, { defaultValue: '清零本月残留期初' })}
                </Button>
              </Space>
            }
          />
        ) : null}

        {trial ? (
          <Alert
            showIcon
            type={trial.balanced ? 'success' : 'error'}
            title={
              trial.balanced
                ? t(`${NS}.trialBalanced`, { defaultValue: '试算平衡' })
                : t(`${NS}.trialUnbalanced`, { defaultValue: '试算不平衡' })
            }
            description={
              <Typography.Text>
                {t(`${NS}.trialDetail`, {
                  defaultValue: '期初借 {{od}} / 贷 {{oc}}；期末借 {{ed}} / 贷 {{ec}}',
                  od: formatAmount(trial.opening_debit || 0),
                  oc: formatAmount(trial.opening_credit || 0),
                  ed: formatAmount(trial.ending_debit || 0),
                  ec: formatAmount(trial.ending_credit || 0),
                })}
              </Typography.Text>
            }
          />
        ) : null}

        <Tabs
          activeKey={activeTab}
          onChange={(k) => setActiveTab(k as 'account' | 'aux')}
          items={[
            { key: 'account', label: t(`${NS}.tab.account`, { defaultValue: '科目期初' }) },
            { key: 'aux', label: t(`${NS}.tab.aux`, { defaultValue: '辅助期初' }) },
          ]}
        />

        {activeTab === 'account' ? (
          <Table<BalanceRow>
            rowKey="key"
            loading={loading}
            columns={accountColumns}
            dataSource={accountRows}
            size="medium"
            pagination={{ pageSize: 50, showSizeChanger: true }}
            scroll={{ x: 720 }}
          />
        ) : (
          <Table<BalanceRow>
            rowKey="key"
            loading={loading}
            columns={auxColumns}
            dataSource={auxRows}
            size="medium"
            pagination={{ pageSize: 50, showSizeChanger: true }}
            scroll={{ x: 980 }}
          />
        )}
      </Space>
    </ListPageTemplate>
  );
};

export default OpeningBalancesPage;
