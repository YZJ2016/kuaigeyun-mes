import React, { useMemo } from 'react';
import SyncFromSourceModal from '../../../components/sync-from-source-modal';
import type { SyncFromSourceResult } from '../../../components/sync-from-source-modal/types';
import { createMaterialMultiUnitSyncConfig } from '../materialMultiUnitSyncConfig';

export interface MaterialMultiUnitSyncFromSourceModalProps {
  open: boolean;
  onClose: () => void;
  onComplete?: (result: SyncFromSourceResult) => void;
  zIndex?: number;
}

export const MaterialMultiUnitSyncFromSourceModal: React.FC<
  MaterialMultiUnitSyncFromSourceModalProps
> = (props) => {
  const config = useMemo(() => createMaterialMultiUnitSyncConfig(), []);
  return <SyncFromSourceModal {...props} config={config} />;
};

export default MaterialMultiUnitSyncFromSourceModal;
