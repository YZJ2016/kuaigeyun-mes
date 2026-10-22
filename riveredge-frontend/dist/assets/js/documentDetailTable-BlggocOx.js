import{j as t,G as r,H as u,I as s,a1 as d,br as c}from"./vendor-Dydz7BWI.js";import{c as m}from"./clientRelease-yJWjgpia.js";const p="quotation-detail-table",f={material:280,variantAttributes:240,spec:140,unit:108,quantity:112,unitPrice:132,exclAmount:120,taxRate:108,taxAmount:112,lineAmount:132,deliveryDate:152,notes:140},q={align:"left"},D={align:"right",onHeaderCell:()=>({style:{textAlign:"left"}})},L={display:"block",textAlign:"right"},A={width:"100%",minWidth:140},C={className:p,size:"middle",style:{width:"100%",margin:0}},i="middle",n="—";function x({readOnly:a,placeholder:e=n,size:l=i,...o}){return t.jsx(s,{readOnly:a,placeholder:e,size:l,...o})}function I(a){return t.jsx(x,{readOnly:!0,placeholder:n,...a})}const T=`
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
`;function g(){return t.jsx("style",{children:T})}function O({onBatch:a}){const{t:e}=m();return t.jsxs("span",{style:{whiteSpace:"nowrap"},children:[e("app.kuaizhizao.salesOrder.taxRate"),t.jsx(u,{type:"link",size:"small",style:{padding:"0 4px",height:"auto"},onClick:a,children:e("app.kuaizhizao.salesOrder.batch")})]})}const b={display:"inline-flex",alignItems:"center",padding:"0 8px",color:"var(--ant-color-text-secondary)",background:"var(--ant-color-fill-alter)",border:"1px solid var(--ant-color-border)",borderLeft:0,borderRadius:"0 var(--ant-border-radius) var(--ant-border-radius) 0",fontSize:"inherit"};function E({value:a,onChange:e}){return t.jsxs(d.Compact,{style:{width:"100%"},children:[t.jsx(c,{value:a,onChange:e,placeholder:"0",min:0,max:100,precision:0,controls:!1,size:i,style:{width:"100%"}}),t.jsx("span",{style:b,children:"%"})]})}function y({index:a}){return t.jsx("div",{className:"quotation-tax-rate-cell",children:t.jsx(r.Item,{name:[a,"tax_rate"],style:{margin:0},children:t.jsx(E,{})})})}export{g as D,y as T,C as a,q as b,f as c,D as d,i as e,O as f,A as g,x as h,I as i,n as j,L as k};
