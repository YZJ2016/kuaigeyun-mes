import React, { useMemo, useState } from 'react';
import {
  AppstoreOutlined,
  AuditOutlined,
  BookOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ContainerOutlined,
  FileTextOutlined,
  SearchOutlined,
  FormOutlined,
  HourglassOutlined,
  InboxOutlined,
  ProfileOutlined,
  ReadOutlined,
  StopOutlined,
  ToolOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Input, Tree } from 'antd';
import type { DataNode } from 'antd/es/tree';
import { useTranslation } from 'react-i18next';
import { ThemedSegmented } from '../../../../../components/themed-segmented';
import {
  buildSystemDocumentNavTreeData,
  defaultNavSelection,
  SYSTEM_DOCUMENT_NAV_ALL_KEY,
  type QmsStandardNavItem,
  type SystemDocumentNavDimension,
} from './systemDocumentNav';

export interface SystemDocumentNavTreeProps {
  dimension: SystemDocumentNavDimension;
  selectedKey: string;
  standards: QmsStandardNavItem[];
  onDimensionChange: (dimension: SystemDocumentNavDimension, selectedKey: string) => void;
  onSelectKey: (key: string) => void;
}

function stackedStandardTitle(code: string, name?: string) {
  return (
    <span className="qms-system-document-nav-title qms-system-document-nav-title--stacked">
      <span className="qms-system-document-nav-title-primary">{code}</span>
      {name ? <span className="qms-system-document-nav-title-secondary">{name}</span> : null}
    </span>
  );
}

function docTypeIcon(value: string): React.ReactNode {
  switch (value) {
    case 'manual':
      return <ReadOutlined />;
    case 'procedure':
      return <ProfileOutlined />;
    case 'work_instruction':
      return <ToolOutlined />;
    case 'form':
      return <FormOutlined />;
    case 'record':
      return <ContainerOutlined />;
    default:
      return <FileTextOutlined />;
  }
}

function enrichTreeNodes(
  nodes: DataNode[],
  dimension: SystemDocumentNavDimension,
  standards: QmsStandardNavItem[],
): DataNode[] {
  return nodes.map((node) => {
    const key = String(node.key ?? '');
    const [, part] = key.split(':');

    if (dimension === 'standard') {
      if (part === SYSTEM_DOCUMENT_NAV_ALL_KEY) {
        return { ...node, icon: <AppstoreOutlined /> };
      }
      if (part === 'null') {
        return { ...node, icon: <InboxOutlined /> };
      }
      const id = Number(part);
      const standard = standards.find((s) => s.id === id);
      if (standard) {
        return {
          ...node,
          icon: <BookOutlined />,
          title: stackedStandardTitle(standard.code, standard.name),
        };
      }
      return { ...node, icon: <BookOutlined /> };
    }

    if (dimension === 'doc_type') {
      if (part === SYSTEM_DOCUMENT_NAV_ALL_KEY) {
        return { ...node, icon: <AppstoreOutlined /> };
      }
      return { ...node, icon: docTypeIcon(part) };
    }

    const lifecycleIcons: Record<string, React.ReactNode> = {
      [SYSTEM_DOCUMENT_NAV_ALL_KEY]: <AppstoreOutlined />,
      formal: <CheckCircleOutlined />,
      review_due: <WarningOutlined />,
      pending: <HourglassOutlined />,
      pending_audit: <AuditOutlined />,
      draft_rejected: <ClockCircleOutlined />,
      obsolete: <StopOutlined />,
    };
    return { ...node, icon: lifecycleIcons[part] ?? <FileTextOutlined /> };
  });
}

function nodeSearchText(node: DataNode, standards: QmsStandardNavItem[]): string {
  const key = String(node.key ?? '');
  if (key.startsWith('standard:')) {
    const part = key.split(':')[1];
    if (part === SYSTEM_DOCUMENT_NAV_ALL_KEY || part === 'null') {
      return typeof node.title === 'string' ? node.title : '';
    }
    const id = Number(part);
    const s = standards.find((item) => item.id === id);
    if (s) return `${s.code} ${s.name ?? ''}`;
  }
  return typeof node.title === 'string' ? node.title : '';
}

const SystemDocumentNavTree: React.FC<SystemDocumentNavTreeProps> = ({
  dimension,
  selectedKey,
  standards,
  onDimensionChange,
  onSelectKey,
}) => {
  const { t } = useTranslation();
  const [filterText, setFilterText] = useState('');

  const treeData = useMemo(() => {
    const base = buildSystemDocumentNavTreeData(dimension, t, standards);
    const enriched = enrichTreeNodes(base, dimension, standards);
    const q = filterText.trim().toLowerCase();
    if (!q) return enriched;
    return enriched.filter((node) => {
      const key = String(node.key ?? '');
      const part = key.split(':')[1];
      // 「全部」在各维度筛选时始终保留，避免树被筛空
      if (part === SYSTEM_DOCUMENT_NAV_ALL_KEY) return true;
      return nodeSearchText(node, standards).toLowerCase().includes(q);
    });
  }, [dimension, filterText, standards, t]);

  const filterPlaceholder = useMemo(() => {
    if (dimension === 'standard') return t('app.kuaizhizao.quality.qms.nav.filterStandards');
    if (dimension === 'doc_type') return t('app.kuaizhizao.quality.qms.nav.filterDocTypes');
    return t('app.kuaizhizao.quality.qms.nav.filterLifecycle');
  }, [dimension, t]);

  return (
    <div className="qms-system-document-nav">
      <div className="qms-system-document-nav-dimension">
        <ThemedSegmented
          block
          size="medium"
          value={dimension}
          onChange={(v) => {
            const next = v as SystemDocumentNavDimension;
            const defaults = defaultNavSelection(next);
            setFilterText('');
            onDimensionChange(next, defaults.selectedKey);
          }}
          options={[
            { label: t('app.kuaizhizao.quality.qms.nav.dimension.standard'), value: 'standard' },
            { label: t('app.kuaizhizao.quality.qms.nav.dimension.docType'), value: 'doc_type' },
            { label: t('app.kuaizhizao.quality.qms.nav.dimension.lifecycle'), value: 'lifecycle' },
          ]}
        />
      </div>
      <div className="qms-system-document-nav-filter">
        <Input
          allowClear
          size="medium"
          prefix={<SearchOutlined style={{ opacity: 0.45 }} />}
          placeholder={filterPlaceholder}
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
        />
      </div>
      <div className="two-column-layout-left-tree qms-system-document-nav-tree-scroll">
        <Tree
          className="file-manager-tree qms-system-document-nav-tree"
          blockNode
          showIcon
          selectedKeys={[selectedKey]}
          treeData={treeData}
          onSelect={(keys) => {
            const key = keys[0];
            if (typeof key === 'string') onSelectKey(key);
          }}
        />
      </div>
    </div>
  );
};

export default SystemDocumentNavTree;
