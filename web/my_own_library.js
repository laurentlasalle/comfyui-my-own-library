// My Own Library - a personal library for your ComfyUI creations.
// The window is modeled on ComfyUI's Templates browser.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const BASE = "/my_own_library";
const RECENT_DAYS = 14;
const PAGE = 200;
// Suggestions for the Model field, written the way their creators write them.
const KNOWN_FAMILIES = ["FLUX.1", "FLUX.1 Kontext", "FLUX.2", "Qwen Image", "Qwen Image Edit", "Z-Image", "Z-Image-Turbo",
    "Wan 2.1", "Wan 2.2", "MiniMax H3", "Chatterbox", "HunyuanVideo", "HunyuanImage", "LTX-Video", "LTX-2", "HiDream", "Chroma", "SD 1.5", "SDXL",
    "SD3", "SD 3.5", "Illustrious", "Pony"];

// ---------------------------------------------------------------- helpers

const url = (path, params = {}) => {
    const q = new URLSearchParams(params).toString();
    return api.apiURL(BASE + path + (q ? "?" + q : ""));
};

async function call(path, body) {
    const res = await api.fetchApi(BASE + path, body === undefined ? {} : {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || res.statusText);
    return data;
}

function toast(summary, detail = "", severity = "success") {
    try {
        app.extensionManager.toast.add({ severity, summary, detail, life: 3500 });
    } catch {
        console.log(`[My Own Library] ${summary} ${detail}`);
    }
}

function h(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
        if (v === undefined || v === null || v === false) continue;
        if (k === "class") el.className = v;
        else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
        else if (k.startsWith("on")) el.addEventListener(k.slice(2).toLowerCase(), v);
        else if (k === "html") el.innerHTML = v;
        else el.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
        if (c === undefined || c === null || c === false) continue;
        el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
}

const icon = (name) => h("i", { class: `pi pi-${name}` });

// Small per-browser preferences (sort order). Storage can be unavailable: ignore errors.
function loadPref(key, fallback) {
    try { return localStorage.getItem("my_own_library." + key) || fallback; } catch { return fallback; }
}
function savePref(key, value) {
    try { localStorage.setItem("my_own_library." + key, value); } catch {}
}

const KINDS = {
    image: { icon: "image", label: "Image" },
    video: { icon: "video", label: "Video" },
    audio: { icon: "volume-up", label: "Audio" },
};
const kindBadge = (kind, cls = "mol-badge") =>
    h("span", { class: cls }, icon((KINDS[kind] || KINDS.image).icon), (KINDS[kind] || KINDS.image).label);

function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function fmtSize(bytes) {
    if (!bytes && bytes !== 0) return "";
    const units = ["B", "KB", "MB", "GB"];
    let i = 0;
    while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
    return `${bytes.toFixed(i ? 1 : 0)} ${units[i]}`;
}

async function copyText(text) {
    try {
        await navigator.clipboard.writeText(text);
        toast("Copied to clipboard");
    } catch {
        toast("Could not copy", "", "error");
    }
}

function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ------------------------------------------------------------------ styles

const CSS = `
.mol-dialog{position:fixed;inset:0;margin:auto;width:90vw;height:80vh;max-width:1400px;max-height:none;padding:0;box-sizing:border-box;box-shadow:0 18px 60px rgba(0,0,0,.5);
  border:1px solid var(--mol-border);border-radius:16px;background:var(--mol-bg);color:var(--mol-fg);overflow:hidden;
  font-family:inherit;font-size:14px;z-index:10000;
  --mol-bg:#171718;--mol-panel:#262729;--mol-card:#262729;--mol-hover:#2f3034;--mol-border:#2f3034;
  --mol-fg:#ececec;--mol-dim:#9a9a9a;--mol-accent:#f0cf98;--mol-danger:#e57373;--mol-input:#1a1a1a}
.mol-dialog::backdrop{background:rgba(0,0,0,.55)}
/* Same size as ComfyUI's Templates window (BaseModalLayout, size md) */
.mol-dialog.maximized{width:100vw;height:100vh;max-width:none;max-height:none;border:0;border-radius:0}
.mol-root{display:flex;height:100%;outline:none}
/* Left column: same measures as Templates (LeftSidePanel, NavItem, NavTitle) */
.mol-nav{width:224px;flex:none;background:var(--mol-panel);
  display:flex;flex-direction:column;gap:4px;padding:0 12px 12px;overflow:auto;box-sizing:border-box}
.mol-brand{display:flex;align-items:center;gap:8px;font-size:16px;font-weight:600;height:72px;flex:none;padding-left:12px;margin-bottom:-4px}
.mol-navitem{display:flex;align-items:center;gap:8px;padding:12px 16px;border-radius:6px;cursor:pointer;
  color:var(--mol-fg);user-select:none;font-size:14px;line-height:20px}
.mol-navitem>i{font-size:14px}
.mol-section ~ .mol-navitem{margin-top:4px}
.mol-navitem:hover{background:var(--mol-hover)}
.mol-navitem.active{background:#3c3d42}
.mol-navitem .mol-count{margin-left:auto;color:var(--mol-dim);font-size:12px}
.mol-navitem .mol-tools{display:none;margin-left:auto;gap:6px}
.mol-navitem:hover .mol-tools{display:flex}
.mol-navitem:hover .mol-tools + .mol-count{display:none}
.mol-tools i{opacity:.7;padding:2px}
.mol-tools i:hover{opacity:1}
.mol-section{display:flex;align-items:center;justify-content:space-between;color:var(--mol-dim);font-size:12px;
  font-weight:700;padding:20px 12px 0;text-transform:uppercase;min-height:16px}
.mol-section{padding-right:16px}
.mol-addcat{font-size:12px;padding:4px;margin:-4px -4px -4px 0;min-width:0;min-height:0;color:var(--mol-fg);line-height:1}
.mol-addcat i{font-size:12px}
.mol-navfoot{margin-top:auto;padding:16px 10px 2px;color:var(--mol-dim);font-size:11px;word-break:break-all;line-height:1.5}
.mol-inline-input{width:100%;background:var(--mol-input);color:var(--mol-fg);border:1px solid #555;border-radius:8px;padding:7px 9px;font:inherit}
.mol-main{flex:1;display:flex;flex-direction:column;min-width:0;position:relative}
/* Header: 72 px high, 24 px sides, search 36 px high up to 384 px, 40 px close button */
.mol-head{padding:0 24px 12px;display:flex;flex-direction:column;gap:12px}
.mol-head>.mol-row:first-child{height:72px;flex-wrap:nowrap;margin-bottom:-12px;gap:8px}
.mol-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.mol-title{font-size:16px;font-weight:500;margin-right:auto;white-space:nowrap}
.mol-search{display:flex;align-items:center;gap:8px;border:1px solid rgba(255,255,255,.14);border-radius:8px;padding:0 12px;
  height:36px;box-sizing:border-box;width:100%;max-width:384px;background:transparent;margin-left:auto}
.mol-head>.mol-row:first-child>.mol-iconbtn{width:40px;height:40px;padding:0;display:inline-flex;align-items:center;justify-content:center}
.mol-search input{flex:1;background:none;border:0;outline:0;color:var(--mol-fg);font:inherit}
.mol-iconbtn{background:none;border:0;color:var(--mol-fg);cursor:pointer;font-size:16px;padding:8px;border-radius:8px}
.mol-iconbtn:hover{background:var(--mol-hover)}
.mol-chip{display:inline-flex;align-items:center;gap:6px;height:32px;box-sizing:border-box;padding:0 12px;border-radius:8px;background:var(--mol-card);
  border:1px solid transparent;cursor:pointer;color:var(--mol-fg);font:inherit;font-size:12px;user-select:none}
.mol-chip i{font-size:12px}
.mol-chip:hover{background:var(--mol-hover)}
.mol-chip.active{background:#f2f2f2;color:#111}
.mol-select{background:var(--mol-card);color:var(--mol-fg);border:1px solid var(--mol-border);border-radius:10px;
  padding:8px 12px;font:inherit;cursor:pointer;max-width:220px}
/* Filter menus of the top bar, like Model Filter and the sort menu of Templates */
.mol-filtersel{display:inline-flex;align-items:center;gap:6px;height:32px;box-sizing:border-box;padding:0 4px 0 10px;
  border:1px solid rgba(255,255,255,.14);border-radius:8px;font-size:12px;color:var(--mol-fg)}
.mol-filtersel i{font-size:12px}
.mol-filtersel select{background:transparent;color:var(--mol-fg);border:0;outline:0;font:inherit;font-size:12px;cursor:pointer;max-width:200px;height:30px}
.mol-filtersel select option{background:#262729}
.mol-spacer{flex:1}
.mol-btn{display:inline-flex;align-items:center;gap:8px;padding:9px 16px;border-radius:10px;border:1px solid var(--mol-border);
  background:var(--mol-card);color:var(--mol-fg);font:inherit;cursor:pointer}
.mol-btn:hover{background:var(--mol-hover)}
.mol-btn.primary{background:#2a241c;border-color:#7d6848;color:var(--mol-accent);font-weight:600}
.mol-btn.primary:hover{background:#3a3124}
.mol-btn.danger{color:var(--mol-danger)}
.mol-btn:disabled{opacity:.45;cursor:default}
.mol-tagfilter{display:flex;gap:6px;flex-wrap:wrap}
.mol-tag{display:inline-flex;align-items:center;gap:6px;padding:5px 11px;border-radius:8px;background:var(--mol-card);
  font-size:13px;color:#d6d6d6;cursor:pointer;white-space:nowrap}
.mol-tag.active{background:var(--mol-accent);color:#1b1b1b}
.mol-tag i{font-size:10px}
.mol-grid-wrap{flex:1;overflow:auto;padding:12px 24px 30px}
.mol-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:26px 24px}
.mol-card{cursor:pointer;min-width:0}
.mol-thumb{position:relative;aspect-ratio:1/1;border-radius:14px;overflow:hidden;background:var(--mol-card)}
.mol-thumb img,.mol-thumb video{width:100%;height:100%;object-fit:cover;display:block;transition:transform .25s}
.mol-card:hover .mol-thumb img{transform:scale(1.03)}
.mol-badge,.mol-star,.mol-check,.mol-inlib,.mol-family,.mol-families{z-index:2}
.mol-badge{position:absolute;top:10px;left:10px;display:flex;align-items:center;gap:7px;padding:5px 10px;border-radius:8px;
  background:rgba(40,40,40,.82);color:#fff;font-size:13px;backdrop-filter:blur(4px)}
.mol-star{position:absolute;top:10px;right:10px;padding:6px 8px;border-radius:8px;background:rgba(40,40,40,.82);color:#ffd54f}
.mol-check{position:absolute;top:10px;right:10px;width:26px;height:26px;border-radius:8px;background:rgba(40,40,40,.82);
  border:2px solid #bbb;display:flex;align-items:center;justify-content:center;color:#111}
.mol-check.on{background:var(--mol-accent);border-color:var(--mol-accent)}
.mol-inlib{position:absolute;bottom:10px;right:10px;padding:4px 9px;border-radius:8px;background:rgba(240,207,152,.92);color:#1b1b1b;font-size:12px;font-weight:600}
.mol-families{position:absolute;bottom:10px;left:10px;display:flex;flex-direction:column;align-items:flex-start;gap:4px;max-width:62%}
.mol-families .mol-family{position:static;max-width:100%}
.mol-family{position:absolute;bottom:10px;left:10px;padding:4px 9px;border-radius:8px;background:rgba(20,20,20,.82);color:#fff;font-size:12px;font-weight:600;backdrop-filter:blur(4px);max-width:60%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mol-topright{position:absolute;top:10px;right:10px;display:flex;gap:6px;align-items:center;z-index:2}
.mol-topright .mol-star{position:static}
.mol-ver{padding:5px 9px;border-radius:8px;background:rgba(240,207,152,.94);color:#1b1b1b;font-size:12px;font-weight:700}
.mol-thumb.stack{box-shadow:6px -6px 0 -1px #3b3b3b,12px -12px 0 -2px #2a2a2a}
.mol-libcheck{left:10px;right:auto;opacity:0;transition:opacity .15s}
.mol-card:hover .mol-libcheck,.mol-libcheck.on,.mol-selecting .mol-libcheck{opacity:1}
.mol-card:hover .mol-badge.lib,.mol-selecting .mol-badge.lib{opacity:0}
.mol-suggestion{display:flex;flex-wrap:wrap;align-items:center;gap:14px;padding:12px 16px;margin:4px 0 22px;border:1px solid #7d6848;border-radius:12px;background:#221e18}
.mol-sugthumbs{display:flex;padding-left:10px}
.mol-sugthumbs img{width:44px;height:44px;object-fit:cover;border-radius:8px;border:2px solid #221e18;margin-left:-10px;background:#2a2a2a}
.mol-strip{position:absolute;left:0;right:0;bottom:0;display:flex;gap:8px;justify-content:center;padding:12px;background:linear-gradient(transparent,rgba(0,0,0,.8));overflow-x:auto}
.mol-stripitem{position:relative;width:64px;height:64px;padding:0;border:2px solid transparent;border-radius:9px;overflow:hidden;background:#222;cursor:pointer;flex:none}
.mol-stripitem.active{border-color:var(--mol-accent)}
.mol-stripitem.drop{border-color:#fff;transform:scale(1.08)}
.mol-stripitem img{width:100%;height:100%;object-fit:cover;display:block}
.mol-stripitem span{position:absolute;left:4px;bottom:3px;font-size:11px;font-weight:700;color:#fff;text-shadow:0 1px 3px #000}
.mol-preview.has-strip{padding-bottom:92px}
.mol-changes{border:1px solid var(--mol-border);border-radius:10px;padding:12px 14px;display:grid;gap:8px;font-size:13px;background:var(--mol-input)}
.mol-changes .row{display:flex;gap:10px}
.mol-changes .key{color:var(--mol-dim);width:84px;flex:none}
.mol-changes .val{display:flex;flex-wrap:wrap;gap:4px 8px}
.mol-add{color:#81c784}
.mol-del{color:#e57373;text-decoration:line-through}
.mol-checkline{display:inline-flex;align-items:center;gap:8px;color:var(--mol-dim);cursor:pointer;user-select:none}
.mol-checkline input{accent-color:#c9a86b;width:16px;height:16px;margin:0}
.mol-audio{width:min(720px,90%);display:flex;flex-direction:column;gap:18px;align-items:center}
.mol-audio .mol-wave{width:100%;max-height:60%;object-fit:contain;border-radius:12px}
.mol-audio audio{width:100%}
.mol-sugtext{flex:1 1 240px;min-width:200px}
.mol-dupgroup{margin:0 0 26px}
.mol-dupgroup>.mol-row{margin-bottom:10px}
.mol-dupcopy .mol-thumb{opacity:.6}
.mol-jobbar{gap:12px}
.mol-jobtext{white-space:nowrap;flex:none;font-variant-numeric:tabular-nums}
.mol-jobname{flex:1;min-width:0;display:flex;color:var(--mol-dim);white-space:nowrap}
.mol-jobhead{overflow:hidden;text-overflow:ellipsis;min-width:0}
.mol-jobtail{flex:none}
.mol-jobtrack{flex:none;width:300px;max-width:30%;height:6px;border-radius:3px;background:var(--mol-card);overflow:hidden}
.mol-jobfill{display:block;height:100%;width:0;background:var(--mol-accent);transition:width .3s}
.mol-chipcount{margin-left:6px;padding:0 7px;border-radius:9px;background:var(--mol-accent);color:#1b1b1b;font-size:12px;font-weight:700;line-height:18px}
.mol-dd{display:inline-flex;align-items:center;gap:6px;height:32px;box-sizing:border-box;padding:0 10px;min-width:0;
  border:1px solid rgba(255,255,255,.14);border-radius:8px;background:transparent;color:var(--mol-fg);font:inherit;font-size:12px;cursor:pointer;white-space:nowrap}
.mol-dd:hover,.mol-dd.open{background:var(--mol-hover)}
.mol-dd>i{font-size:12px;color:var(--mol-dim)}
.mol-dd .mol-ddlabel{overflow:hidden;text-overflow:ellipsis;max-width:180px}
.mol-dd .mol-ddchev{font-size:10px;margin-left:6px}
.mol-ddcount{display:inline-flex;align-items:center;justify-content:center;min-width:14px;height:14px;border-radius:7px;background:var(--mol-fg);color:#171718;font-size:9px;font-weight:600;padding:0 3px}
.mol-ddpanel{position:absolute;z-index:40;background:#171718;border:1px solid rgba(255,255,255,.14);border-radius:8px;padding:8px;
  box-shadow:0 8px 24px rgba(0,0,0,.45);display:flex;flex-direction:column;outline:none;font-size:14px;animation:mol-ddin .12s ease-out}
@keyframes mol-ddin{from{opacity:0;transform:translateY(-4px) scale(.98)}to{opacity:1;transform:none}}
.mol-ddlist{overflow:auto;display:flex;flex-direction:column;gap:2px}
.mol-dditem{display:flex;align-items:center;gap:12px;padding:12px 8px;border-radius:4px;cursor:pointer;white-space:nowrap}
.mol-ddpanel.multi .mol-dditem{height:40px;box-sizing:border-box;padding:0 8px;gap:8px;border-radius:8px}
.mol-dditem.hl{background:var(--mol-hover)}
.mol-dditem.on{background:#3c3d42}
.mol-ddpanel.multi .mol-dditem.on{background:transparent}
.mol-ddpanel.multi .mol-dditem.on.hl{background:var(--mol-hover)}
.mol-ddtext{flex:1}
.mol-ddhint{color:var(--mol-dim);font-size:12px}
.mol-ddcheck i{font-size:12px}
.mol-ddbox{width:16px;height:16px;border-radius:4px;background:#3c3d42;display:inline-flex;align-items:center;justify-content:center;flex:none}
.mol-ddbox.on{background:#0b8ce9}
.mol-ddbox i{font-size:10px;font-weight:700;color:#fff}
.mol-ddhead{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:2px 4px 8px;color:var(--mol-dim);font-size:13px}
.mol-ddclear{background:none;border:0;color:var(--mol-fg);font:inherit;font-size:13px;cursor:pointer;text-decoration:underline;opacity:.7;padding:0}
.mol-ddclear:hover{opacity:1}
.mol-ddclear:disabled{opacity:.3;cursor:default}
.mol-simlabel{display:flex;align-items:center;gap:8px;color:var(--mol-dim);font-size:13px;white-space:nowrap}
.mol-suggestion-empty{padding:8px 16px;background:transparent;border-color:#3a3a3a}
.mol-simscore{color:#f0cf98}
.mol-review{position:absolute;inset:0;background:var(--mol-bg);display:flex;flex-direction:column;z-index:5}
.mol-reviewgrid{grid-template-columns:repeat(auto-fill,minmax(340px,1fr))}
.mol-reviewcard.off .mol-thumb{opacity:.35;filter:grayscale(.7)}
.mol-reviewcard.off .mol-cardtitle{opacity:.5}
.mol-reviewtext{color:var(--mol-dim);font-size:12.5px;line-height:1.5;margin-top:6px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.mol-zoom{position:absolute;inset:0;background:rgba(10,10,10,.94);display:flex;align-items:center;justify-content:center;padding:30px;z-index:6;cursor:zoom-out}
.mol-zoom img,.mol-zoom video{max-width:100%;max-height:100%;object-fit:contain;cursor:default}
.mol-zoomclose{position:absolute;top:14px;right:14px;font-size:18px}
.mol-new{background:rgba(129,199,132,.95)}
.mol-noimg{width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:var(--mol-dim);font-size:34px}
.mol-cardtitle{font-weight:600;font-size:15.5px;margin:12px 2px 8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mol-cardtags{display:flex;gap:6px;flex-wrap:nowrap;overflow:hidden}
.mol-empty{color:var(--mol-dim);text-align:center;padding:80px 20px;line-height:1.7}
.mol-more{display:flex;justify-content:center;padding:26px}
.mol-actionbar{display:flex;align-items:center;flex-wrap:wrap;gap:10px;padding:12px 30px;border-top:1px solid var(--mol-border);background:var(--mol-panel)}
.mol-detail{position:absolute;inset:0;background:var(--mol-bg);display:flex;z-index:5}
.mol-thumbbtns{position:absolute;top:16px;right:16px;z-index:3;display:flex;gap:8px}
.mol-overbtn{background:rgba(20,20,20,.75);backdrop-filter:blur(4px)}
.mol-preview{flex:1;display:flex;align-items:center;justify-content:center;background:#0f0f0f;position:relative;min-width:0}
.mol-preview img,.mol-preview video{max-width:100%;max-height:100%;object-fit:contain}
.mol-navarrow{position:absolute;top:50%;transform:translateY(-50%);background:rgba(40,40,40,.8);border:0;color:#fff;
  width:42px;height:42px;border-radius:50%;cursor:pointer;font-size:16px}
.mol-navarrow:hover{background:rgba(70,70,70,.9)}
.mol-info{width:430px;flex:none;border-left:1px solid var(--mol-border);display:flex;flex-direction:column;background:var(--mol-panel)}
.mol-infohead{display:flex;align-items:center;gap:8px;padding:14px 16px;border-bottom:1px solid var(--mol-border)}
.mol-infobody{flex:1;overflow:auto;padding:18px 20px;display:flex;flex-direction:column;gap:16px}
.mol-field label{display:block;color:var(--mol-dim);font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;margin-bottom:7px}
.mol-field input[type=text],.mol-field textarea,.mol-field select{width:100%;box-sizing:border-box;background:var(--mol-input);color:var(--mol-fg);
  border:1px solid var(--mol-border);border-radius:9px;padding:9px 11px;font:inherit}
.mol-field textarea{min-height:110px;resize:vertical;line-height:1.5}
.mol-field input:focus,.mol-field textarea:focus,.mol-field select:focus{outline:0;border-color:#7d6848}
.mol-tagsbox{display:flex;flex-wrap:wrap;gap:6px;align-items:center;background:var(--mol-input);border:1px solid var(--mol-border);
  border-radius:9px;padding:7px}
.mol-tagsbox{position:relative}
.mol-suggest{position:absolute;left:0;right:0;top:calc(100% + 4px);background:#262626;border:1px solid #3a3a3a;border-radius:10px;padding:4px;z-index:20;box-shadow:0 8px 24px rgba(0,0,0,.45);max-height:260px;overflow:auto}
.mol-tagsbox.up .mol-suggest{top:auto;bottom:calc(100% + 4px)}
.mol-suggest-item{display:flex;justify-content:space-between;gap:12px;padding:7px 10px;border-radius:7px;cursor:pointer}
.mol-suggest-item.active,.mol-suggest-item:hover{background:#363636}
.mol-suggest-item .mol-count{color:var(--mol-dim);font-size:12px}
.mol-hint{color:var(--mol-dim);font-size:12px;margin-top:6px}
.mol-tagsbox input{flex:1;min-width:120px;background:none;border:0;outline:0;color:var(--mol-fg);font:inherit;padding:3px}
.mol-prompt{background:var(--mol-input);border:1px solid var(--mol-border);border-radius:9px;padding:10px 12px;white-space:pre-wrap;
  max-height:220px;overflow:auto;line-height:1.5;font-size:13px}
.mol-promptbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:7px}
.mol-promptbar label{margin:0}
.mol-kv{display:grid;grid-template-columns:110px 1fr;gap:6px 12px;font-size:13px}
.mol-kv div:nth-child(odd){color:var(--mol-dim)}
.mol-kv div{word-break:break-word}
.mol-infofoot{display:flex;gap:8px;flex-wrap:wrap;padding:14px 16px;border-top:1px solid var(--mol-border)}
.mol-saved{color:var(--mol-dim);font-size:12px;margin-left:auto}
.mol-sidebar{padding:16px;display:grid;gap:14px}
.mol-sidecard{display:grid;gap:12px;padding:16px;border:1px solid color-mix(in srgb,currentColor 18%,transparent);border-radius:12px;
  background:color-mix(in srgb,currentColor 5%,transparent)}
.mol-sidecard h2{margin:0;font-size:16px}
.mol-sidecard p{margin:0;opacity:.7;font-size:12px;line-height:1.6}
.mol-sidecard button{width:100%;padding:10px 12px;border:1px solid #7d6848;border-radius:9px;background:#2a241c;color:#f0cf98;
  font:600 13px/1.2 inherit;cursor:pointer}
`;

function injectCSS() {
    if (document.getElementById("mol-style")) return;
    document.head.append(h("style", { id: "mol-style" }, CSS));
}

// ------------------------------------------------------------------- state

const S = {
    dialog: null,
    view: "all",          // all | recent | favorites | uncategorized | output | cat:<name>
    kind: "all",          // all | image | video
    search: "",
    tags: new Set(),
    families: new Set(),    // Model Filter: several models can be ticked
    sort: loadPref("sort", "created-desc"),
    items: [],
    categories: [],
    libraryDir: "",
    output: { files: [], total: 0, notAdded: 0, loading: false },
    selected: new Set(),    // output files selected, as "root|rel" keys
    selInfo: new Map(),     // key -> {root, rel, name, size, in_library}, including files not displayed
    addCategory: "",
    addTags: [],
    removeAfter: false,     // delete from output once copied to the library
    libSelected: new Set(), // works selected in the library grid
    bulkTags: [],
    suggestions: [],        // creations from one workflow, not grouped yet
    similarity: loadPref("similarity", "normal"),  // strict | normal | loose
    versionsOpen: loadPref("versionsOpen", "1") === "1",  // Detect versions banner shown
    suggestionIndex: 0,
    review: null,           // {sug, checked: Set, zoom: id|null}: suggestion being reviewed
    hideAdded: false,
    newOnly: false,         // Output view: only files created since the previous visit
    lastVisit: 0,           // previous visit of the Output view (Unix time)
    badge: 0,
    editingCategory: null,  // name being renamed, or "" for a new one
    detail: null,           // {type: "item"|"file", list, index}
};

function applySnapshot(data) {
    S.items = data.items || [];
    S.categories = data.categories || [];
    S.libraryDir = data.library_dir || "";
    S.duplicates = data.duplicates || [];
}

async function loadSuggestions() {
    try {
        const r = await call("/versions/suggestions?level=" + encodeURIComponent(S.similarity));
        S.suggestions = r.suggestions || [];
        S.sigPending = r.pending || 0;
    } catch {
        S.suggestions = [];
        S.sigPending = 0;
    }
    if (S.suggestionIndex >= S.suggestions.length) S.suggestionIndex = 0;
    watchPending();
}

// While creations are still being analyzed in the background, refresh the
// suggestions now and then, without disturbing an open detail or Review panel.
function watchPending() {
    clearTimeout(S.pendingTimer);
    if (!S.sigPending || !S.dialog?.open) return;
    S.pendingTimer = setTimeout(async () => {
        if (!S.dialog?.open) return;
        await loadSuggestions();
        if (!S.detail && !S.review) render();
    }, 5000);
}

async function loadLibrary() {
    applySnapshot(await call("/library"));
    await loadSuggestions();
}

async function loadOutput(reset = true) {
    S.output.loading = true;
    const offset = reset ? 0 : S.output.files.length;
    const data = await call(`/output?${new URLSearchParams({
        offset, limit: PAGE, kind: S.kind, q: S.search, hide_added: S.hideAdded ? 1 : 0,
        ...(S.newOnly ? { since: S.lastVisit } : {}),
    })}`);
    S.output.files = reset ? data.files : S.output.files.concat(data.files);
    S.output.total = data.total;
    S.output.notAdded = data.not_added;
    S.output.loading = false;
}

// ------------------------------------------------------- new-files badge

const TAB_ID = "my-own-library";

// Uses the official iconBadge property of sidebar tabs. The tab object kept by
// ComfyUI's sidebar store is reactive, so changing it updates the icon.
function setBadge(n) {
    S.badge = n;
    const text = n > 0 ? (n > 99 ? "99+" : String(n)) : "";
    const manager = app.extensionManager;
    const tabs = manager?.sidebarTab?.sidebarTabs ?? manager?.getSidebarTabs?.();
    const tab = Array.isArray(tabs) ? tabs.find((t) => t.id === TAB_ID) : null;
    if (tab && tab.iconBadge !== text) tab.iconBadge = text;
}

async function refreshBadge() {
    try {
        const d = await call("/badge");
        setBadge(d.count);
    } catch {}
}

// Entering the Output view counts as a visit: the badge resets, and the view
// opens on the new files when there were some.
async function markOutputSeen() {
    const hadNew = S.badge > 0;
    try {
        const d = await call("/seen", {});
        S.lastVisit = d.previous;
    } catch {}
    S.newOnly = hadNew;
    setBadge(0);
}

const onNewOutput = debounce(async () => {
    if (S.dialog?.open && S.view === "output") {
        try { await call("/seen", {}); } catch {}
        setBadge(0);
        if (!S.detail) { await loadOutput(true); render(); }
    } else {
        refreshBadge();
    }
}, 1200);

const allTags = () => {
    const map = new Map();
    for (const it of S.items) for (const t of it.tags || []) {
        const k = t.toLowerCase();
        map.set(k, { name: map.get(k)?.name || t, count: (map.get(k)?.count || 0) + 1 });
    }
    return [...map.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
};

// Model families of a creation, in order of execution. A hand-typed override
// ("Qwen Image 2.1, SeedVR2") replaces the detected list.
function familiesOf(it) {
    if (it.family_override) return it.family_override.split(",").map((x) => x.trim()).filter(Boolean);
    if (it.summary?.families?.length) return it.summary.families;
    return it.summary?.family ? [it.summary.family] : [];
}

function familyStack(list) {
    if (!list?.length) return null;
    return h("span", { class: "mol-families" }, ...list.map((f) => h("span", { class: "mol-family", title: f }, f)));
}

const allFamilies = () => {
    const set = new Set();
    for (const it of S.items) for (const f of familiesOf(it)) set.add(f);
    return [...set].sort((a, b) => a.localeCompare(b));
};

function filteredItems() {
    const q = S.search.toLowerCase();
    const recentLimit = Date.now() - RECENT_DAYS * 86400000;
    let list = S.items.filter((it) => {
        if (S.view === "favorites" && !it.favorite) return false;
        if (S.view === "uncategorized" && it.category) return false;
        if (S.view === "recent" && new Date(it.added).getTime() < recentLimit) return false;
        if (S.view.startsWith("cat:") && it.category !== S.view.slice(4)) return false;
        if (S.kind !== "all" && it.kind !== S.kind) return false;
        if (S.families.size && !familiesOf(it).some((f) => S.families.has(f))) return false;
        if (S.tags.size) {
            const own = new Set((it.tags || []).map((t) => t.toLowerCase()));
            for (const t of S.tags) if (!own.has(t)) return false;
        }
        if (q) {
            const hay = [it.title, it.notes, it.category, ...(it.tags || []),
                ...(it.summary?.positive || []), ...(it.summary?.negative || []), ...(it.summary?.text || []),
                ...(it.summary?.models || []), ...(it.summary?.loras || []), it.source?.name, ...familiesOf(it)]
                .join("\n").toLowerCase();
            if (!hay.includes(q)) return false;
        }
        return true;
    });
    const by = {
        "added-desc": (a, b) => (b.added || "").localeCompare(a.added || ""),
        "added-asc": (a, b) => (a.added || "").localeCompare(b.added || ""),
        "created-desc": (a, b) => (b.created || "").localeCompare(a.created || ""),
        "created-asc": (a, b) => (a.created || "").localeCompare(b.created || ""),
        "title": (a, b) => a.title.localeCompare(b.title),
    }[S.sort];
    return list.sort(by);
}

// ------------------------------------------------------------------- works
// A work is one creation, or several creations grouped as versions of it.

const byCreated = (a, b) => (a.created || "").localeCompare(b.created || "") || (a.added || "").localeCompare(b.added || "");

// Versions in their order: the one set by hand if any, else by creation.
const byVersion = (a, b) => (a.work_pos ?? Infinity) - (b.work_pos ?? Infinity) || byCreated(a, b);

function membersOf(it) {
    return it.work_id ? S.items.filter((x) => x.work_id === it.work_id).sort(byVersion) : [it];
}

const coverOf = (members) => members.find((m) => m.work_cover) || members[members.length - 1];

function groupWorks(items) {
    const seen = new Set();
    const works = [];
    for (const it of items) {
        const key = it.work_id || it.id;
        if (seen.has(key)) continue;
        seen.add(key);
        const members = membersOf(it);
        works.push({ key, members, cover: coverOf(members) });
    }
    return works;
}

// Total size of a work: all its versions (and their companion files' share is ignored).
const workSize = (w) => w.members.reduce((a, m) => a + (m.size || 0), 0);

// Works with at least one version matching the filters, in the chosen order.
function filteredWorks() {
    const works = groupWorks(filteredItems());
    const latest = (w, field) => w.members.reduce((a, m) => ((m[field] || "") > a ? m[field] : a), "");
    const by = {
        "added-desc": (a, b) => latest(b, "added").localeCompare(latest(a, "added")),
        "added-asc": (a, b) => latest(a, "added").localeCompare(latest(b, "added")),
        "created-desc": (a, b) => latest(b, "created").localeCompare(latest(a, "created")),
        "created-asc": (a, b) => latest(a, "created").localeCompare(latest(b, "created")),
        "title": (a, b) => a.cover.title.localeCompare(b.cover.title),
        "size-desc": (a, b) => workSize(b) - workSize(a),
        "size-asc": (a, b) => workSize(a) - workSize(b),
    }[S.sort];
    return works.sort(by);
}

function openItemById(id, extraWorks) {
    const works = extraWorks || groupWorks([...S.items].sort((a, b) => (b.added || "").localeCompare(a.added || "")));
    const index = works.findIndex((w) => w.members.some((m) => m.id === id));
    if (index < 0) return;
    openDetail("item", works, index, works[index].members.findIndex((m) => m.id === id));
}

async function groupIds(ids) {
    try {
        const data = await call("/versions/group", { ids });
        applySnapshot(data);
        await loadSuggestions();
        S.libSelected.clear();
        const n = S.items.filter((x) => x.work_id === data.work_id).length;
        toast("Grouped as versions", `${n} versions`);
    } catch (e) {
        toast("Could not group", e.message, "error");
    }
    render();
}

async function versionAction(action, body) {
    try {
        applySnapshot(await call("/versions/" + action, body));
        await loadSuggestions();
    } catch (e) {
        toast("Versions", e.message, "error");
    }
}

// ------------------------------------------------------------------- media

const itemThumb = (it) => url("/thumb", { id: it.id, v: it.modified || "" });
const itemFile = (it, extra = {}) => url("/file", { id: it.id, ...extra });
const fileThumb = (f) => url("/thumb", { root: f.root, rel: f.rel, v: f.mtime });
const fileSource = (f) => url("/source", { root: f.root, rel: f.rel });

function thumbEl(src, kind, videoSrc) {
    const wrap = h("div", { style: { width: "100%", height: "100%" } });
    const img = h("img", { src, loading: "lazy", draggable: "false" });
    img.onerror = () => {
        if (kind === "video" && videoSrc) {
            const v = h("video", { src: videoSrc + "#t=0.5", muted: true, preload: "metadata", playsinline: true });
            v.muted = true;
            img.replaceWith(v);
        } else {
            img.replaceWith(h("div", { class: "mol-noimg" }, icon((KINDS[kind] || KINDS.image).icon)));
        }
    };
    wrap.append(img);
    return wrap;
}

// Muted video preview on hover (no sound previews: audio plays in the detail view only).
const hoverVideos = new Set();

function stopHoverVideos() {
    for (const v of hoverVideos) {
        v.pause();
        v.removeAttribute("src");
        v.load(); // releases the decoder and the network request
        v.remove();
    }
    hoverVideos.clear();
}

function attachHoverPlay(thumb, kind, videoSrc) {
    if (kind !== "video") return;
    let v = null;
    thumb.addEventListener("mouseenter", () => {
        v = h("video", { src: videoSrc, muted: true, autoplay: true, loop: true, playsinline: true,
            style: { position: "absolute", inset: "0", pointerEvents: "none", zIndex: "1" } });
        v.muted = true;
        hoverVideos.add(v);
        thumb.append(v);
    });
    thumb.addEventListener("mouseleave", () => {
        if (!v) return;
        hoverVideos.delete(v);
        v.pause();
        v.removeAttribute("src");
        v.load();
        v.remove();
        v = null;
    });
}

// ------------------------------------------------------------------ render

async function setView(id) {
    S.view = id;
    S.detail = null;
    S.review = null;
    S.editingCategory = null;
    if (id === "output") {
        S.selected.clear();
        await markOutputSeen();
        try { await loadOutput(true); } catch (e) { toast("Could not read the output folder", e.message, "error"); }
    }
    render();
}

// Drop filters that point to things no longer in the library (for example a
// model whose last creations were just removed), so a filter never stays
// active while the menu shows "All models".
function pruneFilters() {
    if (S.families.size) {
        const all = new Set(allFamilies());
        for (const f of [...S.families]) if (!all.has(f)) S.families.delete(f);
    }
    if (S.tags.size) {
        const existing = new Set(allTags().map((t) => t.name.toLowerCase()));
        for (const t of [...S.tags]) if (!existing.has(t)) S.tags.delete(t);
    }
}

function render() {
    if (!S.dialog) return;
    closeMenu();
    stopHoverVideos();
    pruneFilters();
    const root = S.dialog.querySelector(".mol-root");
    const scroll = root.querySelector(".mol-grid-wrap")?.scrollTop || 0;
    const reviewScroll = root.querySelector(".mol-review .mol-grid-wrap")?.scrollTop || 0;
    // A re-render must not restart the video of the detail panel.
    const oldVideo = root.querySelector(".mol-preview video");
    const playback = oldVideo ? { src: oldVideo.getAttribute("src"), time: oldVideo.currentTime, paused: oldVideo.paused } : null;
    root.replaceChildren(renderNav(), renderMain());
    const wrap = root.querySelector(".mol-grid-wrap");
    if (wrap) wrap.scrollTop = scroll;
    if (S.detail) {
        root.querySelector(".mol-main").append(renderDetail());
        const video = root.querySelector(".mol-preview video");
        if (video && playback && video.getAttribute("src") === playback.src) {
            if (playback.paused) video.removeAttribute("autoplay");
            const restore = () => {
                video.currentTime = playback.time;
                if (playback.paused) video.pause(); else video.play().catch(() => {});
            };
            if (video.readyState >= 1) restore(); else video.addEventListener("loadedmetadata", restore, { once: true });
        }
    }
    else if (S.review) {
        root.querySelector(".mol-main").append(renderReview());
        // Ticking or unticking a card keeps the Review list where it was.
        const rwrap = root.querySelector(".mol-review .mol-grid-wrap");
        if (rwrap) rwrap.scrollTop = S.review.fresh ? 0 : reviewScroll;
        S.review.fresh = false;
    }
    // Re-rendering removes the focused element; keep keyboard focus inside the
    // window so Esc and the arrows keep working and ComfyUI shortcuts don't fire.
    if (S.dialog.open && !S.dialog.contains(document.activeElement)) root.focus({ preventScroll: true });
}

function navItem(id, label, iconName, count, tools) {
    const el = h("div", {
        class: "mol-navitem" + (S.view === id ? " active" : ""),
        onclick: () => setView(id),
    }, icon(iconName), h("span", { style: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, label),
        tools || null, count !== undefined ? h("span", { class: "mol-count" }, count) : null);
    return el;
}

function categoryInput(initial, onDone) {
    const input = h("input", { class: "mol-inline-input", type: "text", value: initial, placeholder: "Category name" });
    let done = false;
    const finish = async (save) => {
        if (done) return;
        done = true;
        S.editingCategory = null;
        if (save && input.value.trim() && input.value.trim() !== initial) await onDone(input.value.trim());
        else render();
    };
    input.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Enter") finish(true);
        if (e.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
    setTimeout(() => { input.focus(); input.select(); }, 0);
    return h("div", { style: { padding: "4px 6px" } }, input);
}

async function categoryAction(action, name, new_name) {
    try {
        const data = await call("/category", { action, name, new_name });
        S.categories = data.categories;
        if (action === "rename") {
            for (const it of S.items) if (it.category === name) it.category = new_name;
            if (S.view === "cat:" + name) S.view = "cat:" + new_name;
        }
        if (action === "delete") {
            for (const it of S.items) if (it.category === name) it.category = "";
            if (S.view === "cat:" + name) S.view = "all";
        }
    } catch (e) {
        toast("Category", e.message, "error");
    }
    render();
}

function renderNav() {
    // Counts are in works: a creation with its versions counts once.
    const works = groupWorks(S.items);
    const counts = {};
    for (const w of works) counts[w.cover.category || ""] = (counts[w.cover.category || ""] || 0) + 1;
    const recentLimit = Date.now() - RECENT_DAYS * 86400000;
    const recent = works.filter((w) => w.members.some((m) => new Date(m.added).getTime() >= recentLimit)).length;

    const cats = S.categories.map((name) => {
        if (S.editingCategory === name) {
            return categoryInput(name, (v) => categoryAction("rename", name, v));
        }
        const tools = h("span", { class: "mol-tools" },
            h("i", { class: "pi pi-pencil", title: "Rename", onclick: (e) => { e.stopPropagation(); S.editingCategory = name; render(); } }),
            h("i", {
                class: "pi pi-trash", title: "Delete category (creations become uncategorized)",
                onclick: (e) => {
                    e.stopPropagation();
                    if (confirm(`Delete the category "${name}"?\nIts ${counts[name] || 0} creation(s) will become uncategorized. Nothing is deleted from the library.`))
                        categoryAction("delete", name);
                },
            }));
        return navItem("cat:" + name, name, "folder", counts[name] || 0, tools);
    });
    if (S.editingCategory === "") cats.push(categoryInput("", (v) => categoryAction("create", v)));

    return h("nav", { class: "mol-nav" },
        h("div", { class: "mol-brand" }, icon("bookmark"), "My Own Library"),
        navItem("all", "All Creations", "th-large", works.length),
        navItem("recent", "Recent", "clock", recent),
        navItem("favorites", "Favorites", "star", works.filter((w) => w.cover.favorite).length),
        navItem("uncategorized", "Uncategorized", "inbox", counts[""] || 0),
        S.duplicates?.length || S.view === "duplicates" ? navItem("duplicates", "Duplicates", "copy", S.duplicates?.length || 0) : null,
        h("div", { class: "mol-section" }, "Output folder"),
        navItem("output", "Output", "download", S.output.notAdded ? `${S.output.notAdded} new` : undefined),
        h("div", { class: "mol-section" }, "Categories",
            h("button", { class: "mol-iconbtn mol-addcat", title: "New category",
                onclick: () => { S.editingCategory = ""; render(); } }, icon("plus"))),
        ...cats,
        h("div", { class: "mol-navfoot", title: "Change it in ComfyUI/user/my_own_library.config.json" },
            "Library folder: ", S.libraryDir));
}

function viewTitle() {
    if (S.view === "all") return "All Creations";
    if (S.view === "recent") return `Added in the last ${RECENT_DAYS} days`;
    if (S.view === "favorites") return "Favorites";
    if (S.view === "uncategorized") return "Uncategorized";
    if (S.view === "output") return "Output folder";
    if (S.view === "duplicates") return "Duplicates";
    return S.view.slice(4);
}

// ---------------------------------------------------------------- dropdowns
// Menus styled like ComfyUI's own (Templates' Model Filter and sort menus):
// a bordered 32 px trigger with a chevron, and a floating list with a check
// mark (single choice) or check boxes (several choices). The browser's native
// menus can't be styled, hence this.
let openMenu = null;

// A multi-choice menu stays open while ticking: re-open it after the re-render.
function reopenMenu(title) {
    const t = [...S.dialog.querySelectorAll(".mol-dd")].find((x) => x.title.startsWith("Show only creations") && title === "Model Filter");
    t?.click();
}

function closeMenu() {
    if (!openMenu) return;
    openMenu.panel.remove();
    document.removeEventListener("mousedown", openMenu.outside, true);
    openMenu.trigger.classList.remove("open");
    openMenu = null;
}

function dropdown({ label, iconName, options, value, values, onChange, title, multi = false, clearLabel = "Clear all" }) {
    const text = () => {
        if (!multi) return options.find((o) => o.value === value)?.label ?? label;
        if (!values.size) return label;
        if (values.size === 1) return options.find((o) => values.has(o.value))?.label ?? label;
        return label;
    };
    const trigger = h("button", { class: "mol-dd", title: title || label, type: "button" },
        iconName ? icon(iconName) : null,
        h("span", { class: "mol-ddlabel" }, text()),
        multi && values.size > 1 ? h("span", { class: "mol-ddcount" }, String(values.size)) : null,
        h("i", { class: "pi pi-chevron-down mol-ddchev" }));
    trigger.addEventListener("click", (e) => {
        e.stopPropagation();
        if (openMenu?.trigger === trigger) { closeMenu(); return; }
        closeMenu();
        const panel = h("div", { class: "mol-ddpanel" + (multi ? " multi" : "") });
        let active = Math.max(0, options.findIndex((o) => (multi ? values.has(o.value) : o.value === value)));
        const rows = options.map((o, i) => {
            const on = multi ? values.has(o.value) : o.value === value;
            const row = h("div", { class: "mol-dditem" + (on ? " on" : ""), role: "option" },
                multi ? h("span", { class: "mol-ddbox" + (on ? " on" : "") }, on ? icon("check") : null) : null,
                h("span", { class: "mol-ddtext" }, o.label),
                o.hint ? h("span", { class: "mol-ddhint" }, o.hint) : null,
                !multi && on ? h("span", { class: "mol-ddcheck" }, icon("check")) : null);
            row.addEventListener("mousedown", (ev) => ev.preventDefault());
            row.addEventListener("click", () => choose(i));
            row.addEventListener("mouseenter", () => highlight(i));
            return row;
        });
        const highlight = (i) => { active = i; rows.forEach((r, k) => r.classList.toggle("hl", k === i)); rows[i]?.scrollIntoView({ block: "nearest" }); };
        const choose = (i) => {
            const o = options[i];
            if (!o) return;
            if (multi) {
                values.has(o.value) ? values.delete(o.value) : values.add(o.value);
                onChange(values);
            } else {
                closeMenu();
                onChange(o.value);
            }
        };
        if (multi) {
            panel.append(h("div", { class: "mol-ddhead" },
                h("span", {}, values.size ? `${values.size} selected` : "None selected"),
                h("button", { class: "mol-ddclear", type: "button", disabled: !values.size,
                    onclick: () => { values.clear(); onChange(values); } }, clearLabel)));
        }
        panel.append(h("div", { class: "mol-ddlist" }, ...rows));
        panel.tabIndex = -1;
        panel.addEventListener("keydown", (ev) => {
            if (ev.key === "ArrowDown") { ev.preventDefault(); highlight(Math.min(options.length - 1, active + 1)); }
            else if (ev.key === "ArrowUp") { ev.preventDefault(); highlight(Math.max(0, active - 1)); }
            else if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); choose(active); }
            else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); closeMenu(); trigger.focus(); }
            ev.stopPropagation();
        });
        S.dialog.append(panel);
        const r = trigger.getBoundingClientRect();
        const d = S.dialog.getBoundingClientRect();
        panel.style.minWidth = Math.max(r.width, 180) + "px";
        const top = r.bottom - d.top + 6;
        panel.style.top = top + "px";
        panel.style.maxHeight = Math.max(160, d.height - top - 16) + "px";
        const left = Math.min(r.left - d.left, d.width - panel.offsetWidth - 12);
        panel.style.left = Math.max(12, left) + "px";
        const outside = (ev) => { if (!panel.contains(ev.target) && !trigger.contains(ev.target)) closeMenu(); };
        document.addEventListener("mousedown", outside, true);
        openMenu = { panel, trigger, outside };
        trigger.classList.add("open");
        highlight(active);
        panel.focus({ preventScroll: true });
    });
    return trigger;
}

// The banner opens by itself when a suggestion appears that wasn't there before;
// closing it is remembered otherwise.
function syncVersionBanner() {
    if (S.view === "output" || S.view === "duplicates") return;
    let seen;
    try { seen = new Set(JSON.parse(localStorage.getItem("my_own_library.seenSuggestions") || "[]")); } catch { seen = new Set(); }
    const keys = visibleSuggestions().map((sug) => sug.workflow_id + ":" + [...sug.ids].sort().join(","));
    const fresh = keys.filter((k) => !seen.has(k));
    if (!fresh.length) return;
    S.versionsOpen = true;
    savePref("versionsOpen", "1");
    try { localStorage.setItem("my_own_library.seenSuggestions", JSON.stringify([...seen, ...fresh].slice(-500))); } catch { /* per-browser only */ }
}

function renderMain() {
    syncVersionBanner();
    const isOutput = S.view === "output";
    const searchInput = h("input", {
        type: "text", placeholder: "Search ...", title: isOutput ? "Search file names" : "Search titles, prompts, notes, tags and models",
        value: S.search,
    });
    const doSearch = debounce(async () => {
        S.search = searchInput.value;
        if (isOutput) await loadOutput(true);
        render();
        const again = S.dialog.querySelector(".mol-search input");
        again.focus();
        again.setSelectionRange(again.value.length, again.value.length);
    }, 250);
    searchInput.addEventListener("input", doSearch);

    const chip = (id, label, iconName) => h("button", {
        class: "mol-chip" + (S.kind === id ? " active" : ""),
        onclick: async () => { S.kind = id; if (isOutput) await loadOutput(true); render(); },
    }, iconName ? icon(iconName) : null, label);

    const filters = [chip("all", "All"), chip("image", "Images", "image"), chip("video", "Videos", "video"),
        chip("audio", "Audio", "volume-up")];
    if (!isOutput) {
        const families = allFamilies();
        const modelSel = dropdown({
            label: "Model Filter", multi: true, values: S.families, title: "Show only creations made with these models",
            options: families.map((m) => ({ value: m, label: m })),
            onChange: () => { S.suggestionIndex = 0; render(); reopenMenu("Model Filter"); },
        });
        const sortBox = dropdown({
            iconName: "sort-alt", value: S.sort, title: "Sort order",
            options: [["created-desc", "Newest created"], ["created-asc", "Oldest created"], ["added-desc", "Newest added"],
                ["added-asc", "Oldest added"], ["size-desc", "Largest first"], ["size-asc", "Smallest first"], ["title", "Title"]]
                .map(([v, l]) => ({ value: v, label: l })),
            onChange: (v) => { S.sort = v; savePref("sort", S.sort); render(); },
        });
        const nSug = visibleSuggestions().length;
        const detectBtn = h("button", {
            class: "mol-chip" + (S.versionsOpen ? " active" : ""),
            title: "Show or hide the suggestions of creations to group as versions, and how alike they must be",
            onclick: () => { S.versionsOpen = !S.versionsOpen; savePref("versionsOpen", S.versionsOpen ? "1" : "0"); render(); },
        }, icon("clone"), "Detect versions", nSug ? h("span", { class: "mol-chipcount" }, String(nSug)) : null);
        filters.push(h("span", { class: "mol-spacer" }), detectBtn, modelSel, sortBox);
    } else {
        filters.push(h("button", {
            class: "mol-chip" + (S.newOnly ? " active" : ""), title: "Only files created since your previous visit of this view",
            onclick: async () => { S.newOnly = !S.newOnly; await loadOutput(true); render(); },
        }, icon("sparkles"), "New since last visit"));
        filters.push(h("span", { class: "mol-spacer" }), h("button", {
            class: "mol-chip" + (S.hideAdded ? " active" : ""), title: "Show only files not yet copied to the library",
            onclick: async () => { S.hideAdded = !S.hideAdded; await loadOutput(true); render(); },
        }, icon(S.hideAdded ? "eye-slash" : "eye"), "Hide added"));
    }

    // The Duplicates view lists every group; filters don't apply there.
    const isDup = S.view === "duplicates";
    const tags = isOutput || isDup ? [] : allTags();
    const tagRow = tags.length ? h("div", { class: "mol-tagfilter" },
        ...tags.slice(0, 40).map((t) => h("span", {
            class: "mol-tag" + (S.tags.has(t.name.toLowerCase()) ? " active" : ""),
            onclick: () => { const k = t.name.toLowerCase(); S.tags.has(k) ? S.tags.delete(k) : S.tags.add(k); render(); },
        }, icon("tag"), `${t.name} · ${t.count}`))) : null;

    const head = h("div", { class: "mol-head" },
        h("div", { class: "mol-row" },
            h("div", { class: "mol-title" }, viewTitle()),
            h("div", { class: "mol-search" }, icon("search"), searchInput),
            maximizeButton(),
            h("button", { class: "mol-iconbtn", title: "Close", onclick: close }, icon("times"))),
        isDup ? null : h("div", { class: "mol-row" }, ...filters),
        tagRow);

    const main = h("section", { class: "mol-main" }, head);
    if (isOutput) {
        main.append(renderOutputGrid(), renderOutputBar());
    } else {
        main.append(renderItemGrid());
        const bar = renderLibraryBar();
        if (bar) main.append(bar);
    }
    return main;
}

// Suggestions restricted to the current view and filters: with FLUX.2 selected,
// only FLUX.2 creations of a workflow are proposed.
function visibleSuggestions() {
    const shown = new Set(filteredItems().map((it) => it.id));
    return S.suggestions
        .map((sug) => ({ ...sug, ids: sug.ids.filter((id) => shown.has(id)) }))
        .filter((sug) => {
            if (sug.ids.length < 2) return false;
            // Nothing to suggest if the shown creations are already one work.
            const works = new Set(sug.ids.map((id) => S.items.find((x) => x.id === id)?.work_id || null));
            return !(works.size === 1 && !works.has(null));
        });
}

const SIMILARITY = [
    ["strict", "Strict", "Only near-identical variations"],
    ["normal", "Normal", "Clear variations of the same image, video or sound"],
    ["loose", "Loose", "Looser resemblance, more suggestions"],
];

function similaritySelect() {
    const sel = dropdown({
        value: S.similarity, title: "How alike creations must look (or sound) to be suggested as versions",
        options: SIMILARITY.map(([v, label, tip]) => ({ value: v, label, hint: tip })),
        onChange: async (v) => {
            S.similarity = v;
            savePref("similarity", S.similarity);
            S.suggestionIndex = 0;
            await loadSuggestions();
            render();
        },
    });
    return h("span", { class: "mol-simlabel" }, "Similarity", sel);
}

function renderSuggestion() {
    if (S.view === "output" || !S.versionsOpen) return null;
    const list = visibleSuggestions();
    const pending = S.sigPending ? `${S.sigPending} creation${S.sigPending > 1 ? "s" : ""} still being analyzed for similarity.` : "";
    const closeBtn = h("button", { class: "mol-iconbtn", title: "Hide (Detect versions button to show again)",
        onclick: () => { S.versionsOpen = false; savePref("versionsOpen", "0"); render(); } }, icon("times"));
    if (!list.length) {
        return h("div", { class: "mol-suggestion mol-suggestion-empty" },
            h("span", { class: "mol-hint", style: { margin: 0 } }, pending || "No version suggestions at this level."),
            h("span", { class: "mol-spacer" }),
            similaritySelect(), closeBtn);
    }
    if (S.suggestionIndex >= list.length) S.suggestionIndex = 0;
    const sug = list[S.suggestionIndex];
    const items = sug.ids.map((id) => S.items.find((x) => x.id === id)).filter(Boolean);
    if (items.length < 2) return null;
    return h("div", { class: "mol-suggestion" },
        h("div", { class: "mol-sugthumbs" }, ...items.slice(0, 5).map((it) => h("img", { src: itemThumb(it), alt: "" }))),
        h("div", { class: "mol-sugtext" },
            h("b", {}, `${items.length} similar creations come from the same workflow.`),
            h("div", { class: "mol-hint" }, "Group them as versions of one work, in order of creation?"),
            pending ? h("div", { class: "mol-hint" }, pending) : null),
        h("span", { class: "mol-spacer" }),
        similaritySelect(),
        list.length > 1 ? h("button", { class: "mol-btn", title: "Next suggestion",
            onclick: () => { S.suggestionIndex = (S.suggestionIndex + 1) % list.length; render(); } },
        `${S.suggestionIndex + 1} of ${list.length}`, icon("chevron-right")) : null,
        h("button", { class: "mol-btn", title: "See them in large thumbnails and choose which to group",
            onclick: () => { S.review = { sug, checked: new Set(sug.ids), zoom: null, skipped: new Set() }; render(); } },
        icon("eye"), "Review"),
        h("button", { class: "mol-btn", onclick: async () => {
            await versionAction("dismiss", { workflow_id: sug.workflow_id, ids: sug.ids });
            render();
        } }, "Not the same work"),
        h("button", { class: "mol-btn primary", onclick: () => groupIds(sug.ids) }, icon("clone"), "Group as versions"),
        closeBtn);
}

// Review panel: the suggested creations in large thumbnails, all ticked;
// untick the ones that don't belong, then group the rest.
// Review goes through the suggestions one after the other: after grouping or
// "Not the same work", the next one opens; Skip leaves one for later.
const sugKey = (sug) => sug.workflow_id + ":" + [...sug.ids].sort().join(",");

function reviewNext(fromKey) {
    const R = S.review;
    const skipped = R?.skipped || new Set();
    const list = visibleSuggestions();
    const at = list.findIndex((x) => sugKey(x) === fromKey);
    // Next one after the current position, then from the start.
    const order = at >= 0 ? [...list.slice(at + 1), ...list.slice(0, at)] : list;
    const next = order.find((x) => !skipped.has(sugKey(x)) && sugKey(x) !== fromKey);
    if (!next) {
        S.review = null;
        toast("All suggestions reviewed", skipped.size ? `${skipped.size} skipped for later` : "");
    } else {
        S.review = { sug: next, checked: new Set(next.ids), zoom: null, skipped, fresh: true };
    }
    render();
}

function renderReview() {
    const R = S.review;
    const list = visibleSuggestions();
    const pos = list.findIndex((x) => sugKey(x) === sugKey(R.sug));
    const items = R.sug.ids.map((id) => S.items.find((x) => x.id === id)).filter(Boolean).sort(byCreated);
    const n = items.filter((it) => R.checked.has(it.id)).length;
    const close = () => { S.review = null; render(); };

    // Ticking updates the card in place (no re-render), so the list stays
    // exactly where it is, even while thumbnails are still loading.
    const groupLabel = (count) => count < 2 ? "Tick at least two" : `Group ${count} as versions`;
    let groupBtn = null;
    const cards = items.map((it, i) => {
        const on = R.checked.has(it.id);
        const check = h("span", { class: "mol-check" + (on ? " on" : ""), title: on ? "Leave out" : "Include" }, on ? icon("check") : null);
        check.addEventListener("click", (e) => {
            e.stopPropagation();
            const now = !R.checked.has(it.id);
            now ? R.checked.add(it.id) : R.checked.delete(it.id);
            check.className = "mol-check" + (now ? " on" : "");
            check.title = now ? "Leave out" : "Include";
            check.replaceChildren(...(now ? [icon("check")] : []));
            check.closest(".mol-reviewcard")?.classList.toggle("off", !now);
            const count = items.filter((x) => R.checked.has(x.id)).length;
            if (groupBtn) {
                groupBtn.disabled = count < 2;
                groupBtn.replaceChildren(icon("clone"), groupLabel(count));
            }
        });
        const thumb = h("div", { class: "mol-thumb", title: "Click to see it large" },
            thumbEl(itemThumb(it), it.kind, itemFile(it)),
            kindBadge(it.kind),
            check,
            familyStack(familiesOf(it)));
        attachHoverPlay(thumb, it.kind, itemFile(it));
        const excerpt = [...(it.summary?.positive || []), ...(it.summary?.text || [])].join(" ").slice(0, 180);
        return h("div", { class: "mol-card mol-reviewcard" + (on ? "" : " off"), onclick: () => { R.zoom = it.id; render(); } },
            thumb,
            h("div", { class: "mol-cardtitle", title: it.title }, `#${i + 1} · ${it.title}`),
            h("div", { class: "mol-hint", style: { marginTop: "-4px" } }, fmtDate(it.created),
                R.sug.scores?.[it.id] != null ? h("span", { class: "mol-simscore", title: "Lowest similarity with the other creations of this suggestion" },
                    ` · ${R.sug.scores[it.id]}% similar`) : null),
            excerpt ? h("div", { class: "mol-reviewtext" }, excerpt + (excerpt.length >= 180 ? "…" : "")) : null);
    });

    const panel = h("div", { class: "mol-review" },
        h("div", { class: "mol-head" },
            h("div", { class: "mol-row" },
                h("button", { class: "mol-iconbtn", title: "Back (Esc)", onclick: close }, icon("arrow-left")),
                h("div", { class: "mol-title" }, (list.length > 1 && pos >= 0 ? `Suggestion ${pos + 1} of ${list.length} · ` : "")
                    + `${items.length} similar creations from the same workflow`),
                h("span", { class: "mol-hint", style: { margin: 0 } }, "Untick the ones that are not versions of this work."))),
        h("div", { class: "mol-grid-wrap" }, h("div", { class: "mol-grid mol-reviewgrid" }, ...cards)),
        h("div", { class: "mol-actionbar" },
            h("button", { class: "mol-btn", onclick: close }, "Cancel"),
            h("span", { class: "mol-spacer" }),
            list.length > 1 ? h("button", { class: "mol-btn", title: "Decide later: go to the next suggestion",
                onclick: () => { R.skipped.add(sugKey(R.sug)); reviewNext(sugKey(R.sug)); } }, "Skip", icon("chevron-right")) : null,
            h("button", { class: "mol-btn", onclick: async () => {
                const key = sugKey(R.sug);
                await versionAction("dismiss", { workflow_id: R.sug.workflow_id, ids: R.sug.ids });
                reviewNext(key);
            } }, "Not the same work"),
            groupBtn = h("button", { class: "mol-btn primary", disabled: n < 2, onclick: async () => {
                const ids = items.filter((it) => R.checked.has(it.id)).map((it) => it.id);
                const workflowId = R.sug.workflow_id;
                const shownIds = R.sug.ids;
                const key = sugKey(R.sug);
                await groupIds(ids);
                // The left-out creations stay separate; don't suggest them again.
                if (ids.length < items.length) await versionAction("dismiss", { workflow_id: workflowId, ids: shownIds });
                reviewNext(key);
            } }, icon("clone"), groupLabel(n))));

    if (R.zoom) {
        const it = items.find((x) => x.id === R.zoom);
        if (it) {
            panel.append(h("div", { class: "mol-zoom", onclick: () => { R.zoom = null; render(); } },
                h("div", { onclick: (e) => e.stopPropagation(), style: { display: "contents" } },
                    previewEl(it.kind, itemFile(it), itemThumb(it))),
                h("button", { class: "mol-iconbtn mol-zoomclose", title: "Close (Esc)", onclick: () => { R.zoom = null; render(); } }, icon("times"))));
        }
    }
    return panel;
}

// Groups of identical creations: same file, or same pixels / frames / samples
// with different metadata. "Keep one" merges each group into one creation.
const byId = (id) => S.items.find((x) => x.id === id);

function keptOf(group) {
    // Same rule as the server: a version of a work if any, else the first added.
    return group.find((it) => it.work_id) || [...group].sort((a, b) => (a.added || "").localeCompare(b.added || ""))[0];
}

async function mergeDuplicates(body) {
    try {
        const res = await call("/duplicates/merge", body);
        applySnapshot(res);
        await loadSuggestions();
        if (res.errors?.length) toast("Some duplicates were not merged", res.errors.join("\n"), "warn");
        else toast("Duplicates merged", `${res.kept.length} creation${res.kept.length > 1 ? "s" : ""} kept`);
    } catch (e) {
        toast("Could not merge", e.message, "error");
    }
    render();
}

function renderDuplicates() {
    const wrap = h("div", { class: "mol-grid-wrap" });
    const groups = (S.duplicates || []).map((ids) => ids.map(byId).filter(Boolean)).filter((g) => g.length > 1);
    if (!groups.length) {
        wrap.append(h("div", { class: "mol-empty" }, "No duplicates in your library."));
        return wrap;
    }
    const extra = groups.reduce((n, g) => n + g.length - 1, 0);
    wrap.append(h("div", { class: "mol-suggestion" },
        h("div", { class: "mol-sugtext" },
            h("b", {}, `${groups.length} group${groups.length > 1 ? "s" : ""} of identical creations`),
            h("div", { class: "mol-hint" }, "Same file, or same image, video or sound with different metadata. "
                + "Keep one merges tags, notes and favorite into the creation kept and takes the oldest date; "
                + "the other copies leave the library (files in output are not touched).")),
        h("button", { class: "mol-btn primary", onclick: () => {
            if (confirm(`Merge all ${groups.length} groups?\n${extra} library cop${extra > 1 ? "ies" : "y"} will be removed. Files in the output folder are not touched.`))
                mergeDuplicates({ all: true });
        } }, icon("check"), `Keep one of each (${groups.length})`)));
    for (const group of groups) {
        const kept = keptOf(group);
        const works = groupWorks(group);
        const grid = h("div", { class: "mol-grid" });
        for (const it of [kept, ...group.filter((x) => x !== kept)]) {
            const pos = it.work_id ? membersOf(it).indexOf(it) + 1 : 0;
            const thumb = h("div", { class: "mol-thumb" },
                thumbEl(itemThumb(it), it.kind, itemFile(it)),
                kindBadge(it.kind, "mol-badge lib"),
                it === kept ? h("span", { class: "mol-topright" }, h("span", { class: "mol-ver" }, "Kept")) : null);
            attachHoverPlay(thumb, it.kind, itemFile(it));
            grid.append(h("div", { class: "mol-card" + (it === kept ? "" : " mol-dupcopy"), onclick: () => openItemById(it.id, works) },
                thumb,
                h("div", { class: "mol-cardtitle", title: it.title }, it.title),
                h("div", { class: "mol-hint", style: { marginTop: "-4px" } },
                    fmtDate(it.created), pos ? ` · v${pos} of a work` : "", it.source?.name ? ` · ${it.source.name}` : "")));
        }
        wrap.append(h("div", { class: "mol-dupgroup" },
            h("div", { class: "mol-row" },
                h("b", {}, `${group.length} identical copies`),
                h("span", { class: "mol-spacer" }),
                h("button", { class: "mol-btn", onclick: () => mergeDuplicates({ ids: group.map((x) => x.id) }) }, icon("check"), "Keep one")),
            grid));
    }
    return wrap;
}

function renderItemGrid() {
    if (S.view === "duplicates") return renderDuplicates();
    const works = filteredWorks();
    const wrap = h("div", { class: "mol-grid-wrap" });
    const banner = renderSuggestion();
    if (banner) wrap.append(banner);
    if (!works.length) {
        wrap.append(h("div", { class: "mol-empty" }, S.items.length
            ? "Nothing matches these filters."
            : h("span", {}, "Your library is empty.", h("br"),
                "Open ", h("b", {}, "Output"), " in the left column to add creations, or right-click an image on a Save Image or Preview node and choose ",
                h("b", {}, "Add to My Own Library"), ".")));
        return wrap;
    }
    const grid = h("div", { class: "mol-grid" + (S.libSelected.size ? " mol-selecting" : "") });
    works.forEach((w, index) => {
        const it = w.cover;
        const n = w.members.length;
        const on = S.libSelected.has(w.key);
        const check = h("span", {
            class: "mol-check mol-libcheck" + (on ? " on" : ""), title: "Select (to group as versions)",
            onclick: (e) => { e.stopPropagation(); on ? S.libSelected.delete(w.key) : S.libSelected.add(w.key); render(); },
        }, on ? icon("check") : null);
        const thumb = h("div", { class: "mol-thumb" + (n > 1 ? " stack" : "") },
            thumbEl(itemThumb(it), it.kind, itemFile(it)),
            kindBadge(it.kind, "mol-badge lib"),
            check,
            h("span", { class: "mol-topright" },
                it.favorite ? h("span", { class: "mol-star" }, icon("star-fill")) : null,
                n > 1 ? h("span", { class: "mol-ver", title: `${n} versions` }, `v${n}`) : null),
            familyStack(familiesOf(it)));
        attachHoverPlay(thumb, it.kind, itemFile(it));
        const chips = [];
        if (it.category) chips.push(h("span", { class: "mol-tag" }, icon("folder"), it.category));
        (it.tags || []).slice(0, 2).forEach((t) => chips.push(h("span", { class: "mol-tag" }, t)));
        if ((it.tags || []).length > 2) chips.push(h("span", { class: "mol-tag" }, `+${it.tags.length - 2}`));
        const size = workSize(w);
        grid.append(h("div", {
            class: "mol-card", title: (n > 1 ? `${n} versions, ` : "") + fmtSize(size),
            onclick: () => openDetail("item", works, index),
        }, thumb, h("div", { class: "mol-cardtitle", title: it.title }, it.title), h("div", { class: "mol-cardtags" }, chips)));
    });
    wrap.append(grid);
    return wrap;
}

function renderLibraryBar() {
    if (S.job) return renderJobProgress();
    if (!S.libSelected.size) return null;
    const works = groupWorks(S.items).filter((w) => S.libSelected.has(w.key));
    const ids = works.flatMap((w) => w.members.map((m) => m.id));
    const shown = filteredWorks();
    const allShown = shown.length && shown.every((w) => S.libSelected.has(w.key));

    const moveSel = h("select", { class: "mol-select", title: "Move the selection to a category",
        onchange: async (e) => {
            let value = e.target.value;
            if (value === "__new__") {
                value = (prompt("New category name") || "").trim();
                if (!value) { e.target.value = "__label__"; return; }
            }
            await bulkUpdate(ids, { category: value === "__none__" ? "" : value },
                value === "__none__" ? "Moved to Uncategorized" : `Moved to ${value}`);
        } },
    h("option", { value: "__label__", selected: true, disabled: true }, "Move to category"),
    h("option", { value: "__none__" }, "No category"),
    ...S.categories.map((c) => h("option", { value: c }, c)),
    h("option", { value: "__new__" }, "+ New category"));

    const tags = tagEditor(S.bulkTags || [], (v) => { S.bulkTags = v; }, { dropUp: true, placeholder: "Tags to add" });

    return h("div", { class: "mol-actionbar" },
        h("span", {}, `${works.length} selected`),
        h("button", { class: "mol-btn", onclick: () => { S.libSelected.clear(); render(); } }, "Clear selection"),
        h("button", { class: "mol-btn", title: "Select every card in the current view",
            onclick: () => {
                for (const w of shown) allShown ? S.libSelected.delete(w.key) : S.libSelected.add(w.key);
                render();
            } }, icon("check-square"), allShown ? "Unselect all shown" : "Select all shown"),
        h("span", { class: "mol-spacer" }),
        moveSel,
        h("div", { style: { width: "200px" } }, tags.el),
        h("button", { class: "mol-btn", onclick: async () => {
            const add = tags.get();
            if (!add.length) { toast("Type at least one tag first", "", "info"); return; }
            await bulkUpdate(ids, { add_tags: add }, `Tags added: ${add.join(", ")}`);
            S.bulkTags = [];
            render();
        } }, icon("tag"), "Add tags"),
        h("button", { class: "mol-btn danger", onclick: () => removeWorks(works) }, icon("trash"), `Remove ${works.length} from library`),
        h("button", { class: "mol-btn primary", disabled: ids.length < 2, onclick: () => groupIds(ids),
            title: "Versions are numbered in order of creation" }, icon("clone"), "Group as versions"));
}

async function bulkUpdate(ids, body, done) {
    try {
        applySnapshot(await call("/items/update", { ids, ...body }));
        toast(done, `${S.libSelected.size} selected`);
    } catch (e) {
        toast("Could not update", e.message, "error");
    }
    render();
}

async function removeWorks(works) {
    const members = works.flatMap((w) => w.members);
    const size = members.reduce((a, m) => a + (m.size || 0), 0);
    const versions = members.length > works.length ? ` (${members.length} versions)` : "";
    const what = works.length === 1 ? `"${works[0].cover.title}"${versions}` : `${works.length} creations${versions}`;
    if (!confirm(`Remove ${what} from your library, ${fmtSize(size)}?\n\n`
        + "The library copies are deleted permanently. Files still in the output folder are not touched.")) return;
    const job = await runJob("Removing from library", members.map((m) => m.id), 1,
        (chunk, info) => call("/items/remove", { ids: chunk, job: info }));
    if (!job) return;
    const last = job.results[job.results.length - 1];
    if (last) applySnapshot(last);
    await loadSuggestions();
    if (!job.cancelled) S.libSelected.clear();
    const removed = job.results.reduce((a, r) => a + (r.removed || 0), 0);
    const freed = job.results.reduce((a, r) => a + (r.freed || 0), 0);
    toast(job.cancelled ? "Removal stopped" : "Removed from library", `${removed} file(s), ${fmtSize(freed)} freed`);
    render();
}

function renderSkippedDuplicates() {
    const sk = S.skippedDups;
    if (!sk) return null;
    const names = sk.list.slice(0, 3).map((d) => `${d.rel.split("/").pop()} (same as "${d.title}")`).join(", ")
        + (sk.list.length > 3 ? `, and ${sk.list.length - 3} more` : "");
    return h("div", { class: "mol-suggestion" },
        h("div", { class: "mol-sugtext" },
            h("b", {}, `${sk.list.length} file${sk.list.length > 1 ? "s were" : " was"} not copied: identical to creations already in your library.`),
            h("div", { class: "mol-hint" }, names + (sk.list.length > 1
                ? ". They count as added, so you can delete them from output."
                : ". It counts as added, so you can delete it from output."))),
        h("button", { class: "mol-btn", onclick: () => { S.skippedDups = null; render(); } }, "OK"),
        h("button", { class: "mol-btn", title: "Copy them to the library as separate creations",
            onclick: () => { S.skippedDups = null; addFiles(sk.files, sk.category, sk.tags, false, true); } }, "Add anyway"));
}

function renderOutputGrid() {
    const wrap = h("div", { class: "mol-grid-wrap" });
    const skipped = renderSkippedDuplicates();
    if (skipped) wrap.append(skipped);
    const files = S.output.files;
    if (!files.length) {
        wrap.append(h("div", { class: "mol-empty" }, S.output.loading ? "Loading" : "No images or videos in the output folder."));
        return wrap;
    }
    const grid = h("div", { class: "mol-grid" });
    files.forEach((f, index) => {
        const key = f.root + "|" + f.rel;
        const on = S.selected.has(key);
        const check = h("span", {
            class: "mol-check" + (on ? " on" : ""), title: "Select",
            onclick: (e) => {
                e.stopPropagation();
                if (on) S.selected.delete(key);
                else { S.selected.add(key); S.selInfo.set(key, f); }
                render();
            },
        }, on ? icon("check") : null);
        const thumb = h("div", { class: "mol-thumb" },
            thumbEl(fileThumb(f), f.kind, fileSource(f)),
            kindBadge(f.kind),
            check,
            familyStack(f.families),
            f.in_library ? h("span", { class: "mol-inlib" }, "In library")
                : (S.lastVisit && f.mtime > S.lastVisit ? h("span", { class: "mol-inlib mol-new" }, "New") : null));
        attachHoverPlay(thumb, f.kind, fileSource(f));
        grid.append(h("div", { class: "mol-card", onclick: () => openDetail("file", files, index) },
            thumb,
            h("div", { class: "mol-cardtitle", title: f.rel }, f.name),
            h("div", { class: "mol-cardtags" },
                h("span", { class: "mol-tag" }, fmtDate(f.created)),
                f.rel.includes("/") ? h("span", { class: "mol-tag" }, icon("folder"), f.rel.split("/").slice(0, -1).join("/")) : null)));
    });
    wrap.append(grid);
    if (files.length < S.output.total) {
        wrap.append(h("div", { class: "mol-more" },
            h("button", { class: "mol-btn", onclick: async () => { await loadOutput(false); render(); } },
                `Load more (${S.output.total - files.length} remaining)`)));
    }
    return wrap;
}

// Tag editor with suggestions from the tags already used in the library.
// Up/Down to choose, Enter or Tab to take a suggestion, Esc to close the list.
function tagEditor(initial, onChange, { dropUp = false, placeholder = "Add a tag" } = {}) {
    let tags = [...(initial || [])];
    let options = [];
    let active = -1;
    const box = h("div", { class: "mol-tagsbox" + (dropUp ? " up" : "") });
    const input = h("input", { type: "text", placeholder, autocomplete: "off", spellcheck: "false" });
    const menu = h("div", { class: "mol-suggest" });
    menu.hidden = true;

    const known = () => allTags();
    const closeMenu = () => { options = []; active = -1; menu.hidden = true; };
    const draw = () => box.replaceChildren(
        ...tags.map((t) => h("span", { class: "mol-tag" }, t, h("i", {
            class: "pi pi-times", title: "Remove",
            onclick: () => { tags = tags.filter((x) => x !== t); onChange(tags); draw(); },
        }))),
        input, menu);
    const commit = (raw) => {
        let t = String(raw || "").replace(/,+$/, "").trim();
        if (!t) return;
        // Reuse the existing spelling of a tag, whatever the case typed.
        t = known().find((k) => k.name.toLowerCase() === t.toLowerCase())?.name || t;
        if (!tags.some((x) => x.toLowerCase() === t.toLowerCase())) {
            tags = [...tags, t];
            onChange(tags);
        }
        input.value = "";
        closeMenu();
        draw();
        input.focus();
    };
    const drawMenu = () => {
        menu.replaceChildren(...options.map((o, i) => h("div", {
            class: "mol-suggest-item" + (i === active ? " active" : ""),
            onmousedown: (e) => { e.preventDefault(); commit(o.name); },
        }, h("span", {}, o.name), h("span", { class: "mol-count" }, o.count))));
        menu.hidden = !options.length;
    };
    const suggest = () => {
        const q = input.value.trim().toLowerCase();
        if (!q) { closeMenu(); return; }
        const have = new Set(tags.map((x) => x.toLowerCase()));
        options = known()
            .filter((t) => !have.has(t.name.toLowerCase()) && t.name.toLowerCase().includes(q))
            .sort((a, b) => (b.name.toLowerCase().startsWith(q) - a.name.toLowerCase().startsWith(q)) || b.count - a.count)
            .slice(0, 8);
        active = options.length ? 0 : -1;
        drawMenu();
    };

    input.addEventListener("input", suggest);
    input.addEventListener("blur", () => setTimeout(closeMenu, 120));
    input.addEventListener("keydown", (e) => {
        const open = !menu.hidden && options.length;
        if (e.key === "ArrowDown" && open) {
            e.preventDefault(); active = (active + 1) % options.length; drawMenu();
        } else if (e.key === "ArrowUp" && open) {
            e.preventDefault(); active = (active - 1 + options.length) % options.length; drawMenu();
        } else if (e.key === "Enter") {
            e.preventDefault();
            commit(open && active >= 0 ? options[active].name : input.value);
        } else if (e.key === "Tab" && open && active >= 0) {
            e.preventDefault(); commit(options[active].name);
        } else if (e.key === ",") {
            e.preventDefault(); commit(input.value);
        } else if (e.key === "Escape" && open) {
            e.preventDefault(); e.stopPropagation(); closeMenu();
        } else if (e.key === "Backspace" && !input.value && tags.length) {
            tags = tags.slice(0, -1); onChange(tags); draw(); input.focus();
        }
    });
    draw();
    return { el: box, get: () => tags };
}

function categorySelect(value, onChange) {
    const sel = h("select", { class: "mol-select", onchange: async (e) => {
        if (e.target.value === "__new__") {
            const name = prompt("New category name");
            if (name && name.trim()) {
                await categoryAction("create", name.trim());
                onChange(name.trim());
            } else {
                e.target.value = value;
            }
            return;
        }
        onChange(e.target.value);
    } },
    h("option", { value: "" }, "No category"),
    ...S.categories.map((c) => h("option", { value: c, selected: c === value }, c)),
    h("option", { value: "__new__" }, "+ New category"));
    return sel;
}

function selectedFiles() {
    const loaded = new Map(S.output.files.map((f) => [f.root + "|" + f.rel, f]));
    return [...S.selected].map((k) => loaded.get(k) || S.selInfo.get(k)).filter(Boolean);
}

// Select (or unselect) every file of the output folder matching the current
// filters, including the ones not displayed yet. which: "missing" | "added".
async function selectWholeFolder(which) {
    let files;
    try {
        files = (await call(`/output?${new URLSearchParams({
            keys_only: 1, kind: S.kind, q: S.search, hide_added: S.hideAdded ? 1 : 0,
            ...(S.newOnly ? { since: S.lastVisit } : {}),
        })}`)).files;
    } catch (e) {
        toast("Could not read the output folder", e.message, "error");
        return;
    }
    files = files.filter((f) => (which === "added" ? f.in_library : !f.in_library));
    const keys = files.map((f) => f.root + "|" + f.rel);
    const allOn = keys.length && keys.every((k) => S.selected.has(k));
    files.forEach((f, i) => {
        if (allOn) S.selected.delete(keys[i]);
        else { S.selected.add(keys[i]); S.selInfo.set(keys[i], f); }
    });
    if (!keys.length) toast(which === "added" ? "No file of this view is in the library yet" : "Every file of this view is already in the library", "", "info");
    render();
}

// ------------------------------------------------------------------- jobs
// Long operations (adding, moving, deleting many files) are sent one file at a
// time: the window shows the progress, other actions wait, and Cancel stops
// after the current file. The server prints each file in the terminal.

async function runJob(label, list, size, send) {
    if (S.job) { toast("Please wait", `${S.job.label} is still running`, "warn"); return null; }
    const job = S.job = { id: Math.random().toString(36).slice(2), label, total: list.length, done: 0, cancel: false, next: list[0] };
    render();  // swaps the action bar for the progress bar
    const results = [];
    let processed = 0;
    try {
        for (let start = 0; start < list.length; start += size) {
            const chunk = list.slice(start, start + size);
            job.next = chunk[0];
            updateJobProgress();
            const last = start + size >= list.length;
            results.push(await send(chunk, { id: job.id, start, total: list.length, last }));
            processed = start + chunk.length;
            job.done = processed;
            updateJobProgress();
            if (job.cancel && !last) {
                try { await call("/job/cancel", { job: { id: job.id } }); } catch { /* only the terminal summary is lost */ }
                break;
            }
        }
    } catch (e) {
        toast(label + " stopped", e.message, "error");
        try { await call("/job/cancel", { job: { id: job.id } }); } catch { /* ignore */ }
    } finally {
        S.job = null;
    }
    return { results, processed, cancelled: processed < list.length, list };
}

// The progress bar replaces the action bar while a job runs; it is updated in
// place so the grid isn't rebuilt (and scrolled) for every batch.
function renderJobProgress() {
    const job = S.job;
    if (!job) return null;
    // Fixed layout: counter, file name (cut in the middle when too long, since
    // names of one series differ by their end), then a bar of fixed width.
    job.text = h("span", { class: "mol-jobtext" });
    job.head = h("span", { class: "mol-jobhead" });
    job.tail = h("span", { class: "mol-jobtail" });
    job.name = h("span", { class: "mol-jobname" }, job.head, job.tail);
    job.bar = h("span", { class: "mol-jobfill" });
    job.btn = h("button", { class: "mol-btn", onclick: () => { job.cancel = true; updateJobProgress(); } }, "Cancel");
    job.el = h("div", { class: "mol-actionbar mol-jobbar" },
        h("i", { class: "pi pi-spin pi-spinner" }), job.text, job.name,
        h("span", { class: "mol-jobtrack" }, job.bar), job.btn);
    updateJobProgress();
    return job.el;
}

function updateJobProgress() {
    const job = S.job;
    if (!job?.text) return;
    const name = typeof job.next === "string" ? "" : (job.next?.rel || job.next?.name || "").split("/").pop();
    job.text.textContent = job.cancel
        ? `${job.label}: stopping after the current file (${job.done} / ${job.total})`
        : `${job.label}: ${job.done} / ${job.total}`;
    const shown = !job.cancel && job.done < job.total ? name : "";
    const cut = shown.length > 24 ? shown.length - 14 : shown.length;
    job.head.textContent = shown.slice(0, cut);
    job.tail.textContent = shown.slice(cut);
    job.name.title = shown;
    job.bar.style.width = (job.total ? (100 * job.done) / job.total : 0) + "%";
    job.btn.disabled = job.cancel;
}

async function deleteFromOutput(files) {
    if (!files.length) return;
    const total = files.reduce((a, f) => a + (f.size || 0), 0);
    const msg = files.length === 1
        ? `Permanently delete "${files[0].name}" (${fmtSize(total)}) from the output folder?`
        : `Permanently delete ${files.length} files (${fmtSize(total)}) from the output folder?`;
    if (!confirm(msg + "\n\nYour library keeps its copies. This cannot be undone.")) return false;
    const job = await runJob("Deleting from output", files.map((f) => ({ root: f.root, rel: f.rel })), 1,
        (chunk, info) => call("/output/delete", { files: chunk, job: info }));
    if (!job) return false;
    const deleted = job.results.flatMap((r) => r.deleted || []);
    const errors = job.results.flatMap((r) => r.errors || []);
    const freed = job.results.reduce((a, r) => a + (r.freed || 0), 0);
    if (errors.length) toast("Some files were not deleted", errors.map((e) => `${e.rel}: ${e.error}`).join("\n"), "warn");
    toast(job.cancelled ? "Deletion stopped" : "Deleted from output", `${deleted.length} file(s), ${fmtSize(freed)} freed`
        + (job.cancelled ? `, ${files.length - job.processed} left` : ""));
    for (const f of job.list.slice(0, job.processed)) S.selected.delete(f.root + "|" + f.rel);
    await refreshAfterJob();
    return true;
}

// Show what is left to do in the output folder, with the same filters.
async function refreshAfterJob() {
    try {
        await loadLibrary();
        await loadOutput(true);
    } catch (e) {
        toast("Could not refresh", e.message, "error");
    }
    render();
    refreshBadge();
}

function removeAfterBox(get, set) {
    const box = h("input", { type: "checkbox" });
    box.checked = get();
    box.addEventListener("change", () => set(box.checked));
    return h("label", { class: "mol-checkline", title: "Delete the file from the output folder once it is safely copied" },
        box, "Remove from output after adding");
}

function renderOutputBar() {
    if (S.job) return renderJobProgress();
    const shownKeys = new Set(S.output.files.map((f) => f.root + "|" + f.rel));
    const hidden = [...S.selected].filter((k) => !shownKeys.has(k)).length;
    const sel = selectedFiles();
    const toAdd = sel.filter((f) => !f.in_library);
    const toDelete = sel.filter((f) => f.in_library);
    return h("div", { class: "mol-actionbar" },
        h("button", { class: "mol-btn", onclick: () => selectWholeFolder("missing"),
            title: "Every file of the output folder (in this view) not copied to the library yet, including those not displayed" },
        icon("check-square"), "Select not in library"),
        h("button", { class: "mol-btn", onclick: () => selectWholeFolder("added"),
            title: "Every file of the output folder (in this view) already copied to the library, including those not displayed" },
        icon("check-square"), "Select added"),
        S.selected.size ? h("span", { style: { color: "var(--mol-dim)" } },
            `${S.selected.size} selected` + (hidden ? ` (${hidden} not displayed)` : "")) : null,
        S.selected.size ? h("button", { class: "mol-btn", onclick: () => { S.selected.clear(); S.selInfo.clear(); render(); } }, "Clear") : null,
        toDelete.length ? h("button", { class: "mol-btn danger", onclick: () => deleteFromOutput(toDelete) },
            icon("trash"), `Delete ${toDelete.length} from output`) : null,
        h("span", { class: "mol-spacer" }),
        categorySelect(S.addCategory, (v) => { S.addCategory = v; }),
        h("div", { style: { width: "260px" } },
            tagEditor(S.addTags, (v) => { S.addTags = v; }, { dropUp: true, placeholder: "Tags for the selection" }).el),
        removeAfterBox(() => S.removeAfter, (v) => { S.removeAfter = v; }),
        h("button", {
            class: "mol-btn primary", disabled: !toAdd.length,
            onclick: async () => {
                const res = await addFiles(toAdd.map((f) => ({ root: f.root, rel: f.rel })), S.addCategory, S.addTags, S.removeAfter);
                if (res) { S.addTags = []; render(); }
            },
        }, icon("plus"), `Add ${toAdd.length || ""} to library`));
}

async function addFiles(files, category = "", tags = [], removeAfter = false, allowDuplicates = false) {
    if (!files.length) return;
    if (!S.dialog?.open) toast("Adding to library", `${files.length} file(s), copying`, "info");
    const label = removeAfter ? "Moving to library" : "Adding to library";
    const job = await runJob(label, files, 1, (chunk, info) =>
        call("/add", { files: chunk, category, tags, remove_after: !!removeAfter, allow_duplicates: !!allowDuplicates, job: info }));
    if (!job) return;
    const res = { added: [], existing: [], duplicates: [], errors: [], removed: [], freed: 0 };
    for (const r of job.results) {
        for (const k of ["added", "existing", "duplicates", "errors", "removed"]) res[k] = res[k].concat(r[k] || []);
        res.freed += r.freed || 0;
    }
    try {
        for (const f of files.slice(0, job.processed)) S.selected.delete(f.root + "|" + f.rel);
        const dups = res.duplicates || [];
        // Files identical to a creation already in the library are linked to it
        // instead of copied again; offer to add them anyway (unless just deleted).
        const gone = new Set(res.removed || []);
        const kept = dups.filter((d) => !gone.has(d.rel));
        S.skippedDups = kept.length ? { files: kept.map((d) => ({ root: d.root, rel: d.rel })), category, tags, list: kept } : null;
        if (res.errors.length) toast("Some files were not added", res.errors.map((e) => `${e.rel}: ${e.error}`).join("\n"), "warn");
        toast(job.cancelled ? `${label} stopped` : "Added to library", `${res.added.length} added${res.existing.length ? `, ${res.existing.length} already there` : ""}`
            + (dups.length ? `, ${dups.length} skipped as identical to a creation already in the library` : "")
            + (res.removed?.length ? `, ${res.removed.length} removed from output (${fmtSize(res.freed)})` : "")
            + (job.cancelled ? `, ${files.length - job.processed} left` : ""));
        await refreshAfterJob();
        return res;
    } catch (e) {
        toast("Could not add", e.message, "error");
    }
}

// ------------------------------------------------------------------ detail

function openDetail(type, list, index, ver) {
    S.detail = { type, list, index, ver };
    render();
}

function closeDetail() {
    S.detail = null;
    render();
}

function moveDetail(step) {
    if (!S.detail) return;
    const n = S.detail.list.length;
    S.detail.index = (S.detail.index + step + n) % n;
    S.detail.ver = undefined;
    render();
}

// Move the version shown one step earlier or later in the work.
async function shiftVersion(step) {
    const work = S.detail?.type === "item" ? S.detail.list[S.detail.index] : null;
    if (!work || work.members.length < 2) return;
    const members = work.members;
    const from = S.detail.ver ?? members.indexOf(work.cover);
    const to = from + step;
    if (from < 0 || to < 0 || to >= members.length) return;
    await reorderVersions(members, from, to);
}

async function reorderVersions(members, from, to) {
    const ids = members.map((m) => m.id);
    const [moved] = ids.splice(from, 1);
    ids.splice(to, 0, moved);
    await versionAction("order", { work_id: members[0].work_id, ids });
    refreshDetailWork(moved);
}

function moveVersion(step) {
    const work = S.detail?.type === "item" ? S.detail.list[S.detail.index] : null;
    if (!work || work.members.length < 2) return;
    const n = work.members.length;
    const cur = S.detail.ver ?? work.members.indexOf(work.cover);
    S.detail.ver = Math.min(n - 1, Math.max(0, cur + step));
    render();
}

function kv(rows) {
    const box = h("div", { class: "mol-kv" });
    for (const [k, v] of rows) if (v) box.append(h("div", {}, k), h("div", {}, v));
    return box;
}

function promptBlock(label, texts) {
    if (!texts?.length) return null;
    const text = texts.join("\n\n");
    return h("div", { class: "mol-field" },
        h("div", { class: "mol-promptbar" }, h("label", {}, label),
            h("button", { class: "mol-iconbtn", title: "Copy", onclick: () => copyText(text) }, icon("copy"))),
        h("div", { class: "mol-prompt" }, text));
}

function summaryBlocks(sum) {
    if (!sum) return [];
    const hasData = ["positive", "negative", "text", "seeds", "models", "loras"].some((k) => sum[k]?.length);
    if (!hasData) return [h("div", { class: "mol-hint" }, "No ComfyUI metadata found in this file.")];
    return [
        promptBlock("Positive prompt", sum.positive),
        promptBlock("Negative prompt", sum.negative),
        promptBlock("Text", sum.text),
        kv([
            ["Seed", (sum.seeds || []).join(", ")],
            ["Models", (sum.models || []).join("\n")],
            ["LoRAs", (sum.loras || []).join("\n")],
        ]),
    ].filter(Boolean);
}

function previewEl(kind, src, thumb) {
    if (kind === "audio") {
        const wave = h("img", { src: thumb, draggable: "false", class: "mol-wave" });
        wave.onerror = () => wave.replaceWith(h("div", { class: "mol-noimg", style: { height: "220px" } }, icon("volume-up")));
        return h("div", { class: "mol-audio" }, wave, h("audio", { src, controls: true, autoplay: true }));
    }
    return kind === "video"
        ? h("video", { src, controls: true, autoplay: true, loop: true, playsinline: true })
        : h("img", { src, draggable: "false" });
}

// New thumbnail (and Reset thumbnail, only once one was chosen) over the player.
// They update the page in place, so the video keeps playing or stays paused.
function thumbButtons(it, preview) {
    const box = h("div", { class: "mol-thumbbtns" });
    const fill = () => {
        box.replaceChildren(
            it.thumb_custom ? h("button", { class: "mol-btn mol-overbtn", title: "Back to the automatic thumbnail",
                onclick: () => resetThumbnail(it, fill, preview) }, icon("replay"), "Reset thumbnail") : null,
            h("button", { class: "mol-btn mol-overbtn", title: "Use the frame shown in the player as this video's thumbnail",
                onclick: (e) => newThumbnail(it, preview.querySelector("video"), e.currentTarget, fill, preview) }, icon("camera"), "New thumbnail"));
    };
    fill();
    return box;
}

// Show the new thumbnail wherever this creation appears in the open panel.
function refreshThumbImages(it, preview) {
    const src = itemThumb(it);
    const strip = preview?.querySelectorAll(".mol-stripitem img") || [];
    const work = S.detail?.list?.[S.detail.index];
    (work?.members || []).forEach((m, i) => { if (m.id === it.id && strip[i]) strip[i].src = src; });
    if (work) work.members = work.members.map((m) => (m.id === it.id ? it : m));
    if (work?.cover?.id === it.id) work.cover = it;
}

// Thumbnail from the frame shown in the player (paused or playing).
async function newThumbnail(it, video, btn, refill, preview) {
    if (!video || !video.videoWidth) { toast("New thumbnail", "The video isn't loaded yet", "warn"); return; }
    const scale = Math.min(1, 1024 / Math.max(video.videoWidth, video.videoHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    if (btn) btn.disabled = true;
    try {
        const res = await call("/item/thumbnail", { id: it.id, image: canvas.toDataURL("image/jpeg", 0.92), time: video.currentTime });
        applyItemUpdate(res.item);
        Object.assign(it, res.item);
        refreshThumbImages(it, preview);
        refill?.();
        const work = it.work_id && S.items.filter((x) => x.work_id === it.work_id).length > 1;
        toast("New thumbnail", work && !res.item.work_cover
            ? `Taken at ${video.currentTime.toFixed(1)} s. This version isn't the cover: use Set as cover to show it on the card.`
            : `Taken at ${video.currentTime.toFixed(1)} s`);
    } catch (e) {
        toast("Could not set the thumbnail", e.message, "error");
    }
    if (btn) btn.disabled = false;
}

async function resetThumbnail(it, refill, preview) {
    try {
        const res = await call("/item/thumbnail", { id: it.id, reset: true });
        applyItemUpdate(res.item);
        for (const k of Object.keys(it)) if (!(k in res.item)) delete it[k];
        Object.assign(it, res.item);
        refreshThumbImages(it, preview);
        refill?.();
        toast("Thumbnail reset", it.title);
    } catch (e) {
        toast("Could not reset the thumbnail", e.message, "error");
    }
}

function applyItemUpdate(item) {
    const idx = S.items.findIndex((x) => x.id === item.id);
    if (idx >= 0) S.items[idx] = item;  // the server sends the whole item
}

function renderDetail() {
    const { type, list, index } = S.detail;
    const isItem = type === "item";
    const work = isItem ? list[index] : null;
    const members = work ? work.members : [];
    let ver = 0;
    if (work) {
        ver = S.detail.ver ?? members.indexOf(work.cover);
        if (ver < 0 || ver >= members.length) ver = members.length - 1;
    }
    const entry = isItem ? members[ver] : list[index];
    const media = isItem ? itemFile(entry) : fileSource(entry);

    // Drag a thumbnail of the strip to put that version elsewhere.
    let dragFrom = null;
    const strip = members.length > 1 ? h("div", { class: "mol-strip" },
        ...members.map((m, i) => h("button", {
            class: "mol-stripitem" + (i === ver ? " active" : ""),
            title: `v${i + 1} · ${fmtDate(m.created)}${m.work_cover ? " · cover" : ""}\n↑ / ↓ to browse, drag or Alt+↑ / Alt+↓ to move`,
            draggable: "true",
            onclick: () => { S.detail.ver = i; render(); },
            ondragstart: (e) => { dragFrom = i; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", m.id); },
            ondragover: (e) => { if (dragFrom === null) return; e.preventDefault(); e.currentTarget.classList.add("drop"); },
            ondragleave: (e) => e.currentTarget.classList.remove("drop"),
            ondragend: () => { dragFrom = null; },
            ondrop: async (e) => {
                e.preventDefault();
                e.currentTarget.classList.remove("drop");
                const from = dragFrom;
                dragFrom = null;
                if (from !== null && from !== i) await reorderVersions(members, from, i);
            },
        }, h("img", { src: itemThumb(m), alt: "", draggable: "false" }), h("span", {}, `v${i + 1}`)))) : null;

    const preview = h("div", { class: "mol-preview" + (strip ? " has-strip" : "") },
        previewEl(entry.kind, media, isItem ? itemThumb(entry) : fileThumb(entry)),
        list.length > 1 ? h("button", { class: "mol-navarrow", style: { left: "16px" }, title: "Previous (←)", onclick: () => moveDetail(-1) }, icon("chevron-left")) : null,
        list.length > 1 ? h("button", { class: "mol-navarrow", style: { right: "16px" }, title: "Next (→)", onclick: () => moveDetail(1) }, icon("chevron-right")) : null,
        strip);
    if (isItem && entry.kind === "video") preview.append(thumbButtons(entry, preview));

    const info = h("aside", { class: "mol-info" });
    const headTitle = h("div", { style: { fontWeight: 600, flex: 1 } }, `${index + 1} / ${list.length}`,
        members.length > 1 ? h("span", { style: { color: "var(--mol-accent)", marginLeft: "10px" } }, `v${ver + 1} of ${members.length}`) : null);
    info.append(h("div", { class: "mol-infohead" },
        h("button", { class: "mol-iconbtn", title: "Back to grid (Esc)", onclick: closeDetail }, icon("arrow-left")),
        headTitle,
        maximizeButton(),
        h("button", { class: "mol-iconbtn", title: "Close library", onclick: close }, icon("times"))));

    const body = h("div", { class: "mol-infobody" });
    info.append(body);
    if (isItem) fillItemDetail(entry, body, info, members, ver);
    else fillFileDetail(entry, body, info);
    return h("div", { class: "mol-detail" }, preview, info);
}

// What changed between two versions: seed, prompt words, models, LoRAs.
function tokens(text) {
    return (text || "").split(/[\s,;]+/).map((t) => t.replace(/^[("'\[]+|[)"'.!?:\]]+$/g, "")).filter(Boolean);
}

function wordDiff(before, after) {
    const count = new Map();
    for (const t of tokens(before)) count.set(t.toLowerCase(), (count.get(t.toLowerCase()) || 0) + 1);
    const added = [];
    for (const t of tokens(after)) {
        const k = t.toLowerCase();
        if (count.get(k)) count.set(k, count.get(k) - 1);
        else added.push(t);
    }
    const left = new Map(count);
    const removed = [];
    for (const t of tokens(before)) {
        const k = t.toLowerCase();
        if (left.get(k)) { removed.push(t); left.set(k, left.get(k) - 1); }
    }
    return { added, removed };
}

function changesBlock(prev, cur, prevLabel) {
    const a = prev.summary || {};
    const b = cur.summary || {};
    const rows = [];
    const row = (key, ...vals) => rows.push(h("div", { class: "row" }, h("span", { class: "key" }, key), h("span", { class: "val" }, ...vals)));
    const list = (added, removed) => [...added.map((x) => h("span", { class: "mol-add" }, "+ " + x)),
        ...removed.map((x) => h("span", { class: "mol-del" }, x))];
    const sa = (a.seeds || []).join(", ");
    const sb = (b.seeds || []).join(", ");
    if (sa !== sb) row("Seed", h("span", { class: "mol-del" }, sa || "none"), h("span", {}, "→"), h("span", { class: "mol-add" }, sb || "none"));
    for (const [key, label] of [["positive", "Positive"], ["negative", "Negative"], ["text", "Text"]]) {
        const d = wordDiff((a[key] || []).join(" "), (b[key] || []).join(" "));
        if (d.added.length || d.removed.length) row(label, ...list(d.added, d.removed));
    }
    for (const [key, label] of [["models", "Models"], ["loras", "LoRAs"]]) {
        const pa = new Set(a[key] || []);
        const pb = new Set(b[key] || []);
        const added = [...pb].filter((x) => !pa.has(x));
        const removed = [...pa].filter((x) => !pb.has(x));
        if (added.length || removed.length) row(label, ...list(added, removed));
    }
    return h("div", { class: "mol-field" }, h("label", {}, `Changes since ${prevLabel}`),
        h("div", { class: "mol-changes" }, ...(rows.length ? rows
            : [h("div", { class: "mol-hint", style: { margin: 0 } }, "Same seed, prompts and models.")])));
}

function fillItemDetail(it, body, info, members = [it], ver = 0) {
    const versioned = members.length > 1;
    const saved = h("span", { class: "mol-saved" }, "");
    const save = async (fields) => {
        saved.textContent = "Saving";
        try {
            const res = await call("/item/update", { id: it.id, fields });
            Object.assign(it, res.item);
            const idx = S.items.findIndex((x) => x.id === it.id);
            if (idx >= 0) S.items[idx] = it;
            // Title, category, tags and favorite are shared by all versions of a work.
            for (const m of members) {
                if (m === it) continue;
                for (const k of ["title", "category", "tags", "favorite"]) if (k in fields) m[k] = it[k];
            }
            S.categories = res.categories;
            saved.textContent = "Saved";
        } catch (e) {
            saved.textContent = "Not saved";
            toast("Could not save", e.message, "error");
        }
    };
    const saveSoon = debounce(save, 600);

    const title = h("input", { type: "text", value: it.title });
    title.addEventListener("input", () => saveSoon({ title: title.value }));

    const star = h("button", { class: "mol-iconbtn", title: "Favorite", style: { color: it.favorite ? "#ffd54f" : "" },
        onclick: async () => { await save({ favorite: !it.favorite }); render(); } },
    icon(it.favorite ? "star-fill" : "star"));

    const tags = tagEditor(it.tags, (v) => { it.tags = v; save({ tags: v }); }, { placeholder: "Add a tag, then Enter" });

    const detected = (it.summary?.families?.length ? it.summary.families : [it.summary?.family].filter(Boolean)).join(", ");
    const familyList = "mol-families";
    const family = h("input", { type: "text", value: it.family_override || "", list: familyList,
        placeholder: detected ? `${detected} (detected)` : "Not detected, type a name" });
    family.addEventListener("input", () => saveSoon({ family_override: family.value }));
    const familyOptions = h("datalist", { id: familyList },
        ...[...new Set([...KNOWN_FAMILIES, ...allFamilies()])].map((f) => h("option", { value: f })));

    const notes = h("textarea", { placeholder: "What worked, what to try next" }, it.notes || "");
    notes.addEventListener("input", () => saveSoon({ notes: notes.value }));

    body.append(
        h("div", { class: "mol-field" }, h("label", {}, "Title"), h("div", { style: { display: "flex", gap: "6px" } }, title, star)),
        h("div", { class: "mol-field" }, h("label", {}, "Category"),
            categorySelect(it.category, (v) => { it.category = v; save({ category: v }); })),
        h("div", { class: "mol-field" }, h("label", {}, "Model"), family, familyOptions,
            h("div", { class: "mol-hint" }, detected ? "Leave empty to use the detected models. Several: separate them with commas, in order of execution."
                : "No model family recognized in this file.")),
        h("div", { class: "mol-field" }, h("label", {}, "Tags"), tags.el),
        h("div", { class: "mol-field" }, h("label", {}, versioned ? `Notes for v${ver + 1}` : "Notes"), notes),
        ...(ver > 0 ? [changesBlock(members[ver - 1], it, `v${ver}`)] : []),
        ...summaryBlocks(it.summary),
        kv([
            ["Created", fmtDate(it.created)],
            ["Added", fmtDate(it.added)],
            ["Size", fmtSize(it.size) + (it.width ? ` · ${it.width} × ${it.height}` : "")],
            ["Original file", it.source ? `${it.source.root}/${it.source.rel}` : ""],
        ]));

    let armed = false;
    const removeBtn = h("button", { class: "mol-btn danger", onclick: async () => {
        if (!armed) { armed = true; removeBtn.lastChild.textContent = "Click again to confirm"; return; }
        try {
            await call("/item/remove", { id: it.id });
            await loadLibrary();
            toast("Removed from library", it.title);
            closeDetail();
        } catch (e) { toast("Could not remove", e.message, "error"); }
    } }, icon("trash"), h("span", {}, versioned ? `Remove v${ver + 1}` : "Remove"));

        const versionButtons = versioned ? [
        h("button", { class: "mol-btn", disabled: !!it.work_cover, title: "Show this version on the card",
            onclick: async () => { await versionAction("cover", { id: it.id }); refreshDetailWork(it.id); } },
        icon("image"), it.work_cover ? "Cover" : "Set as cover"),
        h("button", { class: "mol-iconbtn", disabled: ver === 0, title: "Move this version earlier (Alt+↑)",
            onclick: () => shiftVersion(-1) }, icon("arrow-up")),
        h("button", { class: "mol-iconbtn", disabled: ver === members.length - 1, title: "Move this version later (Alt+↓)",
            onclick: () => shiftVersion(1) }, icon("arrow-down")),
        members.some((m) => m.work_pos != null) ? h("button", { class: "mol-btn", title: "Put the versions back in order of creation",
            onclick: async () => { await versionAction("sortbydate", { work_id: it.work_id }); refreshDetailWork(it.id); } },
        icon("sort"), "Sort by date") : null,
        h("button", { class: "mol-btn", title: "Make this version a separate creation again",
            onclick: async () => { await versionAction("ungroup", { id: it.id }); refreshDetailWork(it.id); } },
        icon("external-link"), "Separate"),
    ] : [];

    info.append(h("div", { class: "mol-infofoot" },
        h("button", { class: "mol-btn primary", disabled: !(it.has_workflow || it.has_prompt), onclick: () => loadWorkflow(it) },
            icon("sitemap"), "Load workflow"),
        it.summary?.positive?.length ? h("button", { class: "mol-btn", onclick: () => copyText(it.summary.positive.join("\n\n")) }, icon("copy"), "Copy prompt") : null,
        h("a", { class: "mol-btn", href: itemFile(it, { download: 1 }), title: "Download" }, icon("download")),
        ...versionButtons,
        removeBtn,
        saved));
}

// After a version change, rebuild the list shown in the detail panel and
// reopen the same creation in it.
function refreshDetailWork(id) {
    const works = filteredWorks();
    openItemById(id, works.some((w) => w.members.some((m) => m.id === id)) ? works : undefined);
}

function fillFileDetail(f, body, info) {
    const state = h("div", { style: { color: "var(--mol-dim)" } }, "Reading metadata");
    body.append(
        h("div", { style: { fontWeight: 600, fontSize: "16px", wordBreak: "break-all" } }, f.name),
        kv([["Model", (f.families || []).join(" → ")], ["Created", fmtDate(f.created)], ["Size", fmtSize(f.size)], ["Folder", `${f.root}/${f.rel}`]]),
        state);

    let category = S.addCategory;
    let removeAfter = S.removeAfter;
    const tags = tagEditor([], () => {}, { placeholder: "Add a tag, then Enter" });
    const addBtn = h("button", { class: "mol-btn primary", onclick: async () => {
        const res = await addFiles([{ root: f.root, rel: f.rel }], category, tags.get(), removeAfter);
        const item = res?.added?.[0] || res?.existing?.[0];
        if (item) {
            f.in_library = item.id;
            openItemById(item.id);
        }
    } }, icon("plus"), "Add to library");

    const foot = h("div", { class: "mol-infofoot" });
    info.append(foot);

    call(`/inspect?${new URLSearchParams({ root: f.root, rel: f.rel })}`).then((d) => {
        state.remove();
        body.append(...summaryBlocks(d.summary).filter(Boolean));
        if (d.in_library) {
            foot.append(
                h("button", { class: "mol-btn primary", onclick: () => openItemById(d.in_library) },
                    icon("bookmark"), "Already in library, open it"),
                h("button", { class: "mol-btn danger", onclick: async () => {
                    if (await deleteFromOutput([f])) closeDetail();
                } }, icon("trash"), "Delete from output"));
        } else {
            body.append(
                h("div", { class: "mol-field" }, h("label", {}, "Category"), categorySelect(category, (v) => { category = v; })),
                h("div", { class: "mol-field" }, h("label", {}, "Tags"), tags.el),
                removeAfterBox(() => removeAfter, (v) => { removeAfter = v; }));
            foot.append(addBtn);
        }
    }).catch((e) => { state.textContent = "Could not read the file: " + e.message; });
}

async function loadWorkflow(it) {
    try {
        const meta = await call(`/meta?${new URLSearchParams({ id: it.id })}`);
        const name = (it.title || "creation").replace(/[\\/:*?"<>|]/g, "_");
        if (meta.workflow) {
            const file = new File([JSON.stringify(meta.workflow)], name + ".json", { type: "application/json" });
            await app.handleFile(file);
        } else if (meta.prompt) {
            app.loadApiJson(meta.prompt, name + ".json");
        } else {
            toast("No workflow in this file", "", "warn");
            return;
        }
        close();
        toast("Workflow loaded", it.title);
    } catch (e) {
        toast("Could not load the workflow", e.message, "error");
    }
}

// ------------------------------------------------------------- open/close

function onKey(e) {
    if (!S.dialog?.open) return;
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
    if (e.key === "Escape") {
        e.preventDefault();
        if (S.review?.zoom) { S.review.zoom = null; render(); }
        else if (S.review) { S.review = null; render(); }
        else if (S.detail) closeDetail();
        else close();
        return;
    }
    if (S.detail && !typing) {
        if (e.key === "ArrowLeft") moveDetail(-1);
        if (e.key === "ArrowRight") moveDetail(1);
        if (e.key === "ArrowUp" && e.altKey) { e.preventDefault(); shiftVersion(-1); return; }
        if (e.key === "ArrowDown" && e.altKey) { e.preventDefault(); shiftVersion(1); return; }
        if (e.key === "ArrowUp") { e.preventDefault(); moveVersion(-1); }
        if (e.key === "ArrowDown") { e.preventDefault(); moveVersion(1); }
    }
}

// Full-screen window, remembered between visits.
function applyMaximized() {
    S.dialog?.classList.toggle("maximized", loadPref("maximized", "0") === "1");
}

function maximizeButton() {
    const on = loadPref("maximized", "0") === "1";
    return h("button", { class: "mol-iconbtn", title: on ? "Restore" : "Maximize",
        onclick: () => { savePref("maximized", on ? "0" : "1"); applyMaximized(); render(); } },
    icon(on ? "window-minimize" : "window-maximize"));
}

async function open(view) {
    injectCSS();
    if (!S.dialog) {
        S.dialog = h("dialog", { class: "mol-dialog" }, h("div", { class: "mol-root", tabindex: "-1" }));
        // Native Esc: go back from a detail first, then close.
        S.dialog.addEventListener("cancel", (e) => { e.preventDefault(); onKey({ key: "Escape", preventDefault() {} }); });
        // Handle our keys, then keep ComfyUI shortcuts from firing behind the window.
        S.dialog.addEventListener("keydown", (e) => { onKey(e); e.stopPropagation(); });
        // A click on the dimmed backdrop closes the window, like Templates. Only
        // when the press started there too, so selecting text and releasing
        // outside the window doesn't close it.
        let pressOutside = false;
        const outside = (e) => {
            if (e.target !== S.dialog) return false;
            const r = S.dialog.getBoundingClientRect();
            return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
        };
        S.dialog.addEventListener("mousedown", (e) => { pressOutside = outside(e); });
        S.dialog.addEventListener("click", (e) => { if (pressOutside && outside(e)) close(); pressOutside = false; });
        document.body.append(S.dialog);
    }
    applyMaximized();
    if (view) S.view = view;
    S.detail = null;
    S.dialog.showModal();
    S.dialog.querySelector(".mol-root").replaceChildren(h("div", { class: "mol-empty", style: { flex: 1 } }, "Loading library"));
    if (S.view === "output") { S.selected.clear(); await markOutputSeen(); }
    try {
        await Promise.all([loadLibrary(), loadOutput(true)]);
    } catch (e) {
        toast("Could not open the library", e.message, "error");
    }
    render();
}

function close() {
    stopHoverVideos();
    S.detail = null;
    S.dialog?.close();
    S.dialog?.querySelectorAll("video").forEach((v) => v.pause());
}

// ---------------------------------------------------- node context menu

function nodeOutputs(node) {
    const out = [];
    const push = (arr) => {
        for (const x of arr || []) if (x?.filename && (x.type === "output" || x.type === "temp"))
            out.push({ root: x.type, rel: (x.subfolder ? x.subfolder + "/" : "") + x.filename });
    };
    const fromStore = app.nodeOutputs?.[node.id] || app.nodeOutputs?.[String(node.id)];
    if (fromStore) { push(fromStore.images); push(fromStore.gifs); push(fromStore.videos); push(fromStore.audio); }
    if (!out.length) push(node.images);
    if (!out.length && Array.isArray(node.imgs)) {
        for (const img of node.imgs) {
            try {
                const u = new URL(img.src, location.href);
                const filename = u.searchParams.get("filename");
                const type = u.searchParams.get("type");
                const sub = u.searchParams.get("subfolder") || "";
                if (filename && (type === "output" || type === "temp")) out.push({ root: type, rel: (sub ? sub + "/" : "") + filename });
            } catch {}
        }
    }
    const seen = new Set();
    return out.filter((f) => { const k = f.root + "|" + f.rel; if (seen.has(k)) return false; seen.add(k); return true; });
}

// ---------------------------------------------------------------- sidebar

function renderSidebar(el) {
    injectCSS();
    // Clicking the icon while it shows a badge goes straight to the new files.
    if (S.badge > 0) open("output");
    el.replaceChildren(h("div", { class: "mol-sidebar" },
        h("section", { class: "mol-sidecard" },
            h("h2", {}, "My Own Library"),
            h("p", {}, "Your creations, copied out of the output folder and organized with titles, categories, tags and notes."),
            h("button", { onclick: () => open("all") }, "Open library"),
            h("button", { onclick: () => open("output"), style: { background: "transparent" } }, "Browse output folder"))));
}

app.registerExtension({
    name: "MyOwnLibrary",
    commands: [
        { id: "MyOwnLibrary.Open", label: "Open My Own Library", icon: "pi pi-bookmark", function: () => open() },
    ],
    setup() {
        const manager = app.extensionManager;
        const register = manager?.sidebarTab?.registerSidebarTab ?? manager?.registerSidebarTab;
        if (register) {
            register({
                id: TAB_ID,
                icon: "pi pi-bookmark",
                title: "My Own Library",
                tooltip: "My Own Library",
                type: "custom",
                render: renderSidebar,
                // Official hook: returning true tells ComfyUI not to open the side panel,
                // so the icon opens the library window directly.
                onToggle: () => { open(S.badge > 0 ? "output" : "all"); return true; },
            });
        }
        api.addEventListener("executed", ({ detail }) => {
            const out = detail?.output || {};
            if (["images", "gifs", "videos", "audio"].some((k) => (out[k] || []).some((x) => x?.type === "output"))) onNewOutput();
        });
        api.addEventListener("execution_success", () => onNewOutput());
        refreshBadge();
    },
    // Called only for nodes placed in the graph, never once per node type,
    // so it adds nothing to the frontend's node registration at startup.
    nodeCreated(node) {
        const original = node.getExtraMenuOptions;
        node.getExtraMenuOptions = function (canvas, options) {
            const result = original?.apply(this, arguments);
            const files = nodeOutputs(this);
            if (files.length) {
                options.push(null, {
                    content: files.length > 1 ? `Add ${files.length} outputs to My Own Library` : "Add to My Own Library",
                    callback: () => addFiles(files),
                });
            }
            return result;
        };
    },
});
