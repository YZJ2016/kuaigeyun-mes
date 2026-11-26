import React from 'react';
import { Button, Popover, Space, Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import './RoleMemberSearchHint.less';

type RoleMemberSearchHintProps = {
  open: boolean;
  onDismiss: () => void;
  children: React.ReactElement;
};

export const RoleMemberSearchHint: React.FC<RoleMemberSearchHintProps> = ({
  open,
  onDismiss,
  children,
}) => {
  const { t } = useTranslation();

  return (
    <Popover
      open={open}
      trigger={[]}
      placement="rightTop"
      getPopupContainer={() => document.body}
      zIndex={2100}
      arrow
      onOpenChange={(next) => {
        if (next) return;
      }}
      styles={{ root: { maxWidth: 340 } }}
      content={
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'nowrap' }}>
            <span className="role-member-search-hint-new-tag">
              <Tag color="gold" variant="filled" style={{ margin: 0, position: 'relative', zIndex: 0 }}>
                NEW
              </Tag>
              <span className="role-member-search-hint-new-tag__shine" aria-hidden />
            </span>
            <span style={{ fontSize: 13, lineHeight: '22px', whiteSpace: 'nowrap' }}>
              {t('pages.system.roles.searchMemberNewHint')}
            </span>
          </div>
          <Button type="primary" size="small" block onClick={onDismiss}>
            {t('components.uniQuery.gotIt')}
          </Button>
        </Space>
      }
    >
      {children}
    </Popover>
  );
};