import{r as n,j as e,M as E,D as v,a8 as z,V as x,a$ as $,a2 as C,ag as s}from"./vendor-cCqhGuHR.js";import{g as L,b as M}from"./printTemplateSchemas-CsddcG1G.js";import{b as W,be as w,F as O}from"./clientRelease-CrzFR-4k.js";import{M as H}from"./main-Cd-M0Ans.js";import"./LinkedDocumentDetailContext-B5OIUoP7.js";import"./detailDrawerTimeFields-DK-8K50I.js";import"./index.es-ClE4ORn6.js";import"./sessionCurrentUser-BuexxRE5.js";import"./globalStore-C7639EnZ.js";import"./restoredUser-RPqouIp6.js";import"./tokenRefresh-Eo1cwdVF.js";import"./building-2-CtRHOjVz.js";import"./clearSessionQueries-Db_KN_8V.js";import"./index-CwEgpnVj.js";import"./statusBadges-D8Xs4e15.js";/* empty css                            */import"./UniLifecycleStepper-CDYBTpd_.js";import"./globalLifecycleI18n-DuNjswJt.js";import"./documentLifecycleStatusTag-JTLlUDCk.js";import"./documentStatusColors-BR5wLZoJ.js";import"./operationColumn-BoevU2gT.js";import"./ActionConfirmPopconfirm-Cc-yKbnt.js";import"./listLifecycleStage-BIJOhOUg.js";import"./permissionContract-BJ9IXtJr.js";import"./permissionResource-C4537ZA2.js";import"./approvalInstance-1NaOkCMI.js";import"./index-BfHwCPdy.js";import"./timer-haTt7V0m.js";import"./user-Dtjd613v.js";import"./displayContract-CXE8o5Qo.js";import"./userDisplay-DexhPGXI.js";import"./QuantityWithUnitDisplay-BJApuwsX.js";import"./materialUnitDisplay-Csk_cvH_.js";import"./material-unit-C1MBH0Ch.js";import"./formDate-DYomDxx0.js";import"./index-BpH84CiY.js";import"./kuaireportSharedFilePreview-pwRtUqpB.js";import"./customFieldJsonUtils-DpNbUP6i.js";import"./index-3YX93eW4.js";import"./index-BYHzNl6W.js";import"./index-CRmdpUD9.js";import"./index-C5mzhXt5.js";import"./createForOfIteratorHelper-hqDhe0gs.js";import"./index-Bkz85HTx.js";import"./vendor-libredwg-DmGv96h2.js";import"./vendor-three-BPXNOO5B.js";import"./index-D9A9zz6m.js";import"./index-DkbpOR4j.js";import"./index-CG-IbnYY.js";import"./isObject-D1zkLHcH.js";import"./_baseIsEqual-Bu-2RPEE.js";import"./debounce-DsZmk-0I.js";import"./throttle-BnFJGdap.js";import"./routes-BHNSvbuS.js";import"./backendLifecycle-DVdlPVyL.js";import"./systemDictionaryI18n-CzXHyYH5.js";import"./orderPaymentMilestonesFields-BijO6vru.js";import"./index-BYoNchy1.js";import"./index-jeGq0t_t.js";import"./index-BIqwgzKd.js";import"./useResourcePermissions-DJwAgVtW.js";import"./documentStatus-Dm9jDFLu.js";import"./purchase-D3xflpti.js";import"./fieldPermissionResources-C_2_hnsG.js";import"./demandType-CENkZ_y9.js";import"./quotation-W7uvd_BC.js";import"./warehouseMarkerTags-BKRpbhEG.js";import"./warehouse-execution-D5vg-suA.js";import"./sales-order-CDuKiAM7.js";import"./dataDictionary-BYPXAnAP.js";import"./material-C7uC-KKC.js";import"./purchase-requisition-BwlNKksH.js";import"./demand-computation-DJRtpcib.js";import"./availableInventoryCell-DIxVdYId.js";import"./MrpMaterialPlanPanel-CRgc8sbL.js";import"./workOrderLifecycle-DO6K7voA.js";import"./workOrderReporting-D5XZA1-Q.js";import"./documentAttachments-B6G-CjQB.js";import"./WorkOrderMaterialMovementsPanel-nJw1zEsO.js";import"./work-order-BzAd8WKL.js";import"./logisticsListPresentation-CJXZwndR.js";import"./reporting-bunjxqUr.js";import"./afterSalesListPresentation-DLt7xJ_3.js";import"./modalEventIsolation-BQxAC9d8.js";import"./after-sales-service-oqWqKYkP.js";import"./index-BdVZF-Ig.js";import"./LineAttachmentsUpload-CiUDtoLG.js";import"./AuditPhaseBadge-CyAE_Aeh.js";import"./formListItems-DcSxpq1Y.js";const yr=({visible:m,onCancel:f,workOrderData:T,workOrderId:j})=>{const{t}=W(),[b,P]=n.useState([]),[k,g]=n.useState(!1),[y,d]=n.useState(!1),[a,u]=n.useState(),[h,l]=n.useState(""),c=n.useRef({}),p=j??T?.id;c.current={selectedTemplateId:a,effectiveWorkOrderId:p},n.useEffect(()=>{m&&(_(),u(void 0),l(""))},[m]),n.useEffect(()=>{m&&a&&p?I():l("")},[m,a,p]);const _=async()=>{g(!0);try{const r=await L({is_active:!0,document_type:"work_order"});P(r);const i=r.find(o=>o.is_default)??r.find(o=>o.code===M.work_order)??r[0];i&&u(i.uuid)}catch(r){w(r,t("app.kuaizhizao.workOrder.msgLoadPrintTemplateFailed"))}finally{g(!1)}},I=async()=>{if(!p||!a)return;const r=`${a}-${p}`;d(!0);try{const i=await O(`/apps/kuaizhizao/work-orders/${p}/print`,{method:"GET",params:{template_uuid:a,output_format:"html",response_format:"json"}}),o=c.current;if(r!==`${o.selectedTemplateId}-${o.effectiveWorkOrderId}`)return;l(i?.content??"")}catch(i){const o=c.current;if(r!==`${o.selectedTemplateId}-${o.effectiveWorkOrderId}`)return;w(i,t("app.kuaizhizao.workOrder.msgLoadPreviewFailed")),l("")}finally{const i=c.current;r===`${i.selectedTemplateId}-${i.effectiveWorkOrderId}`&&d(!1)}},S=async()=>{if(!p){s.warning(t("app.kuaizhizao.workOrder.msgWorkOrderIdMissingPrint"));return}if(!a){s.warning(t("app.kuaizhizao.workOrder.msgSelectPrintTemplate"));return}d(!0);try{const i=(await O(`/apps/kuaizhizao/work-orders/${p}/print`,{method:"GET",params:{template_uuid:a,output_format:"html",response_format:"json"}}))?.content??"";if(!i){s.error(t("app.kuaizhizao.workOrder.msgPrintContentEmpty"));return}const o=window.open("","_blank");o?(o.document.write(`<!DOCTYPE html><html><head><meta charset="UTF-8"><title>${t("common.print")}</title></head><body>${i}</body></html>`),o.document.close(),o.focus(),o.print(),o.close(),s.success(t("app.kuaizhizao.workOrder.msgPrintSent"))):s.error(t("app.kuaizhizao.workOrder.msgPrintPopupBlocked"))}catch(r){w(r,t("app.kuaizhizao.workOrder.msgPrintFailed"))}finally{d(!1)}};return e.jsxs(E,{title:e.jsxs("div",{className:"no-print",style:{display:"flex",alignItems:"center",justifyContent:"space-between",width:"100%",gap:16},children:[e.jsx("span",{style:{fontWeight:600,fontSize:16},children:t("app.kuaizhizao.workOrder.modalPrintTitle")}),e.jsx(C,{style:{width:260,flexShrink:0},placeholder:t("app.kuaizhizao.workOrder.msgSelectPrintTemplatePlaceholder"),value:a,onChange:u,loading:k,options:b.map(r=>({label:r.name,value:r.uuid}))})]}),open:m,onCancel:f,width:H.LARGE_WIDTH,wrapClassName:"work-order-print-modal-wrap",styles:{body:{padding:0,overflow:"hidden",height:"70vh",minHeight:500}},footer:[e.jsx(x,{onClick:f,children:t("common.cancel")},"cancel"),e.jsx(x,{type:"primary",icon:e.jsx($,{}),onClick:S,loading:y,disabled:!a||!p,children:t("common.print")},"print")],className:"work-order-print-modal",children:[e.jsx(v,{spinning:k,children:e.jsx("div",{className:"work-order-print-preview",style:{height:"100%",overflow:"auto"},children:p?y&&!h?e.jsx("div",{style:{display:"flex",justifyContent:"center",alignItems:"center",height:"100%",minHeight:400},children:e.jsx(v,{description:t("app.kuaizhizao.workOrder.msgLoadingPreview"),children:e.jsx("div",{style:{minHeight:24}})})}):h?e.jsx("div",{dangerouslySetInnerHTML:{__html:h},style:{height:"100%",overflow:"auto",padding:16}}):e.jsx(z,{description:t("app.kuaizhizao.workOrder.msgSelectValidPrintTemplate"),style:{paddingTop:100}}):e.jsx(z,{description:t("app.kuaizhizao.workOrder.msgWorkOrderIdMissingPreview"),style:{paddingTop:100}})})}),e.jsx("style",{children:`
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
