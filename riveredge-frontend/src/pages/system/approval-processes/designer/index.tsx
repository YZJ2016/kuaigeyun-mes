/**
 * 审批流设计器页面
 * 
 * 修改记录：
 * - 修正 CanvasPageTemplate 用法。
 * - 修复翻译 Key。
 * - 修正状态管理：避免在 Render 中直接访问 Ref。
 * - 统一 UniFlowNode 设计语言。
 * - 修复类型错误与 Lint。
 */

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ProForm, ProFormText } from '@ant-design/pro-components';
import { App, Button, Form, Space, theme, Typography } from 'antd';
import { 
  SaveOutlined, CloseOutlined, PlusOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { useNodesState, useEdgesState } from '@ant-design/pro-flow';
import type { Node, Edge } from '@ant-design/pro-flow';
import {
  ReactFlowProvider,
  ReactFlow,
  Background,
  BackgroundVariant,
  addEdge,
  Connection,
} from 'reactflow';
// @ts-ignore
import 'reactflow/dist/style.css';
import {
  getApprovalProcessByUuid,
  updateApprovalProcess,
  publishApprovalProcess,
  getConditionFields,
  getEditableFields,
  ApprovalProcess,
} from '../../../../services/approvalProcess';
import { CanvasPageTemplate } from '../../../../components/layout-templates/CanvasPageTemplate';
import UniFlowNode from '../../../../components/common/uni-flow-node';
import {
  CANVAS_GRID_REACTFLOW,
  CANVAS_GRID_REACTFLOW_FRAMED_INNER,
} from '../../../../components/layout-templates/constants';
import {
  defaultApprovalNodeEditFlags,
  normalizeFlowGraph,
  normalizeNodeData,
  nodeDataToFormValues,
  validateFlowGraph,
} from '../../../../types/approvalFlowSchema';
import {
  APPROVAL_FLOW_EDGE_STYLE,
  applyVerticalLayout,
  enrichApprovalFlowGraph,
} from '../../../../utils/approvalFlowLayout';
import {
  ApprovalNodeForm,
  CcNodeForm,
  ConditionNodeForm,
  mergeFormToNodeData,
} from './properties/NodePropertyForms';

const { useToken } = theme;

const ApprovalProcessDesignerPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const { token } = useToken();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const processUuid = searchParams.get('uuid');
  
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [processData, setProcessData] = useState<ApprovalProcess | null>(null);
  
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [nodeDataMap, setNodeDataMap] = useState<Record<string, any>>({});

  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [nodeConfigForm] = Form.useForm();
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);
  const [conditionFieldOptions, setConditionFieldOptions] = useState<{ label: string; value: string }[]>([]);
  const [editableFieldOptions, setEditableFieldOptions] = useState<{ label: string; value: string }[]>([]);

  useEffect(() => {
    const code = processData?.code;
    if (!code) return;
    getConditionFields(code)
      .then((res) => {
        setConditionFieldOptions(
          (res.fields || []).map((f) => ({ label: f.label || f.field, value: f.field })),
        );
      })
      .catch(() => setConditionFieldOptions([]));
    getEditableFields(code)
      .then((res) => {
        setEditableFieldOptions(
          (res.fields || []).map((f) => ({ label: f.label || f.field, value: f.field })),
        );
      })
      .catch(() => setEditableFieldOptions([]));
  }, [processData?.code]);

  const loadProcessData = useCallback(async () => {
    if (!processUuid) return;
    try {
      setLoading(true);
      const data = await getApprovalProcessByUuid(processUuid);
      setProcessData(data);
      let nodesData: Node[] = [];
      let edgesData: Edge[] = [];
      const graphSource = (data as ApprovalProcess & { draft_nodes?: { nodes?: Node[]; edges?: Edge[] } }).draft_nodes
        && (data as ApprovalProcess & { draft_nodes?: { nodes?: Node[] } }).draft_nodes?.nodes?.length
        ? (data as ApprovalProcess & { draft_nodes: { nodes: Node[]; edges?: Edge[] } }).draft_nodes
        : data.nodes;
      if (graphSource && typeof graphSource === 'object') {
        nodesData = (graphSource as any).nodes ?? [];
        edgesData = (graphSource as any).edges ?? [];
      }
      if (nodesData.length === 0) {
        nodesData = [
          { id: 'start', type: 'start', position: { x: 0, y: 0 }, data: { label: t('pages.approval.designer.start') } },
          { id: 'end', type: 'end', position: { x: 0, y: 0 }, data: { label: t('pages.approval.designer.end') } },
        ];
        edgesData = [{ id: 'e-start-end', source: 'start', target: 'end', type: 'smoothstep' }];
      }
      
      const initialDataMap: Record<string, any> = {};
      nodesData.forEach(node => {
        // 存规范化节点数据，不要存表单临时字段 approvers/roles（否则会盖掉后续改动）
        initialDataMap[node.id] = normalizeNodeData(String(node.type), { ...(node.data as object) });
      });
      setNodeDataMap(initialDataMap);

      const normalizedEdges = edgesData.map((e, i) => ({
        ...e,
        id: e.id || `e-${e.source}-${e.target}-${i}`,
        type: e.type || 'default',
      }));
      const { nodes: laidOutNodes, edges: laidOutEdges } = enrichApprovalFlowGraph(
        nodesData as Node[],
        normalizedEdges as Edge[],
        { relayout: true },
      );
      setNodes(laidOutNodes as any);
      setEdges(laidOutEdges as any);
    } catch (error: any) {
      messageApi.error(error.message || t('common.loadFailed'));
      navigate('/system/approval-processes');
    } finally {
      setLoading(false);
    }
  }, [processUuid, messageApi, navigate, t, setNodes, setEdges]);

  useEffect(() => {
    const init = async () => {
      if (processUuid) {
        await loadProcessData();
      }
    };
    init();
  }, [processUuid, loadProcessData]);

  const buildNewNodeSeed = useCallback(
    (type: 'approval' | 'cc' | 'condition', label: string) => {
      if (type === 'approval') {
        return { label, ...defaultApprovalNodeEditFlags() };
      }
      return { label };
    },
    [],
  );

  const addNextNodeFromNode = useCallback((sourceNodeId: string, type: 'approval' | 'cc' | 'condition') => {
    const newId = `${type}_${Math.random().toString(36).substr(2, 9)}`;
    const label = t(`pages.approval.designer.${type}Node`);
    const data = buildNewNodeSeed(type, label);
    const newNode: Node = { id: newId, type, position: { x: 0, y: 0 }, data };
    const outEdges = edges.filter((e) => e.source === sourceNodeId);
    let newEdges = edges.filter((e) => e.source !== sourceNodeId);
    newEdges.push({ id: `e-${sourceNodeId}-${newId}`, source: sourceNodeId, target: newId, type: 'default' });
    outEdges.forEach((e, i) => {
      newEdges.push({ id: `e-${newId}-${e.target}-${i}`, source: newId, target: e.target, type: 'default' });
    });
    
    setNodeDataMap(prev => ({ ...prev, [newId]: data }));
    const newNodes = [...nodes, newNode];
    setNodes(enrichApprovalFlowGraph(newNodes as Node[], newEdges as Edge[], { relayout: true }).nodes as any);
    setEdges(newEdges);
  }, [nodes, edges, setNodes, setEdges, t, buildNewNodeSeed]);

  const addBranchFromConditionNode = useCallback((type: 'approval' | 'cc' | 'condition') => {
    if (!selectedNode || selectedNode.type !== 'condition') return;
    const sourceNodeId = selectedNode.id;
    const newId = `${type}_${Math.random().toString(36).substr(2, 9)}`;
    const label = t(`pages.approval.designer.${type}Node`);
    const data = buildNewNodeSeed(type, label);
    const newNode: Node = { id: newId, type, position: { x: 0, y: 0 }, data };
    const newEdges = [
      ...edges,
      { id: `e-${sourceNodeId}-${newId}`, source: sourceNodeId, target: newId, type: 'default' },
      { id: `e-${newId}-end`, source: newId, target: 'end', type: 'default' },
    ];
    
    setNodeDataMap(prev => ({ ...prev, [newId]: data }));
    const newNodes = [...nodes, newNode];
    setNodes(enrichApprovalFlowGraph(newNodes as Node[], newEdges as Edge[], { relayout: true }).nodes as any);
    setEdges(newEdges);
  }, [selectedNode, nodes, edges, setNodes, setEdges, t, buildNewNodeSeed]);

  const addNodeOnEdge = useCallback((type: 'approval' | 'cc' | 'condition') => {
    if (!selectedEdge) return;
    const edge = selectedEdge;
    const newId = `${type}_${Math.random().toString(36).substr(2, 9)}`;
    const label = t(`pages.approval.designer.${type}Node`);
    const data = buildNewNodeSeed(type, label);
    const newNode: Node = { id: newId, type, position: { x: 0, y: 0 }, data };
    const newEdges = edges.filter((e) => e.id !== edge.id).concat([
      { id: `e-${edge.source}-${newId}`, source: edge.source, target: newId, type: 'default' },
      { id: `e-${newId}-${edge.target}`, source: newId, target: edge.target, type: 'default' },
    ]);
    
    setNodeDataMap(prev => ({ ...prev, [newId]: data }));
    const newNodes = [...nodes, newNode];
    setNodes(enrichApprovalFlowGraph(newNodes as Node[], newEdges as Edge[], { relayout: true }).nodes as any);
    setEdges(newEdges);
    setSelectedEdge(null);
  }, [selectedEdge, nodes, edges, setNodes, setEdges, t, buildNewNodeSeed]);

  const onConnect = useCallback((params: Connection) => {
    setEdges((eds) => addEdge({ ...params, type: 'default' }, eds));
  }, [setEdges]);

  /** 刷入右侧表单最新值并组装可提交流程图；校验失败返回 null */
  const buildPersistGraph = useCallback(() => {
    const livePatch =
      selectedNode &&
      (selectedNode.type === 'approval' || selectedNode.type === 'cc' || selectedNode.type === 'condition')
        ? {
            [selectedNode.id]: (() => {
              const merged = mergeFormToNodeData(
                String(selectedNode.type),
                nodeConfigForm.getFieldsValue(true) as Record<string, unknown>,
              );
              delete merged.approvers;
              delete merged.roles;
              return { ...nodeDataMap[selectedNode.id], ...merged };
            })(),
          }
        : {};
    const latestMap = { ...nodeDataMap, ...livePatch };
    const strippedNodes = applyVerticalLayout(
      nodes.map((node) => {
        const merged = mergeFormToNodeData(String(node.type), {
          ...node.data,
          ...latestMap[node.id],
        });
        delete merged.approvers;
        delete merged.roles;
        const data = normalizeNodeData(String(node.type), merged);
        return {
          id: node.id,
          type: node.type,
          position: node.position,
          data,
        };
      }) as Node[],
      edges as Edge[],
    ).map((node) => ({
      id: node.id,
      type: node.type,
      position: node.position,
      data: node.data,
    }));
    const graph = normalizeFlowGraph({ nodes: strippedNodes, edges });
    const validationErrors = validateFlowGraph(graph);
    if (validationErrors.length > 0) {
      messageApi.error(validationErrors.join('；'));
      return null;
    }
    return { graph, latestMap, livePatch };
  }, [selectedNode, nodeConfigForm, nodeDataMap, nodes, edges, messageApi]);

  const handleSave = async () => {
    if (!processUuid || !processData) return;
    try {
      setSaving(true);
      const built = buildPersistGraph();
      if (!built) return;
      if (Object.keys(built.livePatch).length > 0) {
        setNodeDataMap(built.latestMap);
      }
      await updateApprovalProcess(processUuid, { ...processData, nodes: built.graph });
      messageApi.success(t('common.saveSuccess'));
      await loadProcessData();
    } catch (error: any) {
      messageApi.error(error.message || t('common.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  /** 一次发布：先落当前编辑再 publish，不必先点保存 */
  const handlePublish = async () => {
    if (!processUuid || !processData) return;
    try {
      setSaving(true);
      const built = buildPersistGraph();
      if (!built) return;
      if (Object.keys(built.livePatch).length > 0) {
        setNodeDataMap(built.latestMap);
      }
      await updateApprovalProcess(processUuid, { ...processData, nodes: built.graph });
      await publishApprovalProcess(processUuid);
      messageApi.success(t('pages.approval.designer.publishSuccess'));
      await loadProcessData();
    } catch (error: any) {
      messageApi.error(error.message || t('pages.approval.designer.publishFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleOrganizeNodes = useCallback(() => {
    const laid = applyVerticalLayout(nodes as Node[], edges as Edge[]);
    const enriched = enrichApprovalFlowGraph(laid, edges as Edge[], { relayout: false });
    setNodes(enriched.nodes as any);
    setEdges(enriched.edges as any);
  }, [nodes, edges, setNodes, setEdges]);

  const { flowNodes, flowEdges } = useMemo(() => {
    const merged = (nodes as Node[]).map((n) => ({
      ...n,
      selected: selectedNode?.id === n.id,
      data: { ...n.data, ...nodeDataMap[n.id] },
    }));
    const { nodes: laid, edges: enriched } = enrichApprovalFlowGraph(merged, edges as Edge[], {
      relayout: true,
    });
    const branchOrdinal: Record<string, number> = {};
    return {
      flowNodes: laid,
      flowEdges: enriched.map((e) => {
        const sourceNode = merged.find((n) => n.id === e.source);
        let edgeLabel: string | undefined;
        if (sourceNode?.type === 'condition') {
          const idx = branchOrdinal[e.source] || 0;
          branchOrdinal[e.source] = idx + 1;
          const conds = (sourceNode.data as { conditions?: Array<{ label?: string }> }).conditions;
          const text = String(conds?.[idx]?.label || '').trim();
          if (text) edgeLabel = text;
        }
        return {
          ...e,
          label: edgeLabel,
          labelStyle: edgeLabel ? { fill: token.colorText, fontSize: 12 } : undefined,
          labelBgStyle: edgeLabel ? { fill: token.colorBgContainer } : undefined,
          labelBgPadding: edgeLabel ? ([4, 2] as [number, number]) : undefined,
          labelBgBorderRadius: edgeLabel ? 4 : undefined,
          type: 'default',
          style: {
            ...APPROVAL_FLOW_EDGE_STYLE,
            stroke: selectedEdge?.id === e.id ? token.colorPrimary : APPROVAL_FLOW_EDGE_STYLE.stroke,
            strokeWidth: selectedEdge?.id === e.id ? 3 : APPROVAL_FLOW_EDGE_STYLE.strokeWidth,
            ...(e.style || {}),
          },
        };
      }),
    };
  }, [nodes, edges, nodeDataMap, selectedNode, selectedEdge, token.colorPrimary, token.colorText, token.colorBgContainer]);

  const nodeTypes = useMemo(() => ({
    start: (p: any) => <UniFlowNode {...p} type="start" selected={p.selected} />,
    end: (p: any) => <UniFlowNode {...p} type="end" selected={p.selected} />,
    approval: (p: any) => <UniFlowNode {...p} type="approval" selected={p.selected} />,
    cc: (p: any) => <UniFlowNode {...p} type="cc" selected={p.selected} />,
    condition: (p: any) => <UniFlowNode {...p} type="condition" selected={p.selected} />,
  }), []);

  const toolbar = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <Space>
        <span style={{ color: token.colorTextSecondary, fontSize: 13, marginRight: 8 }}>
          {t('pages.approval.designer.selectedNode')}: <Typography.Text strong>{selectedNode ? (nodeDataMap[selectedNode.id]?.label || selectedNode.id) : t('pages.approval.designer.noneSelected')}</Typography.Text>
        </span>
        <Button 
          type="primary" 
          icon={<PlusOutlined />} 
          disabled={!selectedNode || selectedNode.id === 'end'}
          onClick={() => selectedNode && addNextNodeFromNode(selectedNode.id, 'approval')}
        >
          {t('pages.approval.designer.addApproval')}
        </Button>
        <Button 
          type="primary" 
          icon={<PlusOutlined />} 
          disabled={!selectedNode || selectedNode.id === 'end'}
          onClick={() => selectedNode && addNextNodeFromNode(selectedNode.id, 'cc')}
        >
          {t('pages.approval.designer.addCC')}
        </Button>
        <Button 
          type="primary" 
          icon={<PlusOutlined />} 
          disabled={!selectedNode || selectedNode.id === 'end'}
          onClick={() => selectedNode && addNextNodeFromNode(selectedNode.id, 'condition')}
        >
          {t('pages.approval.designer.addCondition')}
        </Button>
        <Button 
          type="primary" 
          ghost 
          disabled={!selectedNode || selectedNode.type !== 'condition'}
          onClick={() => addBranchFromConditionNode('approval')}
        >
          {t('pages.approval.designer.addBranch')}
        </Button>
        <Button 
          danger 
          icon={<DeleteOutlined />} 
          disabled={!selectedNode || selectedNode.id === 'start' || selectedNode.id === 'end'}
          onClick={() => { 
            if (!selectedNode) return;
            const newDataMap = { ...nodeDataMap };
            delete newDataMap[selectedNode.id];
            setNodeDataMap(newDataMap);
            setNodes(nodes.filter((n) => n.id !== selectedNode.id)); 
            setEdges(edges.filter((e) => e.source !== selectedNode.id && e.target !== selectedNode.id)); 
            setSelectedNode(null); 
          }}
        >
          {t('common.delete')}
        </Button>
        <Button
          icon={<ReloadOutlined />}
          disabled={nodes.length === 0}
          onClick={handleOrganizeNodes}
        >
          {t('pages.approval.designer.organizeNodes')}
        </Button>
        {selectedEdge && (
          <Space>
            <Button onClick={() => addNodeOnEdge('approval')}>{t('pages.approval.designer.addApproval')}</Button>
            <Button onClick={() => addNodeOnEdge('cc')}>{t('pages.approval.designer.addCC')}</Button>
            <Button onClick={() => addNodeOnEdge('condition')}>{t('pages.approval.designer.addCondition')}</Button>
            <Button danger icon={<DeleteOutlined />} onClick={() => { setEdges(edges.filter(e => e.id !== selectedEdge.id)); setSelectedEdge(null); }}>{t('pages.approval.designer.deleteEdge')}</Button>
          </Space>
        )}
      </Space>
      <Space>
        <Button loading={saving} onClick={() => void handlePublish()}>
          {t('pages.approval.designer.publishDraft')}
        </Button>
        <Button icon={<CloseOutlined />} onClick={() => navigate('/system/approval-processes')}>{t('common.close')}</Button>
        <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => void handleSave()}>{t('common.save')}</Button>
      </Space>
    </div>
  );

  const canvas = (
    <div style={{ width: '100%', height: '100%', ...CANVAS_GRID_REACTFLOW_FRAMED_INNER }}>
      <ReactFlow
        nodes={flowNodes as any}
        edges={flowEdges}
        defaultEdgeOptions={{ type: 'default', style: { ...APPROVAL_FLOW_EDGE_STYLE } }}
        nodesDraggable={false}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        nodeTypes={nodeTypes}
        onNodeClick={(_, node) => {
          setSelectedNode(node); setSelectedEdge(null);
          const raw = { ...(node.data || {}), ...(nodeDataMap[node.id] || {}) };
          delete (raw as Record<string, unknown>).approvers;
          delete (raw as Record<string, unknown>).roles;
          const formValues = nodeDataToFormValues(normalizeNodeData(String(node.type), raw));
          nodeConfigForm.resetFields();
          nodeConfigForm.setFieldsValue({ label: formValues.label || node.id, ...formValues });
        }}
        onEdgeClick={(_, edge) => { setSelectedEdge(edge); setSelectedNode(null); }}
        onPaneClick={() => { setSelectedNode(null); setSelectedEdge(null); }}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1.0 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background 
          variant={CANVAS_GRID_REACTFLOW.variant as BackgroundVariant} 
          color={CANVAS_GRID_REACTFLOW.color} 
          gap={CANVAS_GRID_REACTFLOW.gap} 
          size={CANVAS_GRID_REACTFLOW.size} 
        />
      </ReactFlow>
    </div>
  );

  const conditionBranchCount = selectedNode?.type === 'condition'
    ? edges.filter((e) => e.source === selectedNode.id).length
    : 0;

  const conditionBranchTargets = selectedNode?.type === 'condition'
    ? edges
        .filter((e) => e.source === selectedNode.id)
        .map((e) => {
          const target = nodes.find((n) => n.id === e.target);
          const data = {
            ...(target?.data || {}),
            ...(nodeDataMap[e.target] || {}),
          } as { label?: string };
          return {
            nodeId: String(e.target),
            label: String(data.label || e.target || ''),
          };
        })
    : [];

  const rightPanel = selectedNode && (selectedNode.type === 'approval' || selectedNode.type === 'cc' || selectedNode.type === 'condition') ? {
    title: t('pages.approval.designer.nodeConfig'),
    children: (
      <ProForm form={nodeConfigForm} submitter={false} onValuesChange={() => {
        if (!selectedNode) return;
        // 用 getFieldsValue(true) 拿完整表单（含 ProFormDependency 内字段），避免 allValues 缺 approvers
        const values = nodeConfigForm.getFieldsValue(true) as Record<string, unknown>;
        const merged = mergeFormToNodeData(String(selectedNode.type), values);
        setNodeDataMap((prev) => {
          const nextNode = { ...prev[selectedNode.id], ...merged };
          delete nextNode.approvers;
          delete nextNode.roles;
          return { ...prev, [selectedNode.id]: nextNode };
        });
        setNodes((nds) =>
          nds.map((n) =>
            n.id === selectedNode.id
              ? { ...n, data: { ...n.data, ...merged } }
              : n,
          ) as any,
        );
      }}>
        <ProFormText name="label" label={t('pages.approval.designer.nodeLabel')} rules={[{ required: true }]} />
        {selectedNode.type === 'approval' && (
          <ApprovalNodeForm editableFieldOptions={editableFieldOptions} />
        )}
        {selectedNode.type === 'cc' && <CcNodeForm />}
        {selectedNode.type === 'condition' && (
          <ConditionNodeForm
            branchCount={conditionBranchCount}
            fieldOptions={conditionFieldOptions}
            branchTargets={conditionBranchTargets}
          />
        )}
      </ProForm>
    )
  } : undefined;

  if (loading) return <CanvasPageTemplate toolbar={null} canvas={<div style={{ height: 600 }} />} functionalTitle={t('pages.approval.designer.title')} />;

  return (
    <CanvasPageTemplate
      functionalTitle={`${t('pages.approval.designer.title')}: ${processData?.name || ''}`}
      toolbar={toolbar}
      canvas={canvas}
      rightPanel={rightPanel}
    />
  );
};

const ApprovalProcessDesignerPageWrapper: React.FC = () => (
  <ReactFlowProvider>
    <App>
      <ApprovalProcessDesignerPage />
    </App>
  </ReactFlowProvider>
);

export default ApprovalProcessDesignerPageWrapper;
