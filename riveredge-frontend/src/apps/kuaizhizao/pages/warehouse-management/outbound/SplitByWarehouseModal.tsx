/**
 * 销售出库新建：按仓拆行（一行多仓 → 多行一仓）
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { App, InputNumber, Modal, Spin, Table, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  ReferenceDisplayAccessError,
  searchReferenceDisplay,
  type ReferenceDisplayItem,
} from '../../../../../utils/referenceDisplay';
import { formatQuantity } from '../../../../../utils/format';
import {
  loadAvailableQtyByMaterialWarehouse,
  resolveAllowNegativeInventory,
} from './outboundConfirmInventoryOptions';
import { MODAL_ISOLATE_POINTER_PROPS } from '../../../../../utils/modalEventIsolation';

export type SplitByWarehouseAllocation = {
  warehouseId: number;
  warehouseName: string;
  quantity: number;
};

export type SplitByWarehouseModalProps = {
  open: boolean;
  onClose: () => void;
  onConfirm: (allocations: SplitByWarehouseAllocation[]) => void;
  materialId: number;
  materialLabel: string;
  /** 本行出库数量，各仓分摊合计须等于该值 */
  targetQuantity: number;
  hostResource?: string;
  quantityPrecision?: number;
};

type WarehouseRow = {
  id: number;
  code: string;
  name: string;
  stockQty: number;
};

function mapWarehouseDisplayItem(item: ReferenceDisplayItem): WarehouseRow {
  return {
    id: Number(item.id),
    code: String(item.code ?? ''),
    name: String(item.name ?? ''),
    stockQty: 0,
  };
}

export const SplitByWarehouseModal: React.FC<SplitByWarehouseModalProps> = ({
  open,
  onClose,
  onConfirm,
  materialId,
  materialLabel,
  targetQuantity,
  hostResource,
  quantityPrecision = 2,
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [allowNegative, setAllowNegative] = useState(false);
  const [rows, setRows] = useState<WarehouseRow[]>([]);
  const [qtyByWh, setQtyByWh] = useState<Record<number, number>>({});

  const target = Number(targetQuantity) || 0;
  const mid = Number(materialId) || 0;

  const loadData = useCallback(async () => {
    if (!(mid > 0)) return;
    setLoading(true);
    try {
      const [whRes, stockMap, neg] = await Promise.all([
        searchReferenceDisplay({
          resource: 'master-data:warehouse:warehouse',
          hostResource,
          isActive: true,
          pageSize: 200,
        }),
        loadAvailableQtyByMaterialWarehouse([mid]),
        resolveAllowNegativeInventory(),
      ]);
      setAllowNegative(neg);
      const stockByWh = stockMap[mid] ?? {};
      const list = (whRes.items || []).map(mapWarehouseDisplayItem).map((w) => ({
        ...w,
        stockQty: Number(stockByWh[w.id] ?? 0),
      }));
      list.sort((a, b) => {
        const aHas = a.stockQty > 0 ? 1 : 0;
        const bHas = b.stockQty > 0 ? 1 : 0;
        if (aHas !== bHas) return bHas - aHas;
        if (a.stockQty !== b.stockQty) return b.stockQty - a.stockQty;
        return `${a.code} ${a.name}`.localeCompare(`${b.code} ${b.name}`, 'zh');
      });
      setRows(list);
      setQtyByWh({});
    } catch (error) {
      console.error(error);
      if (error instanceof ReferenceDisplayAccessError) {
        message.error(error.message);
      } else {
        message.error(t('app.kuaizhizao.warehouseOutbound.splitByWarehouse.loadFailed'));
      }
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [hostResource, message, mid, t]);

  useEffect(() => {
    if (!open) {
      setQtyByWh({});
      return;
    }
    void loadData();
  }, [loadData, open]);

  const allocatedSum = useMemo(
    () =>
      Object.values(qtyByWh).reduce((sum, v) => sum + (Number(v) || 0), 0),
    [qtyByWh],
  );

  const handleOk = () => {
    const allocations: SplitByWarehouseAllocation[] = [];
    for (const row of rows) {
      const q = Number(qtyByWh[row.id] ?? 0);
      if (!(q > 0)) continue;
      if (!allowNegative && q > row.stockQty + 1e-9) {
        message.error(
          t('app.kuaizhizao.warehouseOutbound.splitByWarehouse.exceedsStock', {
            warehouse: `${row.code} ${row.name}`.trim(),
            stock: formatQuantity(row.stockQty),
          }),
        );
        return;
      }
      allocations.push({
        warehouseId: row.id,
        warehouseName: row.name,
        quantity: q,
      });
    }
    if (allocations.length < 2) {
      message.warning(t('app.kuaizhizao.warehouseOutbound.splitByWarehouse.needTwoWarehouses'));
      return;
    }
    if (Math.abs(allocatedSum - target) > 1e-6) {
      message.error(
        t('app.kuaizhizao.warehouseOutbound.splitByWarehouse.sumMismatch', {
          target: formatQuantity(target),
          actual: formatQuantity(allocatedSum),
        }),
      );
      return;
    }
    onConfirm(allocations);
    onClose();
  };

  const columns = [
    {
      title: t('app.kuaizhizao.warehouseOutbound.col.warehouseName'),
      dataIndex: 'name',
      render: (_: unknown, row: WarehouseRow) => {
        const label = `${row.code} ${row.name}`.trim() || String(row.id);
        const qty = Number(row.stockQty ?? 0);
        return (
          <span>
            {qty > 0
              ? t('components.uniWhDropdown.warehouseWithStock', {
                  warehouse: label,
                  qty: formatQuantity(qty),
                })
              : t('components.uniWhDropdown.warehouseWithStockEmpty', { warehouse: label })}
          </span>
        );
      },
    },
    {
      title: t('app.kuaizhizao.warehouseOutbound.splitByWarehouse.colQty'),
      width: 140,
      render: (_: unknown, row: WarehouseRow) => (
        <InputNumber
          size="small"
          min={0}
          precision={quantityPrecision}
          style={{ width: '100%' }}
          value={qtyByWh[row.id] ?? undefined}
          placeholder="0"
          onChange={(v) => {
            setQtyByWh((prev) => {
              const next = { ...prev };
              const n = Number(v) || 0;
              if (n <= 0) delete next[row.id];
              else next[row.id] = n;
              return next;
            });
          }}
        />
      ),
    },
  ];

  return (
    <Modal
      title={t('app.kuaizhizao.warehouseOutbound.splitByWarehouse.title')}
      open={open}
      onCancel={onClose}
      onOk={handleOk}
      okText={t('app.kuaizhizao.warehouseOutbound.splitByWarehouse.confirm')}
      cancelText={t('common.cancel')}
      width={640}
      destroyOnHidden
      {...MODAL_ISOLATE_POINTER_PROPS}
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        {t('app.kuaizhizao.warehouseOutbound.splitByWarehouse.hint', {
          material: materialLabel,
          target: formatQuantity(target),
        })}
      </Typography.Paragraph>
      <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
        {t('app.kuaizhizao.warehouseOutbound.splitByWarehouse.sumLabel', {
          actual: formatQuantity(allocatedSum),
          target: formatQuantity(target),
        })}
      </Typography.Text>
      <Spin spinning={loading}>
        <Table
          size="small"
          pagination={false}
          rowKey="id"
          dataSource={rows}
          columns={columns}
          scroll={{ y: 320 }}
        />
      </Spin>
    </Modal>
  );
};

export default SplitByWarehouseModal;
