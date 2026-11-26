import React, { useMemo } from 'react';
import SyncFromSourceModal from '../../../components/sync-from-source-modal';
import type { SyncFromSourceResult } from '../../../components/sync-from-source-modal/types';
import { createStorageLocationSyncConfig } from '../storageLocationSyncConfig';

export interface StorageLocationSyncFromSourceModalProps {
  open: boolean;
  onClose: () => void;
  onComplete?: (result: SyncFromSourceResult) => void;
  zIndex?: number;
}

export const StorageLocationSyncFromSourceModal: React.FC<
  StorageLocationSyncFromSourceModalProps
> = (props) => {
  const config = useMemo(() => createStorageLocationSyncConfig(), []);
  return <SyncFromSourceModal {...props} config={config} />;
};

export default StorageLocationSyncFromSourceModal;
