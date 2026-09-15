/**
 * 新建群聊：名称 + 成员（≥1 名他人）+ 可选绑定模块
 */
import React, { useMemo, useState } from 'react';
import { Form, Input, Modal, Select, message as antMessage } from 'antd';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { createGroupImConversation } from '../../services/im';
import { getInstalledApplicationList } from '../../services/application';
import { searchUserDisplay, type UserDisplayItem } from '../../services/user';
import { useCurrentUser } from '../../hooks/useCurrentUser';

export type UniImCreateGroupModalProps = {
  open: boolean;
  onClose: () => void;
  onCreated: (conversationUuid: string) => void;
};

export default function UniImCreateGroupModal({
  open,
  onClose,
  onCreated,
}: UniImCreateGroupModalProps) {
  const { t } = useTranslation();
  const currentUser = useCurrentUser();
  const [form] = Form.useForm<{
    title: string;
    member_user_ids: number[];
    module_codes: string[];
  }>();
  const [saving, setSaving] = useState(false);
  const [memberKeyword, setMemberKeyword] = useState('');

  const { data: apps } = useQuery({
    queryKey: ['installedApplications', 'im-group'],
    queryFn: () => getInstalledApplicationList({ is_active: true }),
    enabled: open,
    staleTime: 60_000,
  });

  const { data: usersData, isFetching: usersLoading } = useQuery({
    queryKey: ['imGroupMemberSearch', memberKeyword],
    queryFn: () =>
      searchUserDisplay({
        keyword: memberKeyword.trim() || undefined,
        page: 1,
        page_size: 50,
      }),
    enabled: open,
    staleTime: 30_000,
  });

  const moduleOptions = useMemo(() => {
    return (apps ?? [])
      .filter((app) => !!app.code && app.code !== 'kuaiai')
      .map((app) => ({
        value: app.code,
        label: app.name || app.code,
      }));
  }, [apps]);

  const memberOptions = useMemo(() => {
    const selfId = currentUser?.id;
    return ((usersData?.items ?? []) as UserDisplayItem[])
      .filter((u) => u.id !== selfId)
      .map((u) => ({
        value: u.id,
        label: u.label || u.full_name || u.username,
      }));
  }, [currentUser?.id, usersData?.items]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      const memberIds = values.member_user_ids || [];
      if (memberIds.length < 1) {
        antMessage.warning(t('components.uniIm.groupNeedMembers'));
        return;
      }
      setSaving(true);
      const conv = await createGroupImConversation({
        title: values.title.trim(),
        member_user_ids: memberIds,
        module_codes: values.module_codes || [],
      });
      antMessage.success(t('components.uniIm.groupCreated'));
      form.resetFields();
      onCreated(conv.uuid);
      onClose();
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'errorFields' in e) {
        return;
      }
      const err = e as { message?: string };
      antMessage.error(err?.message || t('components.uniIm.groupCreateFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={t('components.uniIm.createGroup')}
      open={open}
      onCancel={() => {
        if (saving) {
          return;
        }
        form.resetFields();
        onClose();
      }}
      onOk={() => void handleOk()}
      confirmLoading={saving}
      okText={t('components.uniIm.createGroup')}
      destroyOnHidden
      zIndex={1100}
      mask={{ closable: !saving }}
    >
      <Form form={form} layout="vertical" initialValues={{ member_user_ids: [], module_codes: [] }}>
        <Form.Item
          name="title"
          label={t('components.uniIm.groupName')}
          rules={[{ required: true, message: t('components.uniIm.groupNameRequired') }]}
        >
          <Input maxLength={200} placeholder={t('components.uniIm.groupNamePlaceholder')} />
        </Form.Item>
        <Form.Item
          name="member_user_ids"
          label={t('components.uniIm.groupMembers')}
          rules={[{ required: true, type: 'array', min: 1, message: t('components.uniIm.groupNeedMembers') }]}
          extra={t('components.uniIm.groupMembersHint')}
        >
          <Select
            mode="multiple"
            showSearch
            filterOption={false}
            loading={usersLoading}
            options={memberOptions}
            placeholder={t('components.uniIm.groupMembersPlaceholder')}
            onSearch={setMemberKeyword}
          />
        </Form.Item>
        <Form.Item
          name="module_codes"
          label={t('components.uniIm.groupModules')}
          extra={t('components.uniIm.groupModulesHint')}
        >
          <Select
            mode="multiple"
            allowClear
            options={moduleOptions}
            placeholder={t('components.uniIm.groupModulesPlaceholder')}
            optionFilterProp="label"
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
