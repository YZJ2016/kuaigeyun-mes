import React from 'react';
import { Form, Input, Select } from 'antd';
import type { ProFormInstance } from '@ant-design/pro-components';
import { UniUserSelect } from '../../../components/uni-user-select';
import { resolveUserDisplay, type User } from '../../../services/user';

export interface EquipmentPersonSelectProps {
  uuidFieldName: string;
  idFieldName: string;
  nameFieldName: string;
  /** 多人时同步写入的 ID 列表字段（如 inspector_ids） */
  idsFieldName?: string;
  label: string;
  placeholder?: string;
  required?: boolean;
  formRef: React.RefObject<ProFormInstance | undefined>;
  mode?: 'multiple';
  /** 选人后回调（已写入 id/name）；用于联动部门等业务字段 */
  onUserChange?: (user: User | User[] | undefined) => void;
}

function pickUser(user: User | User[] | undefined): User | undefined {
  if (!user) return undefined;
  return Array.isArray(user) ? user[0] : user;
}

function pickUsers(user: User | User[] | undefined): User[] {
  if (!user) return [];
  return Array.isArray(user) ? user : [user];
}

function formatPersonNames(users: User[]): string | undefined {
  const names = users
    .map((u) => (u.full_name || u.username || '').trim())
    .filter(Boolean);
  return names.length ? names.join('、') : undefined;
}

export function syncEquipmentPersonFields(
  formRef: React.RefObject<ProFormInstance | undefined>,
  idFieldName: string,
  nameFieldName: string,
  user: User | User[] | undefined,
  options?: { idsFieldName?: string; multiple?: boolean },
) {
  if (options?.multiple && options.idsFieldName) {
    const users = pickUsers(user);
    const ids = users
      .map((u) => u.id)
      .filter((id): id is number => typeof id === 'number' && id > 0);
    formRef.current?.setFieldsValue({
      [options.idsFieldName]: ids,
      [idFieldName]: ids[0],
      [nameFieldName]: formatPersonNames(users),
    });
    return;
  }
  const picked = pickUser(user);
  formRef.current?.setFieldsValue({
    [idFieldName]: picked?.id,
    [nameFieldName]: picked ? picked.full_name || picked.username : undefined,
    ...(options?.idsFieldName
      ? { [options.idsFieldName]: picked?.id != null ? [picked.id] : [] }
      : {}),
  });
}

export async function resolveUserUuidById(userId?: number | null): Promise<string | undefined> {
  if (!userId) return undefined;
  try {
    const items = await resolveUserDisplay({ user_ids: [userId] });
    return items[0]?.uuid;
  } catch {
    return undefined;
  }
}

export async function resolveUserUuidsByIds(
  userIds?: Array<number | null | undefined> | null,
): Promise<string[]> {
  const ids = (userIds ?? [])
    .map((id) => Number(id))
    .filter((id) => Number.isInteger(id) && id > 0);
  if (!ids.length) return [];
  try {
    const items = await resolveUserDisplay({ user_ids: ids });
    const uuidById = new Map<number, string>();
    for (const item of items) {
      if (item?.id != null && item.uuid) {
        uuidById.set(Number(item.id), String(item.uuid));
      }
    }
    return ids.map((id) => uuidById.get(id)).filter((u): u is string => Boolean(u));
  } catch {
    return [];
  }
}

export const EquipmentPersonSelect: React.FC<EquipmentPersonSelectProps> = ({
  uuidFieldName,
  idFieldName,
  nameFieldName,
  idsFieldName,
  label,
  placeholder,
  required,
  formRef,
  mode,
  onUserChange,
}) => {
  const multiple = mode === 'multiple';
  return (
    <>
      <UniUserSelect
        name={uuidFieldName}
        label={label}
        placeholder={placeholder}
        required={required}
        pageSize={200}
        loadAllWhenNoKeyword
        mode={multiple ? 'multiple' : undefined}
        fieldProps={multiple ? { maxTagCount: 'responsive' } : undefined}
        onChange={(_uuid, user) => {
          syncEquipmentPersonFields(formRef, idFieldName, nameFieldName, user, {
            idsFieldName,
            multiple,
          });
          onUserChange?.(user);
        }}
      />
      <Form.Item name={idFieldName} hidden>
        <Input />
      </Form.Item>
      <Form.Item name={nameFieldName} hidden>
        <Input />
      </Form.Item>
      {idsFieldName ? (
        <Form.Item name={idsFieldName} hidden>
          <Select mode="multiple" />
        </Form.Item>
      ) : null}
    </>
  );
};
