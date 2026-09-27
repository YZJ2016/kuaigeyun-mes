/**
 * 图表组件
 *
 * 基于@ant-design/charts的报表图表组件
 *
 * @author Luigi Lu
 * @date 2025-01-15
 */

import React from 'react';
import {
  ChartSuspense,
  LazyColumn,
  LazyLine,
  LazyPie,
  LazyScatter,
} from '../../common/lazyAntCharts';
import { ReportComponent } from '../index';

/**
 * 图表组件Props
 */
export interface ChartComponentProps {
  component: ReportComponent;
  data?: any[];
}

/**
 * 图表组件
 */
const ChartComponent: React.FC<ChartComponentProps> = ({ component, data = [] }) => {
  const chartType = component.chartType || 'column';
  const config = component.chartConfig || {};

  const commonConfig = {
    data,
    ...config,
  };

  let chart: React.ReactNode;
  switch (chartType) {
    case 'column':
      chart = <LazyColumn {...commonConfig} />;
      break;
    case 'line':
      chart = <LazyLine {...commonConfig} />;
      break;
    case 'pie':
      chart = <LazyPie {...commonConfig} />;
      break;
    case 'scatter':
      chart = <LazyScatter {...commonConfig} />;
      break;
    default:
      chart = <LazyColumn {...commonConfig} />;
  }
  return <ChartSuspense>{chart}</ChartSuspense>;
};

export default ChartComponent;

