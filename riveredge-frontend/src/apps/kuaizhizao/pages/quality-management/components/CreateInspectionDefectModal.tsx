import React, { useEffect, useMemo, useState } from 'react';
import {
  App,
  Button,
  Card,
  Input,
  InputNumber,
  Modal,
  Row,
  Col,
  Select,
  Space,
  Table,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { MODAL_CONFIG } from '../../../../../components/layout-templates/constants';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import { formatQuantityWithUnit } from '../../../../../utils/materialUnitDisplay';
import { formatQuantity } from '../../../../../utils/format';
import { getQualityDefectTypeOptions, getQualityDispositionValueEnum } from './qualityMeta';
import { InspectionDefectLineExtraFields } from './InspectionDefectLineExtraFields';
import {
  createEmptyDefectLine,
  lineNeedsExpandFields,
  sumDefectLineQuantities,
  toDefectLinePayload,
  type InspectionDefectDispositionSource,
  type InspectionDefectLineDraft,
  type InspectionDefectLinePayload,
} from './defectRecordLineTypes';

export type InspectionDefectContext = {
  id: number;
  inspection_code?: string;
  material_name?: string;
  material_unit?: string;
  unqualified_quantity?: number;
};

type CreateInspectionDefectModalProps = {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
  inspection: InspectionDefectContext | null;
  source: InspectionDefectDispositionSource;
  defaultDisposition: string;
  disposalOptions: Array<{ label: string; value: string }>;
  disposalLoading?: boolean;
  canReadNcLedger?: boolean;
  ledgerQueryParam: 'incoming_inspection_id' | 'process_inspection_id' | 'finished_goods_inspection_id';
  createDefectBatch: (inspectionId: string, lines: InspectionDefectLinePayload[]) => Promise<unknown>;
};

function validateLine(
  line: InspectionDefectLineDraft,
  t: (key: string) => string,
): string | null {
  if (!(Number(line.defect_quantity) > 0)) {
    return t('app.kuaizhizao.quality.common.validation.requiredDefectQty');
  }
  if (!line.defect_type) {
    return t('app.kuaizhizao.quality.common.validation.requiredDefectType');
  }
  if (!String(line.defect_reason || '').trim()) {
    return t('app.kuaizhizao.quality.common.validation.requiredDefectReason');
  }
  if (!line.disposition) {
    return t('app.kuaizhizao.quality.common.validation.requiredDisposition');
  }
  if (line.disposition === 'downgrade') {
    if (!line.downgrade_material_id || !line.downgrade_warehouse_id) {
      return t('app.kuaizhizao.quality.common.validation.requiredDowngradeMaterial');
    }
  }
  if (line.disposition === 'quarantine' && !line.quarantine_warehouse_id) {
    return t('app.kuaizhizao.quality.common.validation.requiredQuarantineWarehouse');
  }
  if (line.disposition === 'scrap' && !line.stock_warehouse_id) {
    return t('app.kuaizhizao.quality.common.validation.requiredScrapWarehouse');
  }
  if (line.disposition === 'accept' && !line.stock_warehouse_id) {
    return t('app.kuaizhizao.quality.common.validation.requiredAcceptWarehouse');
  }
  if (line.disposition === 'other' && !String(line.remarks || '').trim()) {
    return t('app.kuaizhizao.quality.common.validation.requiredOtherRemarks');
  }
  return null;
}

export function CreateInspectionDefectModal({
  open,
  onClose,
  onSuccess,
  inspection,
  source,
  defaultDisposition,
  disposalOptions,
  disposalLoading = false,
  canReadNcLedger = false,
  ledgerQueryParam,
  createDefectBatch,
}: CreateInspectionDefectModalProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [lines, setLines] = useState<InspectionDefectLineDraft[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([]);

  const defectTypeOptions = useMemo(() => getQualityDefectTypeOptions(t), [t]);
  const allowedDispositionValues = useMemo(
    () => new Set(Object.keys(getQualityDispositionValueEnum(t, { source }))),
    [source, t],
  );
  const filteredDisposalOptions = useMemo(
    () => disposalOptions.filter((opt) => allowedDispositionValues.has(String(opt.value))),
    [allowedDispositionValues, disposalOptions],
  );

  const maxQuantity = Number(inspection?.unqualified_quantity || 0);
  const allocated = useMemo(() => sumDefectLineQuantities(lines), [lines]);
  const remaining = Math.max(0, maxQuantity - allocated);

  useEffect(() => {
    if (!open || !inspection) return;
    const initial = createEmptyDefectLine(maxQuantity, defaultDisposition);
    setLines([initial]);
    setExpandedRowKeys(lineNeedsExpandFields(initial.disposition) ? [initial.key] : []);
  }, [open, inspection, maxQuantity, defaultDisposition]);

  const updateLine = (key: string, patch: Partial<InspectionDefectLineDraft>) => {
    setLines((prev) =>
      prev.map((line) => {
        if (line.key !== key) return line;
        const next = { ...line, ...patch };
        if (patch.disposition && patch.disposition !== line.disposition) {
          return {
            ...next,
            quarantine_warehouse_id: undefined,
            stock_warehouse_id: undefined,
            downgrade_material_id: undefined,
            downgrade_warehouse_id: undefined,
            remarks: patch.disposition === 'other' ? next.remarks : '',
          };
        }
        return next;
      }),
    );
    if (patch.disposition && lineNeedsExpandFields(patch.disposition)) {
      setExpandedRowKeys((prev) => (prev.includes(key) ? prev : [...prev, key]));
    }
  };

  const handleAddLine = () => {
    const qty = remaining > 0 ? remaining : 0;
    const next = createEmptyDefectLine(qty, defaultDisposition);
    setLines((prev) => [...prev, next]);
    if (lineNeedsExpandFields(next.disposition)) {
      setExpandedRowKeys((prev) => [...prev, next.key]);
    }
  };

  const handleRemoveLine = (key: string) => {
    setLines((prev) => {
      if (prev.length <= 1) return prev;
      return prev.filter((line) => line.key !== key);
    });
    setExpandedRowKeys((prev) => prev.filter((k) => k !== key));
  };

  const handleSubmit = async () => {
    if (!inspection?.id) return;
    if (!lines.length) {
      message.error(t('app.kuaizhizao.quality.common.validation.requiredDefectLine'));
      return;
    }
    for (const line of lines) {
      const err = validateLine(line, t);
      if (err) {
        message.error(err);
        return;
      }
    }
    if (allocated <= 0) {
      message.error(t('app.kuaizhizao.quality.common.validation.requiredDefectQty'));
      return;
    }
    if (allocated > maxQuantity) {
      message.error(
        t('app.kuaizhizao.quality.common.validation.defectQtyExceedsUnqualified', {
          allocated: formatQuantity(allocated),
          max: formatQuantity(maxQuantity),
        }),
      );
      return;
    }

    setSubmitting(true);
    try {
      await createDefectBatch(
        String(inspection.id),
        lines.map((line) => toDefectLinePayload(line)),
      );
      message.success(
        canReadNcLedger
          ? {
              content: (
                <Space>
                  <span>{t('app.kuaizhizao.quality.common.messages.createDefectSuccess')}</span>
                  <Button
                    type="link"
                    size="small"
                    onClick={() =>
                      window.open(
                        `/apps/kuaizhizao/quality-management/nonconforming-ledger?${ledgerQueryParam}=${inspection.id}`,
                        '_blank',
                      )
                    }
                  >
                    {t('app.kuaizhizao.quality.common.actions.viewLedger')}
                  </Button>
                </Space>
              ),
            }
          : t('app.kuaizhizao.quality.common.messages.createDefectSuccess'),
      );
      onSuccess();
      onClose();
    } catch (error: unknown) {
      const err = error as { message?: string };
      message.error(err.message || t('app.kuaizhizao.quality.common.messages.createDefectFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ColumnsType<InspectionDefectLineDraft> = [
    {
      title: t('app.kuaizhizao.quality.common.form.defectQty'),
      dataIndex: 'defect_quantity',
      width: 110,
      render: (_, record) => (
        <InputNumber
          min={0}
          max={maxQuantity}
          precision={2}
          style={{ width: '100%' }}
          value={record.defect_quantity}
          onChange={(value) => updateLine(record.key, { defect_quantity: Number(value ?? 0) })}
        />
      ),
    },
    {
      title: t('app.kuaizhizao.quality.common.form.defectType'),
      dataIndex: 'defect_type',
      width: 120,
      render: (_, record) => (
        <Select
          style={{ width: '100%' }}
          options={defectTypeOptions}
          value={record.defect_type}
          onChange={(value) => updateLine(record.key, { defect_type: value })}
        />
      ),
    },
    {
      title: t('app.kuaizhizao.quality.common.form.defectReason'),
      dataIndex: 'defect_reason',
      width: 180,
      render: (_, record) => (
        <Input.TextArea
          rows={2}
          value={record.defect_reason}
          placeholder={t('app.kuaizhizao.quality.common.placeholder.defectReason')}
          onChange={(e) => updateLine(record.key, { defect_reason: e.target.value })}
        />
      ),
    },
    {
      title: t('app.kuaizhizao.quality.common.form.disposition'),
      dataIndex: 'disposition',
      width: 140,
      render: (_, record) => (
        <UniDropdown
          style={{ width: '100%' }}
          placeholder={t('app.kuaizhizao.quality.common.form.selectDisposition')}
          showSearch
          allowClear={false}
          loading={disposalLoading}
          options={filteredDisposalOptions}
          value={record.disposition}
          onChange={(value) => updateLine(record.key, { disposition: String(value || '') })}
          quickCreate={{
            label: t('app.kuaizhizao.quality.common.form.dataDictionaryManage'),
            onClick: () => navigate('/system/data-dictionaries'),
          }}
        />
      ),
    },
    {
      title: t('common.action'),
      key: 'actions',
      width: 56,
      fixed: 'right',
      align: 'center',
      render: (_, record) => (
        <Button
          type="link"
          danger
          size="small"
          icon={<DeleteOutlined />}
          disabled={lines.length <= 1}
          onClick={() => handleRemoveLine(record.key)}
        />
      ),
    },
  ];

  return (
    <Modal
      title={t('app.kuaizhizao.quality.common.modal.createDefectTitle')}
      open={open}
      onCancel={onClose}
      width={MODAL_CONFIG.LARGE_WIDTH}
      destroyOnHidden
      footer={
        <Space>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="primary" loading={submitting} onClick={() => void handleSubmit()}>
            {t('common.save')}
          </Button>
        </Space>
      }
    >
      {inspection ? (
        <>
          <Card title={t('app.kuaizhizao.quality.common.sections.inspectionInfo')} size="small" style={{ marginBottom: 12 }}>
            <Row gutter={16}>
              <Col span={12}>
                <strong>{t('app.kuaizhizao.quality.common.label.inspectionCode')}：</strong>
                {inspection.inspection_code}
              </Col>
              <Col span={12}>
                <strong>{t('app.kuaizhizao.quality.common.label.materialName')}：</strong>
                {inspection.material_name}
              </Col>
            </Row>
            <Row gutter={16} style={{ marginTop: 8 }}>
              <Col span={12}>
                <strong>{t('app.kuaizhizao.quality.common.label.unqualifiedQty')}：</strong>
                {formatQuantityWithUnit(inspection.unqualified_quantity, inspection.material_unit)}
              </Col>
              <Col span={12}>
                <Typography.Text type={remaining > 0 ? 'warning' : undefined}>
                  {t('app.kuaizhizao.quality.common.label.defectAllocationSummary', {
                    allocated: formatQuantity(allocated),
                    remaining: formatQuantity(remaining),
                  })}
                </Typography.Text>
              </Col>
            </Row>
          </Card>

          <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
            {t('app.kuaizhizao.quality.common.hint.multiDefectLines')}
          </Typography.Paragraph>

          <Table<InspectionDefectLineDraft>
            size="small"
            rowKey="key"
            columns={columns}
            dataSource={lines}
            pagination={false}
            scroll={{ x: 720 }}
            expandable={{
              expandedRowKeys,
              onExpandedRowsChange: (keys) => setExpandedRowKeys(keys as string[]),
              rowExpandable: (record) => lineNeedsExpandFields(record.disposition),
              expandedRowRender: (record) => (
                <InspectionDefectLineExtraFields
                  line={record}
                  source={source}
                  onChange={(patch) => updateLine(record.key, patch)}
                />
              ),
            }}
          />

          <Button
            type="dashed"
            icon={<PlusOutlined />}
            style={{ width: '100%', marginTop: 12 }}
            onClick={handleAddLine}
          >
            {t('app.kuaizhizao.quality.common.actions.addDefectLine')}
          </Button>
        </>
      ) : null}
    </Modal>
  );
}
