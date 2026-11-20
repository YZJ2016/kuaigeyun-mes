import React, { useMemo } from 'react';
import SyncFromSourceModal from '../../../components/sync-from-source-modal';
import type { SyncFromSourceResult } from '../../../components/sync-from-source-modal/types';
import { createMaterialBatchManageSyncConfig } from '../materialBatchManageSyncConfig';

export interface MaterialBatchManageSyncFromSourceModalProps {
  open: boolean;
  onClose: () => void;
  onComplete?: (result: SyncFromSourceResult) => void;
  zIndex?: number;
}

export const MaterialBatchManageSyncFromSourceModal: React.FC<
  MaterialBatchManageSyncFromSourceModalProps
> = (props) => {
  const config = useMemo(() => createMaterialBatchManageSyncConfig(), []);
  return <SyncFromSourceModal {...props} config={config} />;
};

export default MaterialBatchManageSyncFromSourceModal;
