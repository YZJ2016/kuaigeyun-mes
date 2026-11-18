import React from 'react';
import { useTranslation } from 'react-i18next';
import { Table } from 'antd';
import type { PartnerAddress } from '../types/supply-chain';
import { partnerAddressTypeLabel } from '../utils/partner-static-labels';

export interface PartnerAddressesDetailTableProps {
  rows?: PartnerAddress[];
}

export const PartnerAddressesDetailTable: React.FC<PartnerAddressesDetailTableProps> = ({ rows }) => {
  const { t } = useTranslation();
  const dataSource = (rows ?? []).map((row, index) => ({ ...row, key: index }));

  return (
    <Table
      size="small"
      pagination={false}
      rowKey="key"
      locale={{ emptyText: t('common.noData') }}
      dataSource={dataSource}
      columns={[
        {
          title: t('field.partner.addressTypeLabel'),
          dataIndex: 'addressType',
          width: 108,
          render: (value: string) => partnerAddressTypeLabel(t, value),
        },
        {
          title: t('field.partner.addressLine'),
          dataIndex: 'address',
        },
        {
          title: t('field.partner.deliveryContactName'),
          dataIndex: 'contactName',
          width: 120,
        },
        {
          title: t('field.partner.deliveryContactPhone'),
          dataIndex: 'contactPhone',
          width: 130,
        },
        {
          title: t('field.partner.addressDefault'),
          dataIndex: 'isDefault',
          width: 72,
          render: (value: boolean) => (value ? t('common.yes') : ''),
        },
      ]}
    />
  );
};
