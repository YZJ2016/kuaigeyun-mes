/**
 * 技术栈列表 Modal 组件
 * 
 * 展示 RiverEdge SaaS 框架使用的所有技术栈信息，包括版本、作用描述和许可协议
 * 
 * Copyright 2025 无锡快格信息技术有限公司
 * RiverEdge 为无锡快格信息技术有限公司注册商标
 */

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Badge, Modal, Tabs, Table, Tag, Typography, Space, Divider, theme } from 'antd';
import type { TabsProps } from 'antd';
import { ExclamationCircleOutlined, FileTextOutlined } from '@ant-design/icons';
import { CheckCircle2, XCircle } from 'lucide-react';
import {
  MODAL_CONFIG,
  SYSTEM_VIEWPORT_OFFSETS,
  getViewportHeightExpr,
} from '../layout-templates/constants';
import { COPYRIGHT_COMPANY_NAME, COPYRIGHT_TRADEMARK } from '../../constants/copyrightContent';
import { verifyCopyright } from '../../utils/copyrightIntegrity';

import './tech-stack-modal.css';

const { Title, Text, Paragraph } = Typography;
const { useToken } = theme;

/**
 * 技术栈数据类型
 */
interface TechStackItem {
  name: string;
  version: string;
  description: string;
  license: string;
  commercialUse: boolean;
  category: 'backend' | 'frontend' | 'database' | 'infrastructure' | 'mobile';
  isCore?: boolean; // 是否为核心技术组件
}

/**
 * 技术栈数据
 */
const techStackData: TechStackItem[] = [
  {
    name: 'FastAPI',
    version: '0.115.x',
    description: '高性能异步 Web 框架',
    license: 'MIT License',
    commercialUse: true,
    category: 'backend',
    isCore: true,
  },
  {
    name: 'Taskiq',
    version: '0.12.x',
    description: '异步任务队列：PostgreSQL broker + 独立 worker / scheduler，默认无需 Redis',
    license: 'Apache License 2.0',
    commercialUse: true,
    category: 'backend',
    isCore: true,
  },
  {
    name: 'React',
    version: '18.3.1',
    description: 'PC Web 前端框架（触屏工位同版本；移动 App 为 React 19.1）',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
    isCore: true,
  },
  {
    name: 'Python',
    version: '3.11',
    description: '后端运行时；uv.lock 锁定 3.11（requires-python ≥3.11,<3.12）',
    license: 'PSF License (类似 BSD)',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'Uvicorn',
    version: '0.30.x',
    description: 'ASGI 服务器',
    license: 'BSD License',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'Pydantic',
    version: '2.9.x',
    description: '数据校验与设置（含 pydantic-settings）',
    license: 'MIT License',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'Tortoise ORM',
    version: '0.21.1',
    description: '异步 ORM',
    license: 'Apache License 2.0',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'Aerich',
    version: '0.7.1',
    description: 'Tortoise ORM 数据库迁移',
    license: 'Apache License 2.0',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'asyncpg',
    version: '0.29.x',
    description: 'PostgreSQL 异步驱动',
    license: 'Apache License 2.0',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'python-jose',
    version: '3.3.x',
    description: 'JWT 认证',
    license: 'MIT License',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'passlib',
    version: '1.7.4+',
    description: '密码哈希（bcrypt）',
    license: 'MIT License',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'httpx',
    version: '0.27.x',
    description: '异步 HTTP 客户端（含 OpenAI 兼容连接器）',
    license: 'BSD License',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'loguru',
    version: '0.7.3',
    description: '结构化日志',
    license: 'MIT License',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'python-socketio',
    version: '5.11.x',
    description: '实时通道（工位 / 消息）',
    license: 'MIT License',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'webauthn',
    version: '2.7.x',
    description: '通行密钥（WebAuthn）',
    license: 'BSD License',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'aiomqtt',
    version: '2.3.x',
    description: 'MQTT 客户端（快数采接入）',
    license: 'BSD License',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'influxdb-client',
    version: '1.49.x',
    description: '可选时序库客户端（快数采历史点）',
    license: 'MIT License',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'Playwright',
    version: '1.57.x',
    description: '可选 extra：HTML 转 PDF（需 uv sync --extra pdf）',
    license: 'Apache License 2.0',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'prometheus-client',
    version: '0.26.x',
    description: 'HTTP 指标导出（/metrics）',
    license: 'Apache License 2.0',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'openpyxl / pypdf',
    version: '3.1+ / 5.x',
    description: 'Excel 读写与 PDF 解析（发票验票等）',
    license: 'MIT / BSD',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'qrcode / pyzbar',
    version: '7.4+ / 0.1.9+',
    description: '二维码生成与解析',
    license: 'BSD / MIT',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'aiosmtplib',
    version: '3.0.x',
    description: '异步 SMTP 发信',
    license: 'MIT License',
    commercialUse: true,
    category: 'backend',
  },
  {
    name: 'MinIO SDK',
    version: '7.2.x',
    description: '对象存储客户端（兼容 S3；亦可接腾讯云 COS）',
    license: 'Apache License 2.0',
    commercialUse: true,
    category: 'backend',
  },

  // 前端技术栈
  {
    name: 'Vite',
    version: '5.4.8',
    description: 'PC Web 构建工具',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'TypeScript',
    version: '5.6.3',
    description: 'PC Web 静态类型（移动端为 5.9）',
    license: 'Apache License 2.0',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'React Router DOM',
    version: '6.26.2',
    description: '前端路由',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'Zustand',
    version: '5.0.x',
    description: '客户端状态',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'TanStack Query',
    version: '5.51.x',
    description: '服务端状态与缓存',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'Ant Design',
    version: '6.4.4',
    description: '企业级 UI 组件库',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
    isCore: true,
  },
  {
    name: '@ant-design/pro-components',
    version: '2.8.2',
    description: 'ProTable 等业务组件',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: '@ant-design/pro-flow',
    version: '1.3.12',
    description: '审批流 / 业务蓝图设计器',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: '@ant-design/x',
    version: '2.4.x',
    description: 'AI 对话 UI（助手与单据问答）',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: '@ant-design/charts',
    version: '2.1.x',
    description: 'Ant Design 图表',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'ECharts',
    version: '5.6.0',
    description: '图表与地图可视化',
    license: 'Apache License 2.0',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'Three.js / R3F',
    version: '0.183 / 8.18',
    description: '3D 场景（仪表盘等；含 @react-three/fiber、drei）',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: '@svar-ui/react-gantt',
    version: '2.5.2',
    description: '甘特图（排程）',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'Formily',
    version: '2.3.7',
    description: '自定义字段表单（core / react / antd-v5）',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: '@univerjs/*',
    version: '0.12.4',
    description: '在线表格（导入导出）',
    license: 'Apache License 2.0',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'LibreDWG / CAD',
    version: '0.7.x',
    description: '图纸预览（@mlightcad/libredwg-web 等）',
            license: 'GPL-2.0-or-later（libredwg，须遵循 copyleft）',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'ExcelJS',
    version: '4.4.x',
    description: '浏览器端 Excel 读写',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'Centrifuge',
    version: '5.7.x',
    description: '实时收件箱（WebSocket）',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'i18next',
    version: '23.15.2',
    description: '国际化（含 react-i18next）',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'dayjs',
    version: '1.11.13',
    description: '日期时间',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'less',
    version: '4.4.2',
    description: 'CSS 预处理器',
    license: 'Apache License 2.0',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'framer-motion',
    version: '11.5.4',
    description: '动画',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'qrcode.react / html5-qrcode',
    version: '4.2 / 2.3.8',
    description: '二维码展示与摄像头扫码',
    license: 'MIT / Apache-2.0',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'lottie-react',
    version: '2.4.1',
    description: 'Lottie 动画',
    license: 'MIT License',
    commercialUse: true,
    category: 'frontend',
  },
  {
    name: 'lucide-react',
    version: '0.556.x',
    description: '图标',
    license: 'ISC License',
    commercialUse: true,
    category: 'frontend',
  },

  {
    name: 'PostgreSQL',
    version: '15+',
    description: '主数据库；Taskiq broker 亦用 PostgreSQL',
    license: 'PostgreSQL License (类似 BSD/MIT)',
    commercialUse: true,
    category: 'database',
  },
  {
    name: 'InfluxDB',
    version: '可选',
    description: '快数采点位历史（未配置时走库内短窗）',
    license: 'MIT（官方客户端）；服务端许可以部署版本为准',
    commercialUse: true,
    category: 'database',
  },

  {
    name: 'Node.js',
    version: '>=22',
    description: '前端与工位机构建运行时',
    license: 'MIT License',
    commercialUse: true,
    category: 'infrastructure',
  },
  {
    name: 'npm',
    version: '>=10',
    description: '前端包管理',
    license: 'Artistic License 2.0',
    commercialUse: true,
    category: 'infrastructure',
  },
  {
    name: 'UV',
    version: '>=0.4',
    description: 'Python 依赖与虚拟环境（替代 pip/poetry）',
    license: 'MIT / Apache-2.0',
    commercialUse: true,
    category: 'infrastructure',
  },
  {
    name: 'Caddy',
    version: '2.x',
    description: '生产反向代理（Web / H5 / API）',
    license: 'Apache License 2.0',
    commercialUse: true,
    category: 'infrastructure',
  },
  {
    name: 'Electron',
    version: '33.x',
    description: 'Windows 触屏工位机（私仓 riveredge-app-station）',
    license: 'MIT License',
    commercialUse: true,
    category: 'infrastructure',
  },

  {
    name: 'Expo',
    version: '54.0.x',
    description: '移动 App 与 H5 构建、OTA',
    license: 'MIT License',
    commercialUse: true,
    category: 'mobile',
    isCore: true,
  },
  {
    name: 'React Native',
    version: '0.81.5',
    description: '跨平台移动端（React 19.1）',
    license: 'MIT License',
    commercialUse: true,
    category: 'mobile',
    isCore: true,
  },
  {
    name: '@ant-design/react-native',
    version: '5.4.3',
    description: '移动端 UI',
    license: 'MIT License',
    commercialUse: true,
    category: 'mobile',
  },
  {
    name: 'expo-router',
    version: '6.0.x',
    description: '基于文件的路由',
    license: 'MIT License',
    commercialUse: true,
    category: 'mobile',
  },
  {
    name: 'expo-camera',
    version: '17.0.x',
    description: '扫码与拍照',
    license: 'MIT License',
    commercialUse: true,
    category: 'mobile',
  },
  {
    name: 'expo-secure-store',
    version: '55.x',
    description: '钥匙串 / Keystore',
    license: 'MIT License',
    commercialUse: true,
    category: 'mobile',
  },
  {
    name: 'react-native-reanimated',
    version: '4.1.x',
    description: '原生动画',
    license: 'MIT License',
    commercialUse: true,
    category: 'mobile',
  },
  {
    name: 'socket.io-client',
    version: '4.8.x',
    description: '移动端实时通道',
    license: 'MIT License',
    commercialUse: true,
    category: 'mobile',
  },
];

/**
 * 技术栈列表 Modal 组件
 */
interface TechStackModalProps {
  open: boolean;
  onCancel: () => void;
}

const TechStackModal: React.FC<TechStackModalProps> = ({ open, onCancel }) => {
  const { t } = useTranslation();
  const { token } = useToken();
  const overviewPaneRef = useRef<HTMLDivElement>(null);
  const [lockedBodyHeight, setLockedBodyHeight] = useState<number>();

  useEffect(() => {
    if (open) verifyCopyright();
  }, [open]);

  const lockBodyHeightFromOverview = useCallback((pane: HTMLElement | null) => {
    const body = pane?.closest('.ant-modal-body');
    if (!(body instanceof HTMLElement)) {
      return;
    }
    const nextHeight = Math.round(body.getBoundingClientRect().height);
    if (nextHeight <= 0) {
      return;
    }
    setLockedBodyHeight((prev) => prev ?? nextHeight);
  }, []);

  /** 打开时按「概览」自然高度锁定 body，切换 Tab 不再撑高或塌缩 */
  const bindOverviewPane = useCallback((node: HTMLDivElement | null) => {
    overviewPaneRef.current = node;
    if (!open || !node) {
      return;
    }
    lockBodyHeightFromOverview(node);
  }, [open, lockBodyHeightFromOverview]);

  useLayoutEffect(() => {
    if (!open) {
      setLockedBodyHeight(undefined);
      return;
    }
    lockBodyHeightFromOverview(overviewPaneRef.current);
  }, [open, lockBodyHeightFromOverview]);

  /** 各 Tab 内边距：上下略大于左右，避免贴底；高度由锁定后的 tabpane 滚动区承载 */
  const tabContentStyle: React.CSSProperties = {
    padding: `${token.paddingMD}px ${token.paddingSM}px ${token.paddingLG}px`,
    boxSizing: 'border-box',
  };
  const warningBoxStyle: React.CSSProperties = {
    marginTop: 16,
    padding: 12,
    background: token.colorWarningBg,
    borderRadius: token.borderRadius,
    border: `1px solid ${token.colorWarningBorder}`,
  };

  // 按分类分组
  const backendTech = techStackData.filter(item => item.category === 'backend');
  const frontendTech = techStackData.filter(item => item.category === 'frontend');
  const mobileTech = techStackData.filter(item => item.category === 'mobile');
  const databaseTech = techStackData.filter(item => item.category === 'database');
  const infrastructureTech = techStackData.filter(item => item.category === 'infrastructure');

  const columns = [
    {
      title: t('components.techStackModal.columnName'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (text: string, record: TechStackItem) => (
        <Space>
          {text}
          {record.isCore && (
            <Tag color="gold" icon={<FileTextOutlined />}>
              {t('components.techStackModal.tagCore')}
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: t('components.techStackModal.columnVersion'),
      dataIndex: 'version',
      key: 'version',
      width: 150,
      render: (text: string) => <Text code>{text}</Text>,
    },
    {
      title: t('components.techStackModal.columnDescription'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: t('components.techStackModal.columnLicense'),
      dataIndex: 'license',
      key: 'license',
      width: 200,
      render: (text: string) => <Text type="secondary">{text}</Text>,
    },
    {
      title: t('components.techStackModal.columnCommercialUse'),
      dataIndex: 'commercialUse',
      key: 'commercialUse',
      width: 100,
      align: 'center' as const,
      render: (value: boolean) => (
        <Tag
          color={value ? 'success' : 'error'}
          icon={value ? <CheckCircle2 size={12} strokeWidth={1.75} /> : <XCircle size={12} strokeWidth={1.75} />}
        >
          {value ? t('components.techStackModal.tagFree') : t('components.techStackModal.tagRequired')}
        </Tag>
      ),
    },
  ];

  const tabItems: TabsProps['items'] = [
    {
      key: 'overview',
      label: t('components.techStackModal.tabOverview'),
      children: (
        <div ref={bindOverviewPane} style={tabContentStyle}>
          <Title level={4}>{t('components.techStackModal.overview.coreTitle')}</Title>
          <Paragraph>
            {t('components.techStackModal.overview.intro')}
          </Paragraph>
          <Space orientation="vertical" size="medium" style={{ width: '100%' }}>
            <div>
              <Text strong>FastAPI</Text>：{t('components.techStackModal.overview.fastapi')}
            </div>
            <div>
              <Text strong>Taskiq</Text>：{t('components.techStackModal.overview.taskiq')}
            </div>
            <div>
              <Text strong>React</Text>：{t('components.techStackModal.overview.react')}
            </div>
            <div>
              <Text strong>Tortoise ORM</Text>：{t('components.techStackModal.overview.tortoise')}
            </div>
            <div>
              <Text strong>Ant Design</Text>：{t('components.techStackModal.overview.antd')}
            </div>
            <div>
              <Text strong>Expo</Text>：{t('components.techStackModal.overview.expo')}
            </div>
            <div>
              <Text strong>React Native</Text>：{t('components.techStackModal.overview.reactNative')}
            </div>
            <div>
              <Text strong>PostgreSQL</Text>：{t('components.techStackModal.overview.postgresql')}
            </div>
            <div>
              <Text strong>Caddy</Text>：{t('components.techStackModal.overview.caddy')}
            </div>
          </Space>
          <Divider />
          <Title level={5}>{t('components.techStackModal.overview.licenseTitle')}</Title>
          <Paragraph>
            {t('components.techStackModal.overview.licenseIntro')}
          </Paragraph>
          <Paragraph>
            <Space align="start">
              <ExclamationCircleOutlined style={{ color: 'var(--ant-color-warning)', marginTop: 2 }} />
              <span>{t('components.techStackModal.overview.defaultStackNote')}</span>
            </Space>
          </Paragraph>
        </div>
      ),
    },
    {
      key: 'copyright',
      label: (
        <Badge dot color="red" offset={[8, 0]}>
          <span>{t('components.techStackModal.tabCopyright')}</span>
        </Badge>
      ),
      children: (
        <div style={tabContentStyle}>
          <Alert
            title={t('components.techStackModal.copyright.important')}
            description={t('components.techStackModal.copyright.importantDesc')}
            type="info"
            showIcon
            icon={<ExclamationCircleOutlined />}
            style={{ marginBottom: 24 }}
          />
          <Title level={4}>{t('components.techStackModal.copyright.projectTitle')}</Title>
          <Paragraph>
            {t('components.techStackModal.copyright.projectScope')}
          </Paragraph>
          
          <Title level={5}>{t('components.techStackModal.copyright.ownershipTitle')}</Title>
          <Paragraph>
            <Text strong>Copyright © {COPYRIGHT_COMPANY_NAME}</Text>
          </Paragraph>
          <Paragraph type="secondary">
            {t('components.techStackModal.copyright.ownershipDesc', { company: COPYRIGHT_COMPANY_NAME })}
          </Paragraph>
          
          <Divider />
          
          <Title level={5}>{t('components.techStackModal.copyright.trademarkTitle')}</Title>
          <Paragraph>
            {t('components.techStackModal.copyright.trademarkDesc', { trademark: COPYRIGHT_TRADEMARK, company: COPYRIGHT_COMPANY_NAME })}
          </Paragraph>
          <Paragraph>
            {t('components.techStackModal.copyright.trademarkNoGrant')}
          </Paragraph>
          <Paragraph style={{ paddingLeft: token.paddingLG }}>
            • {t('components.techStackModal.copyright.trademarkItem1', { trademark: COPYRIGHT_TRADEMARK })}
          </Paragraph>
          <Paragraph style={{ paddingLeft: token.paddingLG }}>
            • {t('components.techStackModal.copyright.trademarkItem2', { trademark: COPYRIGHT_TRADEMARK })}
          </Paragraph>
          
          <Divider />
          
          <Title level={5}>{t('components.techStackModal.copyright.softwareTitle')}</Title>
          <Paragraph>
            {t('components.techStackModal.copyright.softwareIntro')}
          </Paragraph>
          <Paragraph style={{ paddingLeft: token.paddingLG, display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <CheckCircle2 size={16} strokeWidth={1.75} style={{ flexShrink: 0, marginTop: 2 }} aria-hidden />
            <span>{t('components.techStackModal.copyright.softwareItem1')}</span>
          </Paragraph>
          <Paragraph style={{ paddingLeft: token.paddingLG, display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <CheckCircle2 size={16} strokeWidth={1.75} style={{ flexShrink: 0, marginTop: 2 }} aria-hidden />
            <span>{t('components.techStackModal.copyright.softwareItem2')}</span>
          </Paragraph>
          <Paragraph type="secondary" style={{ marginTop: 8 }}>
            {t('components.techStackModal.copyright.softwareNote')}
          </Paragraph>
          
          <Divider />
          
          <Title level={5}>{t('components.techStackModal.copyright.complianceTitle')}</Title>
          <Paragraph>
            {t('components.techStackModal.copyright.complianceDesc')}
          </Paragraph>
          <Paragraph>
            <Text strong>{t('components.techStackModal.copyright.complianceAuth')}</Text>
          </Paragraph>
          <Paragraph style={warningBoxStyle}>
            <Text type="warning" strong>
              {t('components.techStackModal.copyright.warning')}
            </Text>
          </Paragraph>
        </div>
      ),
    },
    {
      key: 'attribution',
      label: t('components.techStackModal.tabAttribution'),
      children: (
        <div style={tabContentStyle}>
          <Title level={5}>{t('components.techStackModal.copyright.model3dTitle')}</Title>
          <Paragraph>
            {t('components.techStackModal.copyright.model3dDesc')}
          </Paragraph>
          
          <Divider />
          
          <Title level={5}>{t('components.techStackModal.copyright.fontTitle')}</Title>
          <Paragraph>
            {t('components.techStackModal.copyright.fontDesc')}
          </Paragraph>
          <Paragraph style={{ paddingLeft: token.paddingLG }}>
            <Text strong>JetBrains Mono</Text>
          </Paragraph>
          <Paragraph type="secondary" style={{ paddingLeft: token.paddingLG }}>
            {t('components.techStackModal.copyright.fontJetBrains')}
          </Paragraph>
          <Paragraph type="secondary" style={{ paddingLeft: token.paddingLG, marginTop: 8 }}>
            {t('components.techStackModal.copyright.fontSystem')}
          </Paragraph>
          <Paragraph style={{ paddingLeft: token.paddingLG, marginTop: 12 }}>
            <Text strong>wx-icons（SVAR 甘特图图标）</Text>
          </Paragraph>
          <Paragraph type="secondary" style={{ paddingLeft: token.paddingLG }}>
            {t('components.techStackModal.copyright.fontWxIcons')}
          </Paragraph>
          
          <Divider />
          
          <Title level={5}>{t('components.techStackModal.copyright.assetsTitle')}</Title>
          <Paragraph>
            {t('components.techStackModal.copyright.assetsDesc')}
          </Paragraph>
          <Paragraph style={{ paddingLeft: token.paddingLG }}>
            <Text strong>Lottie 动画</Text>
          </Paragraph>
          <Paragraph type="secondary" style={{ paddingLeft: token.paddingLG }}>
            {t('components.techStackModal.copyright.assetsLottie')}
          </Paragraph>
          <Paragraph style={{ paddingLeft: token.paddingLG, marginTop: 8 }}>
            <Text strong>社交平台图标</Text>
          </Paragraph>
          <Paragraph type="secondary" style={{ paddingLeft: token.paddingLG }}>
            {t('components.techStackModal.copyright.assetsSocial')}
          </Paragraph>

          <Divider />

          <Title level={5}>{t('components.techStackModal.copyright.provenanceTitle')}</Title>
          <Paragraph>
            {t('components.techStackModal.copyright.provenanceDesc')}
          </Paragraph>
          <Paragraph type="secondary">
            <a
              href="https://gitee.com/kuaigeyun/kuaigeyun/blob/develop/docs/telemetry-disclosure.md"
              target="_blank"
              rel="noreferrer"
            >
              {t('components.techStackModal.copyright.telemetryLink')}
            </a>
          </Paragraph>
        </div>
      ),
    },
    {
      key: 'ai-assist',
      label: t('components.techStackModal.tabAiAssist'),
      children: (
        <div style={tabContentStyle}>
          <Title level={4}>{t('components.techStackModal.aiAssist.title')}</Title>
          <Paragraph>
            {t('components.techStackModal.aiAssist.intro')}
          </Paragraph>
          <Space orientation="vertical" size="medium" style={{ width: '100%', marginTop: 16 }}>
            <div>
              {t('components.techStackModal.aiAssist.cursor')}
            </div>
            <div>
              {t('components.techStackModal.aiAssist.antigravity')}
            </div>
            <div>
              {t('components.techStackModal.aiAssist.trae')}
            </div>
          </Space>
          <Paragraph type="secondary" style={{ marginTop: 24 }}>
            {t('components.techStackModal.aiAssist.note')}
          </Paragraph>
        </div>
      ),
    },
    {
      key: 'backend',
      label: t('components.techStackModal.tabBackend', { count: backendTech.length }),
      children: (
        <div style={tabContentStyle}>
          <Table
            dataSource={backendTech}
            columns={columns}
            rowKey="name"
            pagination={{ pageSize: 20 }}
            size="small"
          />
        </div>
      ),
    },
    {
      key: 'frontend',
      label: t('components.techStackModal.tabFrontend', { count: frontendTech.length }),
      children: (
        <div style={tabContentStyle}>
          <Table
            dataSource={frontendTech}
            columns={columns}
            rowKey="name"
            pagination={{ pageSize: 20 }}
            size="small"
          />
        </div>
      ),
    },
    {
      key: 'mobile',
      label: t('components.techStackModal.tabMobile', { count: mobileTech.length }),
      children: (
        <div style={tabContentStyle}>
          <Table
            dataSource={mobileTech}
            columns={columns}
            rowKey="name"
            pagination={{ pageSize: 20 }}
            size="small"
          />
        </div>
      ),
    },
    {
      key: 'database',
      label: t('components.techStackModal.tabDatabase', { count: databaseTech.length }),
      children: (
        <div style={tabContentStyle}>
          <Table
            dataSource={databaseTech}
            columns={columns}
            rowKey="name"
            pagination={{ pageSize: 20 }}
            size="small"
          />
        </div>
      ),
    },
    {
      key: 'infrastructure',
      label: t('components.techStackModal.tabInfrastructure', { count: infrastructureTech.length }),
      children: (
        <div style={tabContentStyle}>
          <Table
            dataSource={infrastructureTech}
            columns={columns}
            rowKey="name"
            pagination={{ pageSize: 20 }}
            size="small"
          />
        </div>
      ),
    },
  ];

  const modalBodyMaxHeight = getViewportHeightExpr(SYSTEM_VIEWPORT_OFFSETS.TECH_STACK_MODAL_PX);

  return (
    <Modal
      title={t('components.techStackModal.title')}
      open={open}
      onCancel={onCancel}
      footer={null}
      destroyOnHidden
      width={MODAL_CONFIG.LARGE_WIDTH + 200}
      style={{ top: 24 }}
      styles={{
        body: {
          height: lockedBodyHeight,
          maxHeight: modalBodyMaxHeight,
          overflow: 'hidden',
          padding: `${token.paddingMD}px ${token.paddingLG}px ${token.paddingLG}px`,
          display: 'flex',
          flexDirection: 'column',
          boxSizing: 'border-box',
        },
      }}
    >
      <Tabs
        className={
          lockedBodyHeight != null
            ? 'tech-stack-modal-tabs tech-stack-modal-tabs--locked'
            : 'tech-stack-modal-tabs'
        }
        defaultActiveKey="overview"
        items={tabItems}
        size="medium"
        tabBarStyle={{ marginBottom: token.marginMD, flexShrink: 0 }}
      />
    </Modal>
  );
};

export default TechStackModal;

