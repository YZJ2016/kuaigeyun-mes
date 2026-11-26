/**
 * 采购单据：供应商有多联系人时支持下拉选择（仍保留单条时的文本录入）。
 */
import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { Input, Select } from 'antd';
import { ProFormDependency, ProFormSelect, ProFormText } from '@ant-design/pro-components';
import type { ProFormInstance } from '@ant-design/pro-components';
import {
  mapPartnerReferenceDisplayItem,
  resolveReferenceDisplay,
} from '../../../../../utils/referenceDisplay';
import {
  buildSupplierContactPickOptions,
  preferPartnerSupplierDetail,
} from './partnerSupplierFormSnapshot';
import { resolveFullSupplierFromList, type SupplierLike } from './applySupplierFormFields';

const SupplierPartnerDetailContext = createContext<SupplierLike | null>(null);

export function usePurchaseSupplierPartnerDetail(
  supplierId: unknown,
  supplierList: SupplierLike[],
  hostResource: string,
): SupplierLike | null {
  const [fetched, setFetched] = useState<SupplierLike | null>(null);

  const listSupplier = useMemo(() => {
    const id = Number(supplierId);
    if (!Number.isFinite(id) || id <= 0) return null;
    return resolveFullSupplierFromList({ id }, supplierList);
  }, [supplierId, supplierList]);

  useEffect(() => {
    const id = Number(supplierId);
    if (!Number.isFinite(id) || id <= 0) {
      setFetched(null);
      return;
    }
    let cancelled = false;
    void resolveReferenceDisplay({
      resource: 'master-data:supply-chain:supplier',
      recordIds: [id],
      hostResource,
    })
      .then((items) => {
        if (cancelled || !items.length) return;
        setFetched(mapPartnerReferenceDisplayItem(items[0]) as SupplierLike);
      })
      .catch(() => {
        if (!cancelled) setFetched(null);
      });
    return () => {
      cancelled = true;
    };
  }, [supplierId, hostResource]);

  return useMemo(
    () => preferPartnerSupplierDetail(listSupplier, fetched),
    [fetched, listSupplier],
  );
}

function SupplierPartnerDetailBridgeInner({
  supplierId,
  supplierList,
  hostResource,
  children,
}: {
  supplierId: unknown;
  supplierList: SupplierLike[];
  hostResource: string;
  children: React.ReactNode;
}) {
  const supplier = usePurchaseSupplierPartnerDetail(supplierId, supplierList, hostResource);
  return (
    <SupplierPartnerDetailContext.Provider value={supplier}>
      {children}
    </SupplierPartnerDetailContext.Provider>
  );
}

export const PurchaseSupplierPartnerDetailBridge: React.FC<{
  supplierList: SupplierLike[];
  hostResource: string;
  children: React.ReactNode;
}> = ({ supplierList, hostResource, children }) => (
  <ProFormDependency name={['supplier_id']}>
    {({ supplier_id }) => (
      <SupplierPartnerDetailBridgeInner
        supplierId={supplier_id}
        supplierList={supplierList}
        hostResource={hostResource}
      >
        {children}
      </SupplierPartnerDetailBridgeInner>
    )}
  </ProFormDependency>
);

export const PurchaseSupplierContactFormField: React.FC<{
  formRef: React.RefObject<ProFormInstance | undefined | null>;
  label: string;
  placeholder?: string;
}> = ({ formRef, label, placeholder }) => {
  const supplier = useContext(SupplierPartnerDetailContext);
  const contactOptions = useMemo(
    () => (supplier ? buildSupplierContactPickOptions(supplier) : []),
    [supplier],
  );
  const multi = contactOptions.length >= 2;
  if (multi) {
    return (
      <>
        <ProFormText name="supplier_contact" hidden />
        <ProFormDependency name={['supplier_contact', 'supplier_phone']}>
          {({ supplier_contact, supplier_phone }) => {
            const contactStr = String(supplier_contact ?? '').trim();
            const phoneStr = String(supplier_phone ?? '').trim();
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
                        supplier_contact: undefined,
                        supplier_phone: undefined,
                      });
                      return;
                    }
                    const opt = contactOptions.find((o) => o.value === value);
                    if (opt) {
                      formRef.current?.setFieldsValue({
                        supplier_contact: opt.contact,
                        supplier_phone: opt.phone,
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
  return <ProFormText name="supplier_contact" label={label} placeholder={placeholder} />;
};

export const PurchaseSupplierPhoneFormField: React.FC<{
  label: string;
  placeholder?: string;
}> = ({ label, placeholder }) => (
  <ProFormText name="supplier_phone" label={label} placeholder={placeholder} />
);

/** 询价邀请供应商表、子表等：按 supplier_id 渲染联系人下拉 */
export const PurchaseSupplierContactPickInput: React.FC<{
  supplierId?: number | null;
  supplierList: SupplierLike[];
  hostResource: string;
  value?: string;
  placeholder?: string;
  onChange: (contactName: string | undefined, contactPhone?: string) => void;
}> = ({ supplierId, supplierList, hostResource, value, placeholder, onChange }) => {
  const supplier = usePurchaseSupplierPartnerDetail(supplierId, supplierList, hostResource);
  const contactOptions = useMemo(
    () => (supplier ? buildSupplierContactPickOptions(supplier) : []),
    [supplier],
  );
  if (contactOptions.length > 0) {
    const selectedValue =
      contactOptions.find((o) => o.contact === String(value ?? '').trim())?.value ?? undefined;
    return (
      <Select
        size="small"
        showSearch
        allowClear
        style={{ width: '100%' }}
        placeholder={placeholder}
        optionFilterProp="label"
        value={selectedValue}
        options={contactOptions.map((o) => ({ value: o.value, label: o.label }))}
        onChange={(picked) => {
          if (picked == null) {
            onChange(undefined, undefined);
            return;
          }
          const opt = contactOptions.find((o) => o.value === String(picked));
          onChange(opt?.contact, opt?.phone);
        }}
      />
    );
  }
  return (
    <Input
      size="small"
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value || undefined)}
    />
  );
};
