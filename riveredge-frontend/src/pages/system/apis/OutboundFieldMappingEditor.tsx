/**
 * 出站字段映射：顶部只选一次本地单据，行内按层级选字段 → 对方字段
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ProFormDependency,
  ProFormList,
  ProFormSwitch,
  ProFormText,
} from '@ant-design/pro-components';
import { Button, Col, Form, message, Row, Space, Spin, Typography } from 'antd';
import SafeProFormSelect from '../../../components/safe-pro-form-select';
import {
  getOutboundSourceCatalog,
  type OutboundSourceCatalogResponse,
  type OutboundSourceTableItem,
} from '../../../services/apiManagement';
import { normalizeJsonFieldValue } from '../../../components/custom-fields/customFieldJsonUtils';
import {
  mergeRequestBodyFieldsIntoMappings,
  type OutboundFieldMappingRow,
} from './outboundFieldMappings';

const itemFormProps = { style: { marginBottom: 0 } };

/** 接口失败时的采购入库兜底目录，避免下拉「暂无数据」 */
const FALLBACK_PURCHASE_RECEIPT_TABLES: OutboundSourceTableItem[] = [
  {
    profile_code: 'purchase_receipt',
    profile_name: '采购入库单',
    table: 'apps_kuaizhizao_purchase_receipts',
    label: '采购入库单（表头）',
    level: 'header',
    fields: [
      { field: 'receipt_code', label: '入库单编码' },
      { field: 'purchase_order_code', label: '采购订单编码' },
      { field: 'supplier_name', label: '供应商名称' },
      { field: 'supplier_number', label: '供应商编码（解析后）' },
      { field: 'pay_mode', label: '付款方式' },
      { field: 'buyer_operator_number', label: '采购员工号' },
      { field: 'receiver_name', label: '入库人/验收人姓名' },
      { field: 'warehouse_name', label: '入库仓库名称' },
      { field: 'receipt_time', label: '实际入库时间' },
      { field: 'biztime', label: '业务日期（取入库时间）' },
      { field: 'notes', label: '备注' },
      { field: 'comment', label: '备注（推送文案）' },
      { field: 'org_number', label: '库存组织编码（单据/接口默认）' },
      { field: 'bizorg_number', label: '采购组织编码（单据/接口默认）' },
      { field: 'billtype_number', label: '单据类型编码（单据/接口默认）' },
      { field: 'biztype_number', label: '业务类型编码（单据/接口默认）' },
      { field: 'invscheme_number', label: '库存事务编码（单据/接口默认）' },
    ],
  },
  {
    profile_code: 'purchase_receipt',
    profile_name: '采购入库单',
    table: 'apps_kuaizhizao_purchase_receipt_items',
    label: '采购入库明细',
    level: 'entry',
    fields: [
      { field: 'material_code', label: '物料编码' },
      { field: 'material_name', label: '物料名称' },
      { field: 'receipt_quantity', label: '入库数量' },
      { field: 'material_unit', label: '物料单位' },
      { field: 'unit_number', label: '单位编码（解析后）' },
      { field: 'warehouse_number', label: '仓库编码（解析后）' },
      { field: 'batch_number', label: '批次号' },
      { field: 'lotnumber', label: '批号（同批次号）' },
      { field: 'qty', label: '数量（同入库数量）' },
      { field: 'org_number', label: '组织编码（用于货主/保管者等）' },
      { field: 'notes', label: '备注' },
    ],
  },
];

const MappingRowFields: React.FC<{
  headerTable?: OutboundSourceTableItem;
  entryTable?: OutboundSourceTableItem;
}> = ({ headerTable, entryTable }) => {
  const { t } = useTranslation();
  const form = Form.useFormInstance();

  return (
    <Row gutter={8} align="middle">
      <Col span={3}>
        <ProFormSwitch
          name="enabled"
          label={t('pages.system.apis.outboundMappingEnabled')}
          formItemProps={itemFormProps}
        />
      </Col>
      <Col span={4}>
        <SafeProFormSelect
          name="level"
          label={t('pages.system.apis.outboundMappingLevel')}
          options={[
            { label: t('pages.system.apis.outboundMappingLevelHeader'), value: 'header' },
            { label: t('pages.system.apis.outboundMappingLevelEntry'), value: 'entry' },
          ]}
          formItemProps={itemFormProps}
          fieldProps={{
            onChange: (level: 'header' | 'entry') => {
              const table =
                level === 'entry' ? entryTable?.table : headerTable?.table;
              form.setFieldsValue({
                local_field: undefined,
                source_table: table || undefined,
              });
            },
          }}
        />
      </Col>
      <Col span={6}>
        <ProFormDependency name={['level']}>
          {({ level }) => {
            const table = level === 'entry' ? entryTable : headerTable;
            const fieldOpts = (table?.fields || []).map((f) => ({
              label: `${f.label}（${f.field}）`,
              value: f.field,
            }));
            return (
              <SafeProFormSelect
                name="local_field"
                label={t('pages.system.apis.outboundLocalField')}
                options={fieldOpts}
                showSearch
                allowClear
                placeholder={
                  table
                    ? t('pages.system.apis.outboundLocalFieldSelectPlaceholder')
                    : t('pages.system.apis.outboundLocalFieldNeedDoc')
                }
                disabled={!table}
                formItemProps={itemFormProps}
                fieldProps={{
                  optionFilterProp: 'label',
                  onChange: () => {
                    if (table?.table) {
                      form.setFieldsValue({ source_table: table.table });
                    }
                  },
                }}
              />
            );
          }}
        </ProFormDependency>
      </Col>
      <Col span={5}>
        <ProFormText
          name="remote_field"
          label={t('pages.system.apis.outboundRemoteField')}
          placeholder={t('pages.system.apis.outboundRemoteFieldPlaceholder')}
          formItemProps={itemFormProps}
        />
      </Col>
      <Col span={5}>
        <ProFormText
          name="default_value"
          label={t('pages.system.apis.outboundDefaultValue')}
          placeholder={t('pages.system.apis.outboundDefaultValuePlaceholder')}
          formItemProps={itemFormProps}
        />
      </Col>
      {/* 隐藏写入 source_table，提交时带上 */}
      <ProFormText name="source_table" hidden />
    </Row>
  );
};

export interface OutboundFieldMappingEditorProps {
  path?: string;
}

export const OutboundFieldMappingEditor: React.FC<OutboundFieldMappingEditorProps> = ({
  path,
}) => {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const [loading, setLoading] = useState(false);
  const [catalog, setCatalog] = useState<OutboundSourceCatalogResponse | null>(null);
  const pathLower = String(path || '').toLowerCase();
  const isPurin = pathLower.includes('im_purinbill') || pathLower.includes('purinbill');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void getOutboundSourceCatalog(path)
      .then((res) => {
        if (cancelled) return;
        if (res?.tables?.length) {
          setCatalog(res);
        } else {
          setCatalog({
            profiles: [{ code: 'purchase_receipt', name: '采购入库单', match_paths: ['im_purinbill'] }],
            tables: FALLBACK_PURCHASE_RECEIPT_TABLES,
          });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCatalog({
            profiles: [{ code: 'purchase_receipt', name: '采购入库单', match_paths: ['im_purinbill'] }],
            tables: FALLBACK_PURCHASE_RECEIPT_TABLES,
          });
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  const profileOptions = useMemo(() => {
    const fromApi = (catalog?.profiles || []).map((p) => ({
      label: `${p.name}${p.code && p.code !== p.name ? `（${p.code}）` : ''}`,
      value: p.code,
    }));
    if (fromApi.length) return fromApi;
    return [
      { label: '采购入库单（表头+明细）', value: 'purchase_receipt' },
      ...FALLBACK_PURCHASE_RECEIPT_TABLES.map((tb) => ({
        label: `${tb.label}（${tb.table}）`,
        value: tb.table,
      })),
    ];
  }, [catalog]);

  const tables = catalog?.tables || FALLBACK_PURCHASE_RECEIPT_TABLES;

  // 仅在未选时写入推荐/兜底，不锁死采购入库
  useEffect(() => {
    if (!catalog) return;
    const current = form.getFieldValue('outbound_source_profile');
    if (current) return;
    const recommended =
      catalog.recommended_profile ||
      (isPurin ? 'purchase_receipt' : undefined) ||
      catalog.profiles?.[0]?.code;
    if (recommended) {
      form.setFieldsValue({ outbound_source_profile: recommended });
    }
  }, [isPurin, catalog, form]);

  return (
    <div style={{ marginBottom: 16 }}>
      <Spin spinning={loading}>
        <Row gutter={16} style={{ marginBottom: 12 }}>
          <Col span={14}>
            <SafeProFormSelect
              name="outbound_source_profile"
              label={t('pages.system.apis.outboundSourceDoc')}
              options={profileOptions}
              showSearch
              allowClear
              placeholder={t('pages.system.apis.outboundSourceDocPlaceholder')}
              rules={[{ required: true, message: t('pages.system.apis.outboundSourceDocRequired') }]}
              fieldProps={{
                optionFilterProp: 'label',
                filterOption: (input, option) => {
                  const text = String(option?.label ?? option?.value ?? '').toLowerCase();
                  return text.includes(String(input || '').toLowerCase());
                },
                onChange: (code: string) => {
                  const rows = form.getFieldValue('outbound_field_mappings');
                  if (!Array.isArray(rows) || !rows.length) return;
                  const header = tables.find(
                    (tb) => tb.profile_code === code && tb.level === 'header',
                  );
                  const entry = tables.find(
                    (tb) => tb.profile_code === code && tb.level === 'entry',
                  );
                  form.setFieldsValue({
                    outbound_field_mappings: rows.map((row: Record<string, unknown>) => {
                      const level = row.level === 'entry' ? 'entry' : 'header';
                      return {
                        ...row,
                        local_field: undefined,
                        source_table:
                          level === 'entry'
                            ? entry?.table || header?.table
                            : header?.table || entry?.table,
                      };
                    }),
                  });
                },
              }}
            />
          </Col>
          <Col span={10} style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 8 }}>
            <Typography.Text type="secondary">
              {t('pages.system.apis.outboundSourceDocHint')}
            </Typography.Text>
          </Col>
        </Row>

        <ProFormDependency name={['outbound_source_profile']}>
          {({ outbound_source_profile }) => {
            const profileCode = String(
              outbound_source_profile ||
                catalog?.recommended_profile ||
                'purchase_receipt',
            );
            const profileTables = tables.filter((tb) => tb.profile_code === profileCode);
            const headerTable =
              profileTables.find((tb) => tb.level === 'header') || profileTables[0];
            const entryTable =
              profileTables.find((tb) => tb.level === 'entry') ||
              profileTables.find((tb) => tb.table !== headerTable?.table);

            const fillFromRequestBody = () => {
              const rawBody = normalizeJsonFieldValue(form.getFieldValue('request_body'));
              const before = (form.getFieldValue('outbound_field_mappings') ||
                []) as OutboundFieldMappingRow[];
              const beforeRemotes = new Set(
                (Array.isArray(before) ? before : [])
                  .map((r) => String(r.remote_field || '').trim())
                  .filter(Boolean),
              );
              const merged = mergeRequestBodyFieldsIntoMappings(before, rawBody, {
                headerTable: headerTable?.table,
                entryTable: entryTable?.table,
              });
              const filled = merged.filter((r) => {
                const remote = String(r.remote_field || '').trim();
                return remote && !beforeRemotes.has(remote);
              }).length;
              if (filled <= 0) {
                message.info(t('pages.system.apis.fillRemoteFromBodyNone'));
                return;
              }
              form.setFieldsValue({ outbound_field_mappings: merged });
              message.success(
                t('pages.system.apis.fillRemoteFromBodyDone', { count: filled }),
              );
            };

            return (
              <>
                <Space wrap style={{ marginBottom: 8 }}>
                  <Button type="link" size="small" onClick={fillFromRequestBody}>
                    {t('pages.system.apis.fillRemoteFromBody')}
                  </Button>
                  <Typography.Text type="secondary">
                    {t('pages.system.apis.fillRemoteFromBodyHint')}
                  </Typography.Text>
                </Space>
                <ProFormList
                  name="outbound_field_mappings"
                  label={t('pages.system.apis.outboundFieldMappingLabel')}
                  tooltip={t('pages.system.apis.outboundFieldMappingHintTableFirst')}
                  creatorButtonProps={{
                    creatorButtonText: t('pages.system.apis.addOutboundMappingRow'),
                  }}
                  className="api-form-kv-list"
                  itemRender={({ listDom, action }) => (
                    <div className="api-form-kv-list-item">
                      <div className="api-form-kv-list-item__fields">{listDom}</div>
                      <div className="api-form-kv-list-item__actions">{action}</div>
                    </div>
                  )}
                  min={0}
                  creatorRecord={{
                    enabled: true,
                    level: 'header',
                    source_table: headerTable?.table || '',
                    local_field: '',
                    remote_field: '',
                    default_value: '',
                  }}
                >
                  <MappingRowFields headerTable={headerTable} entryTable={entryTable} />
                </ProFormList>
              </>
            );
          }}
        </ProFormDependency>
      </Spin>
    </div>
  );
};
