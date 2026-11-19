import React from 'react';

import { Typography } from 'antd';

import type { TFunction } from 'i18next';

import type { DefectLedgerItem } from '../../../services/quality-improvement';

import { ROUTES } from '../../../constants/routes';

import { UniTableStackedPrimaryCell } from '../../../../../components/uni-table/stackedPrimaryColumn';



export const SOURCE_INSPECTION_TYPE_I18N = {

  incoming: 'app.kuaizhizao.quality.nc.sourceInspection.type.incoming',

  process: 'app.kuaizhizao.quality.nc.sourceInspection.type.process',

  finished: 'app.kuaizhizao.quality.nc.sourceInspection.type.finished',

  reporting: 'app.kuaizhizao.quality.nc.sourceInspection.type.reporting',

} as const;



export type SourceInspectionKind = keyof typeof SOURCE_INSPECTION_TYPE_I18N;



function pickSource(

  row: DefectLedgerItem,

): { kind: SourceInspectionKind; id: number; code: string } | null {

  if (row.incoming_inspection_id) {

    return {

      kind: 'incoming',

      id: row.incoming_inspection_id,

      code: String(row.incoming_inspection_code || '').trim(),

    };

  }

  if (row.process_inspection_id) {

    return {

      kind: 'process',

      id: row.process_inspection_id,

      code: String(row.process_inspection_code || '').trim(),

    };

  }

  if (row.finished_goods_inspection_id) {

    return {

      kind: 'finished',

      id: row.finished_goods_inspection_id,

      code: String(row.finished_goods_inspection_code || '').trim(),

    };

  }

  const codeOnly =

    String(row.incoming_inspection_code || '').trim() ||

    String(row.process_inspection_code || '').trim() ||

    String(row.finished_goods_inspection_code || '').trim();

  if (codeOnly) {

    if (row.incoming_inspection_code) {

      return { kind: 'incoming', id: 0, code: codeOnly };

    }

    if (row.process_inspection_code) {

      return { kind: 'process', id: 0, code: codeOnly };

    }

    return { kind: 'finished', id: 0, code: codeOnly };

  }

  // 报工登记不良：无检验单，以来源报工记录标识（勿显示「暂无数据」造成误解）

  if (row.reporting_record_id) {

    const wo = String(row.work_order_code || '').trim();

    return {

      kind: 'reporting',

      id: Number(row.reporting_record_id),

      code: wo || `#${row.reporting_record_id}`,

    };

  }

  return null;

}



export function sourceInspectionPath(row: DefectLedgerItem): string | null {

  const source = pickSource(row);

  if (!source?.id) return null;

  if (source.kind === 'incoming') {

    return `/apps/kuaizhizao/quality-management/incoming-inspection?incoming_inspection_id=${source.id}`;

  }

  if (source.kind === 'process') {

    return `/apps/kuaizhizao/quality-management/process-inspection?process_inspection_id=${source.id}`;

  }

  if (source.kind === 'finished') {

    return `/apps/kuaizhizao/quality-management/finished-goods-inspection?finished_goods_inspection_id=${source.id}`;

  }

  if (source.kind === 'reporting') {

    const wo = String(row.work_order_code || '').trim();

    if (wo) {

      return `${ROUTES.REPORTING}?work_order_code=${encodeURIComponent(wo)}`;

    }

    return ROUTES.REPORTING;

  }

  return null;

}



export function sourceInspectionLabel(row: DefectLedgerItem): string | null {

  const source = pickSource(row);

  if (!source) return null;

  return source.code || null;

}



export function sourceInspectionTypeText(

  t: TFunction,

  row: DefectLedgerItem,

): string | null {

  const source = pickSource(row);

  if (!source) return null;

  return t(SOURCE_INSPECTION_TYPE_I18N[source.kind]);

}



/** 不良处理列表「来源单据」堆叠单元格（类型 + 单号/工单） */

export function renderNcSourceInspectionStackedCell(

  t: TFunction,

  row: DefectLedgerItem,

  navigate?: (path: string) => void,

): React.ReactNode {

  const typeText = sourceInspectionTypeText(t, row);

  const label = sourceInspectionLabel(row);

  const path = sourceInspectionPath(row);



  if (!typeText && !label) {

    return (

      <Typography.Text type="secondary">

        {t('app.kuaizhizao.quality.nc.sourceInspection.empty')}

      </Typography.Text>

    );

  }



  return (

    <UniTableStackedPrimaryCell

      primary={typeText || t('app.kuaizhizao.quality.nc.sourceInspection.empty')}

      secondary={label || '-'}

      skipLinkedDocumentLink

      onSecondaryClick={path && label && navigate ? () => navigate(path) : undefined}

    />

  );

}

