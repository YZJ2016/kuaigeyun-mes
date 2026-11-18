/**
 * 客户/供应商地址明细（UniTableDetail + Form.List，布局同联系人）
 */

import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Checkbox, Form, Input, Select } from 'antd';
import { UniTableDetail } from '../../../components/uni-table-detail';
import { PARTNER_ADDRESS_TYPE_CODES, type PartnerAddress } from '../types/supply-chain';

export const EMPTY_PARTNER_ADDRESS_ROW: PartnerAddress = {
  addressType: 'registered',
  address: undefined,
  contactName: undefined,
  contactPhone: undefined,
  isDefault: false,
};

export interface PartnerAddressesFormTableProps {
  titleKey: string;
}

function AddressDefaultCell({ index }: { index: number }) {
  const form = Form.useFormInstance();
  return (
    <Form.Item name={[index, 'isDefault']} style={{ margin: 0 }} valuePropName="checked">
      <Checkbox
        onChange={(event) => {
          if (!event.target.checked) return;
          const rows = form.getFieldValue('addresses');
          if (!Array.isArray(rows)) return;
          rows.forEach((_, rowIndex) => {
            if (rowIndex !== index) {
              form.setFieldValue(['addresses', rowIndex, 'isDefault'], false);
            }
          });
        }}
      />
    </Form.Item>
  );
}

export const PartnerAddressesFormTable: React.FC<PartnerAddressesFormTableProps> = ({ titleKey }) => {
  const { t } = useTranslation();

  const addressTypeOptions = useMemo(
    () =>
      PARTNER_ADDRESS_TYPE_CODES.map((code) => ({
        value: code,
        label: t(`field.partner.addressType.${code}`),
      })),
    [t],
  );

  return (
    <UniTableDetail
      name="addresses"
      title={t(titleKey)}
      required={false}
      initialValue={EMPTY_PARTNER_ADDRESS_ROW}
      containerStyle={{ width: '100%', marginBottom: 24 }}
      tableProps={{ className: 'partner-addresses-detail-table', size: 'small' }}
      columns={[
        {
          title: t('field.partner.addressTypeLabel'),
          dataIndex: 'addressType',
          width: 120,
          render: (_: unknown, __: unknown, index: number) => (
            <Form.Item name={[index, 'addressType']} style={{ margin: 0 }} rules={[{ required: true, message: t('field.partner.addressTypeRequired') }]}>
              <Select size="small" allowClear options={addressTypeOptions} />
            </Form.Item>
          ),
        },
        {
          title: t('field.partner.addressLine'),
          dataIndex: 'address',
          width: 320,
          render: (_: unknown, __: unknown, index: number) => (
            <Form.Item
              name={[index, 'address']}
              style={{ margin: 0 }}
              rules={[
                { required: true, message: t('field.partner.addressLineRequired') },
                { max: 500, message: t('field.partner.addressLineMaxLength') },
              ]}
            >
              <Input
                placeholder={t('field.partner.addressLinePlaceholder')}
                size="small"
                allowClear
                maxLength={500}
              />
            </Form.Item>
          ),
        },
        {
          title: t('field.partner.deliveryContactName'),
          dataIndex: 'contactName',
          width: 120,
          render: (_: unknown, __: unknown, index: number) => (
            <Form.Item
              name={[index, 'contactName']}
              style={{ margin: 0 }}
              rules={[{ max: 100, message: t('field.partner.deliveryContactNameMaxLength') }]}
            >
              <Input placeholder={t('field.partner.deliveryContactNamePlaceholder')} size="small" allowClear />
            </Form.Item>
          ),
        },
        {
          title: t('field.partner.deliveryContactPhone'),
          dataIndex: 'contactPhone',
          width: 130,
          render: (_: unknown, __: unknown, index: number) => (
            <Form.Item
              name={[index, 'contactPhone']}
              style={{ margin: 0 }}
              rules={[{ max: 30, message: t('field.partner.deliveryContactPhoneMaxLength') }]}
            >
              <Input placeholder={t('field.partner.deliveryContactPhonePlaceholder')} size="small" allowClear />
            </Form.Item>
          ),
        },
        {
          title: t('field.partner.addressDefault'),
          dataIndex: 'isDefault',
          width: 72,
          align: 'center',
          render: (_: unknown, __: unknown, index: number) => <AddressDefaultCell index={index} />,
        },
      ]}
    />
  );
};
