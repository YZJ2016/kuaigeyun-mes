/**
 * 库位新建/编辑弹窗
 * 可挂库区，或直挂仓库（所属仓库 + 可选库区）。
 */

import React, { useRef, useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ProFormInstance } from '@ant-design/pro-components';
import { App, theme } from 'antd';
import { FormModalTemplate } from '../../../components/layout-templates';
import { MODAL_CONFIG, MODAL_NESTED_ABOVE_PARENT_OFFSET } from '../../../components/layout-templates/constants';
import { storageLocationApi, storageAreaApi, warehouseApi } from '../services/warehouse';
import { testGenerateCode, generateCode, getCodeRulePageConfig } from '../../../services/codeRule';
import { isAutoGenerateEnabled, getPageRuleCode } from '../../../utils/codeRulePage';
import type {
  StorageLocation,
  StorageLocationCreate,
  StorageLocationUpdate,
  StorageArea,
  Warehouse,
} from '../types/warehouse';
import { SchemaFormRenderer } from '../../../components/schema-form';
import { storageLocationFormSchema } from '../schemas/storage-location';
import { useCustomFields } from '../../../hooks/useCustomFields';
import { CustomFieldsFormSection } from '../../../components/custom-fields';
import { StorageAreaFormModal } from './StorageAreaFormModal';

const PAGE_CODE = 'master-data-warehouse-storage-location';
const CUSTOM_FIELD_TABLE = 'master_data_warehouse_storage_locations';

export interface StorageLocationFormModalProps {
  open: boolean;
  onClose: () => void;
  editUuid: string | null;
  onSuccess: (storageLocation: StorageLocation) => void;
  zIndex?: number;
}

export const StorageLocationFormModal: React.FC<StorageLocationFormModalProps> = ({
  open,
  onClose,
  editUuid,
  onSuccess,
  zIndex,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const { token } = theme.useToken();
  const formRef = useRef<ProFormInstance>();
  const [formLoading, setFormLoading] = useState(false);
  const [previewCode, setPreviewCode] = useState<string | null>(null);
  const [effectiveRuleCode, setEffectiveRuleCode] = useState<string | null>(null);
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [storageAreas, setStorageAreas] = useState<StorageArea[]>([]);
  const [selectedWarehouseId, setSelectedWarehouseId] = useState<number | null>(null);
  const [storageAreaQuickCreateVisible, setStorageAreaQuickCreateVisible] = useState(false);

  const {
    customFields,
    customFieldValues,
    loadFieldValues,
    extractFormValues,
    saveCustomFieldValues,
    resetFieldValues,
  } = useCustomFields({ tableName: CUSTOM_FIELD_TABLE, loadWhenOpen: true, open });

  const isEdit = Boolean(editUuid);

  const nestedModalZIndex =
    zIndex != null
      ? zIndex + MODAL_NESTED_ABOVE_PARENT_OFFSET
      : token.zIndexPopupBase + MODAL_NESTED_ABOVE_PARENT_OFFSET;

  const reloadWarehouses = useCallback(async () => {
    try {
      const result = await warehouseApi.list({ limit: 1000, is_active: true });
      setWarehouses(result.items);
    } catch (error) {
      console.error('加载仓库列表失败:', error);
    }
  }, []);

  const reloadStorageAreas = useCallback(async () => {
    try {
      const result = await storageAreaApi.list({ limit: 1000, is_active: true });
      setStorageAreas(result.items);
    } catch (error) {
      console.error('加载库区列表失败:', error);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    void reloadWarehouses();
    void reloadStorageAreas();
  }, [open, reloadWarehouses, reloadStorageAreas]);

  useEffect(() => {
    if (!open) return;
    formRef.current?.resetFields();
    formRef.current?.setFieldsValue({ isActive: true });
    setSelectedWarehouseId(null);
    resetFieldValues();
    if (!editUuid) {
      (async () => {
        let ruleCode = getPageRuleCode(PAGE_CODE);
        let autoGenerate = isAutoGenerateEnabled(PAGE_CODE);
        try {
          const pageConfig = await getCodeRulePageConfig(PAGE_CODE);
          if (pageConfig?.ruleCode) {
            ruleCode = pageConfig.ruleCode;
            autoGenerate = !!pageConfig.autoGenerate;
          }
        } catch {}
        if (autoGenerate && ruleCode) {
          setEffectiveRuleCode(ruleCode);
          testGenerateCode({ rule_code: ruleCode })
            .then((res) => {
              setPreviewCode(res.code);
              formRef.current?.setFieldsValue({ code: res.code, isActive: true });
            })
            .catch(() => {
              setPreviewCode(null);
              formRef.current?.setFieldsValue({ isActive: true });
            });
        } else {
          setPreviewCode(null);
          setEffectiveRuleCode(null);
          formRef.current?.setFieldsValue({ isActive: true });
        }
      })();
      return;
    }
    setPreviewCode(null);
    setEffectiveRuleCode(null);
    storageLocationApi
      .get(editUuid)
      .then(async (detail) => {
        const warehouseId =
          detail.warehouseId ??
          storageAreas.find((s) => s.id === detail.storageAreaId)?.warehouseId ??
          null;
        setSelectedWarehouseId(warehouseId != null ? Number(warehouseId) : null);
        formRef.current?.setFieldsValue({
          code: detail.code,
          name: detail.name,
          warehouseId: warehouseId ?? undefined,
          storageAreaId: detail.storageAreaId ?? undefined,
          description: detail.description,
          isActive: detail.isActive ?? true,
        });
        const fieldFormValues = await loadFieldValues(detail.id);
        formRef.current?.setFieldsValue(fieldFormValues);
      })
      .catch((err: any) => {
        messageApi.error(err?.message || t('app.master-data.storageLocations.getDetailFailed'));
      });
  }, [open, editUuid]);

  const handleValuesChange = (changed: Record<string, unknown>, all: Record<string, unknown>) => {
    if ('warehouseId' in changed) {
      const nextWh =
        changed.warehouseId != null && Number(changed.warehouseId) > 0
          ? Number(changed.warehouseId)
          : null;
      setSelectedWarehouseId(nextWh);
      const areaId = all.storageAreaId != null ? Number(all.storageAreaId) : null;
      if (areaId != null) {
        const area = storageAreas.find((s) => s.id === areaId);
        if (!area || (nextWh != null && Number(area.warehouseId) !== nextWh)) {
          formRef.current?.setFieldsValue({ storageAreaId: undefined });
        }
      }
    }
    if ('storageAreaId' in changed) {
      const areaId =
        changed.storageAreaId != null && Number(changed.storageAreaId) > 0
          ? Number(changed.storageAreaId)
          : null;
      if (areaId != null) {
        const area = storageAreas.find((s) => s.id === areaId);
        if (area?.warehouseId != null) {
          const wh = Number(area.warehouseId);
          setSelectedWarehouseId(wh);
          formRef.current?.setFieldsValue({ warehouseId: wh });
        }
      }
    }
  };

  const handleSubmit = async (values: any) => {
    try {
      setFormLoading(true);
      const { customData, standardValues } = extractFormValues(values);
      const payload = {
        ...standardValues,
        warehouseId: standardValues.warehouseId ?? null,
        storageAreaId: standardValues.storageAreaId ?? null,
      };

      if (isEdit && editUuid) {
        await storageLocationApi.update(editUuid, payload as StorageLocationUpdate);
        messageApi.success(t('common.updateSuccess'));
        const updated = await storageLocationApi.get(editUuid);
        await saveCustomFieldValues(updated.id, customData);
        onSuccess(updated);
      } else {
        const ruleCodeToUse = effectiveRuleCode || getPageRuleCode(PAGE_CODE);
        if (
          ruleCodeToUse &&
          (isAutoGenerateEnabled(PAGE_CODE) || effectiveRuleCode) &&
          (payload.code === previewCode || !payload.code)
        ) {
          try {
            const codeResponse = await generateCode({ rule_code: ruleCodeToUse });
            payload.code = codeResponse.code;
          } catch {}
        }
        if (payload.isActive === undefined) {
          payload.isActive = true;
        }
        const created = await storageLocationApi.create(payload as StorageLocationCreate);
        await saveCustomFieldValues(created.id, customData);
        messageApi.success(t('common.createSuccess'));
        onSuccess(created);
      }
      onClose();
      formRef.current?.resetFields();
      setPreviewCode(null);
      setEffectiveRuleCode(null);
      setSelectedWarehouseId(null);
      resetFieldValues();
    } catch (error: any) {
      messageApi.error(error?.message || (isEdit ? t('common.updateFailed') : t('common.createFailed')));
    } finally {
      setFormLoading(false);
    }
  };

  const handleClose = () => {
    onClose();
    formRef.current?.resetFields();
    setPreviewCode(null);
    setEffectiveRuleCode(null);
    setSelectedWarehouseId(null);
    resetFieldValues();
  };

  const handleStorageAreaQuickCreateSuccess = (storageArea: StorageArea) => {
    setStorageAreas((prev) => {
      if (prev.some((s) => s.id === storageArea.id)) return prev;
      return [...prev, storageArea];
    });
    if (storageArea.warehouseId != null) {
      setSelectedWarehouseId(Number(storageArea.warehouseId));
      formRef.current?.setFieldsValue({
        warehouseId: storageArea.warehouseId,
        storageAreaId: storageArea.id,
      });
    } else {
      formRef.current?.setFieldsValue({ storageAreaId: storageArea.id });
    }
    setStorageAreaQuickCreateVisible(false);
    void reloadStorageAreas();
  };

  const filteredAreas = useMemo(() => {
    if (selectedWarehouseId == null) return storageAreas;
    return storageAreas.filter((s) => Number(s.warehouseId) === selectedWarehouseId);
  }, [storageAreas, selectedWarehouseId]);

  const optionsMap = {
    warehouseId: warehouses.map((w) => ({
      label: `${w.code} - ${w.name}`,
      value: w.id,
    })),
    storageAreaId: filteredAreas.map((s) => ({
      label: `${s.code} - ${s.name}`,
      value: s.id,
    })),
  };

  return (
    <>
      <FormModalTemplate
        title={isEdit ? t('field.storageLocation.editTitle') : t('field.storageLocation.createTitle')}
        open={open}
        onClose={handleClose}
        onFinish={handleSubmit}
        isEdit={isEdit}
        loading={formLoading}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        formRef={formRef as React.RefObject<ProFormInstance>}
        initialValues={{ isActive: true }}
        layout="vertical"
        grid
        zIndex={zIndex}
        onValuesChange={handleValuesChange}
      >
        <SchemaFormRenderer
          schema={storageLocationFormSchema}
          slots={{ customFields: <CustomFieldsFormSection customFields={customFields} customFieldValues={customFieldValues} gridColumns={2} /> }}
          codeField="code"
          codeAutoGenerated={isAutoGenerateEnabled(PAGE_CODE)}
          codeAutoGeneratedKey="field.storageLocation.codeAutoGenerated"
          isEdit={isEdit}
          allowEditCodeWhenEdit
          optionsMap={optionsMap}
          dropdownEnhanceMap={{
            storageAreaId: {
              quickCreate: {
                label: t('field.storageLocation.quickAddStorageArea'),
                onClick: () => setStorageAreaQuickCreateVisible(true),
              },
            },
          }}
        />
      </FormModalTemplate>

      {storageAreaQuickCreateVisible ? (
        <StorageAreaFormModal
          open={storageAreaQuickCreateVisible}
          editUuid={null}
          onClose={() => setStorageAreaQuickCreateVisible(false)}
          onSuccess={handleStorageAreaQuickCreateSuccess}
          zIndex={nestedModalZIndex}
        />
      ) : null}
    </>
  );
};
