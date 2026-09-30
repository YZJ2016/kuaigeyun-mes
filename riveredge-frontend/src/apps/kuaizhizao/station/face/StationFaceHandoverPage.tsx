import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { App, Button, Card, DatePicker, Empty, Input, Popconfirm, Space, Spin, Tag, Typography } from 'antd';
import type { Dayjs } from 'dayjs';
import { TouchScreenTemplate } from '../../../../components/layout-templates/hmi';
import { STATION_ENTRY_PATH } from '../../../../utils/clientChannel';
import { formatApiErrorDetail } from '../../../../services/api';
import { useCurrentUser } from '../../../../hooks/useCurrentUser';
import {
  confirmShiftHandover,
  deleteFaceTemplate,
  enrollFaceTemplate,
  getOperationDocuments,
  getShiftSummary,
  getWorkOrderDocumentFlags,
  identifyFace,
  listMyFaceTemplates,
  type FaceIdentifyResponse,
  type FaceTemplateResponse,
  type ShiftHandoverResponse,
  type ShiftSummaryResponse,
  type StationDocFileItem,
  type StationOperationDocumentsResponse,
  type StationWorkOrderDocumentFlags,
} from './api';
import { captureFaceResDescriptor } from './capture';
import { setStationOperator } from '../entry/session';

const { RangePicker } = DatePicker;
const { Text, Paragraph } = Typography;

const SOP_KIOSK_PATH = `${STATION_ENTRY_PATH}/sop-viewer/kiosk`;
const DRAWING_KIOSK_PATH = `${STATION_ENTRY_PATH}/drawing-viewer/kiosk`;

const SOURCE_LABEL: Record<string, string> = {
  work_order: '工单附件',
  sop: 'SOP 附件',
  engineering_drawing: '工程图纸',
  material: '物料附件',
};

export interface StationFaceHandoverPageProps {
  /** 工位入口传入的已绑定工位。不读 URL workstationId。缺省时不请求 shift-summary。 */
  workstationId?: number | null;
  workstationName?: string | null;
  /** 工位入口传入的当前工单。不读 URL。缺省时不请求 document-flags，也不列出工单。 */
  workOrderId?: number | null;
  /** 与 workOrderId 同时存在时请求工序文档。由工位入口传入。 */
  operationId?: number | null;
  /**
   * 工位入口传入的当前操作员用户 id。
   * 登记 POST /face-templates 的 user_id。未传入时登记按钮不可用。
   */
  operatorUserId?: number | null;
}

function errorText(error: unknown): string {
  const data = (error as { response?: { data?: { detail?: unknown } } })?.response?.data;
  if (data && 'detail' in data) {
    const detail = formatApiErrorDetail(data.detail);
    if (detail) return detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return '请求失败';
}

function sourceLabel(source: string): string {
  return SOURCE_LABEL[source] ?? source;
}

function qtyText(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '0';
  return String(value);
}

export const StationFaceHandoverPage: React.FC<StationFaceHandoverPageProps> = ({
  workstationId = null,
  workstationName = null,
  workOrderId = null,
  operationId = null,
  operatorUserId = null,
}) => {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const currentUser = useCurrentUser();

  const [templates, setTemplates] = useState<FaceTemplateResponse[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [capturing, setCapturing] = useState(false);
  const [identifiedOperator, setIdentifiedOperator] = useState<Pick<
    FaceIdentifyResponse,
    'user_id' | 'full_name' | 'username'
  > | null>(null);
  const videoRef = React.useRef<HTMLVideoElement>(null);

  const [shiftRange, setShiftRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [remarks, setRemarks] = useState('');
  const [summary, setSummary] = useState<ShiftSummaryResponse | null>(null);
  const [summaryKey, setSummaryKey] = useState('');
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [handover, setHandover] = useState<ShiftHandoverResponse | null>(null);
  const [handoverLoading, setHandoverLoading] = useState(false);

  const [flags, setFlags] = useState<StationWorkOrderDocumentFlags | null>(null);
  const [flagsLoading, setFlagsLoading] = useState(false);
  const [documents, setDocuments] = useState<StationOperationDocumentsResponse | null>(null);
  const [documentsLoading, setDocumentsLoading] = useState(false);

  const loadTemplates = useCallback(async () => {
    setTemplatesLoading(true);
    try {
      const rows = await listMyFaceTemplates();
      setTemplates(Array.isArray(rows) ? rows : []);
    } catch (error) {
      message.error(errorText(error));
    } finally {
      setTemplatesLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void loadTemplates();
  }, [loadTemplates]);

  useEffect(() => {
    setSummary(null);
    setSummaryKey('');
    setHandover(null);
  }, [workstationId]);

  useEffect(() => {
    if (workOrderId == null) {
      setFlags(null);
      setFlagsLoading(false);
      return;
    }
    let cancelled = false;
    setFlags(null);
    setFlagsLoading(true);
    getWorkOrderDocumentFlags([workOrderId])
      .then((res) => {
        if (cancelled) return;
        const item = (res.items ?? []).find((row) => row.work_order_id === workOrderId) ?? null;
        setFlags(item);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setFlags(null);
          message.error(errorText(error));
        }
      })
      .finally(() => {
        if (!cancelled) setFlagsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [message, workOrderId]);

  useEffect(() => {
    if (workOrderId == null || operationId == null) {
      setDocuments(null);
      setDocumentsLoading(false);
      return;
    }
    let cancelled = false;
    setDocuments(null);
    setDocumentsLoading(true);
    getOperationDocuments(workOrderId, operationId)
      .then((res) => {
        if (!cancelled) setDocuments(res);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setDocuments(null);
          message.error(errorText(error));
        }
      })
      .finally(() => {
        if (!cancelled) setDocumentsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [message, operationId, workOrderId]);

  const currentShiftKey = useMemo(() => {
    if (workstationId == null || !shiftRange) return '';
    return `${workstationId}|${shiftRange[0].toISOString()}|${shiftRange[1].toISOString()}`;
  }, [shiftRange, workstationId]);

  const withCapturedDescriptor = async (action: (descriptor: number[]) => Promise<void>) => {
    setCapturing(true);
    let stream: MediaStream | null = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user' },
        audio: false,
      });
      const video = videoRef.current;
      if (!video) throw new Error('摄像头未就绪');
      video.srcObject = stream;
      await video.play();
      if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
        await new Promise<void>((resolve, reject) => {
          const onReady = () => {
            video.removeEventListener('loadeddata', onReady);
            resolve();
          };
          video.addEventListener('loadeddata', onReady);
          window.setTimeout(() => {
            video.removeEventListener('loadeddata', onReady);
            reject(new Error('摄像头没有画面'));
          }, 5000);
        });
      }
      const descriptor = await captureFaceResDescriptor(video);
      await action(descriptor);
    } catch (error) {
      message.error(errorText(error));
    } finally {
      stream?.getTracks().forEach((track) => track.stop());
      if (videoRef.current) videoRef.current.srcObject = null;
      setCapturing(false);
    }
  };

  const handleEnroll = () => {
    if (operatorUserId == null) return;
    const userId = operatorUserId;
    void withCapturedDescriptor(async (descriptor) => {
      await enrollFaceTemplate({ user_id: userId, descriptor });
      message.success('已登记');
      await loadTemplates();
    });
  };

  const handleIdentify = () => {
    void withCapturedDescriptor(async (descriptor) => {
      const res = await identifyFace(descriptor);
      setStationOperator({
        id: res.user_id,
        name: res.full_name || res.username,
      });
      setIdentifiedOperator({
        user_id: res.user_id,
        full_name: res.full_name,
        username: res.username,
      });
      message.success('已切换当前操作员');
    });
  };

  const handleDeleteTemplate = async (templateId: number) => {
    setDeletingId(templateId);
    try {
      await deleteFaceTemplate(templateId);
      message.success('已删除模板');
      await loadTemplates();
    } catch (error) {
      message.error(errorText(error));
    } finally {
      setDeletingId(null);
    }
  };

  const handleLoadSummary = async () => {
    if (workstationId == null || !shiftRange) {
      message.warning(workstationId == null ? '未传入已绑定工位' : '请选择班次起止');
      return;
    }
    const shiftStart = shiftRange[0].toISOString();
    const shiftEnd = shiftRange[1].toISOString();
    setSummaryLoading(true);
    setHandover(null);
    try {
      const res = await getShiftSummary({
        workstation_id: workstationId,
        shift_start: shiftStart,
        shift_end: shiftEnd,
      });
      setSummary(res);
      setSummaryKey(`${workstationId}|${shiftStart}|${shiftEnd}`);
    } catch (error) {
      setSummary(null);
      setSummaryKey('');
      message.error(errorText(error));
    } finally {
      setSummaryLoading(false);
    }
  };

  const handleConfirmHandover = async () => {
    if (workstationId == null || !shiftRange || !summary || summaryKey !== currentShiftKey) {
      message.warning('请先按当前工位和班次查询汇总');
      return;
    }
    setHandoverLoading(true);
    try {
      const res = await confirmShiftHandover({
        workstation_id: workstationId,
        workstation_name: workstationName,
        shift_start: shiftRange[0].toISOString(),
        shift_end: shiftRange[1].toISOString(),
        remarks: remarks.trim() ? remarks.trim() : null,
      });
      setHandover(res);
      message.success('交接班已确认');
    } catch (error) {
      message.error(errorText(error));
    } finally {
      setHandoverLoading(false);
    }
  };

  const openSop = (sopUuid: string) => {
    const search = new URLSearchParams({ sopUuid });
    if (typeof workstationId === 'number' && Number.isInteger(workstationId) && workstationId > 0) {
      search.set('workstationId', String(workstationId));
    }
    navigate({ pathname: SOP_KIOSK_PATH, search: search.toString() });
  };

  const openDrawing = (item: StationDocFileItem) => {
    if (!item.url) {
      message.warning('该文件没有预览地址');
      return;
    }
    const search = new URLSearchParams({ url: item.url });
    if (typeof workstationId === 'number' && Number.isInteger(workstationId) && workstationId > 0) {
      search.set('workstationId', String(workstationId));
    }
    navigate({ pathname: DRAWING_KIOSK_PATH, search: search.toString() });
  };

  const drawings = documents?.drawings ?? [];
  const loginUserId = currentUser?.id ?? null;
  const enrollsOtherOperator =
    operatorUserId != null && loginUserId != null && operatorUserId !== loginUserId;

  return (
    <TouchScreenTemplate title="刷脸与交接班" fullscreen={false}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Card title="我的模板">
          <Paragraph>
            登记使用入口传入的当前操作员
            {operatorUserId == null ? '（尚未传入，登记不可用）' : `（${operatorUserId}）`}
            。「我的模板」只列出当前登录用户。比对成功写入入口当前操作员，不换登录令牌。
          </Paragraph>
          {enrollsOtherOperator ? (
            <Paragraph>
              当前操作员与终端登录用户不是同一人。登记写入该操作员的模板后，不会出现在「我的模板」里。
            </Paragraph>
          ) : null}
          {identifiedOperator ? (
            <Paragraph>
              当前操作员 {identifiedOperator.full_name}（{identifiedOperator.username}，用户{' '}
              {identifiedOperator.user_id}）
            </Paragraph>
          ) : (
            <Paragraph>尚未比对出当前操作员。</Paragraph>
          )}
          <video ref={videoRef} muted playsInline style={{ width: '100%', maxHeight: 240, background: '#111' }} />
          <div style={{ margin: '12px 0' }}>
            <Space>
              <Button size="large" disabled={operatorUserId == null || capturing} onClick={handleEnroll}>
                登记
              </Button>
              <Button size="large" disabled={capturing} onClick={handleIdentify}>
                比对
              </Button>
            </Space>
          </div>
          <Spin spinning={templatesLoading}>
            {templates.length === 0 ? (
              <Empty description="当前登录用户没有人脸模板" />
            ) : (
              <Space direction="vertical" style={{ width: '100%' }}>
                {templates.map((row) => (
                  <Space key={row.id} style={{ width: '100%', justifyContent: 'space-between' }}>
                    <Text>
                      模板 {row.id}
                      {row.created_at ? ` · ${row.created_at}` : ''}
                    </Text>
                    <Popconfirm
                      title="删除这张人脸模板？"
                      okText="删除"
                      cancelText="取消"
                      onConfirm={() => void handleDeleteTemplate(row.id)}
                    >
                      <Button danger size="large" loading={deletingId === row.id}>
                        删除
                      </Button>
                    </Popconfirm>
                  </Space>
                ))}
              </Space>
            )}
          </Spin>
        </Card>

        <Card title="交接班">
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Text>
              工位：{workstationId == null ? '未传入' : workstationId}
              {workstationName ? ` ${workstationName}` : ''}
            </Text>
            <RangePicker
              showTime
              size="large"
              value={shiftRange}
              onChange={(value) => {
                if (value && value[0] && value[1]) {
                  setShiftRange([value[0], value[1]]);
                } else {
                  setShiftRange(null);
                }
                setSummary(null);
                setSummaryKey('');
                setHandover(null);
              }}
            />
            <Input.TextArea
              value={remarks}
              onChange={(event) => setRemarks(event.target.value)}
              placeholder="备注"
              rows={2}
            />
            <Space>
              <Button size="large" type="primary" loading={summaryLoading} onClick={() => void handleLoadSummary()}>
                查询汇总
              </Button>
              <Button
                size="large"
                loading={handoverLoading}
                disabled={!summary || summaryKey !== currentShiftKey}
                onClick={() => void handleConfirmHandover()}
              >
                确认交接班
              </Button>
            </Space>
            {summary ? (
              <Space direction="vertical" size={4}>
                <Text>计划数量 {qtyText(summary.planned_qty)}</Text>
                <Text>完成数量 {qtyText(summary.completed_qty)}</Text>
                <Text>不合格数量 {qtyText(summary.unqualified_qty)}</Text>
                <Text>停机分钟 {qtyText(summary.downtime_minutes)}</Text>
                <Text>安灯次数 {summary.andon_count}</Text>
                <Text>报工次数 {summary.reporting_count}</Text>
              </Space>
            ) : null}
            {handover ? (
              <Text>
                已生成交接班记录 {handover.id}，确认人 {handover.operator_name}（登录用户 {handover.operator_id}）
              </Text>
            ) : null}
          </Space>
        </Card>

        <Card
          title="工序文档"
          extra={
            flagsLoading ? (
              <Spin size="small" />
            ) : flags ? (
              <Space>
                {flags.has_esop ? <Tag>ESOP</Tag> : null}
                {flags.has_drawings ? <Tag>图纸</Tag> : null}
                {flags.has_docs ? <Tag>有文档</Tag> : <Tag>无文档</Tag>}
              </Space>
            ) : null
          }
        >
          {workOrderId == null ? (
            <Empty description="未传入当前工单，不查询文档角标" />
          ) : operationId == null ? (
            <Empty description={`工单 ${workOrderId} 已查角标。未传入当前工序，不查询工序文档。`} />
          ) : (
            <Spin spinning={documentsLoading}>
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                <Text>
                  工单 {workOrderId} · 工序 {operationId}
                </Text>
                {documents?.sop ? (
                  <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                    <Text>
                      SOP {documents.sop.name || documents.sop.uuid}
                      {documents.sop.current_revision ? ` · 修订 ${documents.sop.current_revision}` : ''}
                    </Text>
                    <Button size="large" type="primary" onClick={() => openSop(documents.sop!.uuid)}>
                      打开 SOP
                    </Button>
                  </Space>
                ) : (
                  <Text type="secondary">该工序没有 SOP</Text>
                )}
                {documents?.sop?.steps?.length ? (
                  <Space direction="vertical" size={2}>
                    {documents.sop.steps.map((step) => (
                      <Text key={step.id}>
                        {step.title}
                        {step.description ? ` — ${step.description}` : ''}
                      </Text>
                    ))}
                  </Space>
                ) : null}
                {drawings.length === 0 ? (
                  <Text type="secondary">没有图纸或附件</Text>
                ) : (
                  drawings.map((item) => (
                    <Space key={item.key} style={{ width: '100%', justifyContent: 'space-between' }}>
                      <Text>
                        {sourceLabel(item.source)} · {item.name}
                        {item.drawing_code ? ` · ${item.drawing_code}` : ''}
                        {item.drawing_revision ? ` ${item.drawing_revision}` : ''}
                      </Text>
                      <Button size="large" disabled={!item.url} onClick={() => openDrawing(item)}>
                        打开
                      </Button>
                    </Space>
                  ))
                )}
              </Space>
            </Spin>
          )}
        </Card>
      </Space>
    </TouchScreenTemplate>
  );
};
