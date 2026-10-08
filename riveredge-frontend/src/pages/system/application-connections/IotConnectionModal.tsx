import React from 'react';
import { App, Alert } from 'antd';
import { ProFormText } from '@ant-design/pro-components';
import { FormModalTemplate, FormModalGridBlock, MODAL_CONFIG } from '../../../components/layout-templates';
import { createApplicationConnection, type ApplicationConnection } from '../../../services/applicationConnection';
import { IotConnectionFields } from './IotConnectionFields';
import { buildIotConnectionConfig } from './iotConnectionConfig';

/** 只保存应用连接；父窗口用返回 UUID 绑定数采，不复制凭据。 */
export function IotConnectionModal({ open, type, onOpenChange, onCreated }: {
  open: boolean;
  type: string;
  onOpenChange: (open: boolean) => void;
  onCreated: (connection: ApplicationConnection) => void;
}) {
  const { message } = App.useApp();
  return <FormModalTemplate
    title="新建 IoT 应用连接"
    open={open}
    onOpenChange={onOpenChange}
    grid
    width={MODAL_CONFIG.STANDARD_WIDTH}
    initialValues={{ port: 1883, use_tls: false }}
    onFinish={async values => {
      try {
        const connection = await createApplicationConnection({
          code: String(values.code ?? '').trim(),
          name: String(values.name ?? '').trim(),
          type,
          config: buildIotConnectionConfig(type, values),
          is_active: true,
        });
        onCreated(connection);
        onOpenChange(false);
        message.success('应用连接已创建并选中');
      } catch {
        // 不回显外部服务错误中的地址、凭据或原始请求。
        message.error('应用连接保存失败，请检查编码是否重复、配置和当前权限后重试');
        throw new Error('应用连接保存失败');
      }
    }}
  >
    <FormModalGridBlock><Alert type="info" showIcon message="每条连接独立保存于系统配置的应用连接器中。保存后仍需提交数采接入配置。" style={{ marginBottom: 16 }} /></FormModalGridBlock>
    <ProFormText name="code" label="连接编码" rules={[{ required: true, whitespace: true }]} fieldProps={{ maxLength: 50 }} colProps={{ span: 12 }} />
    <ProFormText name="name" label="连接名称" rules={[{ required: true, whitespace: true }]} fieldProps={{ maxLength: 100 }} colProps={{ span: 12 }} />
    <IotConnectionFields type={type} />
  </FormModalTemplate>;
}
