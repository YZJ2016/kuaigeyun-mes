import{r as n,j as e,M as E,D as v,a8 as z,V as x,a$ as $,a2 as C,ag as s}from"./vendor--Nq-2deO.js";import{g as L,b as M}from"./printTemplateSchemas-CGD8nr3j.js";import{b as W,bf as w,F as O}from"./clientRelease-08UFRSxC.js";import{M as H}from"./main-DzagvtIV.js";import"./LinkedDocumentDetailContext-gor8rFpi.js";import"./detailDrawerTimeFields-Drll2H66.js";import"./index.es-BmPtLWya.js";import"./sessionCurrentUser-8nE5IPr8.js";import"./globalStore-DDnbUc_H.js";import"./restoredUser-F9XQ4uHx.js";import"./tokenRefresh-BrfFkCvD.js";import"./building-2-CVMUo_tx.js";import"./clearSessionQueries-Db_KN_8V.js";import"./index-DOopanlm.js";import"./statusBadges-BR_OmaA3.js";/* empty css                            */import"./UniLifecycleStepper-BidFILeS.js";import"./globalLifecycleI18n-DuNjswJt.js";import"./documentLifecycleStatusTag-DCCrFHGx.js";import"./documentStatusColors-rNj5zSvl.js";import"./operationColumn-BNlbR0Zz.js";import"./ActionConfirmPopconfirm-DtIvIcJ9.js";import"./listLifecycleStage-BIJOhOUg.js";import"./permissionContract-b9tirqKd.js";import"./permissionResource-C4537ZA2.js";import"./approvalInstance-tF_c_Hiw.js";import"./index-Bu9NDdqE.js";import"./timer-haTt7V0m.js";import"./user-CeHCTkEp.js";import"./displayContract-XP_v_mUz.js";import"./userDisplay-BrrTUo-N.js";import"./QuantityWithUnitDisplay-BjjC1BaO.js";import"./materialUnitDisplay-D5BJPZm1.js";import"./material-unit-CIqa3a0I.js";import"./formDate-BAgCgYE3.js";import"./index-BfJGkMtt.js";import"./kuaireportSharedFilePreview-CwZ9L9AV.js";import"./customFieldJsonUtils-DpNbUP6i.js";import"./index-Ce_bWtHp.js";import"./index-C7KhGGZY.js";import"./index-0TX7Sdqa.js";import"./index-NKFBdGAC.js";import"./createForOfIteratorHelper-DH44NlKT.js";import"./index-0rUy1bFC.js";import"./vendor-libredwg-NlOqalEY.js";import"./vendor-three-BPXNOO5B.js";import"./index-CvDRoOEX.js";import"./index-D-QDm0_b.js";import"./index-COBTwvdf.js";import"./isObject-7c2xaHaw.js";import"./_baseIsEqual-CGad34Wp.js";import"./debounce-W7XJv1C6.js";import"./throttle-CeIEW9aj.js";import"./routes-BHNSvbuS.js";import"./backendLifecycle-DVdlPVyL.js";import"./systemDictionaryI18n-CzXHyYH5.js";import"./orderPaymentMilestonesFields-3mYLbm_N.js";import"./index-jW6w9IcW.js";import"./index-c2-X6-2_.js";import"./index-B-WSuaFO.js";import"./useResourcePermissions-ezwKCyXp.js";import"./documentStatus-D5_Wh40f.js";import"./purchase-BjYTfJqQ.js";import"./fieldPermissionResources-DUGmA3f9.js";import"./demandType-D1cNdfw1.js";import"./quotation-C8cz94eV.js";import"./warehouseMarkerTags-BoeFEPrk.js";import"./warehouse-execution-BtQCN4-k.js";import"./sales-order-CJZojdMc.js";import"./dataDictionary-TMB1iHBa.js";import"./material-BjsjUrmg.js";import"./purchase-requisition-D1Xk8OSU.js";import"./demand-computation-Cx_cyUfm.js";import"./availableInventoryCell-C8tx65mZ.js";import"./MrpMaterialPlanPanel-wvHAyEna.js";import"./workOrderLifecycle-DWDGiJQz.js";import"./workOrderReporting-D5XZA1-Q.js";import"./documentAttachments-7vNH5fq4.js";import"./WorkOrderMaterialMovementsPanel-D8tN9Oob.js";import"./work-order-D13KN8gC.js";import"./logisticsListPresentation-CFBKAeTO.js";import"./reporting-CPLuy7l8.js";import"./afterSalesListPresentation-DHVn4wIR.js";import"./modalEventIsolation-BQxAC9d8.js";import"./after-sales-service-DKHoUXQ8.js";import"./index-CBzbtOl-.js";import"./LineAttachmentsUpload-D2cqyqni.js";import"./AuditPhaseBadge-BBz2d43-.js";import"./formListItems-DcSxpq1Y.js";const yr=({visible:m,onCancel:f,workOrderData:T,workOrderId:j})=>{const{t}=W(),[b,P]=n.useState([]),[k,g]=n.useState(!1),[y,d]=n.useState(!1),[a,u]=n.useState(),[h,l]=n.useState(""),c=n.useRef({}),p=j??T?.id;c.current={selectedTemplateId:a,effectiveWorkOrderId:p},n.useEffect(()=>{m&&(_(),u(void 0),l(""))},[m]),n.useEffect(()=>{m&&a&&p?I():l("")},[m,a,p]);const _=async()=>{g(!0);try{const r=await L({is_active:!0,document_type:"work_order"});P(r);const i=r.find(o=>o.is_default)??r.find(o=>o.code===M.work_order)??r[0];i&&u(i.uuid)}catch(r){w(r,t("app.kuaizhizao.workOrder.msgLoadPrintTemplateFailed"))}finally{g(!1)}},I=async()=>{if(!p||!a)return;const r=`${a}-${p}`;d(!0);try{const i=await O(`/apps/kuaizhizao/work-orders/${p}/print`,{method:"GET",params:{template_uuid:a,output_format:"html",response_format:"json"}}),o=c.current;if(r!==`${o.selectedTemplateId}-${o.effectiveWorkOrderId}`)return;l(i?.content??"")}catch(i){const o=c.current;if(r!==`${o.selectedTemplateId}-${o.effectiveWorkOrderId}`)return;w(i,t("app.kuaizhizao.workOrder.msgLoadPreviewFailed")),l("")}finally{const i=c.current;r===`${i.selectedTemplateId}-${i.effectiveWorkOrderId}`&&d(!1)}},S=async()=>{if(!p){s.warning(t("app.kuaizhizao.workOrder.msgWorkOrderIdMissingPrint"));return}if(!a){s.warning(t("app.kuaizhizao.workOrder.msgSelectPrintTemplate"));return}d(!0);try{const i=(await O(`/apps/kuaizhizao/work-orders/${p}/print`,{method:"GET",params:{template_uuid:a,output_format:"html",response_format:"json"}}))?.content??"";if(!i){s.error(t("app.kuaizhizao.workOrder.msgPrintContentEmpty"));return}const o=window.open("","_blank");o?(o.document.write(`<!DOCTYPE html><html><head><meta charset="UTF-8"><title>${t("common.print")}</title></head><body>${i}</body></html>`),o.document.close(),o.focus(),o.print(),o.close(),s.success(t("app.kuaizhizao.workOrder.msgPrintSent"))):s.error(t("app.kuaizhizao.workOrder.msgPrintPopupBlocked"))}catch(r){w(r,t("app.kuaizhizao.workOrder.msgPrintFailed"))}finally{d(!1)}};return e.jsxs(E,{title:e.jsxs("div",{className:"no-print",style:{display:"flex",alignItems:"center",justifyContent:"space-between",width:"100%",gap:16},children:[e.jsx("span",{style:{fontWeight:600,fontSize:16},children:t("app.kuaizhizao.workOrder.modalPrintTitle")}),e.jsx(C,{style:{width:260,flexShrink:0},placeholder:t("app.kuaizhizao.workOrder.msgSelectPrintTemplatePlaceholder"),value:a,onChange:u,loading:k,options:b.map(r=>({label:r.name,value:r.uuid}))})]}),open:m,onCancel:f,width:H.LARGE_WIDTH,wrapClassName:"work-order-print-modal-wrap",styles:{body:{padding:0,overflow:"hidden",height:"70vh",minHeight:500}},footer:[e.jsx(x,{onClick:f,children:t("common.cancel")},"cancel"),e.jsx(x,{type:"primary",icon:e.jsx($,{}),onClick:S,loading:y,disabled:!a||!p,children:t("common.print")},"print")],className:"work-order-print-modal",children:[e.jsx(v,{spinning:k,children:e.jsx("div",{className:"work-order-print-preview",style:{height:"100%",overflow:"auto"},children:p?y&&!h?e.jsx("div",{style:{display:"flex",justifyContent:"center",alignItems:"center",height:"100%",minHeight:400},children:e.jsx(v,{description:t("app.kuaizhizao.workOrder.msgLoadingPreview"),children:e.jsx("div",{style:{minHeight:24}})})}):h?e.jsx("div",{dangerouslySetInnerHTML:{__html:h},style:{height:"100%",overflow:"auto",padding:16}}):e.jsx(z,{description:t("app.kuaizhizao.workOrder.msgSelectValidPrintTemplate"),style:{paddingTop:100}}):e.jsx(z,{description:t("app.kuaizhizao.workOrder.msgWorkOrderIdMissingPreview"),style:{paddingTop:100}})})}),e.jsx("style",{children:`
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
