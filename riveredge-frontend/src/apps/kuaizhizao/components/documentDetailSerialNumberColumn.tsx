/**
 * 单据明细表：批号后固定「序列号」列（列始终存在，未开序列号管理显示 —）。
 */
import React from 'react';
import { Form as AntForm, Input } from 'antd';
import type { MessageInstance } from 'antd/es/message/interface';
import type { ProFormInstance } from '@ant-design/pro-components';
import type { TFunction } from 'i18next';
import { SerialNumbersImportTrigger } from '../../../components/serial-numbers-import';
import {
  materialSerialApi,
  MATERIAL_SERIAL_GENERATE_MAX_COUNT,
} from '../../master-data/services/material';
import {
  DOCUMENT_DETAIL_TEXT_COL,
} from './document-detail-table/documentDetailTable';
import {
  isMaterialSerialEntryEnabled,
  type WarehouseTrackingFlags,
} from '../pages/warehouse-management/shared/warehouseTrackingFlags';

function normalizeSerialList(raw: unknown): string[] {
  if (Array.isArray(raw)) {
    return raw.map((s) => String(s ?? '').trim()).filter(Boolean);
  }
  return [];
}

export type DocumentDetailSerialColumnOptions = {
  t: TFunction;
  trackingFlags: WarehouseTrackingFlags;
  formRef: React.MutableRefObject<ProFormInstance | undefined>;
  messageApi: MessageInstance;
  quantityField: string;
  listName?: string;
  generatingSerialIdx: number | null;
  setGeneratingSerialIdx: (index: number | null) => void;
  titleKey?: string;
  width?: number;
};

export function buildDocumentDetailSerialNumberColumn(
  opts: DocumentDetailSerialColumnOptions,
) {
  const {
    t,
    trackingFlags,
    formRef,
    messageApi,
    quantityField,
    listName = 'items',
    generatingSerialIdx,
    setGeneratingSerialIdx,
    titleKey = 'app.kuaizhizao.warehouseCommon.colSerialNo',
    width = 160,
  } = opts;

  return {
    title: t(titleKey),
    dataIndex: 'serial_numbers',
    width,
    ...DOCUMENT_DETAIL_TEXT_COL,
    render: (_: unknown, __: unknown, index: number) => (
      <>
        <AntForm.Item name={[index, 'serial_numbers']} hidden>
          <Input />
        </AntForm.Item>
        <AntForm.Item
          noStyle
          shouldUpdate={(prev, curr) => prev?.[listName]?.[index] !== curr?.[listName]?.[index]}
        >
          {({ getFieldValue }) => {
            const row = getFieldValue([listName, index]);
            if (!isMaterialSerialEntryEnabled(trackingFlags, row?.serial_managed)) {
              return <span>—</span>;
            }
            const qty = Number(row?.[quantityField] ?? 0);
            const expected = qty > 0 ? Math.floor(qty) : 0;
            const sn = getFieldValue([listName, index, 'serial_numbers']);
            return (
              <SerialNumbersImportTrigger
                serials={normalizeSerialList(sn)}
                expectedCount={expected > 0 ? expected : undefined}
                materialLabel={row?.material_code || row?.material_name}
                generateLoading={generatingSerialIdx === index}
                onSerialsChange={(next) =>
                  formRef.current?.setFieldValue([listName, index, 'serial_numbers'], next)
                }
                onGenerate={async () => {
                  const uuid = getFieldValue([listName, index, 'material_uuid']);
                  if (!uuid || !(expected > 0)) return [];
                  const count = Math.min(expected, MATERIAL_SERIAL_GENERATE_MAX_COUNT);
                  setGeneratingSerialIdx(index);
                  try {
                    const res = await materialSerialApi.generate(String(uuid), count, {});
                    formRef.current?.setFieldValue([listName, index, 'serial_numbers'], res.serial_nos);
                    messageApi.success(
                      t('app.kuaizhizao.warehouseInbound.msg.serialGenerated', {
                        count: res.count,
                      }),
                    );
                    return res.serial_nos;
                  } catch (e: unknown) {
                    messageApi.error(
                      (e as Error)?.message ||
                        t('app.kuaizhizao.warehouseInbound.msg.serialGenerateFailed'),
                    );
                    return [];
                  } finally {
                    setGeneratingSerialIdx(null);
                  }
                }}
              />
            );
          }}
        </AntForm.Item>
      </>
    ),
  };
}

/** 只读明细表列：批号后固定展示（无数据显示 —） */
export function buildDocumentDetailSerialReadonlyColumn(
  t: TFunction,
  dataIndex = 'serial_numbers',
  width = 120,
) {
  return {
    title: t('app.kuaizhizao.warehouseCommon.colSerialNo'),
    dataIndex,
    width,
    render: (val: unknown) => {
      const list = normalizeSerialList(val);
      if (!list.length) return '—';
      return t('app.kuaizhizao.warehouseInbound.detail.serialCount', { count: list.length });
    },
  };
}

/** 只读明细：批号后展示序列号（无数据显示 —） */
export function renderDocumentDetailSerialReadonly(
  t: TFunction,
  val: unknown,
  titleKey = 'app.kuaizhizao.warehouseCommon.colSerialNo',
): { title: string; width: number; render: (v: unknown) => React.ReactNode } {
  return {
    title: t(titleKey),
    width: 120,
    render: (v: unknown) => {
      const list = normalizeSerialList(v ?? val);
      if (!list.length) return '—';
      return t('app.kuaizhizao.warehouseInbound.detail.serialCount', { count: list.length });
    },
  };
}