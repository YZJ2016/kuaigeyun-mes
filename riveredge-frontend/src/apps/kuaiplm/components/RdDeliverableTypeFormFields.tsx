import React from 'react';
import { useTranslation } from 'react-i18next';
import { ProFormDependency, ProFormText } from '@ant-design/pro-components';
import { Alert } from 'antd';
import {
  isPartSpecType,
  isSchematicGerberType,
  isSoftwareSpecType,
  isStructureCatalogType,
  isStructureDrawingType,
  isTestReportCompleteType,
  isTestReportPartType,
} from '../utils/rdDeliverableTypes';

type Props = {
  linkedProjectCode?: string | null;
  showStandaloneProjectCode?: boolean;
};

export const RdDeliverableTypeFormFields: React.FC<Props> = ({
  linkedProjectCode,
  showStandaloneProjectCode,
}) => {
  const { t } = useTranslation();

  return (
    <ProFormDependency name={['deliverable_type', 'project_id']}>
      {({ deliverable_type, project_id }) => {
        const dtype = String(deliverable_type || '').trim();
        const hasProject = project_id != null && project_id !== '';
        if (showStandaloneProjectCode && !hasProject && isSoftwareSpecType(dtype)) {
          return (
            <>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                title={t('app.kuaiplm.rdDeliverables.form.softwareSpecProjectCodeHint')}
              />
              <ProFormText
                name="project_code"
                label={t('app.kuaiplm.rdDeliverables.form.projectCode')}
                rules={[
                  {
                    required: true,
                    message: t('app.kuaiplm.rdDeliverables.form.projectCodeRequired'),
                  },
                ]}
                placeholder={t('app.kuaiplm.rdDeliverables.form.projectCodePlaceholder')}
              />
            </>
          );
        }
        if (isPartSpecType(dtype)) {
          return (
            <>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                title={t('app.kuaiplm.rdProjects.detail.deliverable.partSpecHint')}
              />
              <ProFormText
                name="material_code"
                label={t('app.kuaiplm.rdProjects.detail.deliverable.materialCode')}
                rules={[
                  {
                    required: true,
                    message: t('app.kuaiplm.rdProjects.detail.deliverable.materialCodeRequired'),
                  },
                ]}
                placeholder={t('app.kuaiplm.rdProjects.detail.deliverable.materialCodePlaceholder')}
              />
            </>
          );
        }
        if (isSoftwareSpecType(dtype)) {
          const code = linkedProjectCode?.trim() || 'PROJECT';
          return (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              title={t('app.kuaiplm.rdProjects.detail.deliverable.softwareSpecHint', {
                projectCode: code,
              })}
            />
          );
        }
        if (isSchematicGerberType(dtype)) {
          return (
            <>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                title={t('app.kuaiplm.rdProjects.detail.deliverable.schematicGerberHint')}
              />
              <ProFormText
                name="material_code"
                label={t('app.kuaiplm.rdProjects.detail.deliverable.pcbCode')}
                rules={[
                  {
                    required: true,
                    message: t('app.kuaiplm.rdProjects.detail.deliverable.pcbCodeRequired'),
                  },
                ]}
                placeholder={t('app.kuaiplm.rdProjects.detail.deliverable.pcbCodePlaceholder')}
              />
            </>
          );
        }
        if (isTestReportPartType(dtype)) {
          return (
            <>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                title={t('app.kuaiplm.rdProjects.detail.deliverable.testReportPartHint')}
              />
              <ProFormText
                name="material_code"
                label={t('app.kuaiplm.rdProjects.detail.deliverable.materialCode')}
                rules={[
                  {
                    required: true,
                    message: t('app.kuaiplm.rdProjects.detail.deliverable.materialCodeRequired'),
                  },
                ]}
                placeholder={t('app.kuaiplm.rdProjects.detail.deliverable.materialCodePlaceholder')}
              />
              <ProFormText
                name="legacy_material_code"
                label={t('app.kuaiplm.rdProjects.detail.deliverable.legacyMaterialCode')}
                placeholder={t(
                  'app.kuaiplm.rdProjects.detail.deliverable.legacyMaterialCodePlaceholder',
                )}
              />
            </>
          );
        }
        if (isTestReportCompleteType(dtype)) {
          return (
            <>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                title={t('app.kuaiplm.rdProjects.detail.deliverable.testReportCompleteHint')}
              />
              <ProFormText
                name="material_code"
                label={t('app.kuaiplm.rdProjects.detail.deliverable.completeMachineCode')}
                rules={[
                  {
                    required: true,
                    message: t(
                      'app.kuaiplm.rdProjects.detail.deliverable.completeMachineCodeRequired',
                    ),
                  },
                ]}
                placeholder={t(
                  'app.kuaiplm.rdProjects.detail.deliverable.completeMachineCodePlaceholder',
                )}
              />
            </>
          );
        }
        if (
          dtype === 'drawing_silkscreen' ||
          dtype === 'drawing_assembly' ||
          dtype === 'drawing_packaging' ||
          dtype === 'drawing_pcb_assembly'
        ) {
          return (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              title={t('app.kuaiplm.rdProjects.detail.deliverable.projectDrawingHint')}
            />
          );
        }
        if (dtype === 'customer_spec' || dtype === 'customer_approval') {
          return (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              title={t('app.kuaiplm.rdProjects.detail.deliverable.customerDocHint')}
            />
          );
        }
        if (isStructureDrawingType(dtype)) {
          return (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              title={t('app.kuaiplm.rdProjects.detail.deliverable.structureDrawingHint')}
            />
          );
        }
        if (dtype === 'mold_repair') {
          return (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              title={t('app.kuaiplm.rdProjects.detail.deliverable.moldRepairHint')}
            />
          );
        }
        if (isStructureCatalogType(dtype) && dtype !== 'mold_repair') {
          return (
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
              title={t('app.kuaiplm.rdProjects.detail.deliverable.structureCatalogHint')}
            />
          );
        }
        if (showStandaloneProjectCode && !hasProject && dtype && !isSoftwareSpecType(dtype)) {
          return (
            <ProFormText
              name="project_code"
              label={t('app.kuaiplm.rdDeliverables.form.projectCode')}
              placeholder={t('app.kuaiplm.rdDeliverables.form.projectCodeOptionalPlaceholder')}
              extra={t('app.kuaiplm.rdDeliverables.form.projectCodeOptionalHint')}
            />
          );
        }
        return null;
      }}
    </ProFormDependency>
  );
};
