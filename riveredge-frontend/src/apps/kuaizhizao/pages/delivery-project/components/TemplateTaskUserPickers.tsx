/**
 * 流程模板预置子任务：行内负责人 / 成员选择（可选，不依赖 Form）
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Select } from 'antd';
import { useDebounceFn } from 'ahooks';
import { useTranslation } from 'react-i18next';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import {
  getUserList,
  resolveUserDisplay,
  searchUserDisplay,
  type User,
  type UserDisplayItem,
} from '../../../../../services/user';
import { canReadUserDirectory, formatUserDisplayLabel } from '../../../../../utils/userDisplay';
import type { DeliveryMember } from '../../../services/delivery-project';

function displayItemToUser(item: UserDisplayItem): User {
  return {
    id: item.id,
    uuid: item.uuid,
    username: item.username,
    full_name: item.full_name ?? undefined,
    is_active: true,
    is_tenant_admin: false,
    tenant_id: 0,
    created_at: '',
    updated_at: '',
    department_uuid: item.department_uuid ?? undefined,
  };
}

function mergeUsersById(prev: User[], next: User[]): User[] {
  const map = new Map<number, User>();
  for (const user of prev) {
    if (user.id) map.set(user.id, user);
  }
  for (const user of next) {
    if (user.id) map.set(user.id, user);
  }
  return [...map.values()];
}

async function fetchUsers(keyword?: string, currentUser?: User | null): Promise<User[]> {
  if (!currentUser) return [];
  const useFullList = canReadUserDirectory(currentUser);
  const commonFilters = { is_active: true };
  if (useFullList) {
    const response = await getUserList({
      page: 1,
      page_size: 200,
      keyword,
      ...commonFilters,
    });
    return response.items || [];
  }
  const response = await searchUserDisplay({
    page: 1,
    page_size: 200,
    keyword,
    ...commonFilters,
  });
  return (response.items || []).map(displayItemToUser);
}

interface TemplateTaskOwnerPickerProps {
  ownerId?: number | null;
  ownerName?: string | null;
  disabled?: boolean;
  onChange: (owner: { user_id: number; user_name: string } | null) => void;
}

export const TemplateTaskOwnerPicker: React.FC<TemplateTaskOwnerPickerProps> = ({
  ownerId,
  ownerName,
  disabled,
  onChange,
}) => {
  const { t } = useTranslation();
  const currentUser = useCurrentUser();
  const [users, setUsers] = useState<User[]>([]);

  useEffect(() => {
    if (!ownerId) return;
    let cancelled = false;
    void (async () => {
      try {
        const resolved = await resolveUserDisplay({ user_ids: [ownerId] });
        if (cancelled) return;
        setUsers((prev) => mergeUsersById(prev, resolved.map(displayItemToUser)));
      } catch {
        if (!cancelled && ownerName) {
          setUsers((prev) =>
            mergeUsersById(prev, [
              {
                id: ownerId,
                uuid: String(ownerId),
                username: ownerName,
                full_name: ownerName,
                is_active: true,
                is_tenant_admin: false,
                tenant_id: 0,
                created_at: '',
                updated_at: '',
              },
            ]),
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ownerId, ownerName]);

  const { run: searchUsers } = useDebounceFn(
    (keyword: string) => {
      void fetchUsers(keyword.trim() || undefined, currentUser).then(setUsers);
    },
    { wait: 300 },
  );

  useEffect(() => {
    void fetchUsers(undefined, currentUser).then(setUsers);
  }, [currentUser]);

  const options = useMemo(
    () =>
      users.map((user) => ({
        value: user.id,
        label: formatUserDisplayLabel(user),
      })),
    [users],
  );

  return (
    <Select
      allowClear
      showSearch
      filterOption={false}
      disabled={disabled}
      style={{ width: '100%' }}
      placeholder={t('app.kuaizhizao.deliveryProject.templateTaskOwnerOptional')}
      value={ownerId ?? undefined}
      options={options}
      onSearch={searchUsers}
      onChange={(value) => {
        if (!value) {
          onChange(null);
          return;
        }
        const picked = users.find((user) => user.id === value);
        if (!picked) return;
        onChange({
          user_id: picked.id,
          user_name: picked.full_name || picked.username || String(picked.id),
        });
      }}
    />
  );
};

interface TemplateTaskMembersPickerProps {
  members?: DeliveryMember[];
  ownerId?: number | null;
  disabled?: boolean;
  onChange: (members: DeliveryMember[]) => void;
}

export const TemplateTaskMembersPicker: React.FC<TemplateTaskMembersPickerProps> = ({
  members,
  ownerId,
  disabled,
  onChange,
}) => {
  const { t } = useTranslation();
  const currentUser = useCurrentUser();
  const [users, setUsers] = useState<User[]>([]);
  const memberIds = (members ?? []).map((m) => m.user_id);

  useEffect(() => {
    if (!memberIds.length) return;
    let cancelled = false;
    void (async () => {
      try {
        const resolved = await resolveUserDisplay({ user_ids: memberIds });
        if (cancelled) return;
        setUsers((prev) => mergeUsersById(prev, resolved.map(displayItemToUser)));
      } catch {
        if (!cancelled) {
          setUsers((prev) =>
            mergeUsersById(
              prev,
              (members ?? []).map((m) => ({
                id: m.user_id,
                uuid: String(m.user_id),
                username: m.user_name,
                full_name: m.user_name,
                is_active: true,
                is_tenant_admin: false,
                tenant_id: 0,
                created_at: '',
                updated_at: '',
              })),
            ),
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [memberIds.join(','), members]);

  const { run: searchUsers } = useDebounceFn(
    (keyword: string) => {
      void fetchUsers(keyword.trim() || undefined, currentUser).then(setUsers);
    },
    { wait: 300 },
  );

  useEffect(() => {
    void fetchUsers(undefined, currentUser).then(setUsers);
  }, [currentUser]);

  const options = useMemo(
    () =>
      users
        .filter((user) => user.id !== ownerId)
        .map((user) => ({
          value: user.id,
          label: formatUserDisplayLabel(user),
        })),
    [users, ownerId],
  );

  return (
    <Select
      allowClear
      mode="multiple"
      showSearch
      filterOption={false}
      disabled={disabled}
      style={{ width: '100%' }}
      placeholder={t('app.kuaizhizao.deliveryProject.templateTaskMembersOptional')}
      value={memberIds}
      options={options}
      onSearch={searchUsers}
      onChange={(values) => {
        const nextIds = (values as number[]).filter((id) => id !== ownerId);
        const nextMembers = nextIds.map((id) => {
          const picked = users.find((user) => user.id === id);
          const fallback = members?.find((m) => m.user_id === id);
          return {
            user_id: id,
            user_name: picked
              ? picked.full_name || picked.username || String(id)
              : fallback?.user_name || String(id),
          };
        });
        onChange(nextMembers);
      }}
    />
  );
};
