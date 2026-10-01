import React, { useEffect, useMemo, useState } from 'react';
import { TreeSelect } from 'antd';
import { useTranslation } from 'react-i18next';
import { qualityQmsApi, QmsIsoClauseTreeNode } from '../../../services/quality-qms';

type TreeSelectNode = {
  value: number;
  title: string;
  children?: TreeSelectNode[];
  disabled?: boolean;
};

function mapClauseTree(
  nodes: QmsIsoClauseTreeNode[],
  excludeId?: number,
): TreeSelectNode[] {
  return nodes
    .filter((node) => node.id !== excludeId)
    .map((node) => ({
      value: node.id,
      title: `${node.clause_code} ${node.title}`,
      children:
        node.children && node.children.length > 0
          ? mapClauseTree(node.children, excludeId)
          : undefined,
    }));
}

export type QmsIsoClauseSelectProps = {
  value?: number | number[] | null;
  onChange?: (value?: number | number[] | null) => void;
  standardId?: number;
  standardCode?: string;
  excludeId?: number;
  disabled?: boolean;
  multiple?: boolean;
  placeholder?: string;
};

export const QmsIsoClauseSelect: React.FC<QmsIsoClauseSelectProps> = ({
  value,
  onChange,
  standardId,
  standardCode,
  excludeId,
  disabled,
  multiple = false,
  placeholder,
}) => {
  const { t } = useTranslation();
  const [tree, setTree] = useState<QmsIsoClauseTreeNode[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    qualityQmsApi.isoClauses
      .tree({
        ...(standardId != null ? { standard_id: standardId } : {}),
        ...(standardCode ? { standard_code: standardCode } : {}),
      })
      .then((res) => {
        if (!cancelled) setTree(res ?? []);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [standardId, standardCode]);

  const treeData = useMemo(() => mapClauseTree(tree, excludeId), [tree, excludeId]);

  return (
    <TreeSelect
      allowClear
      showSearch
      treeDefaultExpandAll
      treeNodeFilterProp="title"
      loading={loading}
      disabled={disabled}
      multiple={multiple}
      treeCheckable={multiple}
      showCheckedStrategy={multiple ? TreeSelect.SHOW_PARENT : undefined}
      value={value ?? undefined}
      placeholder={placeholder ?? t('app.kuaizhizao.quality.qms.selectClause')}
      treeData={treeData}
      onChange={(next) => onChange?.(next ?? (multiple ? [] : null))}
      style={{ width: '100%' }}
    />
  );
};

export default QmsIsoClauseSelect;
