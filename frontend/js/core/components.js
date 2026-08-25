// Shared visual components. Safety colours are semantic and never follow the brand.
(function(){
  if(document.getElementById("vcms-component-css"))return;
  var style=document.createElement("style"); style.id="vcms-component-css";
  style.textContent=`
  @media screen{
    :root{
      --vcms-brand:#C00000;--vcms-brand-dark:#960000;--vcms-brand-hover:#A70000;
      --vcms-brand-soft:#F9E6E6;--vcms-brand-border:#E6A3A3;--vcms-on-brand:#fff;
      --vcms-success:#15803D;--vcms-success-soft:#ECFDF3;
      --vcms-warning:#B45309;--vcms-warning-soft:#FFFBEB;
      --vcms-danger:#B91C1C;--vcms-danger-soft:#FEF2F2;
      --vcms-ink:#182230;--vcms-muted:#667085;--vcms-surface:#fff;--vcms-page:#EEF1F5;
      --vcms-line:#DCE1E8;--vcms-control-h:46px;--vcms-radius:12px;
    }
    :root[data-theme="dark"]{--vcms-ink:#F3F4F6;--vcms-muted:#AAB3C0;--vcms-surface:#1B2028;--vcms-page:#0F1216;--vcms-line:#353D49}
    :root[data-theme="contrast"]{font-size:17px;--vcms-ink:#000;--vcms-muted:#111;--vcms-surface:#fff;--vcms-page:#fff;--vcms-line:#111}
    body{color:var(--vcms-ink)}
    .bg-red-600,.bg-red-700{background-color:var(--vcms-brand)!important;color:var(--vcms-on-brand)!important}
    header.bg-red-700,.bg-red-800{background-color:var(--vcms-brand-dark)!important;color:var(--vcms-on-brand)!important}
    .text-red-600,.text-red-700{color:var(--vcms-brand)!important}.border-red-600,.border-red-700{border-color:var(--vcms-brand)!important}
    .accent-red-600,.accent-red-700{accent-color:var(--vcms-brand)!important}.focus\\:ring-red-600:focus{--tw-ring-color:var(--vcms-brand)!important}
    .vcms-btn{min-height:var(--vcms-control-h);display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:0 16px;border:1px solid transparent;border-radius:10px;font-weight:800;font-size:14px;line-height:1.1;transition:background .15s,border-color .15s,transform .08s;white-space:nowrap}
    .vcms-btn:active{transform:translateY(1px)}.vcms-btn:focus-visible,.vcms-control:focus-visible{outline:3px solid var(--vcms-brand-border);outline-offset:2px}
    .vcms-btn-primary{background:var(--vcms-brand);color:var(--vcms-on-brand)}.vcms-btn-primary:hover{background:var(--vcms-brand-hover)}
    .vcms-btn-secondary{background:#252B35;color:#fff}.vcms-btn-tertiary{background:var(--vcms-surface);color:var(--vcms-ink);border-color:var(--vcms-line)}
    .vcms-btn-danger{background:var(--vcms-surface);color:var(--vcms-danger);border-color:var(--vcms-danger)}
    .vcms-btn-success{background:var(--vcms-success);color:#fff}.vcms-btn:disabled{background:#E5E7EB!important;color:#8A94A3!important;border-color:#D1D5DB!important;cursor:not-allowed;box-shadow:none;transform:none}
    .vcms-control{height:var(--vcms-control-h);min-height:var(--vcms-control-h);width:100%;padding:0 12px;border:1px solid var(--vcms-line);border-radius:10px;background:var(--vcms-surface);color:var(--vcms-ink);font-size:14px}
    textarea.vcms-control{height:auto;min-height:96px;padding-top:10px;padding-bottom:10px}.vcms-label{display:block;margin:0 0 6px;color:var(--vcms-muted);font-size:11px;font-weight:800;letter-spacing:.06em;text-transform:uppercase}
    .vcms-page-header{background:var(--vcms-brand-dark);color:var(--vcms-on-brand);box-shadow:0 2px 8px rgba(15,23,42,.18);position:sticky;top:0;z-index:20}
    .vcms-page-header__row{min-height:60px;display:flex;align-items:center;gap:10px;padding:10px 16px}.vcms-page-header__back{width:28px;min-height:40px;display:grid;place-items:center;font-size:25px;font-weight:800}
    .vcms-page-header__title{min-width:0;flex:1}.vcms-page-header__title h1{font-size:18px;font-weight:800;line-height:1.2}.vcms-page-header__title p{font-size:12px;opacity:.82;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .vcms-page-toolbar{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:0 16px 12px}.vcms-page-toolbar>*{min-width:0}
    .vcms-status{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border-radius:999px;font-size:11px;font-weight:800}.vcms-status-success{color:var(--vcms-success);background:var(--vcms-success-soft)}.vcms-status-warning{color:var(--vcms-warning);background:var(--vcms-warning-soft)}.vcms-status-danger{color:var(--vcms-danger);background:var(--vcms-danger-soft)}.vcms-status-neutral{color:#475467;background:#F2F4F7}
    :root[data-theme="dark"] body,:root[data-theme="dark"] .bg-gray-100,:root[data-theme="dark"] .bg-gray-50{background:var(--vcms-page)!important;color:var(--vcms-ink)!important}
    :root[data-theme="dark"] .bg-white,:root[data-theme="dark"] .panel{background:var(--vcms-surface)!important;color:var(--vcms-ink)!important;border-color:var(--vcms-line)!important}
    :root[data-theme="dark"] input,:root[data-theme="dark"] select,:root[data-theme="dark"] textarea{background:#11161D!important;color:var(--vcms-ink)!important;border-color:var(--vcms-line)!important}
    :root[data-theme="contrast"] body,:root[data-theme="contrast"] .bg-gray-100,:root[data-theme="contrast"] .bg-gray-50{background:#fff!important;color:#000!important}
    :root[data-theme="contrast"] .bg-white,:root[data-theme="contrast"] .panel{background:#fff!important;color:#000!important;border:2px solid #111!important;box-shadow:none!important}
    :root[data-theme="contrast"] input,:root[data-theme="contrast"] select,:root[data-theme="contrast"] textarea{background:#fff!important;color:#000!important;border:2px solid #111!important}
    @media(min-width:900px){.vcms-page-header__row{padding-left:24px;padding-right:24px}.vcms-page-toolbar{display:flex;padding:0 24px 12px}.vcms-page-toolbar>*{max-width:320px}}
  }
  @media print{
    :root{--vcms-brand:#C00000;--vcms-brand-dark:#960000;--vcms-on-brand:#fff;--vcms-success:#15803D;--vcms-warning:#B45309;--vcms-danger:#B91C1C}
    .vcms-toast{display:none!important}
  }`;
  (document.head||document.documentElement).appendChild(style);
})();
