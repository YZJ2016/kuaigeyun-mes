import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Form, Input, InputNumber, Modal, Select, Space, Switch, message } from 'antd';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { factoryListItems, productionLineApi } from '../../../master-data/services/factory';
import { materialApi } from '../../../master-data/services/material';
import { industryRelayApi, type RelayLineCapacity } from '../../services/industryRelayApi';

export default function RelayLineCapacityPage() {
  const { t } = useTranslation();
  const actionRef = useRef<ActionType>(null);
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<RelayLineCapacity | null>(null);
  const [lineOptions, setLineOptions] = useState<Array<{ label: string; value: number }>>([]);
  const [productOptions, setProductOptions] = useState<Array<{ label: string; value: number }>>([]);
  const perms = useResourcePermissions('ind-relay:line-capacity');

  useEffect(() => {
    void (async () => {
      // P5-17：大租户下拉默认收敛；超长用 Select showSearch 过滤，避免一次拉 1000 条卡顿
      const res = await productionLineApi.list({ is_active: true, limit: 200 });
      const items = factoryListItems(res);
      setLineOptions(
        items
          .map((row: { id?: number; name?: string; code?: string }) => ({
            value: Number(row.id),
            label: String(row.name || row.code || row.id),
          }))
          .filter((o) => Number.isInteger(o.value) && o.value > 0)
      );
    })();
  }, []);

  const loadProductOptions = useCallback(async (keyword?: string) => {
    const res = await materialApi.list({
      sourceType: 'Make',
      isActive: true,
      keyword: keyword || undefined,
      limit: 200,
    });
    const next = (res.items || [])
      .map((item) => {
        const code = item.mainCode || item.code || '';
        return {
          value: Number(item.id),
          label: code ? `${code} ${item.name || ''}`.trim() : String(item.name || item.id),
        };
      })
      .filter((o) => Number.isInteger(o.value) && o.value > 0);
    setProductOptions(next);
  }, []);

  useEffect(() => {
    void loadProductOptions();
  }, [loadProductOptions]);

  const openCreate = useCallback(() => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      takt_seconds: 0,
      daily_capacity_qty: 0,
      changeover_minutes_default: 0,
      is_active: true,
      product_ids: [],
    });
    setOpen(true);
  }, [form]);

  const openEdit = useCallback(
    (row: RelayLineCapacity) => {
      setEditing(row);
      const rowProducts = (row.products || []).map((item) => ({
        value: Number(item.id),
        label: item.code ? `${item.code} ${item.name || ''}`.trim() : String(item.name || item.id),
      }));
      setProductOptions((prev) => {
        const map = new Map(prev.map((opt) => [opt.value, opt]));
        for (const opt of rowProducts) {
          if (!map.has(opt.value)) {
            map.set(opt.value, opt);
          }
        }
        return Array.from(map.values());
      });
      form.setFieldsValue({
        production_line_id: row.production_line_id,
        takt_seconds: row.takt_seconds,
        daily_capacity_qty: row.daily_capacity_qty,
        changeover_minutes_default: row.changeover_minutes_default,
        is_active: row.is_active,
        remarks: row.remarks,
        product_ids: row.product_ids || rowProducts.map((item) => item.value),
      });
      setOpen(true);
    },
    [form]
  );

  const columns: ProColumns<RelayLineCapacity>[] = useMemo(
    () => [
      {
        title: t('app.ind-relay.lineCapacity.line'),
        dataIndex: 'production_line_name',
        ellipsis: true,
        render: (_, row) => row.production_line_name || row.production_line_code || row.production_line_id,
      },
      { title: t('app.ind-relay.lineCapacity.taktSeconds'), dataIndex: 'takt_seconds', width: 120 },
      { title: t('app.ind-relay.lineCapacity.dailyCapacity'), dataIndex: 'daily_capacity_qty', width: 120 },
      {
        title: t('app.ind-relay.lineCapacity.changeoverMinutes'),
        dataIndex: 'changeover_minutes_default',
        width: 140,
      },
      {
        title: t('app.ind-relay.lineCapacity.products'),
        dataIndex: 'product_count',
        width: 220,
        ellipsis: true,
        render: (_, row) => {
          const count = Number(row.product_count ?? row.product_ids?.length ?? 0);
          if (count <= 0) {
            return t('app.ind-relay.lineCapacity.productsEmpty');
          }
          const names = (row.products || [])
            .slice(0, 3)
            .map((item) => item.code || item.name || item.id)
            .join('、');
          return count > 3
            ? t('app.ind-relay.lineCapacity.productsSummaryMore', { count, names })
            : t('app.ind-relay.lineCapacity.productsSummary', { count, names });
        },
      },
      {
        title: t('common.status'),
        dataIndex: 'is_active',
        width: 90,
        render: (_, row) => (row.is_active ? t('common.enable') : t('common.disabled')),
      },
      {
        title: t('common.actions'),
        valueType: 'option',
        width: 160,
        render: (_, row) =>
          perms.canUpdate ? (
            <Space size={0}>
              <Button type="link" size="small" onClick={() => openEdit(row)}>
                {t('common.edit')}
              </Button>
              <Button
                type="link"
                size="small"
                onClick={async () => {
                  await industryRelayApi.updateLineCapacity(row.id, { is_active: !row.is_active });
                  message.success(t('common.updateSuccess'));
                  actionRef.current?.reload();
                }}
              >
                {row.is_active ? t('common.disable') : t('common.enable')}
              </Button>
            </Space>
          ) : null,
      },
    ],
    [openEdit, perms.canUpdate, t]
  );

  const handleSubmit = useCallback(async () => {
    const values = await form.validateFields();
    const productIds = Array.isArray(values.product_ids)
      ? values.product_ids.map((id: unknown) => Number(id)).filter((id: number) => Number.isInteger(id) && id > 0)
      : [];
    if (editing) {
      await industryRelayApi.updateLineCapacity(editing.id, {
        takt_seconds: values.takt_seconds,
        daily_capacity_qty: values.daily_capacity_qty,
        changeover_minutes_default: values.changeover_minutes_default,
        is_active: values.is_active,
        remarks: values.remarks,
        product_ids: productIds,
      });
      message.success(t('common.updateSuccess'));
    } else {
      await industryRelayApi.createLineCapacity({
        ...values,
        product_ids: productIds,
      });
      message.success(t('app.ind-relay.lineCapacity.createSuccess'));
    }
    setOpen(false);
    setEditing(null);
    form.resetFields();
    actionRef.current?.reload();
  }, [editing, form, t]);

  return (
    <ListPageTemplate>
      <UniTable<RelayLineCapacity>
        actionRef={actionRef}
        rowKey="id"
        headerTitle={t('app.ind-relay.menu.lineCapacity')}
        columnPersistenceId="apps.ind-relay.pages.line-capacity-v2"
        permissionResource="ind-relay:line-capacity"
        createButtonText={t('app.ind-relay.lineCapacity.createButton')}
        showCreateButton
        onCreate={openCreate}
        columns={columns}
        request={async () => {
          const items = await industryRelayApi.listLineCapacities();
          return { data: items, success: true, total: items.length };
        }}
      />
      <Modal
        open={open}
        title={
          editing
            ? t('app.ind-relay.lineCapacity.editTitle')
            : t('app.ind-relay.lineCapacity.createTitle')
        }
        onCancel={() => {
          setOpen(false);
          setEditing(null);
        }}
        onOk={() => void handleSubmit()}
        destroyOnHidden
        width={640}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="production_line_id"
            label={t('app.ind-relay.lineCapacity.line')}
            rules={[{ required: true }]}
          >
            <Select options={lineOptions} showSearch optionFilterProp="label" disabled={!!editing} />
          </Form.Item>
          <Form.Item name="takt_seconds" label={t('app.ind-relay.lineCapacity.taktSeconds')} initialValue={0}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="daily_capacity_qty" label={t('app.ind-relay.lineCapacity.dailyCapacity')} initialValue={0}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="changeover_minutes_default"
            label={t('app.ind-relay.lineCapacity.changeoverMinutes')}
            initialValue={0}
          >
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="product_ids"
            label={t('app.ind-relay.lineCapacity.products')}
            extra={t('app.ind-relay.lineCapacity.productsHint')}
            initialValue={[]}
            rules={[
              {
                validator: async (_, value) => {
                  const ids = Array.isArray(value)
                    ? value.map((v) => Number(v)).filter((v) => Number.isInteger(v) && v > 0)
                    : [];
                  if (ids.length === 0) {
                    throw new Error(t('app.ind-relay.lineCapacity.productsRequired'));
                  }
                },
              },
            ]}
          >
            <Select
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              options={productOptions}
              placeholder={t('app.ind-relay.lineCapacity.productsPlaceholder')}
              onSearch={(keyword) => {
                void loadProductOptions(keyword);
              }}
            />
          </Form.Item>
          {editing ? (
            <Form.Item name="is_active" label={t('common.status')} valuePropName="checked">
              <Switch checkedChildren={t('common.enable')} unCheckedChildren={t('common.disable')} />
            </Form.Item>
          ) : null}
          <Form.Item name="remarks" label={t('common.remark')}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </ListPageTemplate>
  );
}
