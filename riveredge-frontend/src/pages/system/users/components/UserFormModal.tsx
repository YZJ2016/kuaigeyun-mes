/**
 * 用户新建/编辑弹窗
 */

import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { ProFormInstance, ProFormSelect, ProFormSwitch, ProFormText } from '@ant-design/pro-components';
import { App, Form, theme } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { FormModalTemplate, MODAL_CONFIG } from '../../../../components/layout-templates';
import { MODAL_NESTED_ABOVE_PARENT_OFFSET } from '../../../../components/layout-templates/constants';
import {
  getUserByUuid,
  getUserDataScopeBindings,
  createUser,
  replaceUserDataScopeBindings,
  updateUser,
  checkUserFullNameCollision,
  CreateUserData,
  UpdateUserData,
  type User,
} from '../../../../services/user';
import type { Department, DepartmentTreeItem } from '../../../../services/department';
import type { Position } from '../../../../services/position';
import type { Role } from '../../../../services/role';
import {
  getUserFormCoreReferenceOptions,
  getUserFormPartnerOptions,
  roleUuidsNeedPartnerDimension,
  type UserFormSelectOption,
  type UserFormRoleMeta,
} from '../userFormReferenceOptions';
import { validateTenantUsernameInput } from '../../../../utils/reservedUsername';
import { hasPermission } from '../../../../utils/permission';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import { DepartmentFormModal } from '../../departments/components/DepartmentFormModal';
import { PositionFormModal } from '../../positions/components/PositionFormModal';
import { RoleFormModal } from '../../roles/components/RoleFormModal';

/** 账户用户名：2-50 字符，支持中文、字母、数字、下划线、连字符 */
const USERNAME_PATTERN = /^[\u4e00-\u9fa5a-zA-Z0-9_-]+$/;

const PERM_DEPARTMENT_CREATE = 'system:department:create';
const PERM_POSITION_CREATE = 'system:position:create';
const PERM_ROLE_CREATE = 'system:role:create';

function buildQuickCreatePopupRender(
  label: string,
  onClick: () => void,
  token: ReturnType<typeof theme.useToken>['token'],
) {
  return (menu: React.ReactElement) => {
    const footerStyle: React.CSSProperties = {
      borderTop: `1px solid ${token.colorBorder}`,
      padding: '4px 0',
      background: token.colorBgContainer,
    };
    const itemStyle: React.CSSProperties = {
      padding: '6px 12px',
      cursor: 'pointer',
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      fontSize: 12,
      color: token.colorTextSecondary,
    };
    return (
      <>
        {menu}
        <div style={footerStyle}>
          <div
            role="button"
            tabIndex={0}
            style={itemStyle}
            onClick={onClick}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onClick();
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = token.colorFillTertiary;
              e.currentTarget.style.color = token.colorText;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
              e.currentTarget.style.color = token.colorTextSecondary;
            }}
          >
            <PlusOutlined />
            {label}
          </div>
        </div>
      </>
    );
  };
}

export interface UserFormModalProps {
  open: boolean;
  onClose: () => void;
  /** 编辑时传入用户 uuid，为 null 时为新建 */
  editUuid: string | null;
  /** 保存成功；快速新建场景可据此回填选中 */
  onSuccess: (user: User) => void;
  /** 嵌套在外层 Modal 时抬高层级 */
  zIndex?: number;
}

function parseErrorMessage(error: any, t: (key: string) => string): string {
  const message = error.message || error.detail || t('common.deleteFailed');

  if (message.includes('用户名') && message.includes('已存在')) {
    return t('field.user.errorUsernameExists');
  }
  if (message.includes('部门不存在') || message.includes('部门')) {
    return t('field.user.errorDepartmentInvalid');
  }
  if (message.includes('职位不存在') || message.includes('职位')) {
    return t('field.user.errorPositionInvalid');
  }
  if (message.includes('角色') && (message.includes('不存在') || message.includes('无效'))) {
    return t('field.user.errorRoleInvalid');
  }
  if (message.includes('手机号') || message.includes('phone')) {
    return t('field.user.errorPhoneInvalid');
  }
  if (message.includes('邮箱') || message.includes('email')) {
    return t('field.user.errorEmailInvalid');
  }
  if (message.includes('权限') || message.includes('permission')) {
    return t('field.user.errorNoPermission');
  }
  return message;
}

function applyFormValues(formRef: React.RefObject<ProFormInstance | undefined>, values: Record<string, unknown>) {
  requestAnimationFrame(() => {
    formRef.current?.setFieldsValue(values);
  });
}

function normalizeRoleUuids(raw: unknown): string[] {
  return (Array.isArray(raw) ? raw : raw != null ? [raw] : [])
    .map((v: any) => (typeof v === 'string' ? v : v?.value || v?.uuid || ''))
    .filter(Boolean);
}

/** 在 ProForm 内同步 role_uuids → draft（不可用 fieldProps.onChange，会挡写回） */
const RoleUuidsDraftSync: React.FC<{ onDraftChange: (uuids: string[]) => void }> = ({ onDraftChange }) => {
  const roleUuids = Form.useWatch('role_uuids');
  useEffect(() => {
    onDraftChange(normalizeRoleUuids(roleUuids));
  }, [roleUuids, onDraftChange]);
  return null;
};

export const UserFormModal: React.FC<UserFormModalProps> = ({
  open,
  onClose,
  editUuid,
  onSuccess,
  zIndex,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const { token } = theme.useToken();
  const currentUser = useCurrentUser();
  const formRef = useRef<ProFormInstance>();
  const onCloseRef = useRef(onClose);
  const tRef = useRef(t);
  const messageApiRef = useRef(messageApi);
  const [formLoading, setFormLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [formInitialValues, setFormInitialValues] = useState<Record<string, any> | undefined>(undefined);
  const [roleUuidsDraft, setRoleUuidsDraft] = useState<string[]>([]);
  const [departmentOptions, setDepartmentOptions] = useState<UserFormSelectOption[]>([]);
  const [positionOptions, setPositionOptions] = useState<UserFormSelectOption[]>([]);
  const [roleOptions, setRoleOptions] = useState<UserFormSelectOption[]>([]);
  const [roleMetaByUuid, setRoleMetaByUuid] = useState<Record<string, UserFormRoleMeta>>({});
  const [deptTreeItems, setDeptTreeItems] = useState<DepartmentTreeItem[]>([]);
  const [customerOptions, setCustomerOptions] = useState<UserFormSelectOption[]>([]);
  const [supplierOptions, setSupplierOptions] = useState<UserFormSelectOption[]>([]);
  const [manufacturerOptions, setManufacturerOptions] = useState<UserFormSelectOption[]>([]);
  const [departmentCreateOpen, setDepartmentCreateOpen] = useState(false);
  const [positionCreateOpen, setPositionCreateOpen] = useState(false);
  const [roleCreateOpen, setRoleCreateOpen] = useState(false);

  const isEdit = Boolean(editUuid);
  const onRoleDraftChange = useMemo(() => (uuids: string[]) => setRoleUuidsDraft(uuids), []);
  const canCreateDepartment = hasPermission(currentUser, PERM_DEPARTMENT_CREATE);
  const canCreatePosition = hasPermission(currentUser, PERM_POSITION_CREATE);
  const canCreateRole = hasPermission(currentUser, PERM_ROLE_CREATE);
  const nestedModalZIndex = (zIndex ?? 1000) + MODAL_NESTED_ABOVE_PARENT_OFFSET;

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    tRef.current = t;
  }, [t]);

  useEffect(() => {
    messageApiRef.current = messageApi;
  }, [messageApi]);

  const selectedExternalPartnerTypes = useMemo(() => {
    const types = new Set<string>();
    roleUuidsDraft.forEach((uuid) => {
      const role = roleMetaByUuid[uuid];
      if (role?.role_type === 'external' && role.external_partner_type) {
        types.add(role.external_partner_type);
      }
    });
    return types;
  }, [roleUuidsDraft, roleMetaByUuid]);

  const applyCoreReferenceOptions = (core: Awaited<ReturnType<typeof getUserFormCoreReferenceOptions>>) => {
    setDepartmentOptions(core.departmentOptions);
    setPositionOptions(core.positionOptions);
    setRoleOptions(core.roleOptions);
    setRoleMetaByUuid(core.roleMetaByUuid);
    setDeptTreeItems(core.deptTreeItems);
  };

  const refreshCoreReferenceOptions = useCallback(async () => {
    const core = await getUserFormCoreReferenceOptions(tRef.current);
    applyCoreReferenceOptions(core);
    return core;
  }, []);

  useEffect(() => {
    if (!open) {
      setFormInitialValues(undefined);
      setRoleUuidsDraft([]);
      setDetailLoading(false);
      setCustomerOptions([]);
      setSupplierOptions([]);
      setManufacturerOptions([]);
      setDepartmentCreateOpen(false);
      setPositionCreateOpen(false);
      setRoleCreateOpen(false);
      return;
    }

    let cancelled = false;

    void (async () => {
      try {
        formRef.current?.resetFields();

        if (!editUuid) {
          const core = await getUserFormCoreReferenceOptions(tRef.current);
          if (cancelled) return;
          applyCoreReferenceOptions(core);
          const defaults = {
            is_active: true,
            is_tenant_admin: false,
            supplier_scope_codes: [],
            customer_scope_codes: [],
            manufacturer_scope_codes: [],
          };
          setRoleUuidsDraft([]);
          setFormInitialValues(defaults);
          applyFormValues(formRef, defaults);
          return;
        }

        setDetailLoading(true);
        const [detail, core] = await Promise.all([
          getUserByUuid(editUuid),
          getUserFormCoreReferenceOptions(tRef.current),
        ]);
        if (cancelled) return;

        applyCoreReferenceOptions(core);
        const editRoleUuids = detail.roles?.map((r) => r.uuid) || [];
        const baseValues = {
          username: detail.username,
          email: detail.email,
          full_name: detail.full_name,
          phone: detail.phone,
          department_uuid: detail.department_uuid,
          position_uuid: detail.position_uuid,
          role_uuids: editRoleUuids,
          is_active: detail.is_active,
          is_tenant_admin: detail.is_tenant_admin,
          supplier_scope_codes: [] as string[],
          customer_scope_codes: [] as string[],
          manufacturer_scope_codes: [] as string[],
        };
        setRoleUuidsDraft(editRoleUuids);
        setFormInitialValues(baseValues);
        applyFormValues(formRef, baseValues);
        setDetailLoading(false);

        const userUuid = detail.uuid || editUuid;
        const needsSupplier = roleUuidsNeedPartnerDimension(editRoleUuids, core.roleMetaByUuid, 'supplier');
        const needsCustomer = roleUuidsNeedPartnerDimension(editRoleUuids, core.roleMetaByUuid, 'customer');
        const needsManufacturer = roleUuidsNeedPartnerDimension(editRoleUuids, core.roleMetaByUuid, 'manufacturer');
        if (!needsSupplier && !needsCustomer && !needsManufacturer) return;

        const [
          supplierBindings,
          customerBindings,
          manufacturerBindings,
          supplierOpts,
          customerOpts,
          manufacturerOpts,
        ] = await Promise.all([
          needsSupplier ? getUserDataScopeBindings(userUuid, 'supplier') : Promise.resolve([]),
          needsCustomer ? getUserDataScopeBindings(userUuid, 'customer') : Promise.resolve([]),
          needsManufacturer ? getUserDataScopeBindings(userUuid, 'manufacturer') : Promise.resolve([]),
          needsSupplier ? getUserFormPartnerOptions('supplier') : Promise.resolve([]),
          needsCustomer ? getUserFormPartnerOptions('customer') : Promise.resolve([]),
          needsManufacturer ? getUserFormPartnerOptions('manufacturer') : Promise.resolve([]),
        ]);
        if (cancelled) return;

        if (needsSupplier) {
          setSupplierOptions(supplierOpts);
        }
        if (needsCustomer) {
          setCustomerOptions(customerOpts);
        }
        if (needsManufacturer) {
          setManufacturerOptions(manufacturerOpts);
        }
        const scopePatch = {
          supplier_scope_codes: supplierBindings.map((x) => x.scope_code).filter(Boolean),
          customer_scope_codes: customerBindings.map((x) => x.scope_code).filter(Boolean),
          manufacturer_scope_codes: manufacturerBindings.map((x) => x.scope_code).filter(Boolean),
        };
        setFormInitialValues((prev) => ({ ...(prev || {}), ...scopePatch }));
        applyFormValues(formRef, scopePatch);
      } catch (error: any) {
        if (cancelled) return;
        messageApiRef.current.error(error.message || tRef.current('field.user.fetchDetailFailed'));
        onCloseRef.current();
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [open, editUuid, t]);

  useEffect(() => {
    if (!open) return;
    if (selectedExternalPartnerTypes.has('supplier') && supplierOptions.length === 0) {
      void getUserFormPartnerOptions('supplier')
        .then(setSupplierOptions)
        .catch(() => {});
    }
    if (selectedExternalPartnerTypes.has('customer') && customerOptions.length === 0) {
      void getUserFormPartnerOptions('customer')
        .then(setCustomerOptions)
        .catch(() => {});
    }
    if (selectedExternalPartnerTypes.has('manufacturer') && manufacturerOptions.length === 0) {
      void getUserFormPartnerOptions('manufacturer')
        .then(setManufacturerOptions)
        .catch(() => {});
    }
  }, [open, selectedExternalPartnerTypes, supplierOptions.length, customerOptions.length, manufacturerOptions.length]);

  const handleClose = () => {
    onClose();
    setFormInitialValues(undefined);
    setRoleUuidsDraft([]);
  };

  const handleDepartmentCreated = async (created?: Department) => {
    setDepartmentCreateOpen(false);
    await refreshCoreReferenceOptions();
    if (created?.uuid) {
      formRef.current?.setFieldsValue({ department_uuid: created.uuid });
    }
  };

  const handlePositionCreated = async (created?: Position) => {
    setPositionCreateOpen(false);
    await refreshCoreReferenceOptions();
    if (created?.uuid) {
      formRef.current?.setFieldsValue({ position_uuid: created.uuid });
    }
  };

  const handleRoleCreated = async (created?: Role) => {
    setRoleCreateOpen(false);
    await refreshCoreReferenceOptions();
    if (created?.uuid) {
      const prev = normalizeRoleUuids(formRef.current?.getFieldValue('role_uuids'));
      const next = prev.includes(created.uuid) ? prev : [...prev, created.uuid];
      formRef.current?.setFieldsValue({ role_uuids: next });
      setRoleUuidsDraft(next);
    }
  };

  const departmentPopupRender = useMemo(
    () =>
      canCreateDepartment
        ? buildQuickCreatePopupRender(
            t('field.user.quickCreateDepartment'),
            () => setDepartmentCreateOpen(true),
            token,
          )
        : undefined,
    [canCreateDepartment, t, token],
  );

  const positionPopupRender = useMemo(
    () =>
      canCreatePosition
        ? buildQuickCreatePopupRender(
            t('field.user.quickCreatePosition'),
            () => setPositionCreateOpen(true),
            token,
          )
        : undefined,
    [canCreatePosition, t, token],
  );

  const rolePopupRender = useMemo(
    () =>
      canCreateRole
        ? buildQuickCreatePopupRender(
            t('field.user.quickCreateRole'),
            () => setRoleCreateOpen(true),
            token,
          )
        : undefined,
    [canCreateRole, t, token],
  );

  const handleSubmit = async (values: any) => {
    try {
      setFormLoading(true);

      const submitData = { ...values };
      delete submitData.confirmPassword;
      const supplierCodes = (Array.isArray(submitData.supplier_scope_codes) ? submitData.supplier_scope_codes : [])
        .map((v: any) => String(v || '').trim())
        .filter(Boolean);
      const customerCodes = (Array.isArray(submitData.customer_scope_codes) ? submitData.customer_scope_codes : [])
        .map((v: any) => String(v || '').trim())
        .filter(Boolean);
      const manufacturerCodes = (Array.isArray(submitData.manufacturer_scope_codes)
        ? submitData.manufacturer_scope_codes
        : [])
        .map((v: any) => String(v || '').trim())
        .filter(Boolean);
      delete submitData.supplier_scope_codes;
      delete submitData.customer_scope_codes;
      delete submitData.manufacturer_scope_codes;
      if (!submitData.password) {
        delete submitData.password;
      }

      // 编辑时显式传 null：Select 清空后表单值为 undefined，JSON 会省略字段导致后端不更新
      if (isEdit) {
        submitData.department_uuid = submitData.department_uuid || null;
        submitData.position_uuid = submitData.position_uuid || null;
      }

      const latestRoleValue = formRef.current?.getFieldValue?.('role_uuids');
      // 优先表单当前值（ProForm 写回），draft 仅作外部角色区联动兜底
      const rawRoleValue =
        latestRoleValue ??
        submitData.role_uuids ??
        roleUuidsDraft ??
        (isEdit ? formInitialValues?.role_uuids : undefined);
      const normalizedRoleUuids = normalizeRoleUuids(rawRoleValue);
      if (isEdit || normalizedRoleUuids.length > 0 || rawRoleValue !== undefined) {
        submitData.role_uuids = normalizedRoleUuids;
      }

      let savedUser: User;
      if (isEdit && editUuid) {
        savedUser = await updateUser(editUuid, submitData as UpdateUserData);
        await Promise.all([
          replaceUserDataScopeBindings(savedUser.uuid, {
            dimension: 'supplier',
            items: supplierCodes.map((code: string) => ({ dimension: 'supplier', scope_code: code })),
          }),
          replaceUserDataScopeBindings(savedUser.uuid, {
            dimension: 'customer',
            items: customerCodes.map((code: string) => ({ dimension: 'customer', scope_code: code })),
          }),
          replaceUserDataScopeBindings(savedUser.uuid, {
            dimension: 'manufacturer',
            items: manufacturerCodes.map((code: string) => ({ dimension: 'manufacturer', scope_code: code })),
          }),
        ]);
        messageApi.success(t('common.updateSuccess'));
      } else {
        if (!submitData.password) {
          messageApi.error(t('field.user.passwordRequired'));
          return;
        }
        savedUser = await createUser(submitData as CreateUserData);
        await Promise.all([
          replaceUserDataScopeBindings(savedUser.uuid, {
            dimension: 'supplier',
            items: supplierCodes.map((code: string) => ({ dimension: 'supplier', scope_code: code })),
          }),
          replaceUserDataScopeBindings(savedUser.uuid, {
            dimension: 'customer',
            items: customerCodes.map((code: string) => ({ dimension: 'customer', scope_code: code })),
          }),
          replaceUserDataScopeBindings(savedUser.uuid, {
            dimension: 'manufacturer',
            items: manufacturerCodes.map((code: string) => ({ dimension: 'manufacturer', scope_code: code })),
          }),
        ]);
        messageApi.success(t('common.createSuccess'));
      }

      handleClose();
      onSuccess(savedUser);
    } catch (error: any) {
      messageApi.error(parseErrorMessage(error, t));
    } finally {
      setFormLoading(false);
    }
  };

  return (
    <>
      <FormModalTemplate
        title={isEdit ? t('field.user.editTitle') : t('field.user.createTitle')}
        open={open}
        onClose={handleClose}
        onFinish={handleSubmit}
        isEdit={isEdit}
        initialValues={formInitialValues}
        loading={formLoading || detailLoading}
        formRef={formRef}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        grid={true}
        zIndex={zIndex}
      >
        <RoleUuidsDraftSync onDraftChange={onRoleDraftChange} />
      <ProFormText
        name="username"
        label={t('field.user.username')}
        rules={[
          { required: true, message: t('field.user.usernameRequired') },
          { min: 2, message: t('field.user.usernameMin') },
          { max: 50, message: t('field.user.usernameMax') },
          { pattern: USERNAME_PATTERN, message: t('field.user.usernamePattern') },
          {
            validator: async (_, value) => {
              const issue = validateTenantUsernameInput(String(value ?? ''));
              if (issue === 'platformSuperadminReserved') {
                throw new Error(t('field.user.errorUsernamePlatformReserved'));
              }
              if (issue === 'reserved') {
                throw new Error(t('field.user.errorUsernameReserved'));
              }
            },
          },
        ]}
        placeholder={t('field.user.usernamePlaceholder')}
        fieldProps={{
          autoComplete: 'off',
        }}
        colProps={{ span: 12 }}
      />
      <ProFormText
        name="full_name"
        label={t('field.user.fullName')}
        rules={[
          { max: 100, message: t('field.user.fullNameMax') },
          {
            warningOnly: true,
            validator: async (_, value) => {
              const name = String(value ?? '').trim();
              if (!name) return;
              const result = await checkUserFullNameCollision(name, editUuid);
              if (!result.collision) return;
              const accounts = result.users.map((user) => user.username).join('、');
              throw new Error(
                t('field.user.fullNameDuplicateWarning', {
                  count: result.users.length,
                  accounts,
                }),
              );
            },
          },
        ]}
        placeholder={t('field.user.fullNamePlaceholder')}
        colProps={{ span: 12 }}
      />
      <ProFormText
        name="phone"
        label={t('field.user.phone')}
        rules={[
          { required: true, message: t('field.user.phoneRequired') },
          { pattern: /^1[3-9]\d{9}$/, message: t('field.user.phonePattern') },
        ]}
        placeholder={t('field.user.phonePlaceholder')}
        colProps={{ span: 12 }}
      />
      <ProFormText
        name="email"
        label={t('field.user.email')}
        rules={[
          { type: 'email', message: t('field.user.emailInvalid') },
        ]}
        placeholder={t('field.user.emailPlaceholder')}
        fieldProps={{ autoComplete: 'email' }}
        colProps={{ span: 12 }}
      />
      <ProFormText
        name="password"
        label={t('field.user.password')}
        rules={isEdit ? [] : [
          { required: true, message: t('field.user.passwordRequiredPlaceholder') },
          { min: 8, message: t('field.user.passwordMin') },
          { max: 128, message: t('field.user.passwordMax') },
        ]}
        placeholder={isEdit ? t('field.user.passwordPlaceholderEdit') : t('field.user.passwordPlaceholder')}
        fieldProps={{
          type: 'password',
          autoComplete: 'new-password',
        }}
        colProps={{ span: 12 }}
      />
      <ProFormText
        name="confirmPassword"
        label={t('field.user.confirmPassword')}
        rules={isEdit ? [] : [
          { required: true, message: t('field.user.confirmPasswordRequired') },
          { min: 8, message: t('field.user.passwordMin') },
          { max: 128, message: t('field.user.passwordMax') },
          ({ getFieldValue }) => ({
            validator(_, value) {
              if (!value || getFieldValue('password') === value) {
                return Promise.resolve();
              }
              return Promise.reject(new Error(t('field.user.passwordMismatch')));
            },
          }),
        ]}
        placeholder={isEdit ? t('field.user.passwordPlaceholderEdit') : t('field.user.confirmPasswordPlaceholder')}
        fieldProps={{
          type: 'password',
          autoComplete: 'new-password',
        }}
        colProps={{ span: 12 }}
      />
      <ProFormSelect
        name="department_uuid"
        label={t('field.user.department')}
        placeholder={t('field.user.departmentPlaceholder')}
        allowClear
        options={departmentOptions}
        fieldProps={{
          showSearch: true,
          popupRender: departmentPopupRender,
        }}
        colProps={{ span: 8 }}
      />
      <ProFormSelect
        name="position_uuid"
        label={t('field.user.position')}
        placeholder={t('field.user.positionPlaceholder')}
        allowClear
        options={positionOptions}
        fieldProps={{
          showSearch: true,
          popupRender: positionPopupRender,
        }}
        colProps={{ span: 8 }}
      />
      <ProFormSelect
        name="role_uuids"
        label={t('field.user.roles')}
        placeholder={t('field.user.rolesPlaceholder')}
        options={roleOptions}
        fieldProps={{
          mode: 'multiple',
          showSearch: true,
          popupRender: rolePopupRender,
          // 勿在 fieldProps 覆盖 onChange，否则 ProForm 不写回 role_uuids，二次保存角色不变
        }}
        colProps={{ span: 8 }}
      />
      {selectedExternalPartnerTypes.has('supplier') && (
        <ProFormSelect
          name="supplier_scope_codes"
          label="外部角色-供应商绑定"
          placeholder="请选择该账号可访问的供应商（按编码）"
          options={supplierOptions}
          fieldProps={{
            mode: 'multiple',
            showSearch: true,
            optionFilterProp: 'label',
          }}
          extra="根据所选外部角色自动显示；用于供应商数据隔离"
          colProps={{ span: 24 }}
        />
      )}
      {selectedExternalPartnerTypes.has('customer') && (
        <ProFormSelect
          name="customer_scope_codes"
          label="外部角色-客户绑定"
          placeholder="请选择该账号可访问的客户（按编码）"
          options={customerOptions}
          fieldProps={{
            mode: 'multiple',
            showSearch: true,
            optionFilterProp: 'label',
          }}
          extra="根据所选外部角色自动显示；用于客户数据隔离"
          colProps={{ span: 24 }}
        />
      )}
      {selectedExternalPartnerTypes.has('manufacturer') && (
        <ProFormSelect
          name="manufacturer_scope_codes"
          label="外部角色-设备制造商绑定"
          placeholder="请选择该账号可访问的设备制造商（按编码）"
          options={manufacturerOptions}
          fieldProps={{
            mode: 'multiple',
            showSearch: true,
            optionFilterProp: 'label',
          }}
          extra="根据所选外部角色自动显示；用于设备验收单数据隔离"
          colProps={{ span: 24 }}
        />
      )}
      <ProFormSwitch
        name="is_active"
        label={t('common.enabled')}
        colProps={{ span: 12 }}
      />
      <ProFormSwitch
        name="is_tenant_admin"
        label={t('field.user.isTenantAdminLabel')}
        colProps={{ span: 12 }}
      />
      </FormModalTemplate>
      <DepartmentFormModal
        open={departmentCreateOpen}
        editUuid={null}
        onClose={() => setDepartmentCreateOpen(false)}
        onSuccess={handleDepartmentCreated}
        deptTreeItems={deptTreeItems}
        zIndex={nestedModalZIndex}
      />
      <PositionFormModal
        open={positionCreateOpen}
        editUuid={null}
        onClose={() => setPositionCreateOpen(false)}
        onSuccess={handlePositionCreated}
        zIndex={nestedModalZIndex}
      />
      <RoleFormModal
        open={roleCreateOpen}
        editUuid={null}
        onClose={() => setRoleCreateOpen(false)}
        onSuccess={handleRoleCreated}
        zIndex={nestedModalZIndex}
      />
    </>
  );
};
