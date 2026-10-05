import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Modal, Space, Typography } from 'antd';
import { MODAL_CONFIG } from '../../../../../../components/layout-templates';
import EquipmentDispatchCardPicker, {
  type EquipmentDispatchSnapshot,
} from './EquipmentDispatchCardPicker';

type EquipmentListRow = {
  id: number;
  uuid?: string;
  code?: string;
  name?: string;
  status?: string;
  is_active?: boolean;
};

export interface EquipmentDispatchSelectModalProps {
  open: boolean;
  onClose: () => void;
  value?: number[];
  onConfirm: (equipmentIds: number[]) => void;
  equipmentList: EquipmentListRow[];
  snapshotsById: Record<number, EquipmentDispatchSnapshot>;
  listLoading?: boolean;
  snapshotsLoading?: boolean;
  canReadSnapshots: boolean;
  onOpenDetail?: (snapshot: EquipmentDispatchSnapshot) => void;
  dispatchOperationPlannedStart?: string | null;
  dispatchOperationPlannedEnd?: string | null;
  dispatchOperationId?: number;
}

const EquipmentDispatchSelectModal: React.FC<EquipmentDispatchSelectModalProps> = ({
  open,
  onClose,
  value,
  onConfirm,
  equipmentList,
  snapshotsById,
  listLoading = false,
  snapshotsLoading = false,
  canReadSnapshots,
  onOpenDetail,
  dispatchOperationPlannedStart,
  dispatchOperationPlannedEnd,
  dispatchOperationId,
}) => {
  const { t } = useTranslation();
  const [draftIds, setDraftIds] = useState<number[]>([]);

  useEffect(() => {
    if (open) {
      setDraftIds(Array.isArray(value) ? value.filter((id) => Number(id) > 0) : []);
    }
  }, [open, value]);

  return (
    <Modal
      title={t('app.kuaizhizao.workOrder.equipmentDispatchPreview.selectModalTitle')}
      open={open}
      onCancel={onClose}
      width={MODAL_CONFIG.LARGE_WIDTH}
      destroyOnHidden
      mask={{ closable: true }}
      footer={
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Typography.Text type="secondary">
            {t('app.kuaizhizao.workOrder.equipmentDispatchPreview.selectedCount', {
              count: draftIds.length,
            })}
          </Typography.Text>
          <Space>
            <Button
              onClick={() => {
                setDraftIds([]);
                onConfirm([]);
                onClose();
              }}
            >
              {t('app.kuaizhizao.workOrder.equipmentDispatchPreview.clearSelection')}
            </Button>
            <Button onClick={onClose}>{t('common.cancel')}</Button>
            <Button
              type="primary"
              disabled={draftIds.length === 0}
              onClick={() => {
                onConfirm(draftIds);
                onClose();
              }}
            >
              {t('common.confirm')}
            </Button>
          </Space>
        </Space>
      }
    >
      <EquipmentDispatchCardPicker
        value={draftIds}
        onChange={setDraftIds}
        equipmentList={equipmentList}
        snapshotsById={snapshotsById}
        loading={listLoading}
        snapshotsLoading={snapshotsLoading}
        canReadSnapshots={canReadSnapshots}
        onOpenDetail={onOpenDetail}
        dispatchOperationPlannedStart={dispatchOperationPlannedStart}
        dispatchOperationPlannedEnd={dispatchOperationPlannedEnd}
        dispatchOperationId={dispatchOperationId}
      />
    </Modal>
  );
};

export default EquipmentDispatchSelectModal;
