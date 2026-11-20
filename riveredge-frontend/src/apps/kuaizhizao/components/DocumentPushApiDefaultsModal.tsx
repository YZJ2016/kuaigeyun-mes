/**
 * 数据互通：编辑绑定 Save 接口的出站默认编码（组织/业务类型/库存事务）。
 * 写入 outbound_field_mappings.default_value + request_body，推送时优先用这些默认值。
 */
import React, { useEffect, useState } from 'react';
import { App, Form, Input, Modal, Spin, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  getAPIByUuid,
  updateAPI,
  type API,
} from '../../../services/apiManagement';
import { formatApiErrorDetail } from '../../../services/api';

const DEFAULT_KEYS = [
  'org_number',
  'bizorg_number',
  'biztype_number',
  'invscheme_number',
] as const;

type DefaultKey = (typeof DEFAULT_KEYS)[number];

type FormValues = Record<DefaultKey, string>;

function headerFromBody(body: unknown): Record<string, unknown> | null {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return null;
  const root = body as Record<string, unknown>;
  const data = root.data;
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    return data as Record<string, unknown>;
  }
  if (Array.isArray(data) && data[0] && typeof data[0] === 'object') {
    return data[0] as Record<string, unknown>;
  }
  return root;
}

function readDefaultsFromApi(api: API): FormValues {
  const out: FormValues = {
    org_number: '',
    bizorg_number: '',
    biztype_number: '110',
    invscheme_number: '110',
  };
  const maps = Array.isArray(api.outbound_field_mappings) ? api.outbound_field_mappings : [];
  for (const row of maps) {
    const remote = String(row?.remote_field || '').trim() as DefaultKey;
    if (!DEFAULT_KEYS.includes(remote)) continue;
    const dv = row?.default_value;
    if (dv !== undefined && dv !== null && String(dv).trim() !== '') {
      out[remote] = String(dv).trim();
    }
  }
  const header = headerFromBody(api.request_body);
  if (header) {
    for (const key of DEFAULT_KEYS) {
      if (out[key]) continue;
      const raw = header[key];
      const text = String(raw ?? '').trim();
      if (!text || text.toUpperCase().startsWith('REPLACE_')) continue;
      out[key] = text;
    }
  }
  return out;
}

function applyDefaultsToApi(api: API, values: FormValues): {
  outbound_field_mappings: NonNullable<API['outbound_field_mappings']>;
  request_body: Record<string, unknown>;
} {
  const maps = Array.isArray(api.outbound_field_mappings)
    ? api.outbound_field_mappings.map((row) => ({ ...row }))
    : [];
  const seen = new Set<string>();
  for (const row of maps) {
    const remote = String(row?.remote_field || '').trim() as DefaultKey;
    if (!DEFAULT_KEYS.includes(remote)) continue;
    seen.add(remote);
    row.default_value = values[remote] || '';
    row.enabled = row.enabled !== false;
    row.level = row.level === 'entry' ? 'entry' : 'header';
    if (!row.source_table) {
      row.source_table = 'apps_kuaizhizao_purchase_receipts';
    }
    if (!row.local_field) {
      row.local_field = remote;
    }
  }
  for (const key of DEFAULT_KEYS) {
    if (seen.has(key)) continue;
    maps.push({
      enabled: true,
      level: 'header',
      source_table: 'apps_kuaizhizao_purchase_receipts',
      local_field: key,
      remote_field: key,
      default_value: values[key] || '',
    });
  }

  const bodyRoot =
    api.request_body && typeof api.request_body === 'object' && !Array.isArray(api.request_body)
      ? { ...(api.request_body as Record<string, unknown>) }
      : { data: {} };
  let data = bodyRoot.data;
  if (Array.isArray(data)) {
    const first =
      data[0] && typeof data[0] === 'object' && !Array.isArray(data[0])
        ? { ...(data[0] as Record<string, unknown>) }
        : {};
    for (const key of DEFAULT_KEYS) {
      first[key] = values[key] || '';
    }
    bodyRoot.data = [first, ...data.slice(1)];
  } else {
    const header =
      data && typeof data === 'object' && !Array.isArray(data)
        ? { ...(data as Record<string, unknown>) }
        : {};
    for (const key of DEFAULT_KEYS) {
      header[key] = values[key] || '';
    }
    bodyRoot.data = header;
  }

  return {
    outbound_field_mappings: maps,
    request_body: bodyRoot,
  };
}

export interface DocumentPushApiDefaultsModalProps {
  open: boolean;
  apiUuid?: string;
  onClose: () => void;
  onSaved?: () => void;
}

export const DocumentPushApiDefaultsModal: React.FC<DocumentPushApiDefaultsModalProps> = ({
  open,
  apiUuid,
  onClose,
  onSaved,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [form] = Form.useForm<FormValues>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [api, setApi] = useState<API | null>(null);

  useEffect(() => {
    if (!open || !apiUuid) {
      setApi(null);
      form.resetFields();
      return;
    }
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const one = await getAPIByUuid(apiUuid);
        if (cancelled) return;
        setApi(one);
        form.setFieldsValue(readDefaultsFromApi(one));
      } catch (error: unknown) {
        const err = error as { response?: { data?: { detail?: unknown } }; message?: string };
        messageApi.error(
          formatApiErrorDetail(err?.response?.data?.detail) ||
            err?.message ||
            t('common.loadFailed'),
        );
        onClose();
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, apiUuid, form, messageApi, onClose, t]);

  const handleOk = async () => {
    if (!apiUuid || !api) return;
    try {
      const values = await form.validateFields();
      setSaving(true);
      const org = String(values.org_number || '').trim();
      const payload = applyDefaultsToApi(api, {
        org_number: org,
        bizorg_number: String(values.bizorg_number || '').trim() || org,
        biztype_number: String(values.biztype_number || '').trim() || '110',
        invscheme_number: String(values.invscheme_number || '').trim() || '110',
      });
      await updateAPI(apiUuid, payload);
      messageApi.success(t('app.kuaizhizao.documentPush.apiDefaults.saveSuccess'));
      onSaved?.();
      onClose();
    } catch (error: unknown) {
      if ((error as { errorFields?: unknown })?.errorFields) return;
      const err = error as { response?: { data?: { detail?: unknown } }; message?: string };
      messageApi.error(
        formatApiErrorDetail(err?.response?.data?.detail) ||
          err?.message ||
          t('common.saveFailed'),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title={t('app.kuaizhizao.documentPush.apiDefaults.title')}
      open={open}
      onCancel={onClose}
      onOk={() => void handleOk()}
      confirmLoading={saving}
      destroyOnHidden
      width={520}
      okText={t('common.save')}
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        {t('app.kuaizhizao.documentPush.apiDefaults.hint')}
      </Typography.Paragraph>
      <Spin spinning={loading}>
        <Form form={form} layout="vertical" initialValues={{ biztype_number: '110', invscheme_number: '110' }}>
          <Form.Item
            name="org_number"
            label={t('app.kuaizhizao.documentPush.apiDefaults.orgNumber')}
            rules={[
              {
                required: true,
                message: t('app.kuaizhizao.documentPush.apiDefaults.orgNumberRequired'),
              },
            ]}
          >
            <Input placeholder={t('app.kuaizhizao.documentPush.apiDefaults.orgNumberPlaceholder')} />
          </Form.Item>
          <Form.Item
            name="bizorg_number"
            label={t('app.kuaizhizao.documentPush.apiDefaults.bizOrgNumber')}
          >
            <Input placeholder={t('app.kuaizhizao.documentPush.apiDefaults.bizOrgNumberPlaceholder')} />
          </Form.Item>
          <Form.Item
            name="biztype_number"
            label={t('app.kuaizhizao.documentPush.apiDefaults.bizType')}
            rules={[{ required: true, message: t('app.kuaizhizao.documentPush.apiDefaults.bizTypeRequired') }]}
          >
            <Input placeholder="110" />
          </Form.Item>
          <Form.Item
            name="invscheme_number"
            label={t('app.kuaizhizao.documentPush.apiDefaults.invScheme')}
            rules={[
              { required: true, message: t('app.kuaizhizao.documentPush.apiDefaults.invSchemeRequired') },
            ]}
          >
            <Input placeholder="110" />
          </Form.Item>
        </Form>
      </Spin>
    </Modal>
  );
};

export default DocumentPushApiDefaultsModal;
