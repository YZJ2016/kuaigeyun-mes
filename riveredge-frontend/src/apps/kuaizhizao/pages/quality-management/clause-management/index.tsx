import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  App,
  Button,
  Descriptions,
  Empty,
  Flex,
  List,
  Spin,
  Table,
  Tree,
  Typography,
  theme,
} from 'antd';
import type { DataNode } from 'antd/es/tree';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  ProFormDigit,
  ProFormItem,
  ProFormSwitch,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import {
  DetailDrawerSection,
  FormModalTemplate,
  ListPageTemplate,
  MODAL_CONFIG,
  TWO_COLUMN_LAYOUT,
} from '../../../../../components/layout-templates';
import { ClauseManagementColumn } from './clauseManagementColumns';
import PermissionGuard from '../../../../../components/permission/PermissionGuard';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import { withSingleNewShortcutHint } from '../../../../../utils/globalNewShortcut';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { formatDateTimeBySiteSetting } from '../../../../../utils/format';
import { renderMasterActiveTag } from '../../../../master-data/utils/masterListPresentation';
import {
  qualityQmsApi,
  QmsInternalAudit,
  QmsIsoClause,
  QmsIsoClauseComplianceSummary,
  QmsIsoClauseTreeNode,
  QmsStandard,
  QmsSystemDocument,
} from '../../../services/quality-qms';
import QmsClauseSelect from '../qms/QmsClauseSelect';
import { buildListPageHelpViewConfig } from '../../../../../components/page-help-wiki';

const RESOURCE = 'kuaizhizao:quality-management-iso-clauses';

function renderComplianceTag(t: (key: string) => string, status?: string) {
  if (status === 'covered') {
    return <MarkerTag color="success">{t('app.kuaizhizao.quality.isoClauses.compliance.covered')}</MarkerTag>;
  }
  if (status === 'review_due') {
    return <MarkerTag color="warning">{t('app.kuaizhizao.quality.isoClauses.compliance.reviewDue')}</MarkerTag>;
  }
  return <MarkerTag color="error">{t('app.kuaizhizao.quality.isoClauses.compliance.gap')}</MarkerTag>;
}

function mapTreeNodes(nodes: QmsIsoClauseTreeNode[]): DataNode[] {
  return nodes.map((n) => ({
    key: n.id,
    title: `${n.clause_code} ${n.title}`,
    children: n.children?.length ? mapTreeNodes(n.children) : undefined,
  }));
}

const ClauseManagementPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const { token } = theme.useToken();
  const { canCreate, canUpdate } = useResourcePermissions(RESOURCE);

  const [standards, setStandards] = useState<QmsStandard[]>([]);
  const [selectedStandardId, setSelectedStandardId] = useState<number | undefined>();
  const [treeLoading, setTreeLoading] = useState(false);
  const [treeData, setTreeData] = useState<DataNode[]>([]);
  const [selectedClauseId, setSelectedClauseId] = useState<number | undefined>();

  const [detail, setDetail] = useState<QmsIsoClause | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [summary, setSummary] = useState<QmsIsoClauseComplianceSummary | null>(null);
  const [relatedDocs, setRelatedDocs] = useState<QmsSystemDocument[]>([]);
  const [relatedAudits, setRelatedAudits] = useState<QmsInternalAudit[]>([]);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<QmsIsoClause | null>(null);
  const [standardModalOpen, setStandardModalOpen] = useState(false);
  const [newStandardCode, setNewStandardCode] = useState('');
  const [newStandardName, setNewStandardName] = useState('');

  const selectedStandard = useMemo(
    () => standards.find((s) => s.id === selectedStandardId),
    [standards, selectedStandardId],
  );

  const loadStandards = useCallback(async () => {
    const res = await qualityQmsApi.standards.list({ limit: 200 });
    setStandards(res.items);
    setSelectedStandardId((prev) => prev ?? res.items[0]?.id);
  }, []);

  const loadTree = useCallback(async () => {
    if (!selectedStandardId) {
      setTreeData([]);
      return;
    }
    setTreeLoading(true);
    try {
      const tree = await qualityQmsApi.isoClauses.tree({ standard_id: selectedStandardId });
      setTreeData(mapTreeNodes(tree));
    } catch (error) {
      messageApi.error(getApiErrorMessage(error, t('common.loadFailed')));
      setTreeData([]);
    } finally {
      setTreeLoading(false);
    }
  }, [messageApi, selectedStandardId, t]);

  const loadDetail = useCallback(
    async (clauseId: number) => {
      setDetailLoading(true);
      try {
        const [detailRes, summaryRes, docsRes, auditsRes] = await Promise.all([
          qualityQmsApi.isoClauses.get(clauseId),
          qualityQmsApi.isoClauses.complianceSummary(clauseId),
          qualityQmsApi.isoClauses.relatedDocuments(clauseId),
          qualityQmsApi.isoClauses.relatedAudits(clauseId),
        ]);
        setDetail(detailRes);
        setSummary(summaryRes);
        setRelatedDocs(docsRes.items ?? []);
        setRelatedAudits(auditsRes.items ?? []);
      } catch (error) {
        messageApi.error(getApiErrorMessage(error, t('common.loadFailed')));
      } finally {
        setDetailLoading(false);
      }
    },
    [messageApi, t],
  );

  useEffect(() => {
    void loadStandards();
  }, [loadStandards]);

  useEffect(() => {
    void loadTree();
    setSelectedClauseId(undefined);
    setDetail(null);
  }, [loadTree, selectedStandardId]);

  useEffect(() => {
    if (selectedClauseId) void loadDetail(selectedClauseId);
  }, [loadDetail, selectedClauseId]);

  const openCreateClause = () => {
    if (!selectedStandardId) return;
    setEditing(null);
    setModalOpen(true);
  };
  useNewShortcut(() => {
    if (canCreate) openCreateClause();
  });

  const handleLoadPreset = async () => {
    if (!selectedStandard?.code) return;
    try {
      const res = await qualityQmsApi.isoClauses.loadPreset(selectedStandard.code);
      messageApi.success(
        t('app.kuaizhizao.quality.isoClauses.loadPresetSuccess', {
          created: res.created,
          skipped: res.skipped,
          linked: res.linked,
        }),
      );
      await loadTree();
    } catch (error) {
      messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
    }
  };

  const standardsColumnToolbar = (
    <Flex gap={4}>
      <Button
        size="small"
        icon={<ReloadOutlined />}
        aria-label={t('common.refresh')}
        title={t('common.refresh')}
        onClick={() => void loadStandards()}
      />
      {canCreate ? (
        <Button size="small" type="link" onClick={() => setStandardModalOpen(true)}>
          {t('app.kuaizhizao.quality.clauseManagement.newStandardShort')}
        </Button>
      ) : null}
    </Flex>
  );

  const catalogColumnToolbar = (
    <Flex gap={4} wrap="wrap" justify="flex-end">
      {canCreate ? (
        <>
          <Button size="small" type="primary" icon={<PlusOutlined />} onClick={openCreateClause}>
            {withSingleNewShortcutHint(t('app.kuaizhizao.quality.clauseManagement.newClause'))}
          </Button>
          {selectedStandard?.is_preset ? (
            <Button size="small" onClick={() => void handleLoadPreset()}>
              {t('app.kuaizhizao.quality.isoClauses.loadPreset')}
            </Button>
          ) : null}
        </>
      ) : null}
      <Button
        size="small"
        icon={<ReloadOutlined />}
        aria-label={t('common.refresh')}
        title={t('common.refresh')}
        onClick={() => void loadTree()}
        disabled={!selectedStandardId}
      />
    </Flex>
  );

  const contentPanel = !selectedStandardId ? (
    <Empty description={t('app.kuaizhizao.quality.clauseManagement.selectStandardHint')} />
  ) : !selectedClauseId ? (
    <Empty description={t('app.kuaizhizao.quality.clauseManagement.selectClauseHint')} />
  ) : (
    <Spin spinning={detailLoading}>
      {detail ? (
        <div>
          <Typography.Title level={5} style={{ marginTop: 0 }}>
            {detail.clause_code} {detail.title}
          </Typography.Title>
          <Descriptions column={2} size="small" style={{ marginBottom: 16 }}>
            <Descriptions.Item label={t('app.kuaizhizao.quality.isoClauses.standardCode')}>
              {detail.standard_code}
            </Descriptions.Item>
            <Descriptions.Item label={t('common.enabled')}>
              {renderMasterActiveTag(
                t,
                detail.is_active ?? false,
                'common.enabled',
                'common.disabled',
              )}
            </Descriptions.Item>
            <Descriptions.Item label={t('common.remark')} span={2}>
              {detail.description || '-'}
            </Descriptions.Item>
          </Descriptions>
          {summary ? (
            <DetailDrawerSection title={t('app.kuaizhizao.quality.isoClauses.complianceSummary')}>
              <Flex vertical gap={8}>
                {renderComplianceTag(t, summary.compliance_status)}
                <Typography.Text>
                  {t('app.kuaizhizao.quality.isoClauses.effectiveDocuments')}:{' '}
                  {summary.effective_document_count}
                </Typography.Text>
                <Typography.Text>
                  {t('app.kuaizhizao.quality.isoClauses.internalAuditCount')}:{' '}
                  {summary.internal_audit_count}
                </Typography.Text>
              </Flex>
            </DetailDrawerSection>
          ) : null}
          <DetailDrawerSection title={t('app.kuaizhizao.quality.isoClauses.effectiveDocuments')}>
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              dataSource={relatedDocs}
              columns={[
                { title: t('app.kuaizhizao.quality.qms.documentCode'), dataIndex: 'document_code' },
                { title: t('app.kuaizhizao.quality.qms.title'), dataIndex: 'title', ellipsis: true },
              ]}
            />
          </DetailDrawerSection>
          <DetailDrawerSection title={t('app.kuaizhizao.menu.quality-management.internal-audits')}>
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              dataSource={relatedAudits}
              columns={[
                { title: t('app.kuaizhizao.quality.qms.auditCode'), dataIndex: 'audit_code' },
                { title: t('app.kuaizhizao.quality.qms.title'), dataIndex: 'title', ellipsis: true },
                {
                  title: t('app.kuaizhizao.quality.qms.completedDate'),
                  dataIndex: 'completed_date',
                  render: (v) => formatDateTimeBySiteSetting(v) || '-',
                },
              ]}
            />
          </DetailDrawerSection>
        </div>
      ) : null}
    </Spin>
  );

  return (
    <PermissionGuard resource={RESOURCE} action="read">
      <ListPageTemplate fillMain viewTypes={['help']} helpViewConfig={buildListPageHelpViewConfig('kuaizhizao.isoClauses')}>
        <div
          style={{
            display: 'flex',
            flex: 1,
            minHeight: TWO_COLUMN_LAYOUT.MIN_HEIGHT,
            height: '100%',
            width: '100%',
            border: `1px solid ${token.colorBorder}`,
            borderRadius: token.borderRadiusLG,
            overflow: 'hidden',
          }}
        >
          <ClauseManagementColumn
            title={t('app.kuaizhizao.quality.clauseManagement.tierStandard')}
            toolbar={standardsColumnToolbar}
            width={260}
          >
            <List
              size="small"
              dataSource={standards}
              locale={{ emptyText: t('app.kuaizhizao.quality.clauseManagement.emptyStandards') }}
              renderItem={(item) => {
                const selected = item.id === selectedStandardId;
                return (
                  <List.Item
                    style={{
                      cursor: 'pointer',
                      padding: '8px 10px',
                      borderRadius: token.borderRadius,
                      background: selected ? token.colorPrimaryBg : undefined,
                      border: selected ? `1px solid ${token.colorPrimaryBorder}` : '1px solid transparent',
                    }}
                    onClick={() => setSelectedStandardId(item.id)}
                  >
                    <Flex vertical gap={2} style={{ minWidth: 0, width: '100%' }}>
                      <Typography.Text strong ellipsis>
                        {item.code}
                      </Typography.Text>
                      <Typography.Text type="secondary" ellipsis style={{ fontSize: 12 }}>
                        {item.name}
                      </Typography.Text>
                    </Flex>
                  </List.Item>
                );
              }}
            />
          </ClauseManagementColumn>

          <ClauseManagementColumn
            title={t('app.kuaizhizao.quality.clauseManagement.tierCatalog')}
            toolbar={catalogColumnToolbar}
            width={300}
            bodyClassName="two-column-layout-left-tree"
          >
            {!selectedStandardId ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t('app.kuaizhizao.quality.clauseManagement.selectStandardHint')}
              />
            ) : (
              <Spin spinning={treeLoading}>
                {treeData.length ? (
                  <Tree
                    className="clause-mgmt-catalog-tree"
                    blockNode
                    treeData={treeData}
                    selectedKeys={selectedClauseId ? [selectedClauseId] : []}
                    onSelect={(keys) => {
                      const id = keys[0] as number | undefined;
                      setSelectedClauseId(id);
                    }}
                    defaultExpandAll
                  />
                ) : (
                  !treeLoading && (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={t('app.kuaizhizao.quality.clauseManagement.emptyTree')}
                    />
                  )
                )}
              </Spin>
            )}
          </ClauseManagementColumn>

          <ClauseManagementColumn
            title={t('app.kuaizhizao.quality.clauseManagement.tierContent')}
            flex={1}
            isLast
            toolbar={
              canUpdate && detail ? (
                <Button
                  size="small"
                  onClick={() => {
                    setEditing(detail);
                    setModalOpen(true);
                  }}
                >
                  {t('common.edit')}
                </Button>
              ) : null
            }
          >
            {contentPanel}
          </ClauseManagementColumn>
        </div>
      </ListPageTemplate>

      <FormModalTemplate
        title={
          editing
            ? t('app.kuaizhizao.quality.isoClauses.editTitle')
            : t('app.kuaizhizao.quality.clauseManagement.createClauseTitle')
        }
        open={modalOpen}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        grid={false}
        onClose={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        initialValues={
          editing ?? {
            standard_id: selectedStandardId,
            sort_order: 0,
            is_active: true,
          }
        }
        onFinish={async (values) => {
          try {
            const payload = {
              ...values,
              standard_id: selectedStandardId,
              standard_code: selectedStandard?.code,
            };
            if (editing?.id) {
              await qualityQmsApi.isoClauses.update(editing.id, payload);
            } else {
              await qualityQmsApi.isoClauses.create(payload);
            }
            messageApi.success(t('common.saveSuccess'));
            setModalOpen(false);
            await loadTree();
            if (editing?.id) await loadDetail(editing.id);
            return true;
          } catch (error) {
            messageApi.error(getApiErrorMessage(error, t('common.saveFailed')));
            return false;
          }
        }}
      >
        <ProFormText name="clause_code" label={t('app.kuaizhizao.quality.isoClauses.clauseCode')} rules={[{ required: true }]} />
        <ProFormText name="title" label={t('app.kuaizhizao.quality.isoClauses.title')} rules={[{ required: true }]} />
        <ProFormTextArea name="description" label={t('common.remark')} />
        <ProFormItem name="parent_id" label={t('app.kuaizhizao.quality.isoClauses.parentClause')}>
          <QmsClauseSelect standardId={selectedStandardId} excludeId={editing?.id} />
        </ProFormItem>
        <ProFormDigit name="sort_order" label={t('app.kuaizhizao.quality.isoClauses.sortOrder')} />
        <ProFormSwitch name="is_active" label={t('common.enabled')} />
      </FormModalTemplate>

      <FormModalTemplate
        title={t('app.kuaizhizao.quality.clauseManagement.newStandard')}
        open={standardModalOpen}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        grid={false}
        onClose={() => setStandardModalOpen(false)}
        onFinish={async () => {
          const code = newStandardCode.trim();
          if (!code) {
            messageApi.warning(t('app.kuaizhizao.quality.clauseManagement.standardCodeRequired'));
            return false;
          }
          try {
            await qualityQmsApi.standards.create({
              code,
              name: newStandardName.trim() || code,
              family: 'custom',
            });
            messageApi.success(t('common.saveSuccess'));
            setStandardModalOpen(false);
            setNewStandardCode('');
            setNewStandardName('');
            await loadStandards();
            return true;
          } catch (error) {
            messageApi.error(getApiErrorMessage(error, t('common.saveFailed')));
            return false;
          }
        }}
      >
        <ProFormText
          name="_standard_code_ui"
          label={t('app.kuaizhizao.quality.isoClauses.standardCode')}
          fieldProps={{ value: newStandardCode, onChange: (e) => setNewStandardCode(e.target.value) }}
        />
        <ProFormText
          name="_standard_name_ui"
          label={t('app.kuaizhizao.quality.clauseManagement.standardName')}
          fieldProps={{ value: newStandardName, onChange: (e) => setNewStandardName(e.target.value) }}
        />
      </FormModalTemplate>
    </PermissionGuard>
  );
};

export default ClauseManagementPage;
