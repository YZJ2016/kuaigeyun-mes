import{r as n,j as e,M as E,D as v,a8 as z,V as x,a$ as $,a2 as C,ag as s}from"./vendor-CKBUIHtO.js";import{g as L,b as M}from"./printTemplateSchemas-CaKyEecF.js";import{b as W,be as w,F as O}from"./clientRelease-p1K3Xvtk.js";import{M as H}from"./main-CBoU5oBz.js";import"./LinkedDocumentDetailContext-BQO25UtZ.js";import"./detailDrawerTimeFields-q0WCGqa-.js";import"./index.es-D45dBdDm.js";import"./sessionCurrentUser-BwYbN2MM.js";import"./globalStore-C51_ZwXF.js";import"./restoredUser-l8hMKzyb.js";import"./tokenRefresh-CfGA7q2X.js";import"./building-2-DRpOa0cQ.js";import"./clearSessionQueries-Db_KN_8V.js";import"./index-CQ4NFR2b.js";import"./statusBadges-D875fvLb.js";/* empty css                            */import"./UniLifecycleStepper-B4vab2CF.js";import"./globalLifecycleI18n-DuNjswJt.js";import"./documentLifecycleStatusTag-CYEJ6fxx.js";import"./documentStatusColors-DGC8st3Q.js";import"./operationColumn-CF7c02C6.js";import"./ActionConfirmPopconfirm-kQ53HYb2.js";import"./listLifecycleStage-BIJOhOUg.js";import"./permissionContract-CCeLLtCW.js";import"./permissionResource-C4537ZA2.js";import"./approvalInstance-DObs-pio.js";import"./index-BiDOW_k5.js";import"./timer-haTt7V0m.js";import"./user-DOkjQOQT.js";import"./displayContract-CymendGg.js";import"./userDisplay-t7PJBcrh.js";import"./QuantityWithUnitDisplay-x75VrZfW.js";import"./materialUnitDisplay-BaG2RoEM.js";import"./material-unit-N8OrSRJM.js";import"./formDate-CCV7wgTa.js";import"./index-DQybSo2C.js";import"./kuaireportSharedFilePreview-CWMoGAAz.js";import"./customFieldJsonUtils-DpNbUP6i.js";import"./index-0HPi11w3.js";import"./index-Cm1c_uFI.js";import"./index-D9iOWLOE.js";import"./index-KXM0iiGN.js";import"./createForOfIteratorHelper-BrXs85eu.js";import"./index-BpPShxm2.js";import"./vendor-libredwg-ByW_9b-B.js";import"./vendor-three-BPXNOO5B.js";import"./index-4AIaMkWj.js";import"./index-34RWUJy-.js";import"./index-BczVQGL7.js";import"./isObject-BaK2AtFo.js";import"./_baseIsEqual-Q-KQLgHN.js";import"./debounce-Cs4Uf4P3.js";import"./throttle-C1xW9NCQ.js";import"./routes-BHNSvbuS.js";import"./backendLifecycle-DVdlPVyL.js";import"./systemDictionaryI18n-CzXHyYH5.js";import"./orderPaymentMilestonesFields-lEQ01fVf.js";import"./index-C-rdi4OZ.js";import"./index-BBCkAum-.js";import"./index-D9p7NhAH.js";import"./useResourcePermissions-JdCL_baG.js";import"./documentStatus-B56geBPS.js";import"./purchase-CjSbvyGw.js";import"./fieldPermissionResources-DdZWfKRQ.js";import"./demandType-DiP_MLgc.js";import"./quotation-D1V-qtyl.js";import"./warehouseMarkerTags-2IzN0lvb.js";import"./warehouse-execution-Bt__ZQNA.js";import"./sales-order-B_lrRA6-.js";import"./dataDictionary-DHZlbEJa.js";import"./material-BgwfGzSF.js";import"./purchase-requisition-DJsqgS9b.js";import"./demand-computation-BQyu5tNe.js";import"./availableInventoryCell-DwaXZF_U.js";import"./MrpMaterialPlanPanel--qRrVafg.js";import"./workOrderLifecycle-Dkufobho.js";import"./workOrderReporting-D5XZA1-Q.js";import"./documentAttachments-DFrZTS_U.js";import"./WorkOrderMaterialMovementsPanel-BsIQqM4b.js";import"./work-order-CZm-Ldk5.js";import"./logisticsListPresentation-Dgzk954H.js";import"./reporting-Jlq2A5Wt.js";import"./afterSalesListPresentation-COaw4Ou-.js";import"./modalEventIsolation-BQxAC9d8.js";import"./after-sales-service-qGYKUuDe.js";import"./index-YfdN2Rj5.js";import"./LineAttachmentsUpload-Bi-mvdXv.js";import"./AuditPhaseBadge-Dwv2YCEk.js";import"./formListItems-DcSxpq1Y.js";const yr=({visible:m,onCancel:f,workOrderData:T,workOrderId:j})=>{const{t}=W(),[b,P]=n.useState([]),[k,g]=n.useState(!1),[y,d]=n.useState(!1),[a,u]=n.useState(),[h,l]=n.useState(""),c=n.useRef({}),p=j??T?.id;c.current={selectedTemplateId:a,effectiveWorkOrderId:p},n.useEffect(()=>{m&&(_(),u(void 0),l(""))},[m]),n.useEffect(()=>{m&&a&&p?I():l("")},[m,a,p]);const _=async()=>{g(!0);try{const r=await L({is_active:!0,document_type:"work_order"});P(r);const i=r.find(o=>o.is_default)??r.find(o=>o.code===M.work_order)??r[0];i&&u(i.uuid)}catch(r){w(r,t("app.kuaizhizao.workOrder.msgLoadPrintTemplateFailed"))}finally{g(!1)}},I=async()=>{if(!p||!a)return;const r=`${a}-${p}`;d(!0);try{const i=await O(`/apps/kuaizhizao/work-orders/${p}/print`,{method:"GET",params:{template_uuid:a,output_format:"html",response_format:"json"}}),o=c.current;if(r!==`${o.selectedTemplateId}-${o.effectiveWorkOrderId}`)return;l(i?.content??"")}catch(i){const o=c.current;if(r!==`${o.selectedTemplateId}-${o.effectiveWorkOrderId}`)return;w(i,t("app.kuaizhizao.workOrder.msgLoadPreviewFailed")),l("")}finally{const i=c.current;r===`${i.selectedTemplateId}-${i.effectiveWorkOrderId}`&&d(!1)}},S=async()=>{if(!p){s.warning(t("app.kuaizhizao.workOrder.msgWorkOrderIdMissingPrint"));return}if(!a){s.warning(t("app.kuaizhizao.workOrder.msgSelectPrintTemplate"));return}d(!0);try{const i=(await O(`/apps/kuaizhizao/work-orders/${p}/print`,{method:"GET",params:{template_uuid:a,output_format:"html",response_format:"json"}}))?.content??"";if(!i){s.error(t("app.kuaizhizao.workOrder.msgPrintContentEmpty"));return}const o=window.open("","_blank");o?(o.document.write(`<!DOCTYPE html><html><head><meta charset="UTF-8"><title>${t("common.print")}</title></head><body>${i}</body></html>`),o.document.close(),o.focus(),o.print(),o.close(),s.success(t("app.kuaizhizao.workOrder.msgPrintSent"))):s.error(t("app.kuaizhizao.workOrder.msgPrintPopupBlocked"))}catch(r){w(r,t("app.kuaizhizao.workOrder.msgPrintFailed"))}finally{d(!1)}};return e.jsxs(E,{title:e.jsxs("div",{className:"no-print",style:{display:"flex",alignItems:"center",justifyContent:"space-between",width:"100%",gap:16},children:[e.jsx("span",{style:{fontWeight:600,fontSize:16},children:t("app.kuaizhizao.workOrder.modalPrintTitle")}),e.jsx(C,{style:{width:260,flexShrink:0},placeholder:t("app.kuaizhizao.workOrder.msgSelectPrintTemplatePlaceholder"),value:a,onChange:u,loading:k,options:b.map(r=>({label:r.name,value:r.uuid}))})]}),open:m,onCancel:f,width:H.LARGE_WIDTH,wrapClassName:"work-order-print-modal-wrap",styles:{body:{padding:0,overflow:"hidden",height:"70vh",minHeight:500}},footer:[e.jsx(x,{onClick:f,children:t("common.cancel")},"cancel"),e.jsx(x,{type:"primary",icon:e.jsx($,{}),onClick:S,loading:y,disabled:!a||!p,children:t("common.print")},"print")],className:"work-order-print-modal",children:[e.jsx(v,{spinning:k,children:e.jsx("div",{className:"work-order-print-preview",style:{height:"100%",overflow:"auto"},children:p?y&&!h?e.jsx("div",{style:{display:"flex",justifyContent:"center",alignItems:"center",height:"100%",minHeight:400},children:e.jsx(v,{description:t("app.kuaizhizao.workOrder.msgLoadingPreview"),children:e.jsx("div",{style:{minHeight:24}})})}):h?e.jsx("div",{dangerouslySetInnerHTML:{__html:h},style:{height:"100%",overflow:"auto",padding:16}}):e.jsx(z,{description:t("app.kuaizhizao.workOrder.msgSelectValidPrintTemplate"),style:{paddingTop:100}}):e.jsx(z,{description:t("app.kuaizhizao.workOrder.msgWorkOrderIdMissingPreview"),style:{paddingTop:100}})})}),e.jsx("style",{children:`
        .work-order-print-modal-wrap .ant-modal {
          max-width: calc(100vw - 32px) !important;
        }
        .work-order-print-modal-wrap .ant-modal-body .ant-spin-nested-loading,
        .work-order-print-modal-wrap .ant-modal-body .ant-spin-container,
        .work-order-print-modal-wrap .work-order-print-preview {
          height: 100% !important;
        }
        .work-order-print-modal-wrap .work-order-print-iframe {
          width: 100% !important;
          height: 100% !important;
          min-height: 500px !important;
          border: none !important;
          display: block !important;
          background: #fff !important;
        }
        @media print {
          body * {
            visibility: hidden;
          }
          .ant-modal-wrap,
          .ant-modal-wrap *,
          .ant-modal-content,
          .ant-modal-content *,
          .work-order-print-preview,
          .work-order-print-preview * {
            visibility: visible !important;
          }
          .ant-modal-wrap {
            position: absolute !important;
            left: 0;
            top: 0;
            width: 100%;
            height: auto;
            overflow: visible;
          }
          .ant-modal-content {
            position: absolute !important;
            left: 0;
            top: 0;
            width: 100%;
            border: none;
            box-shadow: none;
            background: white;
          }
          .work-order-print-preview {
            width: 100% !important;
            min-height: auto !important;
            overflow: visible !important;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }
          .no-print, .ant-modal-footer, .ant-modal-header, .ant-modal-close {
            display: none !important;
          }
        }
      `})]})};export{yr as default};
