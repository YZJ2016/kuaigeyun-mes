/**
 * 自定义字段 / 接口请求体 JSON 编辑器
 *
 * 默认键值对模式（支持嵌套对象与自行新增子字段）；也可切换 JSON 源码并格式化校验。
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Checkbox, Input, Typography, theme } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { ThemedSegmented } from '../themed-segmented';
import {
  addJsonTreeChild,
  canEditAsJsonTree,
  formatJsonText,
  jsonTreeToValue,
  jsonValueToTree,
  parseJsonText,
  removeJsonTreeNode,
  updateJsonTreeNode,
  type JsonTreeNode,
} from './customFieldJsonUtils';
import './CustomFieldJsonEditor.css';

export type CustomFieldJsonEditorMode = 'kv' | 'source';

export interface CustomFieldJsonModeSegmentedProps {
  mode: CustomFieldJsonEditorMode;
  onChange: (mode: CustomFieldJsonEditorMode) => void;
  disabled?: boolean;
  size?: 'small' | 'middle' | 'large';
}

export const CustomFieldJsonModeSegmented: React.FC<CustomFieldJsonModeSegmentedProps> = ({
  mode,
  onChange,
  disabled = false,
  size = 'small',
}) => (
  <ThemedSegmented
    size={size}
    value={mode}
    disabled={disabled}
    onChange={(v) => onChange(v as CustomFieldJsonEditorMode)}
    options={[
      { label: '字段勾选', value: 'kv' },
      { label: 'JSON 源码', value: 'source' },
    ]}
  />
);

const FIELD_CAPTIONS: Record<string, string> = {
  pageNo: '查询页码',
  page_no: '查询页码',
  pageSize: '分页数量',
  page_size: '分页数量',
  data: '查询条件',
  params: '查询条件',
  org: '库存组织编码',
  material: '物料编码',
  group: '分组汇总（按批号入库请带上 lotnum）',
  lotnum: '批号',
  warehouse: '仓库编码',
};

const objectFieldHint = (key: string) => {
  const caption = FIELD_CAPTIONS[key.trim()];
  if (caption) return `${caption}（勾选子字段后才会传）`;
  return '勾选子字段后才会传';
};

export interface CustomFieldJsonEditorProps {
  value?: unknown;
  onChange?: (value: unknown) => void;
  placeholder?: string;
  disabled?: boolean;
  /** 是否在编辑器顶部显示模式切换，默认 true */
  showModeToggle?: boolean;
  mode?: CustomFieldJsonEditorMode;
  onModeChange?: (mode: CustomFieldJsonEditorMode) => void;
}

interface JsonTreeRowsProps {
  nodes: JsonTreeNode[];
  disabled: boolean;
  onChange: (nodes: JsonTreeNode[]) => void;
}

const JsonTreeRows: React.FC<JsonTreeRowsProps> = ({ nodes, disabled, onChange }) => {
  const updateNode = (id: string, patch: Partial<JsonTreeNode>) => {
    onChange(updateJsonTreeNode(nodes, id, (node) => ({ ...node, ...patch })));
  };

  return (
    <div className="custom-field-json-tree">
      {nodes.map((node) => {
        const inputsDisabled = disabled || !node.enabled;
        const caption = FIELD_CAPTIONS[node.key.trim()];
        return (
          <div key={node.id} className="custom-field-json-tree__item">
            <div className="custom-field-json-tree__main">
              <div className="custom-field-json-tree__check">
                <Checkbox
                  checked={node.enabled}
                  disabled={disabled}
                  onChange={(e) => updateNode(node.id, { enabled: e.target.checked })}
                />
              </div>
              <div className="custom-field-json-tree__key-col">
                <Input
                  placeholder="字段名"
                  value={node.key}
                  disabled={inputsDisabled}
                  onChange={(e) => updateNode(node.id, { key: e.target.value })}
                />
                {caption ? <div className="custom-field-json-tree__caption">{caption}</div> : null}
              </div>
              <div className="custom-field-json-tree__value-col">
                {node.kind === 'object' ? (
                  <span className="custom-field-json-tree__hint">{objectFieldHint(node.key)}</span>
                ) : (
                  <Input
                    placeholder="字段值（空值发送时会自动省略）"
                    value={node.value}
                    disabled={inputsDisabled}
                    onChange={(e) => updateNode(node.id, { value: e.target.value })}
                  />
                )}
              </div>
              <Button
                className="custom-field-json-tree__remove"
                type="text"
                danger
                disabled={disabled}
                icon={<MinusCircleOutlined />}
                onClick={() => onChange(removeJsonTreeNode(nodes, node.id))}
              />
            </div>
            {node.kind === 'object' ? (
              <div className="custom-field-json-tree__children">
                <JsonTreeRows
                  nodes={node.children}
                  disabled={inputsDisabled}
                  onChange={(children) => updateNode(node.id, { children })}
                />
                <Button
                  className="custom-field-json-tree__add"
                  type="dashed"
                  size="small"
                  disabled={inputsDisabled}
                  icon={<PlusOutlined />}
                  onClick={() => onChange(addJsonTreeChild(nodes, node.id))}
                >
                  添加子字段
                </Button>
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
};

export const CustomFieldJsonEditor: React.FC<CustomFieldJsonEditorProps> = ({
  value,
  onChange,
  placeholder,
  disabled = false,
  showModeToggle = true,
  mode: controlledMode,
  onModeChange,
}) => {
  const { token } = theme.useToken();
  const initialMode: CustomFieldJsonEditorMode = canEditAsJsonTree(value) ? 'kv' : 'source';
  const [internalMode, setInternalMode] = useState<CustomFieldJsonEditorMode>(initialMode);
  const mode = controlledMode ?? internalMode;
  const [nodes, setNodes] = useState<JsonTreeNode[]>(() => jsonValueToTree(value));
  const [sourceText, setSourceText] = useState(() => formatJsonText(value));
  const [error, setError] = useState<string | null>(null);
  const lastModeRef = useRef(mode);
  const lastEmittedRef = useRef(JSON.stringify(value ?? null));

  const emitChange = (next: unknown) => {
    lastEmittedRef.current = JSON.stringify(next ?? null);
    onChange?.(next);
  };

  const setMode = (nextMode: CustomFieldJsonEditorMode) => {
    if (controlledMode == null) {
      setInternalMode(nextMode);
    }
    onModeChange?.(nextMode);
  };

  useEffect(() => {
    const serialized = JSON.stringify(value ?? null);
    if (serialized === lastEmittedRef.current) return;
    lastEmittedRef.current = serialized;
    if (canEditAsJsonTree(value)) {
      setNodes(jsonValueToTree(value));
      if (mode === 'kv') {
        setSourceText(formatJsonText(value));
        setError(null);
      }
      return;
    }
    setMode('source');
    setSourceText(typeof value === 'string' ? value : formatJsonText(value));
    setError(null);
  }, [value]);

  useEffect(() => {
    if (controlledMode == null || lastModeRef.current === mode) return;
    const prev = lastModeRef.current;
    lastModeRef.current = mode;
    if (mode === 'source' && prev === 'kv') {
      const objectValue = jsonTreeToValue(nodes);
      setSourceText(formatJsonText(objectValue ?? value));
      setError(null);
      return;
    }
    if (mode === 'kv' && prev === 'source') {
      const parsed = parseJsonText(sourceText);
      if (!parsed.ok) {
        setError(parsed.error);
        lastModeRef.current = prev;
        if (controlledMode != null) onModeChange?.(prev);
        return;
      }
      if (parsed.value != null && !canEditAsJsonTree(parsed.value)) {
        setError('根节点须为 JSON 对象，请继续使用 JSON 源码模式编辑');
        lastModeRef.current = prev;
        if (controlledMode != null) onModeChange?.(prev);
        return;
      }
      setNodes(jsonValueToTree(parsed.value));
      setError(null);
      emitChange(parsed.value);
    }
  }, [mode, controlledMode]);

  const hint = useMemo(
    () => placeholder || '例如：{"优先级": 1, "备注": "加急"}',
    [placeholder],
  );

  const handleModeChange = (nextMode: CustomFieldJsonEditorMode) => {
    if (nextMode === 'source') {
      const objectValue = mode === 'kv' ? jsonTreeToValue(nodes) : value;
      const nextValue = objectValue ?? value;
      setSourceText(formatJsonText(nextValue));
      setError(null);
      setMode('source');
      lastModeRef.current = 'source';
      emitChange(nextValue);
      return;
    }

    const parsed = parseJsonText(sourceText);
    if (!parsed.ok) {
      setError(parsed.error);
      return;
    }
    if (parsed.value != null && !canEditAsJsonTree(parsed.value)) {
      setError('根节点须为 JSON 对象，请继续使用 JSON 源码模式编辑');
      return;
    }
    setNodes(jsonValueToTree(parsed.value));
    setError(null);
    setMode('kv');
    lastModeRef.current = 'kv';
    emitChange(parsed.value);
  };

  const updateNodes = (nextNodes: JsonTreeNode[]) => {
    setNodes(nextNodes);
    const nextValue = jsonTreeToValue(nextNodes);
    setSourceText(formatJsonText(nextValue));
    emitChange(nextValue);
  };

  const handleSourceBlur = () => {
    const parsed = parseJsonText(sourceText);
    if (!parsed.ok) {
      setError(parsed.error);
      emitChange(sourceText);
      return;
    }
    if (parsed.value != null && !canEditAsJsonTree(parsed.value)) {
      setError('根节点须为 JSON 对象，请继续使用 JSON 源码模式编辑');
      emitChange(sourceText);
      return;
    }
    setError(null);
    emitChange(parsed.value);
  };

  const handleFormat = () => {
    const parsed = parseJsonText(sourceText);
    if (!parsed.ok) {
      setError(parsed.error);
      return;
    }
    setSourceText(formatJsonText(parsed.value));
    setError(null);
    emitChange(parsed.value);
  };

  return (
    <div style={{ width: '100%' }}>
      <div
        style={{
          border: `1px solid ${token.colorBorder}`,
          borderRadius: token.borderRadiusLG,
          padding: 16,
          background: token.colorBgContainer,
          width: '100%',
          boxSizing: 'border-box',
        }}
      >
        {showModeToggle ? (
          <div style={{ marginBottom: 12 }}>
            <CustomFieldJsonModeSegmented mode={mode} onChange={handleModeChange} disabled={disabled} />
          </div>
        ) : null}

        {mode === 'kv' ? (
          <>
            <JsonTreeRows nodes={nodes} disabled={disabled} onChange={updateNodes} />
            <Button
              className="custom-field-json-tree__add"
              type="dashed"
              size="small"
              disabled={disabled}
              icon={<PlusOutlined />}
              onClick={() => updateNodes(addJsonTreeChild(nodes, null))}
              style={{ marginTop: 10 }}
            >
              添加一行
            </Button>
          </>
        ) : (
          <>
            <Input.TextArea
              value={sourceText}
              disabled={disabled}
              placeholder={hint}
              rows={6}
              style={{ fontFamily: 'Consolas, Monaco, monospace', fontSize: 13, width: '100%' }}
              onChange={(e) => {
                const text = e.target.value;
                setSourceText(text);
                const parsed = parseJsonText(text);
                if (!parsed.ok) {
                  setError(parsed.error);
                  emitChange(text);
                  return;
                }
                if (parsed.value != null && !canEditAsJsonTree(parsed.value)) {
                  setError('根节点须为 JSON 对象，请继续使用 JSON 源码模式编辑');
                  emitChange(text);
                  return;
                }
                setError(null);
                emitChange(parsed.value);
              }}
              onBlur={handleSourceBlur}
            />
            <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                支持对象、数组等复杂结构；失焦或格式化时自动校验。
              </Typography.Text>
              <Button size="small" disabled={disabled} onClick={handleFormat}>
                格式化
              </Button>
            </div>
          </>
        )}
      </div>

      {error ? (
        <Typography.Text type="danger" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
          {error}
        </Typography.Text>
      ) : null}
    </div>
  );
};
