import React, { useCallback, useEffect, useState } from 'react';
import { App, Button, DatePicker, Input, Space, Switch, Table } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { qualityQmsApi, type QmsManagementReviewResolution } from '../../../services/quality-qms';
import { formatBusinessDateOnly } from '../../../../../utils/format';

type Props = {
  reviewId: number;
  canUpdate: boolean;
  canCreateCa: boolean;
};

type DraftRow = {
  key: string;
  id?: number;
  content: string;
  responsible_person?: string;
  due_on?: string | null;
  convert_to_capa: boolean;
  capa_code?: string | null;
  status: string;
};

const ManagementReviewResolutionsPanel: React.FC<Props> = ({
  reviewId,
  canUpdate,
  canCreateCa,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<DraftRow[]>([]);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const res = await qualityQmsApi.managementReviews.resolutions(reviewId);
      setRows(
        (res.items || []).map((item: QmsManagementReviewResolution) => ({
          key: `r-${item.id}`,
          id: item.id,
          content: item.content,
          responsible_person: item.responsible_person || undefined,
          due_on: item.due_on || null,
          convert_to_capa: !!item.convert_to_capa,
          capa_code: item.capa_code,
          status: item.status,
        })),
      );
    } catch (e: any) {
      messageApi.error(e?.message || t('common.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [messageApi, reviewId, t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const addRow = () => {
    setRows((prev) => [
      ...prev,
      {
        key: `new-${Date.now()}`,
        content: '',
        convert_to_capa: false,
        status: 'open',
      },
    ]);
  };

  const saveRow = async (row: DraftRow) => {
    const content = (row.content || '').trim();
    if (!content) {
      messageApi.warning(t('app.kuaizhizao.quality.qms.messages.resolutionContentRequired'));
      return;
    }
    try {
      if (row.id) {
        await qualityQmsApi.managementReviews.updateResolution(reviewId, row.id, {
          content,
          responsible_person: row.responsible_person,
          due_on: row.due_on || undefined,
          convert_to_capa: row.convert_to_capa,
          status: row.status,
        });
      } else {
        await qualityQmsApi.managementReviews.createResolution(reviewId, {
          content,
          responsible_person: row.responsible_person,
          due_on: row.due_on || undefined,
          convert_to_capa: row.convert_to_capa,
        });
      }
      messageApi.success(t('common.saveSuccess'));
      await reload();
    } catch (e: any) {
      messageApi.error(e?.message || t('common.saveFailed'));
    }
  };

  const markDone = async (row: DraftRow) => {
    if (!row.id) return;
    try {
      await qualityQmsApi.managementReviews.updateResolution(reviewId, row.id, {
        status: 'done',
      });
      messageApi.success(t('app.kuaizhizao.quality.qms.messages.resolutionDone'));
      await reload();
    } catch (e: any) {
      messageApi.error(e?.message || t('common.saveFailed'));
    }
  };

  const generateCa = async (row: DraftRow) => {
    if (!row.id) {
      messageApi.warning(t('app.kuaizhizao.quality.qms.messages.resolutionSaveFirst'));
      return;
    }
    try {
      await qualityQmsApi.correctiveActions.fromSource({
        source_type: 'management_review_resolution',
        source_id: row.id,
        problem_summary: row.content,
        responsible_person: row.responsible_person,
        due_on: row.due_on || undefined,
      });
      messageApi.success(t('app.kuaizhizao.quality.qms.messages.caCreatedFromSource'));
      await reload();
    } catch (e: any) {
      messageApi.error(e?.message || t('common.saveFailed'));
    }
  };

  const removeRow = async (row: DraftRow) => {
    if (!row.id) {
      setRows((prev) => prev.filter((r) => r.key !== row.key));
      return;
    }
    try {
      await qualityQmsApi.managementReviews.deleteResolution(reviewId, row.id);
      messageApi.success(t('common.deleteSuccess'));
      await reload();
    } catch (e: any) {
      messageApi.error(e?.message || t('common.deleteFailed'));
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <strong>{t('app.kuaizhizao.quality.qms.resolutionsTitle')}</strong>
        {canUpdate ? (
          <Button type="dashed" size="small" icon={<PlusOutlined />} onClick={addRow}>
            {t('app.kuaizhizao.quality.qms.addResolution')}
          </Button>
        ) : null}
      </div>
      <Table<DraftRow>
        size="small"
        rowKey="key"
        loading={loading}
        pagination={false}
        dataSource={rows}
        columns={[
          {
            title: t('app.kuaizhizao.quality.qms.resolutionContent'),
            dataIndex: 'content',
            render: (_, row) =>
              canUpdate && row.status !== 'done' ? (
                <Input.TextArea
                  rows={2}
                  value={row.content}
                  onChange={(e) =>
                    setRows((prev) =>
                      prev.map((r) => (r.key === row.key ? { ...r, content: e.target.value } : r)),
                    )
                  }
                />
              ) : (
                row.content
              ),
          },
          {
            title: t('app.kuaizhizao.quality.qms.resolutionOwner'),
            dataIndex: 'responsible_person',
            width: 110,
            render: (_, row) =>
              canUpdate && row.status !== 'done' ? (
                <Input
                  value={row.responsible_person}
                  onChange={(e) =>
                    setRows((prev) =>
                      prev.map((r) =>
                        r.key === row.key ? { ...r, responsible_person: e.target.value } : r,
                      ),
                    )
                  }
                />
              ) : (
                row.responsible_person || '-'
              ),
          },
          {
            title: t('app.kuaizhizao.quality.qms.resolutionDueOn'),
            dataIndex: 'due_on',
            width: 140,
            render: (_, row) =>
              canUpdate && row.status !== 'done' ? (
                <DatePicker
                  value={row.due_on ? dayjs(row.due_on) : null}
                  onChange={(d) =>
                    setRows((prev) =>
                      prev.map((r) =>
                        r.key === row.key
                          ? { ...r, due_on: d ? d.format('YYYY-MM-DD') : null }
                          : r,
                      ),
                    )
                  }
                />
              ) : (
                formatBusinessDateOnly(row.due_on) || '-'
              ),
          },
          {
            title: t('app.kuaizhizao.quality.qms.resolutionConvertCa'),
            dataIndex: 'convert_to_capa',
            width: 100,
            render: (_, row) => (
              <Switch
                checked={row.convert_to_capa}
                disabled={!canUpdate || row.status === 'done' || !!row.capa_code}
                onChange={(checked) =>
                  setRows((prev) =>
                    prev.map((r) => (r.key === row.key ? { ...r, convert_to_capa: checked } : r)),
                  )
                }
              />
            ),
          },
          {
            title: t('app.kuaizhizao.quality.qms.ncCapaCode'),
            dataIndex: 'capa_code',
            width: 130,
            render: (_, row) => row.capa_code || '-',
          },
          {
            title: t('common.status'),
            dataIndex: 'status',
            width: 80,
            render: (_, row) =>
              row.status === 'done'
                ? t('app.kuaizhizao.quality.qms.resolutionStatus.done')
                : t('app.kuaizhizao.quality.qms.resolutionStatus.open'),
          },
          {
            title: t('common.actions'),
            key: 'actions',
            width: 220,
            render: (_, row) => (
              <Space size={4} wrap>
                {canUpdate && row.status !== 'done' ? (
                  <Button type="link" size="small" onClick={() => void saveRow(row)}>
                    {t('common.save')}
                  </Button>
                ) : null}
                {canUpdate &&
                row.status !== 'done' &&
                row.convert_to_capa &&
                !row.capa_code &&
                canCreateCa ? (
                  <Button type="link" size="small" onClick={() => void generateCa(row)}>
                    {t('app.kuaizhizao.quality.qms.actions.generateCa')}
                  </Button>
                ) : null}
                {canUpdate && row.status !== 'done' && !row.convert_to_capa && row.id ? (
                  <Button type="link" size="small" onClick={() => void markDone(row)}>
                    {t('app.kuaizhizao.quality.qms.actions.markResolutionDone')}
                  </Button>
                ) : null}
                {canUpdate && row.status !== 'done' ? (
                  <Button
                    type="link"
                    danger
                    size="small"
                    icon={<DeleteOutlined />}
                    onClick={() => void removeRow(row)}
                  />
                ) : null}
              </Space>
            ),
          },
        ]}
      />
    </div>
  );
};

export default ManagementReviewResolutionsPanel;
