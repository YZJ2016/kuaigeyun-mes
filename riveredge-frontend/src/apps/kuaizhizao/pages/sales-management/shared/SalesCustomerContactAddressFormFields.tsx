/**
 * 销售单据：客户有多联系人 / 多地址时支持下拉选择（仍保留单条时的文本录入）。
 */
import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { ProFormDependency, ProFormSelect, ProFormText } from '@ant-design/pro-components';
import type { ProFormInstance } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import {
  mapPartnerReferenceDisplayItem,
  resolveReferenceDisplay,
} from '../../../../../utils/referenceDisplay';
import {
  buildCustomerContactPickOptions,
  buildCustomerShippingAddressPickOptions,
  preferPartnerCustomerDetail,
} from './partnerCustomerFormSnapshot';
import { resolveFullCustomerFromList, type CustomerLike } from './applyCustomerFormFields';

const CustomerPartnerDetailContext = createContext<CustomerLike | null>(null);

function useCustomerPartnerDetail(
  customerId: unknown,
  customerList: CustomerLike[],
  hostResource: string,
): CustomerLike | null {
  const [fetched, setFetched] = useState<CustomerLike | null>(null);

  const listCustomer = useMemo(() => {
    const id = Number(customerId);
    if (!Number.isFinite(id) || id <= 0) return null;
    return resolveFullCustomerFromList({ id }, customerList);
  }, [customerId, customerList]);

  useEffect(() => {
    const id = Number(customerId);
    if (!Number.isFinite(id) || id <= 0) {
      setFetched(null);
      return;
    }
    let cancelled = false;
    void resolveReferenceDisplay({
      resource: 'master-data:supply-chain:customer',
      recordIds: [id],
      hostResource,
    })
      .then((items) => {
        if (cancelled || !items.length) return;
        setFetched(mapPartnerReferenceDisplayItem(items[0]) as CustomerLike);
      })
      .catch(() => {
        if (!cancelled) setFetched(null);
      });
    return () => {
      cancelled = true;
    };
  }, [customerId, hostResource]);

  return useMemo(
    () => preferPartnerCustomerDetail(listCustomer, fetched),
    [fetched, listCustomer],
  );
}

function CustomerPartnerDetailBridgeInner({
  customerId,
  customerList,
  hostResource,
  children,
}: {
  customerId: unknown;
  customerList: CustomerLike[];
  hostResource: string;
  children: React.ReactNode;
}) {
  const customer = useCustomerPartnerDetail(customerId, customerList, hostResource);
  return (
    <CustomerPartnerDetailContext.Provider value={customer}>{children}</CustomerPartnerDetailContext.Provider>
  );
}

/** 包住一行内的联系/电话/地址字段，共享当前客户的联系人地址明细 */
export const SalesCustomerPartnerDetailBridge: React.FC<{
  customerList: CustomerLike[];
  hostResource: string;
  children: React.ReactNode;
}> = ({ customerList, hostResource, children }) => (
  <ProFormDependency name={['customer_id']}>
    {({ customer_id }) => (
      <CustomerPartnerDetailBridgeInner
        customerId={customer_id}
        customerList={customerList}
        hostResource={hostResource}
      >
        {children}
      </CustomerPartnerDetailBridgeInner>
    )}
  </ProFormDependency>
);

export const SalesCustomerContactFormField: React.FC<{
  formRef: React.RefObject<ProFormInstance | undefined | null>;
  label: string;
  placeholder?: string;
}> = ({ formRef, label, placeholder }) => {
  const customer = useContext(CustomerPartnerDetailContext);
  const contactOptions = useMemo(
    () => (customer ? buildCustomerContactPickOptions(customer) : []),
    [customer],
  );
  const multi = contactOptions.length >= 2;
  if (multi) {
    return (
      <>
        <ProFormText name="customer_contact" hidden />
        <ProFormDependency name={['customer_contact', 'customer_phone']}>
        {({ customer_contact, customer_phone }) => {
          const contactStr = String(customer_contact ?? '').trim();
          const phoneStr = String(customer_phone ?? '').trim();
          const selectedValue =
            contactOptions.find(
              (o) => o.contact === contactStr && (o.phone ?? '') === phoneStr,
            )?.value ?? undefined;
          return (
            <ProFormSelect
              label={label}
              placeholder={placeholder}
              showSearch
              allowClear
              options={contactOptions.map((o) => ({ value: o.value, label: o.label }))}
              fieldProps={{
                value: selectedValue,
                optionFilterProp: 'label',
                onChange: (value: string | undefined) => {
                  if (!value) {
                    formRef.current?.setFieldsValue({
                      customer_contact: undefined,
                      customer_phone: undefined,
                    });
                    return;
                  }
                  const opt = contactOptions.find((o) => o.value === value);
                  if (opt) {
                    formRef.current?.setFieldsValue({
                      customer_contact: opt.contact,
                      customer_phone: opt.phone,
                    });
                  }
                },
              }}
            />
          );
        }}
        </ProFormDependency>
      </>
    );
  }
  return <ProFormText name="customer_contact" label={label} placeholder={placeholder} />;
};

export const SalesCustomerPhoneFormField: React.FC<{
  label: string;
  placeholder?: string;
}> = ({ label, placeholder }) => (
  <ProFormText name="customer_phone" label={label} placeholder={placeholder} />
);

export const SalesCustomerShippingAddressFormField: React.FC<{
  label: string;
  placeholder?: string;
  wide?: boolean;
}> = ({ label, placeholder, wide }) => {
  const { t } = useTranslation();
  const customer = useContext(CustomerPartnerDetailContext);
  const addressOptions = useMemo(() => {
    if (!customer) return [];
    return buildCustomerShippingAddressPickOptions(customer, (type) => {
      const key = `field.partner.addressType.${type}`;
      const translated = t(key);
      return translated !== key ? translated : type;
    });
  }, [customer, t]);
  const multi = addressOptions.length >= 2;
  const field = multi ? (
    <ProFormSelect
      name="shipping_address"
      label={label}
      placeholder={placeholder}
      showSearch
      allowClear
      options={addressOptions.map((o) => ({ value: o.value, label: o.label }))}
      fieldProps={{ optionFilterProp: 'label' }}
    />
  ) : (
    <ProFormText name="shipping_address" label={label} placeholder={placeholder} />
  );
  if (!wide) {
    return <div style={{ width: 'calc(200% + 16px)' }}>{field}</div>;
  }
  return field;
};