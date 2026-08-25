// VCMS appearance foundation: company brand + personal display mode.
(function () {
  var PRESETS = {
    executive:{primary:"#B42318",secondary:"#273142",accent:"#D6A32F",page:"#F2F4F7",surface:"#FFFFFF",ink:"#182230"},
    industrial:{primary:"#175CD3",secondary:"#202B3C",accent:"#00A3A3",page:"#EEF3F8",surface:"#FFFFFF",ink:"#172B4D"},
    construction:{primary:"#C76A00",secondary:"#29313D",accent:"#1E6F68",page:"#F7F3ED",surface:"#FFFFFF",ink:"#252A32"},
    vortex:{primary:"#C00000",secondary:"#273142",accent:"#D6A32F",page:"#F2F4F7",surface:"#FFFFFF",ink:"#182230"},
    blue:{primary:"#1565C0",secondary:"#202B3C",accent:"#00A3A3",page:"#EEF3F8",surface:"#FFFFFF",ink:"#172B4D"},
    orange:{primary:"#C2410C",secondary:"#29313D",accent:"#1E6F68",page:"#F7F3ED",surface:"#FFFFFF",ink:"#252A32"},
    navy:{primary:"#1E3A5F",secondary:"#202B3C",accent:"#00A3A3",page:"#EEF3F8",surface:"#FFFFFF",ink:"#172B4D"},
    emerald:{primary:"#047857",secondary:"#273142",accent:"#D6A32F",page:"#F2F4F7",surface:"#FFFFFF",ink:"#182230"}
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
  function normalise(value) {
    value=value||{}; var base=PRESETS[value.preset]||PRESETS.executive;
    return {preset:value.preset||"executive",primary:cleanHex(value.primary,base.primary),
      secondary:cleanHex(value.secondary,base.secondary),accent:cleanHex(value.accent,base.accent),
      page:cleanHex(value.page,base.page),surface:cleanHex(value.surface,base.surface),
      ink:cleanHex(value.ink,base.ink),t:value.t||0};
  }
  function readBrand() {
    try {
      var hit=JSON.parse(localStorage.getItem(BRAND_KEY)||"null");
      if(hit && hit.primary) return normalise(hit);
    } catch (_) {}
    return normalise({preset:"executive",t:0});
  }
  function readMode() {
    var mode=localStorage.getItem(MODE_KEY), old=localStorage.getItem("vcms_theme");
    if(!mode && old){mode=old==="sun"?"contrast":old;localStorage.setItem(MODE_KEY,mode)}
    return /^(light|dark|contrast)$/.test(mode||"") ? mode : "light";
  }
  function applyBrand(value) {
    value=normalise(value||readBrand()); var primary=value.primary;
    var root=document.documentElement.style;
    root.setProperty("--vcms-brand",primary);
    root.setProperty("--vcms-brand-dark",mix(primary,"#000000",.22));
    root.setProperty("--vcms-brand-hover",mix(primary,"#000000",.13));
    root.setProperty("--vcms-brand-soft",mix(primary,"#FFFFFF",.90));
    root.setProperty("--vcms-brand-border",mix(primary,"#FFFFFF",.62));
    root.setProperty("--vcms-on-brand",readable(primary));
    root.setProperty("--vcms-secondary",value.secondary);
    root.setProperty("--vcms-accent",value.accent);
    root.setProperty("--vcms-page",value.page);
    root.setProperty("--vcms-surface",value.surface);
    root.setProperty("--vcms-ink",value.ink);
    root.setProperty("--brand",primary);root.setProperty("--brand2",mix(primary,"#000000",.22));
    root.setProperty("--bg",value.page);root.setProperty("--ink",value.ink);root.setProperty("--line",mix(value.secondary,"#FFFFFF",.82));
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
    var saved=normalise(value);saved.t=Date.now();
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
