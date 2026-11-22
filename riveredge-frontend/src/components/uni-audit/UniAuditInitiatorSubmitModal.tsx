import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Form, Modal, Select } from 'antd';
import { useTranslation } from 'react-i18next';
import type {
  HierarchyDepartmentOption,
  SubmitInitiatorBranchHint,
  SubmitInitiatorNodeHint,
} from '../../services/uniAudit';
import { searchUserDisplay } from '../../services/user';
import { formatUserDisplayLabel } from '../../utils/userDisplay';

export interface UniAuditInitiatorSubmitModalProps {
  open: boolean;
  entityName: string;
  submitTitle: string;
  nodes: SubmitInitiatorNodeHint[];
  branchConditions?: SubmitInitiatorBranchHint[];
  hierarchyDepartmentRequired?: boolean;
  hierarchyDepartmentOptions?: HierarchyDepartmentOption[];
  defaultHierarchyDepartmentUuid?: string | null;
  loading?: boolean;
  onCancel: () => void;
  onConfirm: (
    selectedByNode: Record<string, number[]>,
    branchByCondition: Record<string, number>,
    hierarchyDepartmentUuid?: string,
  ) => Promise<void>;
}

const UniAuditInitiatorSubmitModal: React.FC<UniAuditInitiatorSubmitModalProps> = ({
  open,
  entityName,
  submitTitle,
  nodes,
  branchConditions = [],
  hierarchyDepartmentRequired = false,
  hierarchyDepartmentOptions = [],
  defaultHierarchyDepartmentUuid = null,
  loading,
  onCancel,
  onConfirm,
}) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<Record<string, number | number[]>>();
  const [userOptions, setUserOptions] = useState<{ label: string; value: number }[]>([]);
  const [fetchingUsers, setFetchingUsers] = useState(false);

  const hasOptional = useMemo(
    () => nodes.some((n) => !n.required),
    [nodes],
  );

  useEffect(() => {
    if (!open) return;
    const branchInitial: Record<string, number> = {};
    for (const cond of branchConditions) {
      if (typeof cond.default_index === 'number') {
        branchInitial[branchField(cond.condition_node_id)] = cond.default_index;
      }
    }
    form.resetFields();
    const initial: Record<string, number | number[] | string> = { ...branchInitial };
    if (defaultHierarchyDepartmentUuid) {
      initial.hierarchy_department_uuid = defaultHierarchyDepartmentUuid;
    }
    if (Object.keys(initial).length) {
      form.setFieldsValue(initial);
    }
    let cancelled = false;
    setFetchingUsers(true);
    searchUserDisplay({ page: 1, page_size: 200, is_active: true })
      .then((res) => {
        if (cancelled) return;
        setUserOptions(
          (res.items || [])
            .filter((u) => typeof u.id === 'number' && u.id > 0)
            .map((u) => ({
              label: formatUserDisplayLabel(u),
              value: u.id as number,
            })),
        );
      })
      .finally(() => {
        if (!cancelled) setFetchingUsers(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, form, branchConditions, defaultHierarchyDepartmentUuid]);

  const branchField = (id: string) => `branch_${id}`;

  const handleOk = async () => {
    const values = await form.validateFields();
    const selectedByNode: Record<string, number[]> = {};
    for (const node of nodes) {
      const raw = values[node.node_id];
      const ids = Array.isArray(raw) ? raw.filter((id) => id > 0) : raw ? [raw] : [];
      if (ids.length) {
        selectedByNode[node.node_id] = ids;
      } else if (node.required) {
        return;
      }
    }
    const branchByCondition: Record<string, number> = {};
    for (const cond of branchConditions) {
      const raw = values[branchField(cond.condition_node_id)];
      if (raw === undefined || raw === null || raw === '') {
        if (cond.required) return;
        continue;
      }
      branchByCondition[cond.condition_node_id] = Number(raw);
    }
    const hierarchyUuid = values.hierarchy_department_uuid
      ? String(values.hierarchy_department_uuid)
      : undefined;
    await onConfirm(selectedByNode, branchByCondition, hierarchyUuid);
  };

  const showHierarchyPicker =
    hierarchyDepartmentRequired && hierarchyDepartmentOptions.length >= 2;

  return (
    <Modal
      open={open}
      title={submitTitle}
      okText={submitTitle}
      cancelText={t('common.cancel')}
      confirmLoading={loading}
      onCancel={onCancel}
      onOk={() => void handleOk()}
      destroyOnHidden
    >
      {hasOptional ? (
        <Alert
          type="info"
          showIcon
          title={t('pages.approval.submitInitiatorOptionalHint')}
          style={{ marginBottom: 12 }}
        />
      ) : null}
      <Form form={form} layout="vertical">
        {showHierarchyPicker ? (
          <Form.Item
            name="hierarchy_department_uuid"
            label={t('pages.approval.hierarchyDepartment')}
            rules={[
              {
                required: true,
                message: t('pages.approval.hierarchyDepartmentRequired'),
              },
            ]}
          >
            <Select
              placeholder={t('pages.approval.hierarchyDepartmentPlaceholder')}
              options={hierarchyDepartmentOptions.map((opt) => ({
                value: opt.uuid,
                label: opt.is_primary ? `${opt.name}（${t('field.user.primaryDepartment')}）` : opt.name,
              }))}
            />
          </Form.Item>
        ) : null}
        {branchConditions.map((cond) => (
          <Form.Item
            key={cond.condition_node_id}
            name={branchField(cond.condition_node_id)}
            label={cond.label}
            rules={
              cond.required
                ? [
                    {
                      required: true,
                      message: t('pages.approval.submitInitiatorBranchRequired', {
                        label: cond.label,
                      }),
                    },
                  ]
                : undefined
            }
          >
            <Select
              allowClear={!cond.required}
              placeholder={t('pages.approval.submitInitiatorBranchPlaceholder')}
              options={(cond.branches || []).map((b) => {
                const target = (b.target_label || '').trim();
                const shown =
                  target && !b.label.includes(target) ? `${b.label} → ${target}` : b.label;
                return {
                  label: b.is_default
                    ? `${shown}（${t('pages.approval.branchDefaultMark')}）`
                    : shown,
                  value: b.index,
                };
              })}
            />
          </Form.Item>
        ))}
        {nodes.map((node) => (
          <Form.Item
            key={node.node_id}
            name={node.node_id}
            label={`${node.label}${node.required ? '' : ` (${t('pages.approval.submitInitiatorOptional')})`}`}
            rules={
              node.required
                ? [
                    {
                      required: true,
                      message: t('pages.approval.submitInitiatorRequired', {
                        node: node.label,
                      }),
                    },
                  ]
                : undefined
            }
          >
            <Select
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              loading={fetchingUsers}
              placeholder={t('pages.approval.submitInitiatorPlaceholder', { entity: entityName })}
              options={userOptions}
            />
          </Form.Item>
        ))}
      </Form>
    </Modal>
  );
};

export default UniAuditInitiatorSubmitModal;
