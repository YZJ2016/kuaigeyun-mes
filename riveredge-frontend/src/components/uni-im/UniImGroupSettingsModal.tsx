/**
 * 群聊设置：改名、绑定模块、解散（公共群不可改成员 / 不可解散）
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Button, Form, Input, Modal, Select, Space, message as antMessage } from 'antd';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import {
  dissolveGroupImConversation,
  listImMembers,
  updateGroupImConversation,
  type ImConversation,
} from '../../services/im';
import {
  getInstalledApplicationList,
  installedApplicationsQueryKey,
} from '../../services/application';
import { getTenantId } from '../../utils/auth';
import { useCurrentUser } from '../../hooks/useCurrentUser';

export type UniImGroupSettingsModalProps = {
  open: boolean;
  conversation: ImConversation | null;
  onClose: () => void;
  onSaved: () => void;
  onDissolved?: () => void;
};

export default function UniImGroupSettingsModal({
  open,
  conversation,
  onClose,
  onSaved,
  onDissolved,
}: UniImGroupSettingsModalProps) {
  const { t } = useTranslation();
  const currentUser = useCurrentUser();
  const [form] = Form.useForm<{
    title: string;
    member_user_ids: number[];
    module_codes: string[];
  }>();
  const [saving, setSaving] = useState(false);
  const [dissolving, setDissolving] = useState(false);
  const isPublic = !!conversation?.is_public;
  const busy = saving || dissolving;

  const { data: apps } = useQuery({
    queryKey: installedApplicationsQueryKey(getTenantId()),
    queryFn: () => getInstalledApplicationList({ is_active: true }),
    enabled: open,
    staleTime: 60_000,
  });

  const { data: membersData } = useQuery({
    queryKey: ['imMembers', conversation?.uuid],
    queryFn: () => listImMembers(conversation!.uuid),
    enabled: open && !!conversation?.uuid,
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
    return (membersData?.items ?? []).map((m) => ({
      value: m.user_id,
      label: m.label || m.full_name || m.username,
    }));
  }, [membersData?.items]);

  const isOwner = useMemo(() => {
    if (!currentUser?.id) {
      return false;
    }
    const byRole = (membersData?.items ?? []).some(
      (m) => m.user_id === currentUser.id && (m.role || '') === 'owner',
    );
    // 与后端 dissolve 判定一致：role=owner 或会话创建人
    const byCreator = conversation?.created_by_id === currentUser.id;
    return byRole || byCreator;
  }, [conversation?.created_by_id, currentUser?.id, membersData?.items]);

  useEffect(() => {
    if (!open || !conversation) {
      return;
    }
    form.setFieldsValue({
      title: conversation.title || '',
      module_codes: conversation.module_codes || [],
      member_user_ids: (membersData?.items ?? [])
        .map((m) => m.user_id)
        .filter((id) => id !== currentUser?.id),
    });
  }, [conversation, currentUser?.id, form, membersData?.items, open]);

  const handleOk = async () => {
    if (!conversation) {
      return;
    }
    try {
      const values = await form.validateFields();
      setSaving(true);
      const payload: {
        title?: string;
        module_codes?: string[];
        member_user_ids?: number[];
      } = {
        title: values.title.trim(),
        module_codes: values.module_codes || [],
      };
      if (!isPublic) {
        payload.member_user_ids = [
          ...(currentUser?.id ? [currentUser.id] : []),
          ...(values.member_user_ids || []),
        ];
      }
      await updateGroupImConversation(conversation.uuid, payload);
      antMessage.success(t('components.uniIm.groupUpdated'));
      onSaved();
      onClose();
    } catch (e: unknown) {
      if (e && typeof e === 'object' && 'errorFields' in e) {
        return;
      }
      const err = e as { message?: string };
      antMessage.error(err?.message || t('components.uniIm.groupUpdateFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleDissolve = () => {
    if (!conversation || isPublic || !isOwner || busy) {
      return;
    }
    Modal.confirm({
      title: t('components.uniIm.dissolveGroupConfirmTitle'),
      content: t('components.uniIm.dissolveGroupConfirmContent'),
      okText: t('components.uniIm.dissolveGroup'),
      okButtonProps: { danger: true },
      cancelText: t('common.cancel'),
      zIndex: 1200,
      onOk: async () => {
        setDissolving(true);
        try {
          await dissolveGroupImConversation(conversation.uuid);
          antMessage.success(t('components.uniIm.groupDissolved'));
          onDissolved?.();
          onClose();
        } catch (e: unknown) {
          const err = e as { message?: string };
          antMessage.error(err?.message || t('components.uniIm.groupDissolveFailed'));
          throw e;
        } finally {
          setDissolving(false);
        }
      },
    });
  };

  return (
    <Modal
      title={t('components.uniIm.groupSettings')}
      open={open}
      onCancel={() => {
        if (!busy) {
          onClose();
        }
      }}
      onOk={() => void handleOk()}
      confirmLoading={saving}
      destroyOnHidden
      zIndex={1100}
      mask={{ closable: !busy }}
      footer={
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <span>
            {!isPublic && isOwner ? (
              <Button danger loading={dissolving} disabled={busy} onClick={handleDissolve}>
                {t('components.uniIm.dissolveGroup')}
              </Button>
            ) : null}
          </span>
          <Space>
            <Button disabled={busy} onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="primary" loading={saving} disabled={dissolving} onClick={() => void handleOk()}>
              {t('common.confirm')}
            </Button>
          </Space>
        </Space>
      }
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="title"
          label={t('components.uniIm.groupName')}
          rules={[{ required: true, message: t('components.uniIm.groupNameRequired') }]}
        >
          <Input maxLength={200} />
        </Form.Item>
        {!isPublic ? (
          <Form.Item
            name="member_user_ids"
            label={t('components.uniIm.groupMembers')}
            extra={t('components.uniIm.groupMembersHint')}
          >
            <Select mode="multiple" options={memberOptions} optionFilterProp="label" />
          </Form.Item>
        ) : (
          <div style={{ marginBottom: 16, color: 'rgba(0,0,0,0.45)', fontSize: 13 }}>
            {t('components.uniIm.publicGroupMembersHint')}
          </div>
        )}
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
