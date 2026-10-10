import React, { useEffect, useMemo, useState } from 'react';
import { Empty, Typography } from 'antd';
import { RightOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { MarkerTag } from '../../../../constants/statusBadges';
import { getPipelineGraph, type PipelineGraph } from '../../services/kuaiiot';
import { translateConnectionType, translateMapTarget, translatePipelineStatus, formatIotTagLabel } from '../../constants/formOptions';
import './index.less';

type PipelineNode = PipelineGraph['nodes'][number];

const STAGE_ORDER = ['connection', 'device', 'tag', 'equipment'] as const;
type StageKey = (typeof STAGE_ORDER)[number];

const STAGE_I18N: Record<StageKey, string> = {
  connection: 'app.kuaiiot.pipeline.connections',
  device: 'app.kuaiiot.pipeline.devices',
  tag: 'app.kuaiiot.pipeline.tags',
  equipment: 'app.kuaiiot.pipeline.equipment',
};

function markerColor(status: string): string {
  if (['healthy', 'online', 'enabled', 'bound'].includes(status)) return 'success';
  if (['offline', 'unhealthy', 'disabled'].includes(status)) return 'default';
  if (status === 'open') return 'error';
  return 'processing';
}

function buildAdjacency(edges: PipelineGraph['edges']) {
  const forward = new Map<string, string[]>();
  const backward = new Map<string, string[]>();
  for (const edge of edges) {
    if (!forward.has(edge.source)) forward.set(edge.source, []);
    if (!backward.has(edge.target)) backward.set(edge.target, []);
    forward.get(edge.source)!.push(edge.target);
    backward.get(edge.target)!.push(edge.source);
  }
  return { forward, backward };
}

function collectRelated(
  seedId: string,
  forward: Map<string, string[]>,
  backward: Map<string, string[]>,
): Set<string> {
  const related = new Set<string>([seedId]);
  const queue = [seedId];
  while (queue.length) {
    const current = queue.shift()!;
    for (const next of [...(forward.get(current) ?? []), ...(backward.get(current) ?? [])]) {
      if (related.has(next)) continue;
      related.add(next);
      queue.push(next);
    }
  }
  return related;
}

const PipelinePage: React.FC = () => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [graph, setGraph] = useState<PipelineGraph | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getPipelineGraph();
        if (!cancelled) setGraph(data);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const groupedNodes = useMemo(() => {
    const groups: Record<StageKey, PipelineNode[]> = {
      connection: [],
      device: [],
      tag: [],
      equipment: [],
    };
    for (const node of graph?.nodes ?? []) {
      if ((STAGE_ORDER as readonly string[]).includes(node.node_type)) {
        groups[node.node_type as StageKey].push(node);
      }
    }
    return groups;
  }, [graph]);

  const adjacency = useMemo(() => buildAdjacency(graph?.edges ?? []), [graph]);

  const relatedIds = useMemo(() => {
    if (!selectedId) return null;
    return collectRelated(selectedId, adjacency.forward, adjacency.backward);
  }, [selectedId, adjacency]);

  const summary = graph?.summary ?? {};
  const metrics = [
    { key: 'connections', label: t('app.kuaiiot.pipeline.connections'), value: summary.connections ?? 0 },
    { key: 'devices', label: t('app.kuaiiot.pipeline.devices'), value: summary.devices ?? 0 },
    { key: 'tags', label: t('app.kuaiiot.pipeline.tags'), value: summary.tags ?? 0 },
    { key: 'bound', label: t('app.kuaiiot.pipeline.boundDevices'), value: summary.bound_devices ?? 0 },
    { key: 'alerts', label: t('app.kuaiiot.pipeline.openAlerts'), value: summary.open_alerts ?? 0 },
  ];

  const toggleSelect = (id: string) => {
    setSelectedId((prev) => (prev === id ? null : id));
  };

  const renderNodeRow = (node: PipelineNode) => {
    const active = selectedId === node.id;
    const dimmed = relatedIds != null && !relatedIds.has(node.id);
    const related = relatedIds != null && relatedIds.has(node.id) && !active;
    const secondary =
      node.node_type === 'device'
        ? String(node.meta?.code ?? '')
        : node.node_type === 'connection'
          ? translateConnectionType(t, String(node.meta?.connection_type ?? ''))
          : node.node_type === 'equipment'
            ? ''
            : '';
    const tagKey = node.node_type === 'tag' ? String(node.meta?.tag_key ?? '') : '';
    const tagName = node.node_type === 'tag' ? String(node.meta?.name ?? '') : '';
    const primaryLabel =
      node.node_type === 'tag'
        ? tagName
          ? formatIotTagLabel(tagName, tagKey)
          : node.label
        : node.label;
    const tagTarget =
      node.node_type === 'tag' && node.meta?.map_target
        ? `${t('app.kuaiiot.pipeline.writeback')} ${translateMapTarget(
            t,
            String(node.meta.map_target),
            tagName,
          )}`
        : '';

    return (
      <button
        type="button"
        key={node.id}
        className={[
          'kuaiiot-pipeline-row',
          active ? 'is-active' : '',
          related ? 'is-related' : '',
          dimmed ? 'is-dimmed' : '',
        ]
          .filter(Boolean)
          .join(' ')}
        onClick={() => toggleSelect(node.id)}
        title={node.label}
      >
        <span className="kuaiiot-pipeline-row-main">
          <span className="kuaiiot-pipeline-row-label">{primaryLabel}</span>
          {tagTarget ? (
            <span className="kuaiiot-pipeline-row-meta">→ {tagTarget}</span>
          ) : secondary ? (
            <span className="kuaiiot-pipeline-row-meta">{secondary}</span>
          ) : null}
        </span>
        <MarkerTag color={markerColor(node.status)} className="kuaiiot-pipeline-row-status">
          {translatePipelineStatus(t, node.status)}
        </MarkerTag>
      </button>
    );
  };

  const renderStage = (stage: StageKey, index: number) => {
    const nodes = groupedNodes[stage];
    const visible =
      relatedIds == null
        ? nodes
        : nodes.filter((node) => relatedIds.has(node.id));
    const title = t(STAGE_I18N[stage]);

    return (
      <React.Fragment key={stage}>
        {index > 0 ? (
          <div className="kuaiiot-pipeline-flow" aria-hidden>
            <RightOutlined />
          </div>
        ) : null}
        <section className="kuaiiot-pipeline-stage">
          <header className="kuaiiot-pipeline-stage-header">
            <Typography.Text strong>{title}</Typography.Text>
            <span className="kuaiiot-pipeline-stage-count">
              {relatedIds ? `${visible.length}/${nodes.length}` : nodes.length}
            </span>
          </header>
          <div className="kuaiiot-pipeline-stage-body">
            {loading ? (
              <div className="kuaiiot-pipeline-empty">{t('common.loading')}</div>
            ) : visible.length === 0 ? (
              <div className="kuaiiot-pipeline-empty">
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    stage === 'equipment'
                      ? t('app.kuaiiot.pipeline.equipmentEmpty')
                      : relatedIds
                        ? t('app.kuaiiot.pipeline.noRelated')
                        : t('common.noData')
                  }
                />
                {stage === 'equipment' && !relatedIds ? (
                  <Typography.Paragraph type="secondary" className="kuaiiot-pipeline-empty-hint">
                    {t('app.kuaiiot.pipeline.equipmentEmptyHint')}
                  </Typography.Paragraph>
                ) : null}
              </div>
            ) : (
              visible.map(renderNodeRow)
            )}
          </div>
        </section>
      </React.Fragment>
    );
  };

  return (
    <ListPageTemplate fillMain>
      <div className="kuaiiot-pipeline">
        <div className="kuaiiot-pipeline-metrics">
          {metrics.map((item) => (
            <div key={item.key} className="kuaiiot-pipeline-metric">
              <div className="kuaiiot-pipeline-metric-value">{loading ? '—' : item.value}</div>
              <div className="kuaiiot-pipeline-metric-label">{item.label}</div>
            </div>
          ))}
        </div>

        <div className="kuaiiot-pipeline-toolbar">
          <Typography.Text type="secondary">{t('app.kuaiiot.pipeline.hint')}</Typography.Text>
          {selectedId ? (
            <button type="button" className="kuaiiot-pipeline-clear" onClick={() => setSelectedId(null)}>
              {t('app.kuaiiot.pipeline.clearSelection')}
            </button>
          ) : (
            <Typography.Text type="secondary">{t('app.kuaiiot.pipeline.selectHint')}</Typography.Text>
          )}
        </div>

        <div className="kuaiiot-pipeline-stages">{STAGE_ORDER.map(renderStage)}</div>
      </div>
    </ListPageTemplate>
  );
};

export default PipelinePage;
