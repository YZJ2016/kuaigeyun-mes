import React, { useMemo } from 'react';
import SyncFromSourceModal from '../../../components/sync-from-source-modal';
import type { SyncFromSourceResult } from '../../../components/sync-from-source-modal/types';
import { createEngineeringBomSyncConfig } from '../bomSyncConfig';

export interface BomSyncFromSourceModalProps {
  open: boolean;
  onClose: () => void;
  onComplete?: (result: SyncFromSourceResult) => void;
  zIndex?: number;
  contentOnly?: boolean;
}

export const BomSyncFromSourceModal: React.FC<BomSyncFromSourceModalProps> = (props) => {
  const config = useMemo(() => createEngineeringBomSyncConfig(), []);
  return <SyncFromSourceModal {...props} config={config} />;
};

export default BomSyncFromSourceModal;
