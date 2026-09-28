/**
 * 报表/大屏共用的分享弹窗。
 * 提交 POST {password, expires_at, allow_ip_cidrs?}，成功展示 share_path 完整 URL（可复制）。
 * 口令只在表单内存里，不持久化、不回显。
 */

import React, { useEffect, useState } from 'react';
import { Alert, App, DatePicker, Form, Input, Modal, Typography } from 'antd';
import type { Dayjs } from 'dayjs';
import type { ShareResult } from '../reports/api';

export interface ShareBody {
  password: string;
  expires_at: string;
  allow_ip_cidrs?: string[];
}

interface ShareFormValues {
  expires_at: Dayjs;
  password: string;
  allow_ip_cidrs?: string;
}

export function ShareModal({
  open,
  resourceName,
  onSubmit,
  onClose,
}: {
  open: boolean;
  resourceName?: string;
  onSubmit: (body: ShareBody) => Promise<ShareResult>;
  /** changed 为 true 表示本次弹窗内成功开启了分享，父级应刷新列表 */
  onClose: (changed: boolean) => void;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm<ShareFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ShareResult | null>(null);
  const [changed, setChanged] = useState(false);

  useEffect(() => {
    if (open) {
      setResult(null);
      setChanged(false);
      form.resetFields();
    }
  }, [open, form]);

  const shareUrl = result?.share_path
    ? `${window.location.origin}${result.share_path}`
    : '';

  const handleOk = async () => {
    const values = await form.validateFields();
    const cidrs = (values.allow_ip_cidrs || '')
      .split(/[,，\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
    setSubmitting(true);
    try {
      const body: ShareBody = {
        password: values.password,
        expires_at: values.expires_at.toISOString(),
      };
      if (cidrs.length) body.allow_ip_cidrs = cidrs;
      const saved = await onSubmit(body);
      setResult(saved);
      setChanged(true);
      message.success('分享已开启');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '分享失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title={`分享${resourceName ? `：${resourceName}` : ''}`}
      okText="开启分享"
      confirmLoading={submitting}
      onOk={result ? () => onClose(changed) : () => void handleOk()}
      okButtonProps={result ? { style: { display: 'none' } } : undefined}
      cancelText="关闭"
      onCancel={() => onClose(changed)}
      destroyOnHidden
    >
      {result ? (
        <>
          <Alert
            type="success"
            showIcon
            message="分享链接已签发"
            description="口令不会出现在链接与日志中，请把口令单独告知访问方。"
            style={{ marginBottom: 12 }}
          />
          <Typography.Paragraph copyable={{ text: shareUrl }} style={{ wordBreak: 'break-all' }}>
            {shareUrl}
          </Typography.Paragraph>
          {result.expires_at ? (
            <Typography.Text type="secondary">
              有效期至 {new Date(result.expires_at).toLocaleString()}
            </Typography.Text>
          ) : null}
        </>
      ) : (
        <Form form={form} layout="vertical">
          <Form.Item
            name="expires_at"
            label="过期时间"
            rules={[{ required: true, message: '请选择过期时间' }]}
          >
            <DatePicker showTime style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="password"
            label="访问口令"
            rules={[{ required: true, message: '请填写访问口令' }]}
          >
            <Input.Password maxLength={64} autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            name="allow_ip_cidrs"
            label="IP 白名单（可选）"
            extra="留空不校验来源 IP；多个用逗号分隔，支持 CIDR，如 10.0.0.0/8"
          >
            <Input.TextArea rows={2} placeholder="192.168.1.10, 10.0.0.0/8" />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
}

export function shareFullUrl(sharePath?: string): string {
  return sharePath ? `${window.location.origin}${sharePath}` : '';
}

export default ShareModal;
