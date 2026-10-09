/**
 * 工单执行详情页 - 触屏模式
 *
 * 核心生产执行界面，集成SOP查看、关键物料批次录入、开始/暂停/结束控制及报工。
 *
 * Author: RiverEdge AI
 * Date: 2026-02-05
 */

import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next'
import { App, Card, Button, Row, Col, Tabs, Tag, Descriptions, Modal, Input, Space, Statistic, Progress, Alert } from 'antd';
import { 
    ArrowLeftOutlined, 
    PlayCircleOutlined, 
    PauseCircleOutlined, 
    CheckCircleOutlined, 
    FileTextOutlined, 
    BarcodeOutlined,
    FormOutlined
} from '@ant-design/icons';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { TOUCH_SCREEN_CONFIG, HMI_DESIGN_TOKENS } from '../../../../../components/layout-templates';
import { TouchScreenTemplate } from '../../../../../components/layout-templates/hmi';
import { touchButtonProps, touchQtyInputProps, TOUCH_INPUT_QTY_STYLE } from '../../../../../components/touch-terminal';
import NumericKeypad from '../../../../../components/touch-keyboard/NumericKeypad';
import { workOrderApi } from '../../../services/production';
import { isStationEntryPath, STATION_ENTRY_PATH } from '../../../../../utils/clientChannel';
import { useStationWriteEnabled } from '../../../station/entry/session';

const { Meta } = Card;

const WorkOrderDetailKioskPage: React.FC = () => {
  const { t } = useTranslation()
    const { message } = App.useApp();
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const location = useLocation();
    // 工位路径下未确认操作员时禁用写按钮；PC 路径（/production-execution/*）行为不变
    const stationWriteEnabled = useStationWriteEnabled();
    const stationRoute = isStationEntryPath(location.pathname);
    const writeBlocked = stationRoute && !stationWriteEnabled;
    const [loading, setLoading] = useState(true);
    const [workOrder, setWorkOrder] = useState<any>(null);
    const [activeOperation, setActiveOperation] = useState<any>(null);
    
    // 报工 Modal
    const [reportModalVisible, setReportModalVisible] = useState(false);
    const [reportQuantity, setReportQuantity] = useState('');
    
    useEffect(() => {
        if (id) {
            loadWorkOrderDetail(id);
        }
    }, [id]);

    const loadWorkOrderDetail = async (workOrderId: string) => {
        setLoading(true);
        try {
            const data = await workOrderApi.get(workOrderId);
            setWorkOrder(data);
            
            // 加载工序信息并找到当前工序
            const ops = await workOrderApi.getOperations(workOrderId);
            if (ops && ops.length > 0) {
                // 简单逻辑：找第一个进行中或待开始的
                const current = ops.find((o: any) => o.status === 'processing') || ops.find((o: any) => o.status === 'pending');
                setActiveOperation(current || ops[0]);
            }
        } catch (error) {
            console.error(error);
            message.error(t('app.kuaizhizao.workOrder.kioskDetailLoadFailed'));
        } finally {
            setLoading(false);
        }
    };

    const handleStart = async () => {
        if (!workOrder || !activeOperation) return;
        const st = String(workOrder.status || '').trim().toLowerCase();
        if (st !== 'released' && st !== 'in_progress' && st !== '已下达' && st !== '执行中') {
            message.warning(t('app.kuaizhizao.workOrder.msgReleaseBeforeStart'));
            return;
        }
        try {
            await workOrderApi.startOperation(workOrder.id, activeOperation.id, {
                stationOperatorSession: stationRoute,
            });
            message.success(t('app.kuaizhizao.workOrder.kioskOpStarted'));
            loadWorkOrderDetail(workOrder.id);
        } catch (error: any) {
            const detail = error?.response?.data?.detail || error?.message || '';
            if (typeof detail === 'string' && (detail.includes('需要先下达') || detail.includes('只能开始已下达'))) {
                message.warning(t('app.kuaizhizao.workOrder.msgReleaseBeforeStart'));
            } else {
                message.error(t('common.operationFailed'));
            }
        }
    };
    
    const handleComplete = async () => {
        // 打开报工弹窗
        setReportQuantity('');
        setReportModalVisible(true);
    };

    const submitReporting = async () => {
        if (!reportQuantity || parseFloat(reportQuantity) <= 0) {
            message.warning(t('app.kuaizhizao.workOrder.kioskEnterValidReportQty'));
            return;
        }

        try {
            // TODO: 调用真实的报工API
            // await reportingApi.create({ ... })
            message.success(`成功报工: ${reportQuantity}`);
            setReportModalVisible(false);
            loadWorkOrderDetail(workOrder.id);
        } catch (error) {
            message.error(t('app.kuaizhizao.workOrder.kioskReportFailed'));
        }
    };

    const handleKeypadInput = (key: string) => {
        if (key === '.') {
            if (!reportQuantity.includes('.')) {
                setReportQuantity(prev => prev + key);
            }
        } else {
            setReportQuantity(prev => prev + key);
        }
    };

    const handleKeypadDelete = () => {
        setReportQuantity(prev => prev.slice(0, -1));
    };

    const handleKeypadClear = () => {
        setReportQuantity('');
    };

    if (!workOrder) {
        if (!stationRoute) return <Card loading={true} />;
        return (
            <TouchScreenTemplate
                title="工单执行"
                footerButtons={[{
                    title: '返回工位入口',
                    type: 'default',
                    icon: <ArrowLeftOutlined />,
                    onClick: () => navigate(`${STATION_ENTRY_PATH}${location.search}`),
                }]}
            >
                <Card loading={loading}>
                    {!loading && <Alert type="error" showIcon message={t('app.kuaizhizao.workOrder.kioskDetailLoadFailed')} />}
                </Card>
            </TouchScreenTemplate>
        );
    }

    return (
        <TouchScreenTemplate
            title={`工单执行: ${workOrder.code}`}
            fullscreen={true}
            footerButtons={[
                {
                    title: t('app.kuaizhizao.workOrder.actionPause'),
                    type: 'default',
                    icon: <PauseCircleOutlined />,
                    onClick: () => message.info(t('app.kuaizhizao.workOrder.kioskPauseNotImplemented')),
                    disabled: activeOperation?.status !== 'processing',
                    block: false
                },
                 {
                    title: stationRoute ? '返回工位入口' : t('app.kuaizhizao.workOrder.actionBackToList'),
                    type: 'default',
                    icon: <ArrowLeftOutlined />,
                    onClick: () =>
                        stationRoute
                            ? navigate(`${STATION_ENTRY_PATH}${location.search}`)
                            : navigate(-1),
                    block: false
                }
            ]}
        >
            <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {writeBlocked ? (
                    <Alert
                        type="info"
                        showIcon
                        message="未确认操作员：可查看工单与状态，开工与完工报工不可用"
                    />
                ) : null}
                {/* 顶部信息栏 */}
                <Card styles={{ body: { padding: '16px' } }}>
                    <Row gutter={[16, 16]}>
                        <Col span={8}>
                            <Statistic title="产品" value={workOrder.product_name} styles={{ content: {fontSize: `${HMI_DESIGN_TOKENS.FONT_BODY_MIN}px`, fontWeight: 'bold' } }} />
                        </Col>
                         <Col span={4}>
                            <Statistic title="计划数量" value={workOrder.quantity} styles={{ content: {fontSize: HMI_DESIGN_TOKENS.FONT_BODY_MIN } }} />
                        </Col>
                        <Col span={4}>
                            <Statistic title="已完工" value={workOrder.completed_quantity || 0} styles={{ content: {color: HMI_DESIGN_TOKENS.STATUS_OK, fontSize: HMI_DESIGN_TOKENS.FONT_BODY_MIN } }} />
                        </Col>
                         <Col span={8} style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '8px' }}>
                             {activeOperation?.status === 'pending' && (
                                 <Button size="large" {...touchButtonProps({ variant: 'primary', size: 'action' })} icon={<PlayCircleOutlined />} onClick={handleStart} disabled={writeBlocked} style={{ width: 140 }}>
                                     开始
                                 </Button>
                             )}
                             {activeOperation?.status === 'processing' && (
                                 <Button size="large" {...touchButtonProps({ variant: 'success', size: 'action' })} icon={<CheckCircleOutlined />} onClick={handleComplete} disabled={writeBlocked} style={{ width: 140 }}>
                                     完工
                                 </Button>
                             )}
                        </Col>
                    </Row>
                    <div style={{ marginTop: '16px' }}>
                         <Progress percent={Math.round(((workOrder.completed_quantity || 0) / workOrder.quantity) * 100)} status="active" strokeColor={{ from: HMI_DESIGN_TOKENS.STATUS_INFO, to: HMI_DESIGN_TOKENS.STATUS_OK }} />
                    </div>
                </Card>

                {/* 主内容区 Tabs */}
                 <div style={{ flex: 1, ...(stationRoute ? {} : { backgroundColor: '#fff' }), padding: '16px', borderRadius: '8px' }}>
                     <Tabs
                        defaultActiveKey="sop"
                        items={[
                            {
                                key: 'sop',
                                label: <span style={{ fontSize: HMI_DESIGN_TOKENS.FONT_BODY_MIN, padding: '12px 16px', minHeight: HMI_DESIGN_TOKENS.TOUCH_MIN_SIZE, display: 'inline-flex', alignItems: 'center' }}><FileTextOutlined /> 作业指导 SOP</span>,
                                children: (
                                    <div style={{ height: '500px', display: 'flex', justifyContent: 'center', alignItems: 'center', ... (stationRoute ? { border: '1px dashed currentColor' } : { backgroundColor: '#f5f5f5', border: '1px dashed #d9d9d9' }) }}>
                                        <div style={{ textAlign: 'center' }}>
                                            <FileTextOutlined style={{ fontSize: '64px', ...(stationRoute ? {} : { color: '#bfbfbf' }) }} />
                                            <div style={{ marginTop: '16px', fontSize: HMI_DESIGN_TOKENS.FONT_BODY_MIN, ...(stationRoute ? {} : { color: '#999' }) }}>{t('app.kuaizhizao.workOrder.kioskNoSopPreview')}</div>
                                            {/* 这里后续集成 PDF 预览或图片轮播 */}
                                        </div>
                                    </div>
                                )
                            },
                             {
                                key: 'material',
                                label: <span style={{ fontSize: HMI_DESIGN_TOKENS.FONT_BODY_MIN, padding: '12px 16px', minHeight: HMI_DESIGN_TOKENS.TOUCH_MIN_SIZE, display: 'inline-flex', alignItems: 'center' }}><BarcodeOutlined /> 关键物料投料</span>,
                                children: (
                                    <div style={{ padding: '20px', textAlign: 'center' }}>
                                        <Button size="large" {...touchButtonProps({ size: 'action' })} icon={<BarcodeOutlined />} style={{ width: 200 }}>
                                            扫描投料
                                        </Button>
                                        <div style={{ marginTop: '20px', fontSize: HMI_DESIGN_TOKENS.FONT_BODY_MIN, ...(stationRoute ? {} : { color: '#999' }) }}>{t('app.kuaizhizao.workOrder.kioskDetailScanFeedHint')}</div>
                                    </div>
                                )
                            }
                        ]}
                     />
                 </div>
            </div>

            {/* 报工弹窗 */}
            <Modal
                title={<span style={{ fontSize: HMI_DESIGN_TOKENS.FONT_TITLE_MIN }}>{t('app.kuaizhizao.workOrder.kioskOpReport')}</span>}
                open={reportModalVisible}
                onCancel={() => setReportModalVisible(false)}
                footer={null}
                width={600}
                centered
                destroyOnHidden
            >
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '24px' }}>
                    <div style={{ width: '100%' }}>
                         <div style={{ marginBottom: '8px', fontSize: HMI_DESIGN_TOKENS.FONT_BODY_MIN, ...(stationRoute ? {} : { color: '#666' }) }}>本次报工数量:</div>
                         <Input
                            {...touchQtyInputProps()}
                            style={TOUCH_INPUT_QTY_STYLE}
                            value={reportQuantity}
                            readOnly
                            placeholder="请点击下方键盘输入"
                         />
                    </div>
                    
                    <NumericKeypad 
                        onInput={handleKeypadInput}
                        onDelete={handleKeypadDelete}
                        onClear={handleKeypadClear}
                        onConfirm={submitReporting}
                        style={{ maxWidth: '100%' }}
                    />
                </div>
            </Modal>
        </TouchScreenTemplate>
    );
};

export default WorkOrderDetailKioskPage;
