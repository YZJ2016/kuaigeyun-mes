/**
 * 设备台账 — 车间 / 产线（线组）/ 工位 / 工作中心级联选择
 */

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Col, Row } from 'antd';
import { ProForm, ProFormDependency, ProFormText } from '@ant-design/pro-components';
import { UniDropdown } from '../../../components/uni-dropdown';
import { MODAL_NESTED_ABOVE_PARENT_OFFSET } from '../../../components/layout-templates/constants';
import { WorkshopFormModal } from '../../master-data/components/WorkshopFormModal';
import { ProductionLineFormModal } from '../../master-data/components/ProductionLineFormModal';
import { WorkstationFormModal } from '../../master-data/components/WorkstationFormModal';
import { WorkCenterFormModal } from '../../master-data/components/WorkCenterFormModal';
import type { ProductionLine, WorkCenter, Workshop, Workstation } from '../../master-data/types/factory';
import {
  factoryListItems,
  productionLineApi,
  workCenterApi,
  workstationApi,
  workshopApi,
} from '../../master-data/services/factory';

type OptionWithMeta = {
  label: string;
  value: number;
  meta?: Record<string, unknown>;
};

interface EquipmentFactoryBindingFieldsProps {
  formRef: React.MutableRefObject<any>;
  embedInParentRow?: boolean;
  zIndex?: number;
}

function pickMeta(option: OptionWithMeta | OptionWithMeta[] | undefined): Record<string, unknown> | undefined {
  const selected = Array.isArray(option) ? option[0] : option;
  return selected?.meta;
}

function clearDownstreamOfWorkshop() {
  return {
    production_line_id: null,
    production_line_code: null,
    production_line_name: null,
    workstation_id: null,
    workstation_code: null,
    workstation_name: null,
    work_center_id: null,
    work_center_code: null,
    work_center_name: null,
  };
}

function EquipmentProductionLineField({
  workshopId,
  formRef,
  colProps,
  options,
  loadProductionLines,
  onQuickAdd,
}: {
  workshopId?: number;
  formRef: React.MutableRefObject<any>;
  colProps: { span: number } | undefined;
  options: OptionWithMeta[];
  loadProductionLines: (workshopId?: number) => Promise<void>;
  onQuickAdd: () => void;
}) {
  const { t } = useTranslation();

  useEffect(() => {
    void loadProductionLines(workshopId);
  }, [workshopId, loadProductionLines]);

  return (
    <>
      <ProForm.Item
        name="production_line_id"
        label={t('app.kuaizhizao.equipment.fieldProductionLine')}
        style={{ width: '100%' }}
      >
        <UniDropdown
          allowClear
          showSearch
          style={{ width: '100%' }}
          placeholder={t('app.kuaizhizao.equipment.phProductionLine')}
          options={options}
          optionFilterProp="label"
          disabled={!workshopId}
          quickCreate={{
            label: t('field.workstation.quickAddProductionLine'),
            onClick: onQuickAdd,
          }}
          onChange={(_value: number | undefined, option: OptionWithMeta | OptionWithMeta[]) => {
            const meta = pickMeta(option);
            formRef.current?.setFieldsValue({
              production_line_code: meta?.code ?? null,
              production_line_name: meta?.name ?? null,
              workstation_id: null,
              workstation_code: null,
              workstation_name: null,
              work_center_id: null,
              work_center_code: null,
              work_center_name: null,
            });
          }}
        />
      </ProForm.Item>
      <ProFormText name="production_line_code" hidden colProps={colProps} />
      <ProFormText name="production_line_name" hidden colProps={colProps} />
    </>
  );
}

function EquipmentWorkstationField({
  productionLineId,
  formRef,
  colProps,
  options,
  loadWorkstations,
  onQuickAdd,
  applyMatchedWorkCenter,
}: {
  productionLineId?: number;
  formRef: React.MutableRefObject<any>;
  colProps: { span: number } | undefined;
  options: OptionWithMeta[];
  loadWorkstations: (productionLineId?: number) => Promise<void>;
  onQuickAdd: () => void;
  applyMatchedWorkCenter: (workstationId?: number) => Promise<void>;
}) {
  const { t } = useTranslation();

  useEffect(() => {
    void loadWorkstations(productionLineId);
  }, [productionLineId, loadWorkstations]);

  return (
    <>
      <ProForm.Item
        name="workstation_id"
        label={t('app.kuaizhizao.equipment.fieldWorkstation')}
        style={{ width: '100%' }}
      >
        <UniDropdown
          allowClear
          showSearch
          style={{ width: '100%' }}
          placeholder={t('app.kuaizhizao.equipment.phWorkstation')}
          options={options}
          optionFilterProp="label"
          disabled={!productionLineId}
          quickCreate={{
            label: t('field.operation.quickAddWorkstation'),
            onClick: onQuickAdd,
          }}
          onChange={(_value: number | undefined, option: OptionWithMeta | OptionWithMeta[]) => {
            const meta = pickMeta(option);
            formRef.current?.setFieldsValue({
              workstation_code: meta?.code ?? null,
              workstation_name: meta?.name ?? null,
              work_center_id: null,
              work_center_code: null,
              work_center_name: null,
            });
            void applyMatchedWorkCenter(_value);
          }}
        />
      </ProForm.Item>
      <ProFormText name="workstation_code" hidden colProps={colProps} />
      <ProFormText name="workstation_name" hidden colProps={colProps} />
    </>
  );
}

export const EquipmentFactoryBindingFields: React.FC<EquipmentFactoryBindingFieldsProps> = ({
  formRef,
  embedInParentRow = false,
  zIndex,
}) => {
  const { t } = useTranslation();
  const [workshopOptions, setWorkshopOptions] = useState<OptionWithMeta[]>([]);
  const [productionLineOptions, setProductionLineOptions] = useState<OptionWithMeta[]>([]);
  const [workstationOptions, setWorkstationOptions] = useState<OptionWithMeta[]>([]);
  const [workCenterOptions, setWorkCenterOptions] = useState<OptionWithMeta[]>([]);
  const [workshopQuickAddOpen, setWorkshopQuickAddOpen] = useState(false);
  const [productionLineQuickAddOpen, setProductionLineQuickAddOpen] = useState(false);
  const [workstationQuickAddOpen, setWorkstationQuickAddOpen] = useState(false);
  const [workCenterQuickAddOpen, setWorkCenterQuickAddOpen] = useState(false);
  const nestedModalZIndex = (zIndex ?? 1000) + MODAL_NESTED_ABOVE_PARENT_OFFSET;

  const wrapField = (key: string, node: React.ReactNode) =>
    embedInParentRow ? <Col key={key} span={12}>{node}</Col> : node;

  const colProps = embedInParentRow ? undefined : { span: 12 };

  const loadWorkshops = useCallback(async () => {
    const workshops = factoryListItems(await workshopApi.list({ limit: 1000, is_active: true }));
    setWorkshopOptions(
      workshops.map((ws) => ({
        label: ws.name,
        value: ws.id,
        meta: { name: ws.name },
      })),
    );
  }, []);

  const loadProductionLines = useCallback(async (workshopId?: number) => {
    if (!workshopId) {
      setProductionLineOptions([]);
      return;
    }
    const lines = factoryListItems(
      await productionLineApi.list({
        workshop_id: workshopId,
        limit: 1000,
        is_active: true,
      }),
    );
    setProductionLineOptions(
      lines.map((line) => ({
        label: `${line.code} - ${line.name}`,
        value: line.id,
        meta: { code: line.code, name: line.name },
      })),
    );
  }, []);

  const loadWorkstations = useCallback(async (productionLineId?: number) => {
    if (!productionLineId) {
      setWorkstationOptions([]);
      return;
    }
    const stations = factoryListItems(
      await workstationApi.list({
        production_line_id: productionLineId,
        limit: 1000,
        is_active: true,
      }),
    );
    setWorkstationOptions(
      stations.map((ws) => ({
        label: `${ws.code} - ${ws.name}`,
        value: ws.id,
        meta: { code: ws.code, name: ws.name },
      })),
    );
  }, []);

  const loadWorkCenters = useCallback(async () => {
    const centers = factoryListItems(await workCenterApi.list({ limit: 1000, is_active: true }));
    setWorkCenterOptions(
      centers.map((wc) => ({
        label: `${wc.code} - ${wc.name}`,
        value: wc.id,
        meta: { code: wc.code, name: wc.name },
      })),
    );
  }, []);

  useEffect(() => {
    void loadWorkshops();
    void loadWorkCenters();
  }, [loadWorkshops, loadWorkCenters]);

  const handleWorkshopQuickCreated = async (created: Workshop) => {
    await loadWorkshops();
    if (created?.id == null) return;
    formRef.current?.setFieldsValue({
      workshop_id: created.id,
      workshop_name: created.name,
      ...clearDownstreamOfWorkshop(),
    });
    setWorkshopQuickAddOpen(false);
  };

  const handleProductionLineQuickCreated = async (created: ProductionLine) => {
    const workshopId = created.workshopId;
    const workshopMeta = workshopOptions.find((item) => item.value === workshopId)?.meta;
    await loadProductionLines(workshopId);
    if (created?.id == null) return;
    formRef.current?.setFieldsValue({
      workshop_id: workshopId,
      workshop_name: workshopMeta?.name ?? formRef.current?.getFieldValue('workshop_name'),
      production_line_id: created.id,
      production_line_code: created.code,
      production_line_name: created.name,
      workstation_id: null,
      workstation_code: null,
      workstation_name: null,
      work_center_id: null,
      work_center_code: null,
      work_center_name: null,
    });
    setProductionLineQuickAddOpen(false);
  };

  const applyMatchedWorkCenter = useCallback(async (workstationId?: number) => {
    if (!workstationId) return;
    try {
      const centers = factoryListItems(await workCenterApi.list({ limit: 1000, is_active: true }));
      const matched = centers.find((wc) => (wc.workstationIds ?? []).includes(workstationId));
      if (matched) {
        formRef.current?.setFieldsValue({
          work_center_id: matched.id,
          work_center_code: matched.code,
          work_center_name: matched.name,
        });
      }
    } catch {
      /* 工作中心为可选关联，失败不阻断 */
    }
  }, [formRef]);

  const handleWorkstationQuickCreated = async (created: Workstation) => {
    const productionLineId = created.productionLineId;
    const lineMeta = productionLineOptions.find((item) => item.value === productionLineId)?.meta;
    await loadWorkstations(productionLineId);
    if (created?.id == null) return;
    formRef.current?.setFieldsValue({
      production_line_id: productionLineId,
      production_line_code: created.productionLineCode ?? lineMeta?.code ?? formRef.current?.getFieldValue('production_line_code'),
      production_line_name: created.productionLineName ?? lineMeta?.name ?? formRef.current?.getFieldValue('production_line_name'),
      workstation_id: created.id,
      workstation_code: created.code,
      workstation_name: created.name,
      work_center_id: null,
      work_center_code: null,
      work_center_name: null,
    });
    await applyMatchedWorkCenter(created.id);
    setWorkstationQuickAddOpen(false);
  };

  const handleWorkCenterQuickCreated = async (created: WorkCenter) => {
    await loadWorkCenters();
    if (created?.id == null) return;
    formRef.current?.setFieldsValue({
      work_center_id: created.id,
      work_center_code: created.code,
      work_center_name: created.name,
    });
    setWorkCenterQuickAddOpen(false);
  };

  const fields = (
    <>
      {wrapField(
        'workshop',
        <>
          <ProForm.Item
            name="workshop_id"
            label={t('app.kuaizhizao.equipment.fieldWorkshop')}
            style={{ width: '100%' }}
          >
            <UniDropdown
              allowClear
              showSearch
              style={{ width: '100%' }}
              placeholder={t('app.kuaizhizao.equipment.phWorkshop')}
              options={workshopOptions}
              optionFilterProp="label"
              quickCreate={{
                label: t('field.operation.quickAddWorkshop'),
                onClick: () => setWorkshopQuickAddOpen(true),
              }}
              onChange={(_value: number | undefined, option: OptionWithMeta | OptionWithMeta[]) => {
                const meta = pickMeta(option);
                formRef.current?.setFieldsValue({
                  workshop_name: meta?.name ?? null,
                  ...clearDownstreamOfWorkshop(),
                });
              }}
            />
          </ProForm.Item>
          <ProFormText name="workshop_name" hidden colProps={colProps} />
        </>,
      )}

      {wrapField(
        'production_line',
        <ProFormDependency name={['workshop_id']}>
          {({ workshop_id }) => (
            <EquipmentProductionLineField
              workshopId={workshop_id}
              formRef={formRef}
              colProps={colProps}
              options={productionLineOptions}
              loadProductionLines={loadProductionLines}
              onQuickAdd={() => setProductionLineQuickAddOpen(true)}
            />
          )}
        </ProFormDependency>,
      )}

      {wrapField(
        'workstation',
        <ProFormDependency name={['production_line_id']}>
          {({ production_line_id }) => (
            <EquipmentWorkstationField
              productionLineId={production_line_id}
              formRef={formRef}
              colProps={colProps}
              options={workstationOptions}
              loadWorkstations={loadWorkstations}
              onQuickAdd={() => setWorkstationQuickAddOpen(true)}
              applyMatchedWorkCenter={applyMatchedWorkCenter}
            />
          )}
        </ProFormDependency>,
      )}

      {wrapField(
        'work_center',
        <>
          <ProForm.Item
            name="work_center_id"
            label={t('app.kuaizhizao.equipment.fieldWorkCenter')}
            style={{ width: '100%' }}
          >
            <UniDropdown
              allowClear
              showSearch
              style={{ width: '100%' }}
              placeholder={t('app.kuaizhizao.equipment.phWorkCenter')}
              options={workCenterOptions}
              optionFilterProp="label"
              quickCreate={{
                label: t('field.operation.quickAddWorkCenter'),
                onClick: () => setWorkCenterQuickAddOpen(true),
              }}
              onChange={(_value: number | undefined, option: OptionWithMeta | OptionWithMeta[]) => {
                const meta = pickMeta(option);
                formRef.current?.setFieldsValue({
                  work_center_code: meta?.code ?? null,
                  work_center_name: meta?.name ?? null,
                });
              }}
            />
          </ProForm.Item>
          <ProFormText name="work_center_code" hidden colProps={colProps} />
          <ProFormText name="work_center_name" hidden colProps={colProps} />
        </>,
      )}
    </>
  );

  const quickAddModals = (
    <>
      {workshopQuickAddOpen ? (
        <WorkshopFormModal
          open
          onClose={() => setWorkshopQuickAddOpen(false)}
          editUuid={null}
          onSuccess={handleWorkshopQuickCreated}
          zIndex={nestedModalZIndex}
        />
      ) : null}
      {productionLineQuickAddOpen ? (
        <ProductionLineFormModal
          open
          onClose={() => setProductionLineQuickAddOpen(false)}
          editUuid={null}
          onSuccess={handleProductionLineQuickCreated}
          zIndex={nestedModalZIndex}
          defaultWorkshopId={formRef.current?.getFieldValue('workshop_id')}
        />
      ) : null}
      {workstationQuickAddOpen ? (
        <WorkstationFormModal
          open
          onClose={() => setWorkstationQuickAddOpen(false)}
          editUuid={null}
          onSuccess={handleWorkstationQuickCreated}
          zIndex={nestedModalZIndex}
          defaultProductionLineId={formRef.current?.getFieldValue('production_line_id')}
        />
      ) : null}
      {workCenterQuickAddOpen ? (
        <WorkCenterFormModal
          open
          onClose={() => setWorkCenterQuickAddOpen(false)}
          editUuid={null}
          onSuccess={handleWorkCenterQuickCreated}
          zIndex={nestedModalZIndex}
        />
      ) : null}
    </>
  );

  if (embedInParentRow) {
    return (
      <>
        {fields}
        {quickAddModals}
      </>
    );
  }

  return (
    <>
      <Row gutter={16}>
        <Col span={24}>{fields}</Col>
      </Row>
      {quickAddModals}
    </>
  );
};

export default EquipmentFactoryBindingFields;
