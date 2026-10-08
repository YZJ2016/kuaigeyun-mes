import React from 'react';
import { ProFormDigit, ProFormSwitch, ProFormText } from '@ant-design/pro-components';

/** 应用连接器与数采共用：凭据始终保存在应用连接中。 */
export function IotConnectionFields({ type }: { type: string }) {
  if (type === 'mqtt') return <>
    <ProFormText name="host" label="Broker 地址" rules={[{ required: true }]} colProps={{ span: 12 }} />
    <ProFormDigit name="port" label="端口" min={1} max={65535} initialValue={1883} rules={[{ required: true }]} colProps={{ span: 12 }} />
    <ProFormText name="username" label="用户名" colProps={{ span: 12 }} />
    <ProFormText.Password name="password" label="密码" colProps={{ span: 12 }} />
    <ProFormSwitch name="use_tls" label="TLS" colProps={{ span: 12 }} />
  </>;
  if (type === 'thingsboard') return <>
    <ProFormText name="base_url" label="Base URL" placeholder="https://..." colProps={{ span: 24 }} />
    <ProFormText name="username" label="用户名" rules={[{ required: true }]} colProps={{ span: 12 }} />
    <ProFormText.Password name="password" label="密码" rules={[{ required: true }]} colProps={{ span: 12 }} />
  </>;
  if (type === 'jetlinks') return <>
    <ProFormText name="base_url" label="Base URL" placeholder="https://..." colProps={{ span: 24 }} />
    <ProFormText.Password name="token" label="Access Token" rules={[{ required: true }]} colProps={{ span: 24 }} />
  </>;
  return null;
}
