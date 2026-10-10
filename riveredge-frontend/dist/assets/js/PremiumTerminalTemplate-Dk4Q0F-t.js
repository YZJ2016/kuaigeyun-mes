import{V as j,j as e,X as f,aG as w,ax as S,H as _,aW as J,a1 as Y,b4 as Q,c$ as ee,T as Z,b9 as te,dF as K,r as A,a0 as ie,a4 as ne,aa as ae,ag as re,dc as oe,cp as le,a as se}from"./vendor-BcwDzyu6.js";import{aa as D,cV as n,cW as p,au as me}from"./main-BT-YepRy.js";import{c as z,ae as U}from"./clientRelease-9nO3kfEr.js";import{H as t}from"./design-DWUomomX.js";import{T as X}from"./touch-CzJ4Jti_.js";import{t as pe,H as de}from"./hmi-BXeRw_0B.js";const W={HEADER_HEIGHT:64,METRICS_HEIGHT:80,LEFT_PANEL_WIDTH:320,RIGHT_PANEL_WIDTH:360},Ne={SECTION_GAP:20},{useToken:ce}=j,Ee=({quickActions:o=[],todos:a=[],stats:r=[],quickEntries:d=[],children:c,className:y,style:x,showConfigButton:s=!1,onConfigClick:T})=>{const{t:g}=z(),{token:h}=ce(),N=a.length>0||r.length>0||d.length>0;return e.jsxs("div",{className:y,style:{padding:0,flex:1,minHeight:0,width:"100%",display:"flex",flexDirection:"column",backgroundColor:"transparent",boxSizing:"border-box",...x},children:[o.length>0&&e.jsx(f,{title:g("components.layoutTemplates.dashboard.quickActions"),style:{marginBottom:D.BLOCK_GAP},extra:s&&T?e.jsx(_,{type:"text",size:"small",icon:e.jsx(J,{}),onClick:i=>{i.stopPropagation(),T()},children:g("components.layoutTemplates.dashboard.configure")}):void 0,children:e.jsx(w,{gutter:n.SPACING.MD,children:o.map((i,m)=>e.jsx(S,{xs:12,sm:8,md:6,lg:4,xl:4,xxl:3,children:e.jsxs(f,{hoverable:!i.disabled,onClick:()=>{i.disabled||i.onClick?.()},style:{cursor:i.disabled?"not-allowed":"pointer",textAlign:"center",padding:`${n.SPACING.MD}px`,opacity:i.disabled?.5:1},children:[e.jsx("div",{style:{fontSize:n.FONT_SIZE.XXL*1.5,marginBottom:n.SPACING.SM,color:i.type==="primary"?h.colorPrimary:h.colorText,display:"flex",justifyContent:"center",alignItems:"center"},children:i.icon}),e.jsx("div",{style:{fontSize:n.FONT_SIZE.SM,color:h.colorText,fontWeight:500},children:i.title})]})},m))})}),N&&e.jsxs(w,{gutter:n.SPACING.MD,children:[e.jsxs(S,{xs:24,lg:16,children:[a.length>0&&e.jsx(f,{title:g("components.layoutTemplates.dashboard.todos"),style:{marginBottom:D.BLOCK_GAP},children:e.jsx(w,{gutter:n.SPACING.MD,children:a.map((i,m)=>e.jsx(S,{xs:p.TODO_COLUMNS.xs*24,sm:p.TODO_COLUMNS.sm*24,md:p.TODO_COLUMNS.md*12,lg:p.TODO_COLUMNS.lg*12,xl:p.TODO_COLUMNS.xl*12,xxl:p.TODO_COLUMNS.xxl*12,children:e.jsx(f,{hoverable:!0,onClick:i.onClick,style:{cursor:"pointer"},children:e.jsxs(Y,{children:[e.jsx(Q,{count:i.count,showZero:!0,style:{backgroundColor:h.colorPrimary}}),e.jsx("span",{children:i.title})]})})},m))})}),r.length>0&&e.jsx(f,{title:g("components.layoutTemplates.dashboard.statsBoard"),children:e.jsx(w,{gutter:n.SPACING.MD,children:r.map((i,m)=>e.jsx(S,{xs:p.STAT_COLUMNS.xs*24,sm:p.STAT_COLUMNS.sm*12,md:p.STAT_COLUMNS.md*12,lg:p.STAT_COLUMNS.lg*8,xl:p.STAT_COLUMNS.xl*8,xxl:p.STAT_COLUMNS.xxl*8,children:e.jsx(f,{hoverable:!!i.onClick,onClick:i.onClick,style:{cursor:i.onClick?"pointer":"default"},children:e.jsxs("div",{style:{textAlign:"center"},children:[e.jsxs("div",{style:{fontSize:n.FONT_SIZE.XXL,fontWeight:600,color:i.valueStyle?.color||h.colorPrimary,marginBottom:n.SPACING.XS},children:[i.prefix,i.value,i.suffix&&e.jsx("span",{style:{fontSize:n.FONT_SIZE.MD},children:i.suffix})]}),e.jsx("div",{style:{fontSize:n.FONT_SIZE.SM,color:h.colorTextSecondary},children:i.title})]})})},m))})})]}),e.jsx(S,{xs:24,lg:8,children:d.length>0&&e.jsx(f,{title:g("components.layoutTemplates.dashboard.quickEntries"),children:e.jsx(w,{gutter:n.SPACING.MD,children:d.map((i,m)=>e.jsx(S,{xs:12,sm:8,md:8,lg:12,xl:12,xxl:12,children:e.jsxs(f,{hoverable:!0,onClick:i.onClick,style:{cursor:"pointer",textAlign:"center",padding:n.SPACING.MD},children:[e.jsx("div",{style:{fontSize:n.FONT_SIZE.XXL,marginBottom:n.SPACING.SM},children:i.icon}),e.jsx("div",{style:{fontSize:n.FONT_SIZE.SM},children:i.title})]})},m))})})})]}),c&&e.jsx("div",{style:{flex:1,minHeight:0,display:"flex",flexDirection:"column",marginTop:0},children:c})]})},{useToken:xe}=j,Ie=({steps:o,current:a,onStepChange:r,onPrev:d,onNext:c,onFinish:y,showPrev:x=!0,showNext:s=!0,showFinish:T=!0,prevText:g,nextText:h,finishText:N,nextDisabled:i=!1,finishDisabled:m=!1,onSkip:k,skipText:C,className:M,style:L})=>{const{t:E}=z(),{token:I}=xe(),G=g??E("common.previous"),$=h??E("common.next"),O=N??E("components.layoutTemplates.wizard.finish"),B=C??E("components.layoutTemplates.wizard.skipLater"),b=a===0,v=a===o.length-1,P=()=>{if(a>0){const u=a-1;r?.(u),d?.()}},H=()=>{if(a<o.length-1){const u=a+1;r?.(u),c?.()}},F=()=>{y?.()};return e.jsxs("div",{className:M,style:{...me(),...L},children:[e.jsx(f,{style:{marginBottom:D.BLOCK_GAP},children:e.jsx(ee,{current:a,onChange:r,items:o.map(u=>({title:u.title,...u.description&&{content:u.description}}))})}),e.jsx(f,{style:{minHeight:"400px",marginBottom:D.BLOCK_GAP},children:o[a]?.content}),e.jsxs("div",{style:{display:"flex",justifyContent:"space-between",paddingTop:n.SPACING.MD,borderTop:`1px solid ${I.colorBorder}`},children:[e.jsxs(Y,{children:[x&&!b&&e.jsx(_,{onClick:P,children:G}),k&&e.jsx(_,{onClick:k,children:B})]}),e.jsxs(Y,{children:[s&&!v&&e.jsx(_,{type:"primary",onClick:H,disabled:i,children:$}),T&&v&&e.jsx(_,{type:"primary",onClick:F,disabled:m,children:O})]})]})]})},{useToken:ve}=j,{useToken:he}=j,Se=({title:o,children:a,footerButtons:r=[],fullscreen:d=!0,className:c,style:y})=>{const{token:x}=he();return e.jsxs("div",{className:["hmi-root",c].filter(Boolean).join(" "),style:{width:"100%",height:d?"calc(100vh - var(--station-layout-bar-height, 0px))":"auto",padding:`${n.SPACING.LG}px`,backgroundColor:x.colorBgLayout,display:"flex",flexDirection:"column",fontSize:X.FONT_MIN_SIZE,...y},children:[o&&e.jsx("div",{style:{fontSize:Math.max(X.TITLE_FONT_SIZE,t.FONT_TITLE_MIN),fontWeight:600,marginBottom:n.SPACING.LG,textAlign:"center",color:x.colorTextHeading},children:o}),e.jsx("div",{style:{flex:1,overflowY:"auto",marginBottom:r.length>0?n.SPACING.LG:0},children:a}),r.length>0&&e.jsx("div",{style:{display:"flex",flexWrap:"wrap",alignItems:"stretch",justifyContent:"center",gap:n.SPACING.MD,paddingTop:n.SPACING.MD,borderTop:`1px solid ${x.colorBorder}`},children:r.map((s,T)=>e.jsx("div",{style:{flex:s.block===!1?"0 1 auto":"1 1 220px",minWidth:s.block===!1?void 0:220,maxWidth:"100%"},children:e.jsx(_,{size:"large",...pe({variant:s.type==="primary"?"primary":"default",size:"action"}),icon:s.icon,onClick:s.onClick,disabled:s.disabled,block:!0,children:s.title})},T))})]})},{useToken:Ae}=j,{useToken:ke}=j,{Title:Ce,Text:Oe}=Z,{useToken:Pe}=j,{Title:Re,Text:we,Paragraph:De}=Z,{Panel:Me}=te;function V(o){if(!o?.trim())return!1;const a=o.trim(),r=a.toLowerCase();return a==="管理员"||r==="admin"||r==="administrator"||r==="root"}const{Header:ue,Content:fe}=K,Le=({operatorName:o,operatorAvatar:a,operatorRole:r,operatorEmail:d,stationName:c,stationArea:y,stationWorkshop:x,stationLine:s,children:T,headerExtra:g,headerCenter:h,headerAfterClock:N,modeBadge:i,headerLeftExtra:m,hideStationBreadcrumb:k=!1,clockFormat:C="full",hideFullscreenToggle:M=!1,hideOperatorBlock:L=!1,contentPadding:E=24})=>{const{t:I}=z(),G=o??I("components.layoutTemplates.premiumTerminal.notLoggedIn"),$=c??I("components.layoutTemplates.premiumTerminal.notBound"),[O,B]=A.useState(U(new Date,"YYYY-MM-DD HH:mm:ss")),[b,v]=A.useState(!1),P=A.useRef(null);A.useEffect(()=>{const l=setInterval(()=>{B(U(new Date,"YYYY-MM-DD HH:mm:ss"))},1e3);return()=>clearInterval(l)},[]),A.useEffect(()=>{if(!b||!P.current)return;const l=P.current,R=l.requestFullscreen??l.webkitRequestFullscreen;return R&&R.call(l).catch(()=>v(!1)),()=>{(document.fullscreenElement??document.webkitFullscreenElement)&&(document.exitFullscreen??document.webkitExitFullscreen)?.call(document)}},[b]),A.useEffect(()=>{const l=()=>{!document.fullscreenElement&&!document.webkitFullscreenElement&&v(!1)};return document.addEventListener("fullscreenchange",l),document.addEventListener("webkitfullscreenchange",l),()=>{document.removeEventListener("fullscreenchange",l),document.removeEventListener("webkitfullscreenchange",l)}},[]);const H=()=>{if(b){const l=document.exitFullscreen??document.webkitExitFullscreen;l&&l.call(document)}else v(!0)},F={position:"fixed",top:0,left:0,right:0,bottom:0,width:"100vw",height:"100vh",zIndex:9999,background:t.BG_PRIMARY,display:"flex",flexDirection:"column",overflow:"hidden"},u=e.jsx(ie,{theme:{algorithm:j.darkAlgorithm,token:{...de,colorBgBase:t.BG_PRIMARY}},children:e.jsxs(K,{id:"premium-terminal-layout",className:"hmi-root",style:{height:"100%",minHeight:0,width:"100%",maxWidth:"100%",overflow:"hidden",background:t.BG_PRIMARY,position:"relative",boxSizing:"border-box",display:"flex",flexDirection:"column",fontFamily:t.FONT_FAMILY},children:[e.jsx("style",{children:`
          #premium-terminal-layout .ant-layout-header {
            background: ${t.BG_PANEL} !important;
            color: #ffffff !important;
          }
          #premium-terminal-layout .ant-layout-header .ant-typography,
          #premium-terminal-layout .ant-layout-header .ant-btn {
            color: #ffffff !important;
          }
          #premium-terminal-layout .ant-layout-header .ant-btn-primary {
            color: ${t.TEXT_PRIMARY} !important;
            background: ${t.BG_ELEVATED} !important;
            border-color: ${t.BORDER} !important;
          }
          #premium-terminal-layout .premium-header-extra-item {
            display: inline-flex;
            align-items: center;
            margin-left: 20px;
          }
        `}),e.jsxs(ue,{style:{backgroundColor:t.BG_PANEL,background:t.BG_PANEL,borderBottom:`1px solid ${t.BORDER}`,padding:"0 24px",height:W.HEADER_HEIGHT,minHeight:W.HEADER_HEIGHT,display:"flex",alignItems:"center",zIndex:100,color:t.TEXT_PRIMARY,overflowX:"auto",overflowY:"hidden",flexShrink:0},children:[e.jsxs("div",{className:"header-left-block",children:[i||!k||m?e.jsxs("div",{className:"header-station-cluster",children:[i?e.jsx("div",{className:"header-mode-badge",children:typeof i=="string"?e.jsx("span",{className:"header-mode-badge__label",children:i}):i}):null,k?null:e.jsx("div",{className:"header-station-breadcrumb",children:[y,x,s,c].filter(Boolean).length>0?[y,x,s,c].filter(Boolean).map((l,R,q)=>e.jsx("span",{className:`header-station-segment ${R===q.length-1?"header-station-segment-current":""}`,children:l},R)):e.jsx("span",{className:"header-station-segment header-station-segment-current",children:$})}),m?e.jsx("div",{className:"header-station-cluster__action",children:m}):null]}):null,L?null:e.jsxs(e.Fragment,{children:[e.jsx(ne,{orientation:"vertical",className:"header-divider-v"}),e.jsxs("div",{className:"header-operator-block",children:[e.jsx("span",{className:"header-operator-avatar",children:a?e.jsx("img",{src:a,alt:""}):e.jsx(ae,{style:{fontSize:20,color:t.TEXT_TERTIARY}})}),e.jsxs("div",{className:"header-operator-info",children:[e.jsxs("div",{style:{display:"flex",alignItems:"center",gap:8},children:[e.jsx("span",{className:"header-operator-name",children:G}),r&&e.jsx(re,{variant:"filled",style:{margin:0,background:V(r)?"rgba(255, 179, 0, 0.35)":"rgba(255,255,255,0.12)",color:V(r)?"#ffe58f":"#fff",border:"1px solid rgba(255,255,255,0.2)",fontSize:12,lineHeight:"18px",padding:"0 6px",borderRadius:t.RADIUS_CHIP},children:r})]}),d&&e.jsx("span",{className:"header-operator-email",children:d})]})]})]})]}),e.jsx("div",{className:"header-center-slot",children:h}),e.jsxs("div",{className:"header-right-group",children:[e.jsxs("div",{className:"header-extra-container",children:[M?null:e.jsx(_,{type:"default",icon:b?e.jsx(oe,{}):e.jsx(le,{}),onClick:H,children:I(b?"components.layoutTemplates.premiumTerminal.exitFullscreen":"components.layoutTemplates.premiumTerminal.fullscreen")}),g]}),e.jsxs("div",{className:"header-controls",children:[e.jsx("div",{className:`time-display${C==="hm"?" time-display--hm":""}`,children:e.jsxs("div",{className:"time-display-text",children:[e.jsx("span",{className:"time-display-time",children:C==="hm"?(O.split(" ")[1]||"").slice(0,5):O.split(" ")[1]}),C==="full"?e.jsx("span",{className:"time-display-date",children:O.split(" ")[0]}):null]})}),N?e.jsx("div",{className:"header-after-clock",children:N}):null]})]}),e.jsx("style",{children:`
            #premium-terminal-layout .header-tags-group {
              display: flex;
              gap: 8px;
            }
            #premium-terminal-layout .adaptive-tag {
              display: inline-flex !important;
              align-items: center !important;
              min-height: ${t.TOUCH_MIN_SIZE}px !important;
              padding: 2px 12px !important;
              background: ${t.BG_ELEVATED} !important;
              color: ${t.TEXT_PRIMARY} !important;
              border-radius: ${t.RADIUS_CHIP}px !important;
              white-space: nowrap !important;
              font-size: ${t.FONT_BODY_MIN}px !important;
            }
            
            #premium-terminal-layout .header-center-slot {
              flex: 1 1 auto !important;
              min-width: 20px !important;
              display: flex !important;
              align-items: center !important;
              justify-content: flex-start !important;
              padding: 0 12px !important;
              overflow: hidden !important;
            }
            #premium-terminal-layout .header-right-group {
              display: flex !important;
              align-items: center !important;
              gap: ${t.BUTTON_GAP}px !important;
              flex-shrink: 0 !important;
              min-width: 0 !important;
            }
            #premium-terminal-layout .header-extra-container {
              display: flex !important;
              align-items: center !important;
              gap: ${t.BUTTON_GAP}px !important;
              flex-shrink: 0 !important;
              min-width: 0 !important;
              overflow: visible !important;
            }
            #premium-terminal-layout .header-extra-container > * {
              display: flex !important;
              align-items: center !important;
              gap: ${t.BUTTON_GAP}px !important;
              flex-shrink: 0 !important;
            }
            /* 刷新 / 切换工位 / 全屏 / 时钟后按钮：统一顶栏次级按钮样式 */
            #premium-terminal-layout .header-extra-container .ant-btn,
            #premium-terminal-layout .header-after-clock .ant-btn {
              flex-shrink: 0 !important;
              white-space: nowrap !important;
              width: auto !important;
              min-width: auto !important;
              margin: 0 !important;
              box-sizing: border-box !important;
              border-radius: ${t.PANEL_RADIUS}px !important;
              min-height: 36px !important;
              height: 36px !important;
              padding: 0 18px !important;
              font-size: 14px !important;
              font-weight: 600 !important;
              line-height: 1.4 !important;
              gap: 8px !important;
              background: ${t.BG_ELEVATED} !important;
              border: 1px solid var(--river-border-color) !important;
              color: ${t.TEXT_PRIMARY} !important;
            }
            #premium-terminal-layout .header-extra-container .ant-btn:hover,
            #premium-terminal-layout .header-after-clock .ant-btn:hover {
              background: rgba(255,255,255,0.12) !important;
              border-color: ${t.BORDER} !important;
              color: ${t.TEXT_PRIMARY} !important;
            }
            /* 刷新、切换工位、全屏：统一使用 BG_ELEVATED 配色 */
            #premium-terminal-layout .header-extra-buttons {
              gap: ${t.BUTTON_GAP}px !important;
            }
            #premium-terminal-layout .header-extra-buttons .ant-btn {
              flex-shrink: 0 !important;
            }
            #premium-terminal-layout .header-extra-container .ant-btn .anticon,
            #premium-terminal-layout .header-after-clock .ant-btn .anticon {
              color: #fff !important;
            }
            #premium-terminal-layout .header-extra-container .ant-btn .anticon svg,
            #premium-terminal-layout .header-after-clock .ant-btn .anticon svg {
              fill: #fff !important;
              stroke: #fff !important;
              color: #fff !important;
            }

            #premium-terminal-layout .header-controls {
              display: flex !important;
              align-items: center !important;
              gap: ${t.BUTTON_GAP}px !important;
              flex-shrink: 0 !important;
            }
            #premium-terminal-layout .header-after-clock {
              display: flex !important;
              align-items: center !important;
              gap: ${t.BUTTON_GAP}px !important;
              flex-shrink: 0 !important;
            }

            
            #premium-terminal-layout .header-left-block {
              display: flex !important;
              align-items: center !important;
              flex-shrink: 0 !important;
              gap: 0 !important;
              min-width: 800px !important;
            }
            #premium-terminal-layout .header-divider-v {
              border-color: ${t.BORDER} !important;
              height: 28px !important;
              margin: 0 12px !important;
            }
            /* 工位信息：| A> >B > >C | 形，段间有 gap，箭头方向正确 */
            #premium-terminal-layout .header-station-breadcrumb {
              display: inline-flex !important;
              align-items: stretch !important;
              min-width: 0 !important;
              margin-left: 0 !important;
              border-radius: ${t.PANEL_RADIUS}px !important;
              overflow: hidden !important;
              box-shadow: 0 1px 2px rgba(0,0,0,0.25) !important;
              gap: 4px !important;
              isolation: isolate !important;
            }
            #premium-terminal-layout .header-station-segment {
              position: relative !important;
              padding: 8px 18px !important;
              font-size: 14px !important;
              font-weight: 600 !important;
              letter-spacing: 0.02em !important;
              line-height: 1.4 !important;
              white-space: nowrap !important;
              background: ${t.BG_ELEVATED} !important;
              color: ${t.TEXT_PRIMARY} !important;
              margin-left: 0 !important;
            }
            /* 首段：左直 | 右箭头 >（尖朝右），略亮于普通段 */
            #premium-terminal-layout .header-station-segment:first-child {
              padding-left: 18px !important;
              background: rgba(255,255,255,0.1) !important;
              color: ${t.TEXT_PRIMARY} !important;
              clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 50%, calc(100% - 10px) 100%, 0 100%) !important;
            }
            /* 中间段：左 >（尖朝右） 右 > */
            #premium-terminal-layout .header-station-segment + .header-station-segment:not(.header-station-segment-current) {
              padding-left: 20px !important;
              clip-path: polygon(0 0, 10px 50%, 0 100%, calc(100% - 10px) 100%, 100% 50%, calc(100% - 10px) 0) !important;
            }
            /* 末段：左 >（尖朝右） 右直 | */
            #premium-terminal-layout .header-station-segment + .header-station-segment.header-station-segment-current {
              padding-left: 20px !important;
              background: ${t.BG_ELEVATED} !important;
              color: ${t.TEXT_PRIMARY} !important;
              clip-path: polygon(0 0, 10px 50%, 0 100%, 100% 100%, 100% 0) !important;
            }
            #premium-terminal-layout .header-station-segment:only-child {
              margin-left: 0 !important;
              clip-path: none !important;
              border-radius: ${t.PANEL_RADIUS}px !important;
            }
            #premium-terminal-layout .header-operator-block {
              display: flex !important;
              align-items: center !important;
              gap: 10px !important;
            }
            #premium-terminal-layout .header-operator-avatar {
              width: 36px !important;
              height: 36px !important;
              border-radius: 50% !important;
              overflow: hidden !important;
              background: ${t.BG_ELEVATED} !important;
              display: flex !important;
              align-items: center !important;
              justify-content: center !important;
              flex-shrink: 0 !important;
            }
            #premium-terminal-layout .header-operator-avatar img {
              width: 100% !important;
              height: 100% !important;
              object-fit: cover !important;
            }
            #premium-terminal-layout .header-operator-info {
              display: flex !important;
              flex-direction: column !important;
              align-items: flex-start !important;
              justify-content: center !important;
              gap: 2px !important;
            }
            #premium-terminal-layout .header-operator-name {
              font-size: 14px !important;
              font-weight: 500 !important;
              color: ${t.TEXT_PRIMARY} !important;
              line-height: 1.3 !important;
            }
            #premium-terminal-layout .header-operator-role {
              font-size: 11px !important;
              color: ${t.TEXT_TERTIARY} !important;
              margin-top: 1px !important;
            }
            
            #premium-terminal-layout .time-display {
              background: transparent !important;
              border: none !important;
              padding: 8px 0 !important;
              min-height: auto !important;
              min-width: 96px !important;
              display: flex !important;
              align-items: center !important;
              justify-content: flex-end !important;
              color: ${t.TEXT_PRIMARY} !important;
              flex-shrink: 0 !important;
              box-shadow: none !important;
            }
            #premium-terminal-layout .time-display-text {
              display: flex !important;
              flex-direction: column !important;
              align-items: flex-end !important;
              line-height: 1.3 !important;
            }
            #premium-terminal-layout .time-display-text {
              min-width: 96px !important;
              text-align: right !important;
            }
            #premium-terminal-layout .time-display-time {
              font-family: ${t.FONT_FAMILY} !important;
              font-size: 22px !important;
              font-weight: 600 !important;
              font-variant-numeric: tabular-nums !important;
              letter-spacing: 0.08em !important;
              color: ${t.TEXT_PRIMARY} !important;
            }
            #premium-terminal-layout .time-display-date {
              font-size: 12px !important;
              font-variant-numeric: tabular-nums !important;
              color: ${t.TEXT_TERTIARY} !important;
              margin-top: 2px !important;
            }
            
            @media (max-width: 1200px) {
              #premium-terminal-layout .adaptive-tag span { display: none; }
              #premium-terminal-layout .hidden-mobile { display: none; }
            }

            @media (max-width: 1400px) {
              #premium-terminal-layout .hidden-tablet { display: none; }
            }
            
          `})]}),e.jsx(fe,{style:{padding:E,flex:1,minHeight:0,overflow:"hidden",display:"flex",flexDirection:"column",boxSizing:"border-box"},children:T})]})});return b?se.createPortal(e.jsx("div",{ref:P,className:"premium-terminal-fullscreen-wrap",style:F,children:u}),document.body):e.jsx("div",{style:{height:"100%",minHeight:0,display:"flex",flexDirection:"column"},children:u})};export{Ee as D,W as H,Le as P,Se as T,Ie as W,Ne as a};
