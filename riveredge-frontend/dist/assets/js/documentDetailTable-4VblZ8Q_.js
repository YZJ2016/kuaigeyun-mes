import{j as t,G as c,r as m,aw as p,H as x,T as h,a1 as o,br as r,I as T}from"./vendor-CYKOW_ZJ.js";import{c as b}from"./clientRelease-BIOroJJr.js";const f="quotation-detail-table",L={material:280,variantAttributes:240,spec:140,unit:108,quantity:112,unitPrice:132,exclAmount:120,taxRate:108,taxAmount:112,lineAmount:132,deliveryDate:152,notes:140},A={align:"left"},_={align:"right",onHeaderCell:()=>({style:{textAlign:"left"}})},O={display:"block",textAlign:"right"},I={width:"100%",minWidth:140},N={className:f,size:"medium",style:{width:"100%",margin:0}},s="medium",u="—";function E({readOnly:e,placeholder:i=u,size:n=s,...l}){return t.jsx(T,{readOnly:e,placeholder:i,size:n,...l})}function j(e){return t.jsx(E,{readOnly:!0,placeholder:u,...e})}const D=`
  .quotation-detail-table .quotation-material-cell .ant-form-item,
  .quotation-detail-table .quotation-material-cell .ant-form-item-control,
  .quotation-detail-table .quotation-material-cell .ant-form-item-control-input,
  .quotation-detail-table .quotation-material-cell .ant-select,
  .quotation-detail-table .uni-detail-material-cell .ant-form-item,
  .quotation-detail-table .uni-detail-material-cell .ant-form-item-control,
  .quotation-detail-table .uni-detail-material-cell .ant-form-item-control-input,
  .quotation-detail-table .uni-detail-material-cell .ant-select {
    width: 100% !important;
    min-width: 0;
  }
  .quotation-detail-table .ant-input-number-input::selection,
  .quotation-detail-table .ant-input::selection {
    background-color: var(--ant-color-primary, #1677ff);
    color: #fff;
    border-radius: 0;
  }
  .quotation-detail-table td.ant-table-cell-align-right .ant-input-number-input {
    text-align: right;
  }
  .quotation-detail-table td.quotation-tax-rate-col {
    overflow: hidden;
  }
  .quotation-detail-table .quotation-tax-rate-cell,
  .quotation-detail-table .quotation-tax-rate-cell .ant-form-item,
  .quotation-detail-table .quotation-tax-rate-cell .ant-form-item-control-input {
    max-width: 100%;
    min-width: 0;
  }
  .quotation-detail-table .quotation-tax-rate-cell .ant-input-number-group-wrapper {
    display: flex;
    width: 100%;
    max-width: 100%;
  }
  .quotation-detail-table .quotation-tax-rate-cell .ant-input-number {
    flex: 1 1 auto;
    min-width: 0;
    width: auto !important;
  }
  .quotation-detail-table .quotation-tax-rate-cell .ant-input-number-group-addon {
    flex: 0 0 auto;
    padding-inline: 6px;
  }
`;function w(){return t.jsx("style",{children:D})}const q={display:"flex",flexDirection:"column",gap:10,minWidth:220,paddingTop:2};function R({onBatch:e}){const{t:i}=b(),[n,l]=m.useState(13);return t.jsxs("span",{style:{whiteSpace:"nowrap"},children:[i("app.kuaizhizao.salesOrder.taxRate"),t.jsx(p,{icon:null,title:i("app.kuaizhizao.salesOrder.taxRateBatchTitle"),description:t.jsxs("div",{style:q,children:[t.jsx(h.Text,{type:"secondary",style:{fontSize:12,lineHeight:1.5},children:i("app.kuaizhizao.salesOrder.taxRateBatchHint")}),t.jsxs(o.Compact,{style:{width:"100%"},children:[t.jsx(r,{min:0,max:100,precision:0,value:n,onChange:a=>l(typeof a=="number"?a:13),style:{width:"100%"}}),t.jsx("span",{style:d,children:"%"})]})]}),onConfirm:()=>{const a=Math.round(Number(n));!Number.isNaN(a)&&a>=0&&a<=100&&e(a)},onOpenChange:a=>{a&&l(13)},children:t.jsx(x,{type:"link",size:"small",style:{padding:"0 4px",height:"auto"},onClick:a=>a.stopPropagation(),children:i("app.kuaizhizao.salesOrder.batch")})})]})}const d={display:"inline-flex",alignItems:"center",padding:"0 4px",color:"var(--ant-color-text-secondary)",background:"var(--ant-color-fill-alter)",border:"1px solid var(--ant-color-border)",borderLeft:0,borderRadius:"0 var(--ant-border-radius) var(--ant-border-radius) 0",fontSize:"inherit",flexShrink:0};function y({value:e,onChange:i,size:n=s,inputWidth:l=64}){return t.jsxs(o.Compact,{style:{width:"auto",minWidth:0},children:[t.jsx(r,{value:e,onChange:i,placeholder:"0",min:0,max:100,precision:0,controls:!1,size:n,style:{width:l,minWidth:0}}),t.jsx("span",{style:d,children:"%"})]})}function S({index:e}){return t.jsx("div",{className:"quotation-tax-rate-cell",children:t.jsx(c.Item,{name:[e,"tax_rate"],style:{margin:0},children:t.jsx(y,{})})})}({..._});export{L as D,S as T,A as a,s as b,E as c,j as d,w as e,N as f,_ as g,R as h,u as i,O as j,I as k,y as l};
