/**
 * 系统报表预览。config 模式交给 UniReport（内部调用 executeReport，打印走 useUniReportPrint）。
 * 全量 Excel 另请求星报表后端生成工作簿。
 */

import React, { useEffect, useState } from 'react';
import { Button, Space } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import { UniReport } from '../../../../components/uni-report';
import { downloadFile } from '../../../../utils/fileDownload';
import { downloadFullExcel, getReport, type ReportCenterRow } from './api';

export default function ReportPreviewPage() {
  const navigate = useNavigate();
  const params = useParams();
  const reportId = Number(params.reportId);
  const [report, setReport] = useState<ReportCenterRow | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!Number.isFinite(reportId)) return;
    void getReport(reportId).then(setReport);
  }, [reportId]);

  if (!report) {
    return null;
  }

  return (
    <UniReport
      mode="config"
      title={report.name}
      columnPersistenceId={`kuaireport.reports.${report.code}`}
      reportId={report.id}
      reportConfig={report.report_config}
      showPrintButton
      showExportButton={false}
      headerLeft={
        <Space>
          <Button onClick={() => navigate('/apps/kuaireport/reports')}>返回</Button>
          <Button
            type="primary"
            loading={exporting}
            onClick={() => {
              setExporting(true);
              void downloadFullExcel(report.id, {})
                .then((blob) => downloadFile(blob, `${report.code}.xlsx`))
                .finally(() => setExporting(false));
            }}
          >
            全量 Excel
          </Button>
        </Space>
      }
    />
  );
}
