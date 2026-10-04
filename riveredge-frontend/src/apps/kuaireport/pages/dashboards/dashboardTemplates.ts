/**
 * 大屏官方模板。布局是现网流式画布，数据组件用手动示例值，不绑数据源。
 */

import type { DashboardWidget } from './DashboardWidgets';

export interface DashboardTemplate {
  key: string;
  name: string;
  description: string;
  widgets: DashboardWidget[];
}

const THEME = {
  background: '#00D4FF',
  gradient: 'cyanRadial',
  image_url: '',
  image_file_uuid: '',
  image_fit: 'cover',
  image_position: 'center',
  mask_color: '#000000',
  mask_opacity: 0,
  texture: 'grid',
  padding: { top: 16, right: 16, bottom: 16, left: 16 },
};

const LAYOUT = {
  mode: 'canvas',
  compose: 'flow',
  width: 1920,
  height: 1080,
  fit: 'adaptive',
};

function piece(
  id: string,
  type: string,
  title: string,
  height: number,
  options: Record<string, unknown>,
): DashboardWidget {
  return {
    id,
    type,
    title,
    refresh_seconds: 30,
    layout: { x: 0, y: 0, w: 1888, h: height },
    options,
  };
}

function header(prefix: string, title: string): DashboardWidget[] {
  const root = `${prefix}-header`;
  return [
    piece(root, 'columns', '', 72, {
      columns: 3,
      columnRatios: '1:2:1',
      gap: 12,
      fillHeight: 'off',
      minHeight: 64,
      palette_label: '分栏容器',
    }),
    piece(`${prefix}-logo`, 'image', '', 56, {
      role: 'logo',
      source: 'site',
      text: '',
      textSize: 18,
      textAlign: 'right',
      width: 140,
      height: 48,
      align: 'left',
      fillEnabled: 'off',
      fillPadding: 6,
      fillRadius: 4,
      palette_label: '公司LOGO',
      parent_id: root,
      slot: '0',
    }),
    piece(`${prefix}-title`, 'title', title, 56, {
      variant: 'bevel',
      subtitle: '',
      animate: 'on',
      palette_label: '看板标题',
      parent_id: root,
      slot: '1',
    }),
    piece(`${prefix}-clock`, 'clock', '', 56, {
      palette_label: '时间',
      parent_id: root,
      slot: '2',
    }),
    piece(`${prefix}-marquee`, 'marquee', '', 40, {
      text: '欢迎使用生产看板',
      color: '#ffffff',
      palette_label: '跑马灯',
    }),
  ];
}

function metric(id: string, parent: string, slot: string, title: string, value: number, unit: string): DashboardWidget {
  return piece(id, 'metric', title, 140, {
    indicatorType: 'number',
    valueSource: 'manual',
    value,
    unit,
    variant: 'bevel',
    color: '#00d4ff',
    palette_label: '指标卡',
    parent_id: parent,
    slot,
  });
}

export const DASHBOARD_TEMPLATES: DashboardTemplate[] = [
  {
    key: 'production',
    name: '生产综合看板',
    description: '标题、四项指标、趋势图与明细表',
    widgets: [
      ...header('production', '生产综合看板'),
      piece('production-kpis', 'columns', '', 150, {
        columns: 4,
        columnRatios: '1:1:1:1',
        gap: 12,
        fillHeight: 'off',
        minHeight: 140,
        palette_label: '分栏容器',
      }),
      metric('production-m1', 'production-kpis', '0', '当日产量', 1280, '件'),
      metric('production-m2', 'production-kpis', '1', '完成率', 86, '%'),
      metric('production-m3', 'production-kpis', '2', '在制工单', 24, '单'),
      metric('production-m4', 'production-kpis', '3', '异常', 3, '项'),
      piece('production-body', 'columns', '', 640, {
        columns: 2,
        columnRatios: '1:1',
        gap: 12,
        fillHeight: 'on',
        minHeight: 280,
        palette_label: '分栏容器',
      }),
      piece('production-chart', 'chart', '产量趋势', 280, {
        chart_type: 'line',
        palette: 'theme',
        fillHeight: 'on',
        height: 280,
        valueSource: 'manual',
        x_field: 'x',
        y_field: 'y',
        palette_label: '图表',
        parent_id: 'production-body',
        slot: '0',
      }),
      piece('production-table', 'table', '生产明细', 240, {
        height: 240,
        fillHeight: 'on',
        themeMode: 'dark',
        displayMode: 'table',
        columnKeys: '',
        scrollMode: 'none',
        valueSource: 'manual',
        palette_label: '表格',
        parent_id: 'production-body',
        slot: '1',
      }),
    ],
  },
  {
    key: 'equipment',
    name: '设备运行看板',
    description: '设备卡片与点检明细左右分栏',
    widgets: [
      ...header('equipment', '设备运行看板'),
      piece('equipment-body', 'columns', '', 720, {
        columns: 2,
        columnRatios: '1:1',
        gap: 12,
        fillHeight: 'on',
        minHeight: 320,
        palette_label: '分栏容器',
      }),
      piece('equipment-cards', 'card_list', '设备状态', 320, {
        height: 320,
        orientation: 'vertical',
        scrollAxis: 'x',
        fillHeight: 'on',
        cardWidth: 196,
        scrollMode: 'auto',
        scrollInterval: 3000,
        valueSource: 'manual',
        palette_label: '卡片列表',
        parent_id: 'equipment-body',
        slot: '0',
      }),
      piece('equipment-table', 'table', '点检明细', 240, {
        height: 240,
        fillHeight: 'on',
        themeMode: 'dark',
        displayMode: 'table',
        scrollMode: 'none',
        valueSource: 'manual',
        palette_label: '表格',
        parent_id: 'equipment-body',
        slot: '1',
      }),
    ],
  },
  {
    key: 'quality',
    name: '质量仓储看板',
    description: '质量指标、趋势与仓储进度',
    widgets: [
      ...header('quality', '质量仓储看板'),
      piece('quality-stack', 'columns', '', 760, {
        rows: 3,
        rowRatios: '1:2:2',
        gap: 12,
        fillHeight: 'on',
        minHeight: 480,
        palette_label: '分行容器',
      }),
      piece('quality-kpis', 'columns', '', 140, {
        columns: 3,
        columnRatios: '1:1:1',
        gap: 12,
        fillHeight: 'off',
        minHeight: 140,
        palette_label: '分栏容器',
        parent_id: 'quality-stack',
        slot: '0',
      }),
      metric('quality-m1', 'quality-kpis', '0', '合格率', 98, '%'),
      metric('quality-m2', 'quality-kpis', '1', '待检', 16, '批'),
      metric('quality-m3', 'quality-kpis', '2', '不合格', 2, '批'),
      piece('quality-chart', 'chart', '质量趋势', 280, {
        chart_type: 'column',
        palette: 'theme',
        fillHeight: 'on',
        height: 280,
        valueSource: 'manual',
        x_field: 'x',
        y_field: 'y',
        palette_label: '图表',
        parent_id: 'quality-stack',
        slot: '1',
      }),
      piece('quality-progress', 'resource_list', '仓储进度', 220, {
        fillHeight: 'on',
        scrollMode: 'page',
        scrollInterval: 5000,
        valueSource: 'manual',
        palette_label: '进度列表',
        parent_id: 'quality-stack',
        slot: '2',
      }),
    ],
  },
];

export function templateCreateBody(key: string): {
  code: string;
  name: string;
  layout_config: Record<string, unknown>;
  widgets_config: DashboardWidget[];
  theme_config: Record<string, unknown>;
  tv_config: Record<string, unknown>;
} | null {
  const template = DASHBOARD_TEMPLATES.find((item) => item.key === key);
  if (!template) return null;
  return {
    code: `${template.key}_${Date.now()}`.slice(0, 50),
    name: template.name,
    layout_config: LAYOUT,
    widgets_config: template.widgets,
    theme_config: THEME,
    tv_config: { rotate_seconds: 60 },
  };
}
