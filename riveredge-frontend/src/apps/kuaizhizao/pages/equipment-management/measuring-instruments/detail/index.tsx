/**
 * 计量器具详情：基本信息 + 设备二维码/设备卡 + 点检方案绑定 + 校准记录
 * 与设备台账共用 Equipment 行（EQ 码）；企微扫码点检/报修走同一解析路径。
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ProDescriptions,
  type ProDescriptionsItemProps,
} from '@ant-design/pro-components';
import {
  App,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  QRCode,
  Select,
  Space,
  Spin,
  Table,
  Typography,
  Upload,
} from 'antd';
import { ArrowLeftOutlined, EditOutlined, PlusOutlined, QrcodeOutlined, UploadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { equipmentApi } from '../../../../services/equipment';
import { inspectionSchemesApi, schemeBindingsApi } from '../../../../services/equipmentOps';
import {
  DOCUMENT_DETAIL_PAGE_HEADER_STYLE,
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  MultiTabListPageTemplate,
  MODAL_CONFIG,
} from '../../../../../../components/layout-templates';
import { QRCodeGenerator } from '../../../../../../components/qrcode';
import { DocumentTrackingTimelineBody, useDocumentTracking } from '../../../../../../components/document-tracking-panel';
import { ActionConfirmPopconfirm } from '../../../../../../components/action-confirm';
import { rowActionKind } from '../../../../../../components/uni-action';
import { useResourcePermissions } from '../../../../../../hooks/useResourcePermissions';
import { MarkerTag } from '../../../../../../constants/statusBadges';
import { formatDateBySiteSetting, formatDateTime } from '../../../../../../utils/format';
import { normalizeDocumentAttachments } from '../../../../utils/documentAttachments';
import { DocumentAttachmentsReadonly } from '../../../../components/DocumentAttachmentsReadonly';
import { uploadMultipleFiles } from '../../../../../../services/file';
import { FutureDatePicker } from '../../../../../../utils/futureDatePickerShortcuts';
import { useSubmitShortcut } from '../../../../../../hooks/useSubmitShortcut';
import { useKuaizhizaoPrintModal } from '../../../../hooks/useKuaizhizaoPrintModal';
import { useLeaveFormTab, navigateClosingTab, uniTabKey } from '../../../../../../components/uni-tabs/navigateClosingTab';
import { ROUTES } from '../../../../constants/routes';
import {
  KUAIZHIZAO_MEASURING_INSTRUMENT_LIST_PATH,
  buildMeasuringInstrumentDetailPath,
  resolveMeasuringInstrumentDetailTabKey,
} from '../measuringInstrumentPaths';

const P = 'app.kuaizhizao.measuringInstrument';

interface MeasuringInstrumentDetail {
  id?: number;
  uuid?: string;
  code?: string;
  name?: string;
  model?: string;
  brand?: string;
  category?: string;
  workshop_name?: string;
  work_center_name?: string;
  calibration_period?: number;
  last_calibration_date?: string;
  next_calibration_date?: string;
  measuring_precision?: string;
  measurement_range?: string;
  status?: string;
  is_active?: boolean;
  description?: string;
  qr_bind_code?: string | null;
  created_at?: string;
  updated_at?: string;
  created_by_name?: string;
  updated_by_name?: string;
}

function buildSpotCheckCreatePath(equipmentId: number): string {
  const q = new URLSearchParams({ create: '1', equipment_id: String(equipmentId) });
  return `${ROUTES.EQUIPMENT_SPOT_CHECKS}?${q.toString()}`;
}

interface CalibrationRecord {
  uuid?: string;
  plan_type?: string;
  calibration_date?: string;
  result?: string;
  certificate_no?: string;
  expiry_date?: string;
  remark?: string;
  attachments?: Array<{ uid?: string; name?: string; url?: string }>;
  created_by_name?: string;
}

const MeasuringInstrumentDetailPage: React.FC = () => {
  const { uuid } = useParams<{ uuid: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const perms = useResourcePermissions('kuaizhizao:equipment-management-equipment');
  const calibPerms = useResourcePermissions('kuaizhizao:measuring-instrument-calibration');
  const schemePerms = useResourcePermissions('kuaizhizao:equipment-inspection-scheme');
  const spotCheckPerms = useResourcePermissions('kuaizhizao:equipment-spot-check');
  const { openPrint, PrintModal } = useKuaizhizaoPrintModal();

  const activeTab = resolveMeasuringInstrumentDetailTabKey(searchParams.get('tab'));
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<MeasuringInstrumentDetail | null>(null);
  const [calibrations, setCalibrations] = useState<CalibrationRecord[]>([]);
  const [calibLoading, setCalibLoading] = useState(false);
  const [calibModalVisible, setCalibModalVisible] = useState(false);
  const [editingCalib, setEditingCalib] = useState<CalibrationRecord | null>(null);
  const [calibForm] = Form.useForm();
  const [trackingRefreshKey, setTrackingRefreshKey] = useState(0);
  const [boundSpotSchemeIds, setBoundSpotSchemeIds] = useState<number[]>([]);
  const [spotSchemeSelectOptions, setSpotSchemeSelectOptions] = useState<
    { label: string; value: number }[]
  >([]);
  const [schemeBindingsSaving, setSchemeBindingsSaving] = useState(false);

  const canCreateCalib = calibPerms.canCreate || perms.canUpdate;
  const canUpdateCalib = calibPerms.canUpdate;
  const canDeleteCalib = calibPerms.canDelete;
  const canBindSpotSchemes = schemePerms.canUpdate;
  const canCreateSpotCheck = spotCheckPerms.canCreate;

  const tracking = useDocumentTracking(detail?.id ? 'equipment' : undefined, detail?.id, trackingRefreshKey);

  const loadCalibrations = useCallback(async (equipmentUuid: string) => {
    setCalibLoading(true);
    try {
      const res = await equipmentApi.listCalibrations({ equipment_uuid: equipmentUuid, limit: 200 });
      setCalibrations(res?.items ?? []);
    } catch {
      setCalibrations([]);
    } finally {
      setCalibLoading(false);
    }
  }, []);

  const loadSpotSchemeBindings = useCallback(async (equipmentId: number) => {
    const [spotBindings, spotSchemesRes] = await Promise.all([
      schemeBindingsApi.list({ equipment_id: equipmentId, scheme_type: 'spot_check' }),
      inspectionSchemesApi.list({ limit: 1000, is_active: true }),
    ]);
    setBoundSpotSchemeIds((spotBindings ?? []).map((b: { scheme_id: number }) => b.scheme_id));
    setSpotSchemeSelectOptions(
      (spotSchemesRes.items ?? []).map((s: { id: number; code: string; name: string }) => ({
        label: `${s.code} - ${s.name}`,
        value: s.id,
      })),
    );
  }, []);

  const loadPage = useCallback(async () => {
    if (!uuid) return;
    setLoading(true);
    try {
      const loaded = await equipmentApi.get(uuid);
      setDetail(loaded);
      setTrackingRefreshKey((k) => k + 1);
      await loadCalibrations(uuid);
      if (loaded?.id != null) {
        await loadSpotSchemeBindings(loaded.id);
      } else {
        setBoundSpotSchemeIds([]);
        setSpotSchemeSelectOptions([]);
      }
    } catch {
      messageApi.error(t(`${P}.loadFailed`));
    } finally {
      setLoading(false);
    }
  }, [loadCalibrations, loadSpotSchemeBindings, messageApi, t, uuid]);

  useEffect(() => {
    void loadPage();
  }, [loadPage]);

  useLeaveFormTab(uniTabKey(location.pathname));

  const basicColumns: ProDescriptionsItemProps<MeasuringInstrumentDetail>[] = useMemo(
    () => [
      { title: t(`${P}.fieldCode`), dataIndex: 'code' },
      { title: t(`${P}.fieldName`), dataIndex: 'name' },
      { title: t(`${P}.fieldModel`), dataIndex: 'model' },
      { title: t(`${P}.fieldBrand`), dataIndex: 'brand' },
      { title: t(`${P}.fieldCategory`), dataIndex: 'category' },
      { title: t(`${P}.fieldMeasuringPrecision`), dataIndex: 'measuring_precision' },
      { title: t(`${P}.fieldMeasurementRange`), dataIndex: 'measurement_range' },
      { title: t(`${P}.colWorkshop`), dataIndex: 'workshop_name' },
      { title: t(`${P}.fieldWorkCenter`), dataIndex: 'work_center_name' },
      {
        title: t(`${P}.fieldLastCalibrationDate`),
        dataIndex: 'last_calibration_date',
        render: (_, r) =>
          r.last_calibration_date ? formatDateBySiteSetting(r.last_calibration_date) : '-',
      },
      {
        title: t(`${P}.fieldCalibrationPeriod`),
        dataIndex: 'calibration_period',
        render: (_, r) =>
          r.calibration_period != null ? t(`${P}.periodDays`, { count: r.calibration_period }) : '-',
      },
      {
        title: t(`${P}.colNextCalibrationDate`),
        dataIndex: 'next_calibration_date',
        render: (_, r) =>
          r.next_calibration_date ? formatDateBySiteSetting(r.next_calibration_date) : '-',
      },
      {
        title: t(`${P}.fieldStatus`),
        dataIndex: 'status',
        render: (_, r) => <MarkerTag>{r.status ?? '-'}</MarkerTag>,
      },
      {
        title: t('common.enabled'),
        dataIndex: 'is_active',
        render: (_, r) => (
          <MarkerTag color={r.is_active ? 'success' : 'default'}>
            {r.is_active ? t('common.enabled') : t('common.disabled')}
          </MarkerTag>
        ),
      },
      { title: t('common.remark'), dataIndex: 'description', span: 2 },
      { title: t('common.createdAt'), dataIndex: 'created_at', render: (_, r) => formatDateTime(r.created_at) },
      { title: t('common.updatedAt'), dataIndex: 'updated_at', render: (_, r) => formatDateTime(r.updated_at) },
    ],
    [t],
  );

  const calibrationResultOptions = useMemo(
    () => [
      { label: t('app.kuaizhizao.equipment.resultPass'), value: '合格' },
      { label: t('app.kuaizhizao.equipment.resultFail'), value: '不合格' },
      { label: t('app.kuaizhizao.equipment.resultRestricted'), value: '限制使用' },
    ],
    [t],
  );

  const handleOpenCalibrationModal = useCallback(() => {
    setEditingCalib(null);
    calibForm.resetFields();
    calibForm.setFieldsValue({ calibration_date: dayjs(), result: '合格' });
    setCalibModalVisible(true);
  }, [calibForm]);

  const handleEditCalibration = useCallback(
    (record: CalibrationRecord) => {
      setEditingCalib(record);
      calibForm.setFieldsValue({
        calibration_date: record.calibration_date ? dayjs(record.calibration_date) : undefined,
        expiry_date: record.expiry_date ? dayjs(record.expiry_date) : undefined,
        result: record.result,
        certificate_no: record.certificate_no,
        remark: record.remark,
        attachments: record.attachments || [],
      });
      setCalibModalVisible(true);
    },
    [calibForm],
  );

  const handleDeleteCalibration = useCallback(
    async (record: CalibrationRecord) => {
      if (!record.uuid) return;
      try {
        await equipmentApi.deleteCalibrationRecord(record.uuid);
        messageApi.success(t('common.deleteSuccess'));
        await loadPage();
      } catch (e: unknown) {
        const err = e as { message?: string };
        messageApi.error(err?.message || t('common.deleteFailed'));
      }
    },
    [loadPage, messageApi, t],
  );

  const handleSubmitCalibration = async () => {
    try {
      const values = await calibForm.validateFields();
      if (!uuid) return;
      const payload = {
        calibration_date: values.calibration_date?.format?.('YYYY-MM-DD') || values.calibration_date,
        result: values.result,
        certificate_no: values.certificate_no,
        expiry_date: values.expiry_date?.format?.('YYYY-MM-DD') || values.expiry_date,
        remark: values.remark,
        attachments: normalizeDocumentAttachments(values.attachments),
      };
      if (editingCalib?.uuid) {
        await equipmentApi.updateCalibrationRecord(editingCalib.uuid, payload);
      } else {
        await equipmentApi.createCalibration(uuid, payload);
      }
      messageApi.success(t('app.kuaizhizao.equipment.calibrationSaved'));
      setCalibModalVisible(false);
      setEditingCalib(null);
      await loadPage();
    } catch (e: any) {
      if (e?.errorFields) return;
      messageApi.error(e?.message || t('common.saveFailed'));
    }
  };

  useSubmitShortcut(handleSubmitCalibration, calibModalVisible);

  const tabItems = useMemo(() => {
    if (!detail) return [];
    return [
      {
        key: 'info',
        label: t(`${P}.detailTabInfo`),
        children: (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <Card size="small" title={t('app.uniDetail.sectionBasic')}>
              <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <ProDescriptions<MeasuringInstrumentDetail>
                    dataSource={detail}
                    column={3}
                    columns={basicColumns}
                  />
                </div>
                {detail.uuid ? (
                  <div
                    style={{
                      flex: '0 0 168px',
                      width: 168,
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      gap: 8,
                    }}
                  >
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {detail.qr_bind_code
                        ? t('app.kuaizhizao.equipment.qrcodeBindCardTitle')
                        : t('app.kuaizhizao.equipment.qrcodeCardTitle')}
                    </Typography.Text>
                    {detail.qr_bind_code ? (
                      <>
                        <QRCode value={String(detail.qr_bind_code)} size={148} errorLevel="M" />
                        <Typography.Text
                          type="secondary"
                          copyable={{ text: String(detail.qr_bind_code) }}
                          style={{ fontSize: 12, maxWidth: 160, textAlign: 'center' }}
                        >
                          {detail.qr_bind_code}
                        </Typography.Text>
                      </>
                    ) : (
                      <QRCodeGenerator
                        qrcodeType="EQ"
                        data={{
                          equipment_uuid: detail.uuid,
                          equipment_code: detail.code || '',
                          equipment_name: detail.name || '',
                        }}
                        autoGenerate
                        size={6}
                        noCard
                      />
                    )}
                  </div>
                ) : null}
              </div>
            </Card>
            <Card size="small" title={t('app.kuaizhizao.equipmentOps.schemeBindings.title')}>
              <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
                {t(`${P}.spotCheckBindingHint`)}
              </Typography.Paragraph>
              <Typography.Text type="secondary">
                {t('app.kuaizhizao.equipmentOps.schemeBindings.spotCheck')}
              </Typography.Text>
              <Select
                mode="multiple"
                style={{ width: '100%', marginTop: 4 }}
                placeholder={t('app.kuaizhizao.equipmentOps.schemeBindings.selectSchemes')}
                options={spotSchemeSelectOptions}
                value={boundSpotSchemeIds}
                onChange={setBoundSpotSchemeIds}
                disabled={!canBindSpotSchemes || detail.id == null}
              />
              <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {canBindSpotSchemes ? (
                  <Button
                    type="primary"
                    loading={schemeBindingsSaving}
                    disabled={detail.id == null}
                    onClick={async () => {
                      if (detail.id == null) return;
                      setSchemeBindingsSaving(true);
                      try {
                        await schemeBindingsApi.bulkReplace({
                          equipment_id: detail.id,
                          scheme_type: 'spot_check',
                          scheme_ids: boundSpotSchemeIds,
                        });
                        messageApi.success(
                          t('app.kuaizhizao.equipmentOps.schemeBindings.saveSuccess'),
                        );
                      } catch (error: unknown) {
                        const err = error as { message?: string };
                        messageApi.error(err?.message || t('common.operationFailed'));
                      } finally {
                        setSchemeBindingsSaving(false);
                      }
                    }}
                  >
                    {t('common.save')}
                  </Button>
                ) : null}
                {canCreateSpotCheck && detail.id != null ? (
                  <Button onClick={() => navigate(buildSpotCheckCreatePath(detail.id!))}>
                    {t(`${P}.goCreateSpotCheck`)}
                  </Button>
                ) : null}
              </div>
            </Card>
            <Card size="small" title={t('app.uniDetail.sectionTimeline')}>
              {tracking.loading ? <Spin /> : null}
              {tracking.error && !tracking.loading ? (
                <Typography.Text type="danger">{tracking.error}</Typography.Text>
              ) : null}
              {tracking.data && !tracking.loading ? (
                <DocumentTrackingTimelineBody data={tracking.data} />
              ) : null}
              {!tracking.loading && !tracking.data && !tracking.error ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : null}
            </Card>
          </div>
        ),
      },
      {
        key: 'calibrations',
        label: t(`${P}.detailTabCalibrations`, { count: calibrations.length }),
        children: (
          <Card
            size="small"
            title={t(`${P}.detailTabCalibrationsTitle`)}
            extra={
              canCreateCalib ? (
                <Button type="primary" size="small" icon={<PlusOutlined />} onClick={handleOpenCalibrationModal}>
                  {t(`${P}.addCalibration`)}
                </Button>
              ) : null
            }
          >
            <Table<CalibrationRecord>
              size="small"
              loading={calibLoading}
              rowKey={(r) => r.uuid ?? `${r.calibration_date}-${r.certificate_no}`}
              pagination={false}
              dataSource={calibrations}
              columns={[
                {
                  title: t(`${P}.colCalibrationDate`),
                  dataIndex: 'calibration_date',
                  render: (v) => (v ? formatDateBySiteSetting(String(v)) : '-'),
                },
                { title: t(`${P}.colCalibrationResult`), dataIndex: 'result' },
                { title: t(`${P}.colCertificateNo`), dataIndex: 'certificate_no' },
                {
                  title: t(`${P}.colExpiryDate`),
                  dataIndex: 'expiry_date',
                  render: (v) => (v ? formatDateBySiteSetting(String(v)) : '-'),
                },
                {
                  title: t(`${P}.fieldCertificate`),
                  dataIndex: 'attachments',
                  render: (files: CalibrationRecord['attachments']) => (
                    <DocumentAttachmentsReadonly
                      attachments={files}
                      variant="count"
                      showEmpty
                    />
                  ),
                },
                { title: t('common.remark'), dataIndex: 'remark', ellipsis: true },
                { title: t('common.createdBy'), dataIndex: 'created_by_name' },
                {
                  title: t('common.actions'),
                  key: 'option',
                  width: 160,
                  render: (_, record) => (
                    <Space size={4}>
                      {canUpdateCalib ? (
                        <Button
                          {...rowActionKind('update')}
                          onClick={() => handleEditCalibration(record)}
                        >
                          {t('common.edit')}
                        </Button>
                      ) : null}
                      {canDeleteCalib ? (
                        <ActionConfirmPopconfirm
                          title={t('common.deleteTitle')}
                          onConfirm={() => void handleDeleteCalibration(record)}
                        >
                          <Button {...rowActionKind('delete')} danger>
                            {t('common.delete')}
                          </Button>
                        </ActionConfirmPopconfirm>
                      ) : null}
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
        ),
      },
    ];
  }, [
    basicColumns,
    boundSpotSchemeIds,
    calibLoading,
    calibrations,
    canBindSpotSchemes,
    canCreateCalib,
    canCreateSpotCheck,
    canDeleteCalib,
    canUpdateCalib,
    detail,
    handleDeleteCalibration,
    handleEditCalibration,
    handleOpenCalibrationModal,
    messageApi,
    navigate,
    schemeBindingsSaving,
    spotSchemeSelectOptions,
    t,
    tracking.data,
    tracking.error,
    tracking.loading,
  ]);

  if (loading || !detail) {
    return (
      <div style={{ padding: 24, textAlign: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <>
      <MultiTabListPageTemplate
        header={
          <div style={DOCUMENT_DETAIL_PAGE_HEADER_STYLE}>
            <Space wrap>
              <Button
                icon={<ArrowLeftOutlined />}
                onClick={() => navigateClosingTab(navigate, KUAIZHIZAO_MEASURING_INSTRUMENT_LIST_PATH)}
              >
                {t('common.back')}
              </Button>
              {perms.canPrint && detail.uuid ? (
                <Button
                  icon={<QrcodeOutlined />}
                  onClick={() =>
                    openPrint({
                      documentType: 'equipment_card',
                      documentId: detail.id ?? 1,
                      printApiPath: `/apps/kuaizhizao/equipment/${detail.uuid}/print`,
                      pdfDownloadFilename: `equipment-card-${detail.code || detail.uuid}.pdf`,
                    })
                  }
                >
                  {t('app.kuaizhizao.equipment.printEquipmentCards')}
                </Button>
              ) : null}
              {perms.canUpdate ? (
                <Button
                  icon={<EditOutlined />}
                  onClick={() =>
                    navigate(KUAIZHIZAO_MEASURING_INSTRUMENT_LIST_PATH, {
                      state: { openEditUuid: detail.uuid },
                    })
                  }
                >
                  {t('common.edit')}
                </Button>
              ) : null}
            </Space>
            <Typography.Title level={4} style={DOCUMENT_DETAIL_PAGE_TITLE_STYLE}>
              {detail.code} {detail.name}
              <MarkerTag color="success" style={{ marginLeft: 8 }}>
                {detail.status}
              </MarkerTag>
            </Typography.Title>
          </div>
        }
        tabs={tabItems}
        activeTabKey={activeTab}
        onTabChange={(key) => {
          if (!uuid) return;
          setSearchParams(
            key === 'info'
              ? {}
              : { tab: key },
            { replace: true },
          );
          navigate(buildMeasuringInstrumentDetailPath(uuid, key === 'info' ? undefined : key), {
            replace: true,
          });
        }}
      />

      <Modal
        title={
          editingCalib
            ? t('app.kuaizhizao.measuringInstrumentCalibration.editModal')
            : t(`${P}.addCalibration`)
        }
        open={calibModalVisible}
        destroyOnHidden
        width={MODAL_CONFIG.MEDIUM_WIDTH}
        onCancel={() => {
          setCalibModalVisible(false);
          setEditingCalib(null);
        }}
        onOk={() => void handleSubmitCalibration()}
        okText={t('common.save')}
      >
        <Form form={calibForm} layout="vertical">
          <Form.Item name="calibration_date" label={t(`${P}.colCalibrationDate`)} rules={[{ required: true }]}>
            <FutureDatePicker getForm={() => calibForm} baseFieldName="calibration_date" t={t} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="result" label={t(`${P}.colCalibrationResult`)} rules={[{ required: true }]}>
            <Select options={calibrationResultOptions} />
          </Form.Item>
          <Form.Item name="certificate_no" label={t(`${P}.colCertificateNo`)}>
            <Input />
          </Form.Item>
          <Form.Item name="expiry_date" label={t(`${P}.colExpiryDate`)}>
            <FutureDatePicker getForm={() => calibForm} baseFieldName="calibration_date" t={t} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="attachments"
            label={t(`${P}.fieldCertificate`)}
            valuePropName="fileList"
            getValueFromEvent={(e) => (Array.isArray(e) ? e : e?.fileList)}
          >
            <Upload
              multiple
              customRequest={async (options) => {
                const res = await uploadMultipleFiles([options.file as File], {
                  category: 'equipment_calibration_attachments',
                });
                options.onSuccess?.(res[0], options.file as any);
              }}
            >
              <Button icon={<UploadOutlined />}>{t('app.kuaizhizao.equipment.upload')}</Button>
            </Upload>
          </Form.Item>
          <Form.Item name="remark" label={t('common.remark')}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      {PrintModal}
    </>
  );
};

export default MeasuringInstrumentDetailPage;
