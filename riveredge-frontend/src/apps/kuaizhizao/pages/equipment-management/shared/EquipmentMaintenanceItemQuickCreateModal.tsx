/**
 * 设备保养项快速新建：保养方案明细「添加项目」与行内下拉共用（对齐工装 ToolOpsItemQuickCreateModal）。
 */

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Form, Input, theme } from 'antd';
import { QuickCreateModal } from '../../../../../components/uni-dropdown';
import { MODAL_NESTED_ABOVE_PARENT_OFFSET } from '../../../../../components/layout-templates/constants';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { maintenanceItemsApi } from '../../../services/equipmentOps';

export interface EquipmentMaintenanceItemCreated {
  id: number;
  code: string;
  name: string;
  remark?: string | null;
}

export interface EquipmentMaintenanceItemQuickCreateModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (item: EquipmentMaintenanceItemCreated) => void;
  /** 须高于方案 FormModal 与批量选择弹窗 */
  zIndex?: number;
}

const P = 'app.kuaizhizao.equipmentOps.maintenanceItem';

export const EquipmentMaintenanceItemQuickCreateModal: React.FC<
  EquipmentMaintenanceItemQuickCreateModalProps
> = ({ open, onClose, onCreated, zIndex }) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const { token } = theme.useToken();
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm<{ code: string; name: string }>();

  const handleConfirm = async () => {
    const values = await form.validateFields();
    const code = String(values.code ?? '').trim();
    const name = String(values.name ?? '').trim();
    if (!code || !name) return;
    setCreating(true);
    try {
      const created = (await maintenanceItemsApi.create({
        code,
        name,
        is_active: true,
      })) as EquipmentMaintenanceItemCreated;
      if (created?.id == null) {
        throw new Error(t('common.saveFailed'));
      }
      messageApi.success(t('common.createSuccess'));
      form.resetFields();
      onCreated({
        id: Number(created.id),
        code: String(created.code ?? code),
        name: String(created.name ?? name),
        remark: created.remark ?? null,
      });
      onClose();
    } catch (e) {
      messageApi.error(getApiErrorMessage(e, t('common.saveFailed')));
    } finally {
      setCreating(false);
    }
  };

  return (
    <QuickCreateModal
      open={open}
      title={t(`${P}.quickCreateTitle`)}
      zIndex={zIndex ?? token.zIndexPopupBase + MODAL_NESTED_ABOVE_PARENT_OFFSET * 2}
      confirmLoading={creating}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      onClose={() => {
        form.resetFields();
        onClose();
      }}
      onConfirm={handleConfirm}
    >
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item
          name="code"
          label={t('common.code')}
          rules={[{ required: true, whitespace: true, message: t('common.required') }]}
        >
          <Input maxLength={64} autoFocus />
        </Form.Item>
        <Form.Item
          name="name"
          label={t('common.name')}
          rules={[{ required: true, whitespace: true, message: t('common.required') }]}
          style={{ marginBottom: 0 }}
        >
          <Input maxLength={200} />
        </Form.Item>
      </Form>
    </QuickCreateModal>
  );
};
