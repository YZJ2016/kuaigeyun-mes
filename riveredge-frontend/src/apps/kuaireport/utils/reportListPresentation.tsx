import { Badge } from 'antd';
import type { ReactNode } from 'react';

type BadgeStatus = 'success' | 'processing' | 'default' | 'error' | 'warning';

export function renderReportDocTypeMarker(label: ReactNode, status: BadgeStatus = 'default') {
  return <Badge status={status} text={label} />;
}
