// VCMS appearance foundation: company brand + personal display mode.
(function () {
  var PRESETS = {
    vortex: "#C00000", blue: "#1565C0", orange: "#C2410C",
    navy: "#1E3A5F", emerald: "#047857"
  };
  var MODE_KEY = "vcms_mode", BRAND_KEY = "vcms_company_appearance_v1";

  function cleanHex(value, fallback) {
    value = String(value || "").trim().toUpperCase();
    return /^#[0-9A-F]{6}$/.test(value) ? value : fallback;
  }
  function rgb(hex) {
    hex = cleanHex(hex, "#C00000").slice(1);
    return [parseInt(hex.slice(0,2),16), parseInt(hex.slice(2,4),16), parseInt(hex.slice(4,6),16)];
  }
  function mix(hex, target, weight) {
    var a=rgb(hex), b=rgb(target), out=a.map(function(v,i){return Math.round(v+(b[i]-v)*weight)});
    return "#"+out.map(function(v){return v.toString(16).padStart(2,"0")}).join("").toUpperCase();
  }
  function readable(hex) {
    var c=rgb(hex), y=(c[0]*299+c[1]*587+c[2]*114)/1000;
    return y >= 155 ? "#111827" : "#FFFFFF";
  }
  function readBrand() {
    try {
      var hit=JSON.parse(localStorage.getItem(BRAND_KEY)||"null");
      if(hit && hit.primary) return {preset:hit.preset||"custom",primary:cleanHex(hit.primary,"#C00000"),t:hit.t||0};
    } catch (_) {}
    return {preset:"vortex",primary:"#C00000",t:0};
  }
  function readMode() {
    var mode=localStorage.getItem(MODE_KEY), old=localStorage.getItem("vcms_theme");
    if(!mode && old){mode=old==="sun"?"contrast":old;localStorage.setItem(MODE_KEY,mode)}
    return /^(light|dark|contrast)$/.test(mode||"") ? mode : "light";
  }
  function applyBrand(value) {
    value=value||readBrand(); var primary=cleanHex(value.primary,PRESETS[value.preset]||"#C00000");
    var root=document.documentElement.style;
    root.setProperty("--vcms-brand",primary);
    root.setProperty("--vcms-brand-dark",mix(primary,"#000000",.22));
    root.setProperty("--vcms-brand-hover",mix(primary,"#000000",.13));
    root.setProperty("--vcms-brand-soft",mix(primary,"#FFFFFF",.90));
    root.setProperty("--vcms-brand-border",mix(primary,"#FFFFFF",.62));
    root.setProperty("--vcms-on-brand",readable(primary));
    document.documentElement.setAttribute("data-brand",value.preset||"custom");
    var meta=document.querySelector('meta[name="theme-color"]'); if(meta)meta.content=mix(primary,"#000000",.22);
    window.dispatchEvent(new CustomEvent("vcmsappearancechange",{detail:{brand:value,mode:readMode()}}));
  }
  function applyMode(mode) {
    mode=/^(light|dark|contrast)$/.test(mode)?mode:"light";
    document.documentElement.setAttribute("data-theme",mode);
    window.dispatchEvent(new CustomEvent("vcmsappearancechange",{detail:{brand:readBrand(),mode:mode}}));
  }
  function setBrand(value) {
    var saved={preset:value.preset||"custom",primary:cleanHex(value.primary,"#C00000"),t:Date.now()};
    localStorage.setItem(BRAND_KEY,JSON.stringify(saved)); applyBrand(saved); return saved;
  }
  function setMode(mode) { localStorage.setItem(MODE_KEY,mode); applyMode(mode); }

  window.VCMS_APPEARANCE={presets:PRESETS,getBrand:readBrand,setBrand:setBrand,getMode:readMode,setMode:setMode,applyBrand:applyBrand};
  window.vmmsGetTheme=readMode; window.vmmsSetTheme=setMode;
  applyBrand(readBrand()); applyMode(readMode());

  // Refresh the company brand at most every six hours; normal navigation uses the phone cache.
  window.addEventListener("load",function(){
    var cached=readBrand();
    if(cached.t && Date.now()-cached.t<6*3600000)return;
    if(typeof getSession!=="function" || !getSession() || typeof vmmsApi!=="function")return;
    vmmsApi("/api/v1/appearance").then(function(r){return r.ok?r.json():null}).then(function(v){if(v)setBrand(v)}).catch(function(){});
  });
})();
