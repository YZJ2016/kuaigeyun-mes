import React, { useMemo } from 'react';
import SyncFromSourceModal from '../../../components/sync-from-source-modal';
import type { SyncFromSourceResult } from '../../../components/sync-from-source-modal/types';
import { createWarehouseLocationRefSyncConfig } from '../warehouseLocationRefSyncConfig';

export interface WarehouseLocationRefSyncFromSourceModalProps {
  open: boolean;
  onClose: () => void;
  onComplete?: (result: SyncFromSourceResult) => void;
  zIndex?: number;
}

export const WarehouseLocationRefSyncFromSourceModal: React.FC<
  WarehouseLocationRefSyncFromSourceModalProps
> = (props) => {
  const config = useMemo(() => createWarehouseLocationRefSyncConfig(), []);
  return <SyncFromSourceModal {...props} config={config} />;
};

export default WarehouseLocationRefSyncFromSourceModal;
