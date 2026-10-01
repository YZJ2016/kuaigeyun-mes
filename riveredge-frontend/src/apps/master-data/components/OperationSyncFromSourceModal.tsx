import React, { useMemo } from 'react';
import SyncFromSourceModal from '../../../components/sync-from-source-modal';
import type { SyncFromSourceResult } from '../../../components/sync-from-source-modal/types';
import { createOperationSyncConfig } from '../operationSyncConfig';

export interface OperationSyncFromSourceModalProps {
  open: boolean;
  onClose: () => void;
  onComplete?: (result: SyncFromSourceResult) => void;
  zIndex?: number;
  contentOnly?: boolean;
}

export const OperationSyncFromSourceModal: React.FC<OperationSyncFromSourceModalProps> = (props) => {
  const config = useMemo(() => createOperationSyncConfig(), []);
  return <SyncFromSourceModal {...props} config={config} />;
};

export default OperationSyncFromSourceModal;
