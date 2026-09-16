/**
 * 样机制作书（研发项目 §2.15）
 * 项目发起 → 电子/结构并行填写 → 审核下发 → 制造/质量会签
 */

import React, { useCallback, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { ProColumns } from '@ant-design/pro-components';
import {
  ActionType,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { App, Button, Col, Descriptions, Input, Modal, Row, Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { UniTable } from '../../../../components/uni-table';
import { rowActionKind } from '../../../../components/uni-action';
import {
  DetailDrawerTemplate,
  DRAWER_CONFIG,
  FormModalTemplate,
  ListPageTemplate,
  detailDrawerBasicColumn,
} from '../../../../components/layout-templates';
import { detailDrawerDescriptionItems } from '../../../../components/layout-templates/detailDrawerDescriptionItems';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { getApiErrorMessage } from '../../../../utils/errorHandler';
import { renderDocumentStatusTag } from '../../../../utils/documentLifecycleStatusTag';
import { MarkerTag } from '../../../../constants/statusBadges';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../utils/uniTableLayoutColumns';
import { NEW_SHORTCUT_HINT } from '../../../../utils/globalNewShortcut';
import Phase2ProjectSelect from '../../components/Phase2ProjectSelect';
import {
  prototypeBuildSheetApi,
  type PrototypeBuildRound,
  type PrototypeBuildSheet,
  type PrototypeBuildSheetStatus,
} from '../../services/prototype-build-sheet';

const RESOURCE = 'kuaiplm:prototype-build-sheet';
const STATUS_KEYS: PrototypeBuildSheetStatus[] = [
  'draft',
  'pending',
  'approved',
  'issued',
  'closed',
  'rejected',
];
const ROUND_KEYS: PrototypeBuildRound[] = ['handboard', 't1', 't2', 't3'];

const PrototypeBuildSheetsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const perms = useResourcePermissions(RESOURCE);
  const [searchParams] = useSearchParams();
  const filterProjectId = searchParams.get('project_id')
    ? Number(searchParams.get('project_id'))
    : undefined;
  const actionRef = useRef<ActionType>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [sectionOpen, setSectionOpen] = useState(false);
  const [signoffOpen, setSignoffOpen] = useState(false);
  const [activeSection, setActiveSection] = useState<'electronics' | 'structure'>('electronics');
  const [sectionText, setSectionText] = useState('');
  const [mfgOpinion, setMfgOpinion] = useState('');
  const [qaOpinion, setQaOpinion] = useState('');
  const [detail, setDetail] = useState<PrototypeBuildSheet | null>(null);

  const reload = useCallback(() => actionRef.current?.reload(), []);
  const statusLabel = useCallback(
    (s: string) => t(`app.kuaiplm.prototypeBuildSheet.status.${s}`, { defaultValue: s }),
    [t],
  );
  const roundLabel = useCallback(
    (s: string) => t(`app.kuaiplm.prototypeBuildSheet.round.${s}`, { defaultValue: s }),
    [t],
  );

  const refreshDetail = useCallback(async (id: number) => {
    const full = await prototypeBuildSheetApi.get(id);
    setDetail(full);
    reload();
    return full;
  }, [reload]);

  const columns = useMemo<ProColumns<PrototypeBuildSheet>[]>(
    () =>
      alignProColumns(
        [
          {
            title: t('app.kuaiplm.prototypeBuildSheet.fields.code'),
            dataIndex: 'sheet_code',
            key: 'document_code',
            width: 140,
            copyable: true,
            uniTableKeepWidth: true,
          },
          {
            title: t('app.kuaiplm.prototypeBuildSheet.fields.project'),
            dataIndex: 'project_name',
            key: 'project_name',
            width: 180,
            ellipsis: true,
            render: (_, r) => `${r.project_name} (${r.project_code})`,
          },
          {
            title: t('app.kuaiplm.prototypeBuildSheet.fields.round'),
            dataIndex: 'round_key',
            key: 'round_key',
            width: 100,
            uniTableKeepWidth: true,
            render: (_, r) => <MarkerTag variant="filled">{roundLabel(r.round_key)}</MarkerTag>,
          },
          {
            title: t('app.kuaiplm.prototypeBuildSheet.fields.title'),
            dataIndex: 'title',
            key: 'title',
            ellipsis: true,
            uniTableRemainderFlex: true,
          },
          {
            ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
            title: t('common.status'),
            dataIndex: 'status',
            key: 'lifecycle',
            fixed: 'right',
            render: (_, r) => renderDocumentStatusTag(statusLabel(r.status), r.status),
          },
          {
            title: t('common.action'),
            valueType: 'option',
            key: 'option',
            fixed: 'right',
            render: (_, row) => [
              <Button
                key="detail"
                type="link"
                size="small"
                {...rowActionKind('detail')}
                onClick={() => void refreshDetail(row.id).then(setDetail)}
              />,
            ],
          },
        ],
        GLOBAL_DOC_LIST_FIELD_RANK,
      ),
    [refreshDetail, roundLabel, statusLabel, t],
  );

  return (
    <>
      <ListPageTemplate>
        <UniTable<PrototypeBuildSheet>
          actionRef={actionRef}
          columnPersistenceId="apps.kuaiplm.pages.prototype-build-sheets.v1"
          headerTitle={t('app.kuaiplm.prototypeBuildSheet.title')}
          createButtonText={t('app.kuaiplm.prototypeBuildSheet.createButton') + NEW_SHORTCUT_HINT}
          onCreate={perms.canCreate ? () => setModalOpen(true) : undefined}
          columns={columns}
          onTableDataChange={() => {}}
          request={async (params) => {
            const res = await prototypeBuildSheetApi.list({
              skip: ((params.current || 1) - 1) * (params.pageSize || 20),
              limit: params.pageSize || 20,
              keyword: params.keyword as string | undefined,
              project_id: filterProjectId,
            });
            return { data: res.items, success: true, total: res.total };
          }}
        />
      </ListPageTemplate>

      <FormModalTemplate
        title={t('app.kuaiplm.prototypeBuildSheet.createButton')}
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        grid={false}
        onFinish={async (values) => {
          await prototypeBuildSheetApi.create({
            project_id: Number(values.project_id),
            title: String(values.title || '').trim(),
            round_key: values.round_key as string,
            project_requirements: values.project_requirements || undefined,
            remarks: values.remarks || undefined,
          });
          messageApi.success(t('common.saveSuccess'));
          setModalOpen(false);
          reload();
        }}
      >
        <Row gutter={16}>
          <Col span={12}>
            <Phase2ProjectSelect name="project_id" rules={[{ required: true }]} />
          </Col>
          <Col span={12}>
            <ProFormSelect
              name="round_key"
              label={t('app.kuaiplm.prototypeBuildSheet.fields.round')}
              initialValue="t1"
              options={ROUND_KEYS.map((k) => ({ value: k, label: roundLabel(k) }))}
            />
          </Col>
          <Col span={24}>
            <ProFormText name="title" label={t('app.kuaiplm.prototypeBuildSheet.fields.title')} rules={[{ required: true }]} />
          </Col>
          <Col span={24}>
            <ProFormTextArea name="project_requirements" label={t('app.kuaiplm.prototypeBuildSheet.fields.projectRequirements')} />
          </Col>
          <Col span={24}>
            <ProFormTextArea name="remarks" label={t('common.remark')} />
          </Col>
        </Row>
      </FormModalTemplate>

      <DetailDrawerTemplate
        open={!!detail}
        onClose={() => setDetail(null)}
        title={detail?.title}
        subtitle={detail?.sheet_code}
        loading={false}
        size={DRAWER_CONFIG.HALF_WIDTH}
        extra={
          detail ? (
            <Space wrap>
              {perms.canUpdate && ['draft', 'rejected'].includes(detail.status) ? (
                <>
                  <Button
                    size="small"
                    onClick={() => {
                      setActiveSection('electronics');
                      setSectionText(detail.electronics_requirements || '');
                      setSectionOpen(true);
                    }}
                  >
                    {t('app.kuaiplm.prototypeBuildSheet.actions.fillElectronics')}
                  </Button>
                  <Button
                    size="small"
                    onClick={() => {
                      setActiveSection('structure');
                      setSectionText(detail.structure_requirements || '');
                      setSectionOpen(true);
                    }}
                  >
                    {t('app.kuaiplm.prototypeBuildSheet.actions.fillStructure')}
                  </Button>
                </>
              ) : null}
              {perms.canAction?.('submit') && ['draft', 'rejected'].includes(detail.status) ? (
                <Button
                  type="primary"
                  size="small"
                  onClick={async () => {
                    try {
                      await prototypeBuildSheetApi.submit(detail.id);
                      messageApi.success(t('common.submitSuccess'));
                      await refreshDetail(detail.id);
                    } catch (e) {
                      messageApi.error(getApiErrorMessage(e));
                    }
                  }}
                >
                  {t('common.submit')}
                </Button>
              ) : null}
              {perms.canAction?.('approve') && detail.status === 'pending' ? (
                <>
                  <Button
                    size="small"
                    onClick={async () => {
                      await prototypeBuildSheetApi.approve(detail.id);
                      messageApi.success(t('common.approveSuccess'));
                      await refreshDetail(detail.id);
                    }}
                  >
                    {t('common.approve')}
                  </Button>
                  <Button
                    size="small"
                    danger
                    onClick={async () => {
                      await prototypeBuildSheetApi.reject(detail.id);
                      messageApi.success(t('common.rejectSuccess'));
                      await refreshDetail(detail.id);
                    }}
                  >
                    {t('common.reject')}
                  </Button>
                </>
              ) : null}
              {perms.canAction?.('execute') && detail.status === 'approved' ? (
                <Button
                  size="small"
                  onClick={async () => {
                    await prototypeBuildSheetApi.issue(detail.id);
                    messageApi.success(t('app.kuaiplm.prototypeBuildSheet.messages.issued'));
                    await refreshDetail(detail.id);
                  }}
                >
                  {t('app.kuaiplm.prototypeBuildSheet.actions.issue')}
                </Button>
              ) : null}
              {perms.canUpdate && ['approved', 'issued'].includes(detail.status) ? (
                <Button
                  size="small"
                  onClick={() => {
                    setMfgOpinion(detail.manufacturing_opinion || '');
                    setQaOpinion(detail.quality_opinion || '');
                    setSignoffOpen(true);
                  }}
                >
                  {t('app.kuaiplm.prototypeBuildSheet.actions.signoff')}
                </Button>
              ) : null}
              {perms.canUpdate && ['issued', 'approved'].includes(detail.status) ? (
                <Button
                  type="primary"
                  size="small"
                  onClick={async () => {
                    try {
                      await prototypeBuildSheetApi.close(detail.id);
                      messageApi.success(t('common.closeSuccess'));
                      await refreshDetail(detail.id);
                    } catch (e) {
                      messageApi.error(getApiErrorMessage(e));
                    }
                  }}
                >
                  {t('common.close')}
                </Button>
              ) : null}
            </Space>
          ) : undefined
        }
        basic={
          detail ? (
            <Descriptions
              column={detailDrawerBasicColumn(false)}
              items={detailDrawerDescriptionItems([
                { key: 'project', label: t('app.kuaiplm.prototypeBuildSheet.fields.project'), children: `${detail.project_name} (${detail.project_code})` },
                { key: 'round', label: t('app.kuaiplm.prototypeBuildSheet.fields.round'), children: roundLabel(detail.round_key) },
                { key: 'status', label: t('common.status'), children: statusLabel(detail.status) },
                { key: 'electronics_status', label: t('app.kuaiplm.prototypeBuildSheet.fields.electronicsStatus'), children: detail.electronics_status },
                { key: 'structure_status', label: t('app.kuaiplm.prototypeBuildSheet.fields.structureStatus'), children: detail.structure_status },
                { key: 'project_requirements', label: t('app.kuaiplm.prototypeBuildSheet.fields.projectRequirements'), children: detail.project_requirements || '—' },
                { key: 'electronics_requirements', label: t('app.kuaiplm.prototypeBuildSheet.fields.electronicsRequirements'), children: detail.electronics_requirements || '—' },
                { key: 'structure_requirements', label: t('app.kuaiplm.prototypeBuildSheet.fields.structureRequirements'), children: detail.structure_requirements || '—' },
                { key: 'manufacturing_opinion', label: t('app.kuaiplm.prototypeBuildSheet.fields.manufacturingOpinion'), children: detail.manufacturing_opinion || '—' },
                { key: 'quality_opinion', label: t('app.kuaiplm.prototypeBuildSheet.fields.qualityOpinion'), children: detail.quality_opinion || '—' },
              ])}
            />
          ) : null
        }
      />

      <Modal
        title={
          activeSection === 'electronics'
            ? t('app.kuaiplm.prototypeBuildSheet.actions.fillElectronics')
            : t('app.kuaiplm.prototypeBuildSheet.actions.fillStructure')
        }
        open={sectionOpen}
        onCancel={() => setSectionOpen(false)}
        destroyOnHidden
        onOk={async () => {
          if (!detail) return;
          try {
            await prototypeBuildSheetApi.updateSection(detail.id, activeSection, {
              requirements: sectionText,
            });
            messageApi.success(t('common.saveSuccess'));
            setSectionOpen(false);
            await refreshDetail(detail.id);
          } catch (e) {
            messageApi.error(getApiErrorMessage(e));
          }
        }}
      >
        <div>
          <div style={{ marginBottom: 8 }}>{t('app.kuaiplm.prototypeBuildSheet.fields.requirements')}</div>
          <Input.TextArea rows={6} value={sectionText} onChange={(e) => setSectionText(e.target.value)} />
        </div>
      </Modal>

      <Modal
        title={t('app.kuaiplm.prototypeBuildSheet.actions.signoff')}
        open={signoffOpen}
        onCancel={() => setSignoffOpen(false)}
        destroyOnHidden
        onOk={async () => {
          if (!detail) return;
          try {
            await prototypeBuildSheetApi.updateSignoff(detail.id, {
              manufacturing_opinion: mfgOpinion,
              quality_opinion: qaOpinion,
            });
            messageApi.success(t('common.saveSuccess'));
            setSignoffOpen(false);
            await refreshDetail(detail.id);
          } catch (e) {
            messageApi.error(getApiErrorMessage(e));
          }
        }}
      >
        <div style={{ marginBottom: 12 }}>
          <div style={{ marginBottom: 8 }}>{t('app.kuaiplm.prototypeBuildSheet.fields.manufacturingOpinion')}</div>
          <Input.TextArea value={mfgOpinion} onChange={(e) => setMfgOpinion(e.target.value)} />
        </div>
        <div>
          <div style={{ marginBottom: 8 }}>{t('app.kuaiplm.prototypeBuildSheet.fields.qualityOpinion')}</div>
          <Input.TextArea value={qaOpinion} onChange={(e) => setQaOpinion(e.target.value)} />
        </div>
      </Modal>
    </>
  );
};

export default PrototypeBuildSheetsPage;
