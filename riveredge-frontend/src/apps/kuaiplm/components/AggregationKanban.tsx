/**
 * 聚合页看板壳（跨项目待办 / 委托看板等）
 * 只读分列卡片，无拖拽改状态；禁止左侧装饰色条。
 */

import React from 'react';
import { Badge, Button, Card, Empty, Space, Spin, Typography, theme } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const { Text } = Typography;

export type AggregationKanbanColumn<T> = {
  id: string;
  title: string;
  items: T[];
  /** 列标题旁圆点色（非左边条） */
  color?: string;
};

export type AggregationKanbanProps<T> = {
  title: React.ReactNode;
  columns: AggregationKanbanColumn<T>[];
  loading?: boolean;
  getItemKey: (item: T) => string;
  renderCard: (item: T) => React.ReactNode;
  onCardClick?: (item: T) => void;
  onRefresh?: () => void;
  toolbarExtra?: React.ReactNode;
  emptyDescription?: string;
};

function AggregationKanbanInner<T>({
  title,
  columns,
  loading,
  getItemKey,
  renderCard,
  onCardClick,
  onRefresh,
  toolbarExtra,
  emptyDescription,
}: AggregationKanbanProps<T>) {
  const { t } = useTranslation();
  const { token } = theme.useToken();

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
        gap: 12,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <Text strong style={{ fontSize: 16 }}>
          {title}
        </Text>
        <Space wrap>
          {toolbarExtra}
          {onRefresh ? (
            <Button icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>
              {t('common.refresh')}
            </Button>
          ) : null}
        </Space>
      </div>

      <Spin spinning={!!loading}>
        <div
          style={{
            display: 'flex',
            gap: 12,
            overflowX: 'auto',
            paddingBottom: 8,
            alignItems: 'stretch',
            minHeight: 420,
          }}
        >
          {columns.map((column) => (
            <div
              key={column.id}
              style={{
                flex: '1 1 280px',
                minWidth: 260,
                maxWidth: 360,
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <Card
                size="small"
                style={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  border: `1px solid ${token.colorBorderSecondary}`,
                  borderRadius: 6,
                  background: token.colorBgContainer,
                }}
                styles={{
                  body: {
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    padding: 12,
                    minHeight: 360,
                  },
                }}
              >
                <div
                  style={{
                    marginBottom: 12,
                    paddingBottom: 10,
                    borderBottom: `1px solid ${token.colorBorderSecondary}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 8,
                  }}
                >
                  <Space size={8}>
                    {column.color ? (
                      <span
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          backgroundColor: column.color,
                          display: 'inline-block',
                          flexShrink: 0,
                        }}
                      />
                    ) : null}
                    <Text strong>{column.title}</Text>
                  </Space>
                  <Badge count={column.items.length} showZero color={column.color || token.colorPrimary} />
                </div>

                <div
                  style={{
                    flex: 1,
                    overflowY: 'auto',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                  }}
                >
                  {column.items.length === 0 ? (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={emptyDescription || t('components.kanban.noData')}
                      style={{ marginTop: 48 }}
                    />
                  ) : (
                    column.items.map((item) => (
                      <Card
                        key={getItemKey(item)}
                        size="small"
                        hoverable={!!onCardClick}
                        onClick={() => onCardClick?.(item)}
                        style={{
                          border: `1px solid ${token.colorBorderSecondary}`,
                          borderRadius: 6,
                          background: token.colorFillAlter,
                          cursor: onCardClick ? 'pointer' : 'default',
                        }}
                        styles={{ body: { padding: '10px 12px' } }}
                      >
                        {renderCard(item)}
                      </Card>
                    ))
                  )}
                </div>
              </Card>
            </div>
          ))}
        </div>
      </Spin>
    </div>
  );
}

export const AggregationKanban = AggregationKanbanInner as <T>(
  props: AggregationKanbanProps<T>,
) => React.ReactElement;
