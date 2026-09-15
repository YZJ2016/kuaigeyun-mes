import React from 'react';
import { CommentOutlined } from '@ant-design/icons';
import { Button, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useDocumentVisible } from '../../hooks/useDocumentVisible';
import { hasPermission } from '../../utils/permission';
import { useImUnreadTotal } from './useImUnreadTotal';

export type UniImHeaderButtonProps = {
  onClick: () => void;
  panelOpen?: boolean;
};

export const UniImHeaderButton: React.FC<UniImHeaderButtonProps> = ({ onClick, panelOpen = false }) => {
  const { t } = useTranslation();
  const currentUser = useCurrentUser();
  const documentVisible = useDocumentVisible();
  const enabled =
    !!currentUser && documentVisible && hasPermission(currentUser, 'system:user-message:read');
  const unreadTotal = useImUnreadTotal(enabled);

  if (!enabled) {
    return null;
  }

  return (
    <Tooltip title={t('components.uniIm.tooltip')} open={panelOpen ? false : undefined}>
      <Button
        type="text"
        size="small"
        icon={<CommentOutlined />}
        aria-label={t('components.uniIm.tooltip')}
        className={
          unreadTotal > 0
            ? 'riveredge-header-notification-bell riveredge-header-notification-btn--has-count'
            : 'riveredge-header-notification-bell'
        }
        {...(unreadTotal > 0
          ? {
              'data-unread-count': unreadTotal > 99 ? '99+' : String(unreadTotal),
            }
          : {})}
        onClick={onClick}
      />
    </Tooltip>
  );
};
