/* ================= AI AGENT HUB · 控制台（简洁版） ================= */
const S = { tab:"skills", state:null, mcp:null, plugins:null, plan:null,
            q:"", qm:"", qp:"", qh:"", agent:"", driftOnly:false, sel:new Set(), busy:false,
            rev:null, lastNoticeTs:0, autoHost:true };

const $  = (s,r)=> (r||document).querySelector(s);
const $$ = (s,r)=> Array.from((r||document).querySelectorAll(s));
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmtB = n => !n ? "0 B" : n > 1048576 ? (n/1048576).toFixed(1)+" MB" : n > 1024 ? Math.round(n/1024)+" KB" : n+" B";
/* 把家目录前缀折成 ~，兼容 Windows / *nix，且不写死任何用户名 */
const HOME_RE = /^(([A-Za-z]:)?[\\\/]+Users[\\\/]+[^\\\/]+|[\\\/]+home[\\\/]+[^\\\/]+|[\\\/]+Users[\\\/]+[^\\\/]+)(?=[\\\/]|$)/;
function shortPath(p){
  const s = String(p || "");
  const m = s.match(HOME_RE);
  if (m) return "~" + s.slice(m[0].length);
  return s.length > 46 ? "…" + s.slice(-45) : s;
}

async function api(path, body){
  const opt = body ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)} : {};
  const r = await fetch(path, opt);
  const j = await r.json().catch(()=>({error:"响应解析失败"}));
  if (!r.ok) throw new Error(j.error || ("HTTP "+r.status));
  return j;
}
function toast(kind, title, msg){
  const box = $("#toasts");
  const el = document.createElement("div");
  el.className = "toast " + (kind==="err"?"bad":"ok");
  el.innerHTML = '<div><b>'+esc(title)+'</b>'+(msg?'<div class="m">'+esc(msg)+'</div>':'')+'</div>';
  box.append(el);
  setTimeout(()=>{ el.style.opacity="0"; el.style.transform="translateY(8px)"; setTimeout(()=>el.remove(),300); },
               kind==="err"?6000:3200);
}

const ICONS = {
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  box:'<path d="M20 7 12 3 4 7v10l8 4 8-4Z"/><path d="M4 7l8 4 8-4M12 21V11"/>',
  plug:'<path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0Z"/><path d="M12 18v4"/>',
  bolt:'<path d="M13 2 4 14h7l-1 8 9-12h-7Z"/>',
  refresh:'<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/>',
  search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>',
  dots:'<circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/>',
  x:'<path d="M18 6 6 18M6 6l12 12"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  trash:'<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>',
  edit:'<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>'
};

function svgPath(d){
  if (!d) return '<span style="color:#fff;font:700 10px/1 system-ui">?</span>';
  return '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+d+'</svg>';
}
const svg = (n, cls) => '<svg class="'+(cls||"ic")+'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'+(ICONS[n]||"")+'</svg>';


/* ---------------- 统一搜索组件 ---------------- */
function norm(s){ return String(s ?? "").toLowerCase(); }
/* 空格分隔 = 多关键词 AND 匹配 */
function matchQ(hay, q){
  const parts = norm(q).trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return true;
  const h = norm(hay);
  return parts.every(p => h.includes(p));
}
/* 高亮命中片段（先转义再包标签，避免注入） */
function hl(text, q){
  const t = String(text ?? "");
  const parts = String(q || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return esc(t);
  const re = new RegExp("(" + parts.map(s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "ig");
  return t.split(re).map((seg, i) => (i % 2 ? "<mark>" + esc(seg) + "</mark>" : esc(seg))).join("");
}

/* 输入是已 esc 的 HTML 片段：只在纯文本命中处包标签，标签内部不处理 */
function hlPlain(escaped, q){
  const parts = String(q || "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return escaped;
  const re = new RegExp("(" + parts.map(s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "ig");
  return String(escaped).split(/(<[^>]+>)/).map(seg =>
    seg.startsWith("<") ? seg : seg.replace(re, "<mark>$1</mark>")).join("");
}

function searchBox(id, val, ph){
  return '<div class="search">' + svg("search") +
    '<input class="field" id="' + id + '" placeholder="' + esc(ph) + '" value="' + esc(val) +
    '" spellcheck="false" autocomplete="off">' +
    (val ? '<button class="clear" data-act="clear-q" data-target="' + id + '" title="清除">' + svg("x") + '</button>' : '') +
  '</div>';
}
/* 只重绘列表容器，搜索框本身不动 -> 输入焦点不丢 */
function bindSearch(inputId, render){
  const el = document.getElementById(inputId);
  if (!el) return;
  el.addEventListener("input", () => {
    const box = el.closest(".search");
    if (box){
      let b = box.querySelector(".clear");
      if (el.value && !b){
        b = document.createElement("button");
        b.className = "clear"; b.title = "清除";
        b.dataset.act = "clear-q"; b.dataset.target = inputId;
        b.innerHTML = '<svg class="ic" viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>';
        el.after(b);
      } else if (!el.value && b) b.remove();
    }
    render();
  });
}
function updCount(sel, shown, total){
  const c = document.querySelector(sel);
  if (!c) return;
  c.dataset.shown = shown; c.dataset.total = total;
  c.textContent = total ? (shown + " / " + total + " 项") : "";
}

/* ---------------- 外壳 ---------------- */
const TABS = [
  {id:"skills", label:"技能 SKILL",  icon:"grid"},
  {id:"mcp",    label:"MCP 服务",    icon:"plug"},
  {id:"plugin", label:"插件 PLUGIN", icon:"box"},
  {id:"hub",    label:"收敛中心",    icon:"bolt"},
];
function tabCount(id){
  if (!S.state) return 0;
  if (id==="skills") return S.state.stats.skills;
  if (id==="hub")    return S.state.stats.drift;
  if (id==="mcp")    return S.mcp ? S.mcp.rows.length : 0;
  if (id==="plugin") return S.plugins ? S.plugins.total : 0;
  return 0;
}
function renderShell(){
  $("#nav").innerHTML = TABS.map(t =>
    '<button class="nav-i" data-act="tab" data-id="'+t.id+'" aria-current="'+(S.tab===t.id)+'">'+
      svg(t.icon)+'<span class="t">'+t.label+'</span><span class="cnt">'+tabCount(t.id)+'</span></button>').join("");
  if (S.state){
    $("#foot-canon").textContent = S.state.canonical_dir;
    const s = S.state.stats;
    $("#foot-state").textContent = s.hosted
      ? "真源 "+s.hosted+" · 联接 "+s.linked+" · 副本 "+s.real_copies
      : "尚未收敛（真源为空）";
  }
}
function setHeader(title, sub, actions){
  $("#title").textContent = title;
  $("#subtitle").textContent = sub;
  $("#actions").innerHTML = actions || "";
}
async function switchTab(id){
  S.tab = id; S.sel.clear();
  history.replaceState(null, "", "#"+id);
  renderShell(); await render();
}
async function refreshAll(fresh){
  $("#view").innerHTML = '<div class="empty"><b>正在扫描磁盘…</b>读取各 agent 的技能目录与配置</div>';
  S.state = await api("/api/state"+(fresh?"?fresh=1":""));
  renderShell(); await render();
}
const HEADERS = {
  skills: ["技能分发", "单一真源在 D 盘，各 agent 目录用目录联接指向它。点行首方框托管，点方格单独为某个 agent 开关。"],
  mcp:    ["MCP 服务", "Hub 持有一份主列表，按各家原生格式分发：Codex 写 config.toml，其余写各自 mcp.json。写入前自动备份。"],
  plugin: ["插件盘点", "各工具插件格式互不兼容（清单/缓存/签名机制不同），此页只做跨 agent 盘点与对照，不做写入。"],
  hub:    ["收敛中心", "把散落在各 agent 的副本合并成单一真源：先备份 zip，再删副本，最后就地建目录联接。"],
};
async function render(keepScroll){
  const v = $("#view");
  /* 页面有两层滚动：外层 #view 与表格容器 .mx-wrap，重建时都要保住 */
  const oldWrap = v.querySelector(".mx-wrap");
  const y  = keepScroll ? v.scrollTop : 0;
  const wy = keepScroll && oldWrap ? oldWrap.scrollTop : 0;
  const wx = keepScroll && oldWrap ? oldWrap.scrollLeft : 0;
  const H = HEADERS[S.tab];
  const auto = S.autoHost !== false;
  const btnAdd = S.tab==="skills"
    ? '<button class="btn primary" data-act="add-skill">'+svg("plus")+'添加技能</button>' : "";
  const btnAuto = (S.tab==="skills"||S.tab==="mcp")
    ? '<button class="btn '+(auto?"":"ghost")+'" data-act="toggle-auto" title="外部 agent 新增技能/配置时自动同步到本界面">'
      + svg("refresh")+'自动同步 '+(auto?"开":"关")+'</button>' : "";
  const btnRescan = '<button class="btn ghost" data-act="rescan">'+svg("refresh")+'重新扫描</button>';
  const btnImport = (S.tab==="skills" && S.state && S.state.stats.unhosted)
    ? '<button class="btn" data-act="import-all" title="把各 agent 里散落、还没进真源的技能一次性收进真源并铺满">'
      + svg("bolt")+'一键导入 ('+S.state.stats.unhosted+')</button>' : "";
  setHeader(H[0], H[1], btnAuto + btnImport + btnAdd + btnRescan);
  if (S.tab==="skills")      v.innerHTML = skillsHTML();
  else if (S.tab==="mcp")    v.innerHTML = await mcpHTML();
  else if (S.tab==="plugin") v.innerHTML = await pluginsHTML();
  else                       v.innerHTML = hubHTML();
  bindView();
  bindTabSearch();
  v.scrollTop = y;
  const nw = v.querySelector(".mx-wrap");
  if (nw){ nw.scrollTop = wy; nw.scrollLeft = wx; }
}

/* ---------------- 视图 · 技能 ---------------- */
function retireDirs(){
  const s = new Set();
  for (const a of S.state.agents) for (const d of a.dirs) if (d.retire) s.add(d.path.toLowerCase());
  return s;
}
function cellState(row, agentId){
  const RD = retireDirs();
  const hits = Object.values(row.locations).filter(l => l.agent === agentId && !RD.has(String(l.dir).toLowerCase()));
  if (!hits.length) return {s:"na"};
  const linked = hits.find(l => l.kind==="junction" || l.kind==="symlink");
  const copy   = hits.find(l => l.kind==="real");
  const diff   = hits.some(l => l.kind==="real" && row.canonical && !l.matches_canonical);
  const base   = linked ? "linked" : "copy";
  return {s: diff ? base+" diff" : base, kind:(linked||copy).kind, path:(linked||copy).path,
          linked:!!linked, copy:!!copy, diff};
}
function skillsHTML(){
  const st = S.state, s = st.stats;
  const cards = [
    ["识别到的技能", s.skills, ""],
    ["已进真源",     s.hosted, s.hosted?"ok":"warn"],
    ["目录联接",     s.linked, ""],
    ["实体副本",     s.real_copies, s.real_copies?"warn":""],
    ["版本漂移",     s.drift,  s.drift?"bad":"ok"],
    ["重复占用",     fmtB(s.bytes_wasted), ""],
  ].map(([l,v,k]) => '<div class="stat"><b>'+esc(v)+'</b><span>'+esc(l)+
      (k?' <span class="chip '+k+'">'+(k==="bad"?"需处理":k==="warn"?"待收敛":"正常")+'</span>':'')+'</span></div>').join("");

  const agTh = st.agents.map(a =>
    '<span class="th-ag" title="'+esc(a.name)+'"><span class="agicon" style="background:'+a.color+'">'+svgPath(a.icon)+
    '</span><em>'+esc(a.name.trim().split(/[\/（(]/)[0])+'</em><b>'+a.skill_count+'</b></span>').join("");

  const opts = ['<option value="">全部</option>'].concat(st.agents.map(a =>
    '<option value="'+a.id+'"'+(S.agent===a.id?" selected":"")+'>'+esc(a.name)+'</option>')).join("");

  return ''+
  '<div class="toolbar-top">'+
    '<div class="tabs"><button class="tab'+(S.tab==="skills"?" on":"")+'" disabled>已托管 '+s.hosted+'</button>'+
      '<button class="tab" data-act="tab" data-id="hub">待收敛 '+s.unhosted+'</button></div>'+
    searchBox("q", S.q, "搜索技能：名称 / 描述 / 路径 / agent，空格分隔多词")+
    '<span class="hit" id="qhit"></span>'+
  '</div>'+
  '<div class="stats">'+cards+'</div>'+
  '<div class="panel">'+
    '<div class="toolbar">'+
      '<label class="cb'+(allChecked()?" on":"")+'" data-act="sel-all" role="checkbox" aria-checked="'+allChecked()+'"></label>'+
      '<select class="mini" id="fagent">'+opts+'</select>'+
      '<label class="mini-l"><input type="checkbox" id="fdrift"'+(S.driftOnly?" checked":"")+'> 仅看版本漂移</label>'+
      '<div class="th-agents">'+agTh+'</div>'+
    '</div>'+
    '<div class="mx-wrap" id="mxwrap">'+matrixHTML()+'</div>'+
    '<div class="hscroll" id="hscroll"><div class="hscroll-thumb"></div></div>'+
    '<div class="legend">'+
      '<span><i style="background:#10b981"></i>联接指向真源</span>'+
      '<span><i style="background:#f59e0b"></i>实体副本（可收敛）</span>'+
      '<span><i style="background:#ef4444"></i>内容与真源不一致</span>'+
      '<span><i style="background:#d1d5db"></i>未安装</span>'+
    '</div>'+
  '</div>';
}
function allChecked(){
  const list = visibleSkills().filter(r => !r.builtin);
  return list.length>0 && list.every(r => r.canonical);
}
function skillHay(r){
  const bits = [r.name, r.meta && r.meta.desc, r.meta && r.meta.name];
  for (const l of Object.values(r.locations || {})){
    bits.push(l.path); bits.push(l.agent); bits.push(l.kind);
  }
  return norm(bits.filter(Boolean).join(" "));
}
function visibleSkills(){
  let list = S.state.skills.slice();
  const q = S.q.trim();
  if (q) list = list.filter(r => matchQ(skillHay(r), q));
  if (S.agent)     list = list.filter(r => r.agents_present.includes(S.agent));
  if (S.driftOnly) list = list.filter(r => r.drift);
  return list;
}
function matrixHTML(){
  const st = S.state, list = visibleSkills();
  if (!list.length) return '<div class="empty"><b>'+(S.q||S.agent||S.driftOnly ? "没有匹配的技能" : "还没有技能")+'</b>'+
    (S.q||S.agent||S.driftOnly ? '当前条件：'+esc([S.q&&('“'+S.q+'”'), S.agent, S.driftOnly&&"仅漂移"].filter(Boolean).join(" · "))+'<br>换个关键词，或点搜索框右侧 × 清除' : '点右上「添加技能」导入')+'</div>';
  const head = '<tr><th><span class="nm">技能</span></th>'+
    st.agents.map(a=>'<th class="agh" title="'+esc(a.name)+'"><span class="agicon" style="background:'+a.color+'">'+
      svgPath(a.icon)+'</span><em>'+esc(a.name.trim().split(/[\/（(]/)[0])+'</em></th>').join("")+'<th class="op"></th></tr>';
  const body = list.map(rowHTML).join("");
  return '<table class="mx"><thead>'+head+'</thead><tbody>'+body+'</tbody></table>';
}


function rowHTML(r){
  const st = S.state;
  const cells = st.agents.map(a => {
    const c = cellState(r, a.id);
    const ro = a.read_only;
    const title = c.s==="na" ? a.name+" · 未安装"
      : a.name+" · "+(c.linked?"联接":c.copy?"实体副本":"")+(c.diff?" · 内容与真源不同":"")+"\n"+c.path;
    return '<td><span class="cell '+c.s+(ro?" ro":"")+'" data-act="cell" data-sk="'+esc(r.name)+
           '" data-ag="'+a.id+'" data-on="'+(c.s!=="na"&&c.linked)+'" title="'+esc(title)+'"></span></td>';
  }).join("");
  return '<tr data-row="'+esc(r.name)+'">'+
    '<td class="skname"><div class="skline">'+
      '<label class="cb'+(r.canonical?" on":(r.builtin?" builtin":" pending"))+'" data-act="host" data-sk="'+esc(r.name)+
        '" title="'+(r.canonical?"已托管：点击从真源移出（内容保留，可恢复）"
                     :(r.builtin?"该 agent 的内置技能，受保护不托管":(r.source_only?"来自只读来源：点击收进真源并分发（原目录保持不动）":"未托管：点击收进真源")))+'"></label>'+
      '<div class="sktxt" data-act="detail" data-sk="'+esc(r.name)+'">'+
        '<b>'+hl(r.name, S.q)+'</b>'+
        (r.drift?'<span class="tag bad">'+r.variant_count+' 个版本</span>':'')+
        (r.ignored?'<span class="tag">已停用</span>':'')+
        (!r.canonical && r.builtin?'<span class="tag" title="agent 自带，不参与托管">内置</span>':'')+
        (!r.canonical && r.source_only?'<span class="tag" title="只读来源，可单向取用">来源</span>':'')+
        '<span class="desc">'+hl((r.meta.desc||"").slice(0,90), S.q)+'</span>'+
        '<span class="src">· '+fmtB(r.bytes_total)+'</span>'+
      '</div></div></td>'+cells+
    '<td class="op"><span class="cell more" data-act="detail" data-sk="'+esc(r.name)+'">'+svg("dots")+'</span></td></tr>';
}

/* 局部更新一行：不重建整页，因此不会跳回顶部 */
function applyRow(row){
  if (!row || !row.name) return;
  const i = S.state.skills.findIndex(x => x.name === row.name);
  if (i >= 0) S.state.skills[i] = row; else S.state.skills.push(row);
  const tr = document.querySelector('tr[data-row="'+CSS.escape(row.name)+'"]');
  if (tr) tr.outerHTML = rowHTML(row);
  refreshCounters();
}

/* 仅用本地数据重算计数，无网络请求 */
function refreshCounters(){
  const sk = S.state.skills;
  const hosted = sk.filter(r => r.canonical && !r.ignored).length;
  const unhosted = sk.filter(r => !r.canonical && !r.ignored && !r.protected).length;
  const drift = sk.filter(r => r.drift && !r.ignored).length;
  let linked = 0, copies = 0;
  const perAgent = {};
  for (const r of sk){
    for (const l of Object.values(r.locations)){
      if (l.role === "source" || l.retire) continue;
      if (l.kind === "real") copies++;
      else if (l.kind === "junction" || l.kind === "symlink") linked++;
    }
    for (const a of r.agents_present || []) perAgent[a] = (perAgent[a]||0) + 1;
  }
  for (const a of S.state.agents){ a.skill_count = perAgent[a.id] || 0; }
  const S2 = S.state.stats;
  S2.hosted = hosted; S2.unhosted = unhosted; S2.drift = drift;
  S2.linked = linked; S2.real_copies = copies; S2.skills = sk.length;
  S2.bytes_wasted = sk.filter(r=>r.drift).reduce((s,r)=>s+(r.bytes_total||0),0);
  $$("#view .stat").forEach(el => {
    const lab = el.querySelector("span"); if (!lab) return;
    const k = lab.textContent.trim();
    const map = {"识别到的技能":S2.skills,"已进真源":S2.hosted,"目录联接":S2.linked,
                 "实体副本":S2.real_copies,"版本漂移":S2.drift,"重复占用":fmtB(S2.bytes_wasted)};
    if (k in map) el.querySelector("b").textContent = map[k];
  });
  const t1 = document.querySelector(".tabs .tab");
  if (t1) t1.textContent = "已托管 " + hosted;
  const t2 = document.querySelectorAll(".tabs .tab")[1];
  if (t2) t2.textContent = "待收敛 " + unhosted;
  $$(".th-agents .th-ag b").forEach((b,i) => {
    const a = S.state.agents[i]; if (a) b.textContent = a.skill_count;
  });
  renderShell();
}

/* ---------------- 交互绑定 ---------------- */
function bindHScroll(){
  const wrap = $("#mxwrap"), bar = $("#hscroll");
  if (!wrap || !bar) return;
  const thumb = bar.querySelector(".hscroll-thumb");
  function sync(){
    const sw = wrap.scrollWidth, cw = wrap.clientWidth;
    if (sw <= cw + 2){ bar.style.display = "none"; return; }
    bar.style.display = "block";
    const tw = Math.max(40, cw * cw / sw);
    thumb.style.width = tw + "px";
    thumb.style.transform = "translateX(" + (wrap.scrollLeft / (sw - cw)) * (bar.clientWidth - tw) + "px)";
  }
  wrap.addEventListener("scroll", sync);
  window.addEventListener("resize", sync);
  try { new ResizeObserver(sync).observe(wrap); } catch(e){}
  let drag = null;
  thumb.addEventListener("pointerdown", e => {
    drag = {x: e.clientX, left: wrap.scrollLeft}; thumb.setPointerCapture(e.pointerId); e.preventDefault();
  });
  thumb.addEventListener("pointermove", e => {
    if (!drag) return;
    const sw = wrap.scrollWidth, cw = wrap.clientWidth;
    const tw = Math.max(40, cw * cw / sw);
    const ratio = (e.clientX - drag.x) / (bar.clientWidth - tw);
    wrap.scrollLeft = drag.left + ratio * (sw - cw);
  });
  const end = () => { drag = null; };
  thumb.addEventListener("pointerup", end); thumb.addEventListener("pointercancel", end);
  bar.addEventListener("pointerdown", e => {
    if (e.target !== bar) return;
    const r = bar.getBoundingClientRect(), cw = wrap.clientWidth, sw = wrap.scrollWidth;
    const center = (e.clientX - r.left) / r.width;
    wrap.scrollTo({left: (sw - cw) * center, behavior: "smooth"});
  });
  sync();
}
function refreshSkillList(){
  $("#mxwrap").innerHTML = matrixHTML();
  updCount("#qhit", visibleSkills().length, S.state.skills.length);
}
function bindView(){
  bindHScroll();
  updCount("#qhit", visibleSkills().length, S.state.skills.length);
  const fa = $("#fagent"); if (fa) fa.addEventListener("change", e => { S.agent = e.target.value; refreshSkillList(); });
  const fd = $("#fdrift"); if (fd) fd.addEventListener("change", e => { S.driftOnly = e.target.checked; refreshSkillList(); });
}
function rerenderSkills(){ $("#view").innerHTML = skillsHTML(); bindView(); }

document.addEventListener("click", async ev => {
  const t = ev.target.closest("[data-act]");
  if (!t) return;
  const act = t.dataset.act;

  if (act === "tab"){ switchTab(t.dataset.id); return; }
  if (act === "rescan"){ S.rev = null; toast("ok","重新扫描","正在读取磁盘…"); await refreshAll(true); return; }
  if (act === "toggle-auto"){
    S.autoHost = !S.autoHost;
    await api("/api/autohost", {on: S.autoHost});
    toast("ok", "自动同步已" + (S.autoHost?"开启":"关闭"), S.autoHost?"外部新增技能会自动收进真源并铺满各 agent":"需手动点重新扫描");
    render(); return;
  }
  if (act === "add-skill"){ openAddDialog(); return; }
  if (act === "import-all"){ doImportAll(t); return; }
  if (act === "clear-q"){
    const id = t.dataset.target, el = document.getElementById(id);
    if (!el) return;
    el.value = ""; el.dispatchEvent(new Event("input")); el.focus();
    const btn = el.closest(".search") && el.closest(".search").querySelector(".clear");
    if (btn) btn.remove();
    return;
  }
  if (act === "add-skill-go"){ doAddSkill(); return; }

  if (act === "cell"){
    const sk = t.dataset.sk, ag = t.dataset.ag, on = t.dataset.on === "true";
    if (t.classList.contains("ro")) return toast("bad","只读来源",(S.state.agents.find(a=>a.id===ag)||{}).name+" 是只读来源，不参与分发");
    const row = S.state.skills.find(x => x.name === sk);
    const want = !on;                       // 目标状态：true=装上，false=收回
    if (!want && !row.canonical)
      return toast("bad","无需收回","该技能不在这个 agent 上");
    await doToggle(sk, ag, want); return;
  }
  if (act === "host"){
    const sk = t.dataset.sk;
    const row = S.state.skills.find(x => x.name === sk);
    if (row && !row.canonical && row.builtin)
      return toast("bad", "内置技能", sk + " 是 agent 自带的受保护技能，不纳入真源托管");
    t.classList.add("busy");
    try{
      if (row.canonical){
        if (!confirm("把「"+sk+"」从真源移出？\n\n内容会保留在 _hub_disabled，所有联接会断开，可随时恢复。")) return;
        const r = await api("/api/skill/unhost", {skill:sk});
        r.ok ? toast("ok","已移出真源", sk+" · 断开 "+r.removed_links+" 处联接") : toast("bad","失败", r.msg);
        if (r.row) applyRow(r.row); else refreshCounters();
      } else {
        const r = await api("/api/skill/host", {skill:sk});
        r.ok ? toast("ok","已托管 "+sk, ((r.actions||[]).length)+" 个 agent 已就绪") : toast("bad","托管失败", r.msg);
        if (r.row) applyRow(r.row); else refreshCounters();
      }
    } finally { t.classList.remove("busy"); }
    return;
  }
  if (act === "detail"){ openDrawer(t.dataset.sk); return; }
  if (act === "close-drawer"){ closeDrawer(); return; }
  if (act === "host-push-all"){
    const sk = t.dataset.sk;
    const agents = S.state.agents.filter(a => !a.read_only);
    let n = 0;
    let last = null;
    for (const a of agents){ const r = await api("/api/skill/agent", {skill:sk, agent:a.id, on:true}); if (r.ok) n++; if (r.row) last = r.row; }
    toast("ok","已推送到全部 agent", sk+" → "+n+" 个目录");
    closeDrawer();
    if (last) applyRow(last); else refreshCounters();
    return;
  }
  if (act === "mcp-toggle-one"){
    const {agent, name, on} = t.dataset;
    const r = await api("/api/mcp/one", {agent, name, on: on !== "true"});
    r.ok ? toast("ok",(on==="true"?"已移除 ":"已写入 ")+name+" → "+agent, r.msg) : toast("bad", agent, r.msg);
    S.mcp = await api("/api/mcp"); $("#view").innerHTML = await mcpHTML(); return;
  }
  if (act === "mcp-push"){
    const r = await api("/api/mcp/push", {name:t.dataset.name});
    const bad = (r.results||[]).filter(x => !x.ok);
    bad.length ? toast("bad","部分失败", bad.map(b => b.agent+": "+b.msg).join(" | "))
               : toast("ok","已推送到全部 agent", (r.results||[]).map(x=>x.agent).join(", "));
    S.mcp = await api("/api/mcp"); $("#view").innerHTML = await mcpHTML(); return;
  }
  if (act === "mcp-global"){
    const {name, on} = t.dataset;
    await api("/api/mcp/global", {name, on: on !== "true"});
    await api("/api/mcp/push", {name});
    toast("ok",(on==="true"?"已停用 ":"已启用 ")+name,"并推送到各 agent");
    S.mcp = await api("/api/mcp"); $("#view").innerHTML = await mcpHTML(); return;
  }
  if (act === "mcp-del"){
    if (!confirm("从 Hub 主列表移除 "+t.dataset.name+"？\n\n不会改动各 agent 已有的配置。")) return;
    await api("/api/mcp/save", {name:t.dataset.name, remove:true});
    toast("ok","已移除", t.dataset.name);
    S.mcp = await api("/api/mcp"); $("#view").innerHTML = await mcpHTML(); renderShell(); return;
  }
  if (act === "mcp-editor"){
    const box = $("#ed-"+t.dataset.name.replace(/[^a-z0-9_-]/gi,"_"));
    if (!box) return;
    box.style.display = box.style.display === "none" ? "block" : "none"; return;
  }
  if (act === "mcp-save"){
    const name = t.dataset.name;
    const cfg = {};
    $$("#ed-"+name.replace(/[^a-z0-9_-]/gi,"_")+" [data-k]").forEach(i => {
      const v = i.value.trim(); if (!v) return;
      cfg[i.dataset.k] = i.dataset.k === "args" ? v.split(/\s+/) : (i.dataset.k==="timeout" ? (Number(v)||v) : v);
    });
    await api("/api/mcp/save", {name, old_name:name, config:cfg});
    toast("ok","已保存主配置", name);
    S.mcp = await api("/api/mcp"); $("#view").innerHTML = await mcpHTML(); return;
  }
  if (act === "mcp-add"){
    const nm = $("#new-name").value.trim();
    if (!nm) return toast("bad","名称必填","给服务器起个英文标识");
    const cfg = {};
    ["type","command","url","description"].forEach(k => { const v = $("#new-"+k).value.trim(); if (v) cfg[k] = v; });
    const args = $("#new-args").value.trim(); if (args) cfg.args = args.split(/\s+/);
    await api("/api/mcp/save", {name:nm, config:cfg});
    toast("ok","已加入主列表", nm+" · 点「推送」写入各 agent");
    S.mcp = await api("/api/mcp"); $("#view").innerHTML = await mcpHTML(); renderShell(); return;
  }
  if (act === "mcp-seed"){
    await api("/api/mcp/seed"); S.mcp = await api("/api/mcp");
    $("#view").innerHTML = await mcpHTML(); renderShell(); toast("ok","已重新吸收","从 Codex 现有配置同步"); return;
  }
  if (act === "plan"){ await loadPlan(); return; }
  if (act === "apply"){ startApply(); return; }
  if (act === "mcp-toggle-cell"){
    const {agent, name, on} = t.dataset;
    const r = await api("/api/mcp/one", {agent, name, on: on !== "true"});
    r.ok ? toast("ok",(on==="true"?"已移除 ":"已写入 ")+name+" → "+agent, r.msg) : toast("bad", agent, r.msg);
    S.mcp = await api("/api/mcp"); $("#view").innerHTML = await mcpHTML(); return;
  }
});
async function doToggle(sk, ag, on){
  const btn = document.querySelector('tr[data-row="'+CSS.escape(sk)+'"] .cell[data-ag="'+ag+'"]');
  if (btn) btn.classList.add("loading");
  try{
    const r = await api("/api/skill/agent", {skill:sk, agent:ag, on});
    if (!r.ok && r.msg) toast("bad", sk, r.msg);
    else if (!r.detail || !r.detail.length) toast("bad","无写入目标","该 agent 没有可分发的技能目录");
    else toast("ok",(on?"已分发 ":"已收回 ")+sk,
      (r.promoted ? "（已先收进真源）" : "") + r.detail.map(d => d.msg).join("; "));
    if (r.row) applyRow(r.row);
  }finally{
    if (btn) btn.classList.remove("loading");
  }
}


async function doImportAll(btn){
  const n = S.state.stats.unhosted;
  if (!confirm("一键导入 " + n + " 个散落技能？\n\n每个技能会：择优收进真源 -> 原有副本先压成 zip 备份 -> 就地改为目录联接 -> 铺满所有 agent。")) return;
  if (btn) btn.classList.add("busy");
  try{
    const r = await api("/api/import/all", {});
    const okN = (r.hosted||[]).length, bad = (r.failed||[]).length;
    toast(bad?"bad":"ok", "导入完成", okN + " 个技能已托管"
      + (bad ? ("，" + bad + " 个失败：" + r.failed.map(f=>f.name).join(", ")) : ""));
    S.rev = null;
    await refreshAll(true);
  }catch(e){ toast("bad","导入失败", e.message); }
  finally{ if (btn) btn.classList.remove("busy"); }
}

/* ---------------- 添加技能对话框 ---------------- */
function openAddDialog(){
  $("#overlay").innerHTML =
    '<div class="scrim" data-act="close-drawer"></div>'+
    '<div class="modal">'+
      '<div class="modal-hd"><h2>添加技能</h2><button class="x" data-act="close-drawer">'+svg("x")+'</button></div>'+
      '<div class="modal-bd">'+
        '<p class="tip">把技能文件夹（含 SKILL.md）或 zip 包的<b>绝对路径</b>粘贴进来。可以是从别的 agent 目录、下载目录、或别人发给你的路径。'+
        '<div class="field-row"><label>技能目录 / zip 路径</label>'+
          '<input class="field" id="addpath" placeholder="例如 D:\\downloads\\my-skill  或  ...\\my-skill.zip" spellcheck="false"></div>'+
        '<label class="mini-l chk"><input type="checkbox" id="addhost" checked> 导入后自动托管并铺满所有 agent</label>'+
        '<div class="hint-box">提示：也可以直接把文件夹放进真源目录 <code>'+esc(S.state.canonical_dir)+'</code>，界面会自动检测到（开着自动同步时会自动铺满）。</div>'+
      '</div>'+
      '<div class="modal-ft"><button class="btn" data-act="close-drawer">取消</button>'+
        '<button class="btn primary" data-act="add-skill-go">'+svg("plus")+'导入</button></div>'+
    '</div>';
  setTimeout(()=>{ const i=$("#addpath"); if(i) i.focus(); }, 50);
}
async function doAddSkill(){
  const path = $("#addpath").value.trim();
  if (!path) return toast("bad","请输入路径","技能目录或 zip 的绝对路径");
  const host = $("#addhost").checked;
  closeDrawer();
  toast("ok","导入中…", path);
  try{
    const r = await api("/api/skill/add", {path, host});
    if (r.added && r.added.length) toast("ok","已导入 "+r.added.length+" 个技能", r.added.join(", "));
    if (r.failed && r.failed.length) toast("bad","部分失败", r.failed.join(" | "));
    if (!r.added || !r.added.length) toast("bad","导入失败", r.msg || "未找到 SKILL.md");
    S.rev = null; await refreshAll(true);
  }catch(e){ toast("bad","导入失败", e.message); }
}

/* ---------------- 抽屉 ---------------- */
function openDrawer(name){
  const row = S.state.skills.find(x => x.name === name); if (!row) return;
  history.replaceState(null, "", "#skill:"+encodeURIComponent(name));
  $("#overlay").innerHTML =
    '<div class="scrim" data-act="close-drawer"></div>'+
    '<div class="drawer">'+
      '<div class="drawer-hd"><div><h2>'+esc(name)+'</h2>'+
        '<div class="chips">'+
          (row.canonical?'<span class="chip ok">真源已托管</span>':'<span class="chip warn">未托管</span>')+
          (row.drift?'<span class="chip bad">'+row.variant_count+' 个版本</span>':'<span class="chip ok">版本一致</span>')+
          '<span class="chip">'+fmtB(row.bytes_total)+'</span>'+
        '</div></div>'+
        '<button class="x" data-act="close-drawer">'+svg("x")+'</button></div>'+
      '<div class="drawer-bd" id="dbody"><div class="empty">加载中…</div></div>'+
    '</div>';
  api("/api/skill/detail?name="+encodeURIComponent(name))
    .then(d => drawDrawer($("#dbody"), row, d))
    .catch(e => { $("#dbody").innerHTML = '<div class="empty"><b>详情读取失败</b>'+esc(e.message)+'</div>'; });
}
function closeDrawer(){ $("#overlay").innerHTML = ""; history.replaceState(null, "", "#"+S.tab); }
function drawDrawer(body, row, d){
  const A = S.state.agents;
  const locs = Object.entries(row.locations).map(([vid,l]) => {
    const a = A.find(x => x.id === l.agent) || {name:l.agent, color:"#9ca3af"};
    return '<div class="row"><span class="agicon" style="background:'+a.color+'">'+svgPath(a.icon)+'</span>'+
      '<span class="rname">'+esc(a.name)+'</span>'+
      '<span class="rdesc" title="'+esc(l.path)+'">'+esc(shortPath(l.path))+'</span>'+
      '<span class="ract"><span class="chip '+(l.kind==="real"?"warn":"ok")+'">'+(l.kind==="real"?"实体副本":"联接")+'</span>'+
      (row.canonical?'<span class="chip '+(l.matches_canonical?"ok":"bad")+'">'+(l.matches_canonical?"与真源一致":"内容不同")+'</span>':'')+
      '</span></div>';
  }).join("");
  body.innerHTML =
    '<dl class="kv">'+
      '<dt>描述</dt><dd class="t">'+esc(row.meta.desc || d.meta.desc || "—")+'</dd>'+
      '<dt>真源</dt><dd>'+(row.canonical ? esc(S.state.canonical_dir+"\\"+row.name) : "（尚未导入）")+'</dd>'+
      '<dt>文件数</dt><dd>'+esc(row.files ?? (d.files||[]).length)+'</dd>'+
      '<dt>版本指纹</dt><dd>'+esc(row.canonical_hash || (Object.values(row.locations)[0]||{}).hash || "—")+'</dd>'+
    '</dl>'+
    (row.canonical ? '<div class="drawer-actions">'+
        '<button class="btn primary" data-act="host-push-all" data-sk="'+esc(row.name)+'">推送到全部 agent</button>'+
        '<button class="btn" data-act="host" data-sk="'+esc(row.name)+'">从真源移出</button></div>' :
        '<div class="drawer-actions"><button class="btn primary" data-act="host" data-sk="'+esc(row.name)+'">收进真源（自动备份）</button></div>')+
    '<div class="sec-title"><h2>出现位置</h2></div><div class="rows">'+locs+'</div>'+
    (d.skill_md ? '<div class="sec-title"><h2>SKILL.md</h2></div><pre class="code">'+esc(d.skill_md.slice(0,20000))+'</pre>' : '')+
    ((d.files||[]).length ? '<div class="sec-title"><h2>文件树（'+d.files.length+'）</h2></div><div class="flist">'+
        d.files.slice(0,90).map(f => '<span>'+esc(f)+'</span>').join("")+'</div>' : '');
}

/* ---------------- 视图 · MCP ---------------- */
const CFG_FIELDS = [["type","类型"],["command","命令"],["args","参数（空格分隔）"],["url","URL"],["timeout","超时 ms"],["description","说明"]];
function mcpShown(){
  if (!S.mcp) return 0;
  return S.mcp.rows.filter(r => matchQ(mcpHay(r, S.mcp.agents), S.qm)).length;
}
function mcpHay(r, A){
  const bits = [r.name, r.config && r.config.command, ((r.config && r.config.args) || []).join(" "),
                r.config && r.config.url, r.config && r.config.description,
                r.config && r.config.type, r.origin];
  for (const a of (A || [])) if (r.agents[a.id]) bits.push(a.name, a.path, a.id);
  return norm(bits.filter(Boolean).join(" "));
}
function mcpRowsHTML(){
  const m = S.mcp, A = m.agents;
  return m.rows.filter(r => matchQ(mcpHay(r, A), S.qm)).map(r => {
    const eid = "ed-" + r.name.replace(/[^a-z0-9_-]/gi, "_");
    const cells = A.map(a => {
      const has = r.agents[a.id];
      return '<td><span class="cell ' + (has ? "linked" : "na") + '" data-act="mcp-toggle-cell" data-agent="' + a.id +
             '" data-name="' + esc(r.name) + '" data-on="' + has + '" title="' + esc(a.name) + " · " +
             (has ? "已配置" : "未配置") + "\n" + esc(a.path) + '"></span></td>';
    }).join("");
    const cmd = r.config.command ? esc(r.config.command + " " + ((r.config.args) || []).join(" ")) : esc(r.config.url || "—");
    return '<tr data-mcp="' + esc(r.name) + '"><td class="skname"><div class="skline">' +
           '<label class="cb' + (r.global_off ? "" : " on") + '" data-act="mcp-global" data-name="' + esc(r.name) +
             '" data-on="' + (!r.global_off) + '" title="' + (r.global_off ? "已停用：点击启用" : "已启用：点击停用") + '"></label>' +
           '<div class="sktxt"><b>' + hl(r.name, S.qm) + '</b><span class="desc">' + hlPlain(cmd, S.qm) + '</span>' +
             (r.origin ? '<span class="tag" title="由 ' + esc(r.origin) + ' 的配置发现并纳入管理">来自 ' + esc(r.origin) + '</span>' : '') +
           '</div></div></td>' +
           cells +
           '<td class="op"><span class="cell more" data-act="mcp-push" data-name="' + esc(r.name) + '" title="推送到全部 agent">' + svg("bolt") + '</span>' +
           '<span class="cell more" data-act="mcp-editor" data-name="' + esc(r.name) + '" title="编辑">' + svg("edit") + '</span>' +
           '<span class="cell more danger" data-act="mcp-del" data-name="' + esc(r.name) + '" title="移除">' + svg("trash") + '</span></td></tr>' +
           '<tr><td colspan="' + (A.length + 2) + '"><div class="editor" id="' + eid + '" style="display:none">' +
             CFG_FIELDS.map(([k, l]) => '<label class="edf"><span>' + l + '</span><input class="field" data-k="' + k + '" value="' +
               esc(Array.isArray(r.config[k]) ? r.config[k].join(" ") : (r.config[k] ?? "")) + '"></label>').join("") +
             '<div class="edrow"><button class="btn primary sm" data-act="mcp-save" data-name="' + esc(r.name) + '">保存主配置</button></div>' +
           '</div></td></tr>';
  }).join("");
}
function mcpHeads(A){
  return A.map(a => '<th class="agh" title="' + esc(a.name) + '"><span class="agicon" style="background:' + a.color + '">' +
    svgPath(a.icon) + '</span><em>' + esc(a.name.trim().split(/[\/（(]/)[0]) + '</em></th>').join("");
}
async function mcpHTML(){
  S.mcp = S.mcp || await api("/api/mcp");
  const m = S.mcp, A = m.agents, heads = mcpHeads(A);
  const nShown = mcpShown();
  return '' +
  '<div class="toolbar-top">' +
    '<div class="tabs"><button class="tab on">服务器 ' + m.rows.length + '</button><button class="tab">配置点 ' + A.length + '</button></div>' +
    searchBox("qm", S.qm, "搜索 MCP：名称 / 命令 / 参数 / URL / 来源，空格分隔多词") +
    '<span class="hit" id="qmhit"></span>' +
    '<button class="btn" data-act="mcp-seed">' + svg("refresh") + '从 Codex 吸收</button>' +
  '</div>' +
  (!m.rows.length ? '<div class="panel"><div class="empty"><b>主列表为空</b>点右上「从 Codex 吸收」把现有 MCP 服务器收进 Hub</div></div>'
   : !nShown ? '<div class="panel"><div class="empty"><b>没有匹配的服务器</b>「' + esc(S.qm) + '」不在任何名称 / 命令 / 参数 / 路径里</div></div>'
   : '' +
  '<div class="panel"><div class="toolbar"><span class="mini-l">服务器 × agent 分发 · 点方格单独增删，⚡ 一键推送全部</span><div class="th-agents">' + heads + '</div></div>' +
    '<div class="mx-wrap" id="mcpwrap">' + mcpListHTML() + '</div>' +
    '<div class="legend"><span><i style="background:#10b981"></i>该 agent 已配置</span><span><i style="background:#d1d5db"></i>未配置</span>' +
    '<span style="margin-left:auto">Codex 写 config.toml，其余写各自 mcp.json；写入前自动备份，TOML 校验失败自动回滚</span></div></div>' +
  '<div class="panel"><div class="toolbar"><span class="mini-l">配置落点</span></div><div class="rows">' +
    A.map(a => '<div class="row"><span class="agicon" style="background:' + a.color + '">' + svgPath(a.icon) + '</span><span class="rname">' + esc(a.name) +
      '</span><span class="rdesc" title="' + esc(a.path) + '">' + esc(shortPath(a.path)) + '</span><span class="ract">' +
      '<span class="chip ' + (a.exists ? "ok" : "warn") + '">' + (a.exists ? "文件存在" : "待创建") + '</span><span class="chip mute">' + a.format + '</span></span></div>').join("") +
  '</div></div>') +
  '<div class="panel"><div class="toolbar"><span class="mini-l">新增 MCP 服务器（加入 Hub 主列表）</span></div>' +
  '<div class="newform">' +
    '<input class="field" id="new-name" placeholder="名称，如 codepptx"><input class="field" id="new-type" placeholder="type：stdio / http">' +
    '<input class="field" id="new-command" placeholder="command，如 npx"><input class="field" id="new-args" placeholder="args，空格分隔">' +
    '<input class="field" id="new-url" placeholder="url（http 类型）"><input class="field" id="new-description" placeholder="说明">' +
    '<button class="btn primary" data-act="mcp-add">' + svg("plus") + '加入主列表</button></div></div>';
}

/* ---------------- 视图 · 插件 ---------------- */
function pluginAll(){
  if (!S.plugins) return [];
  const out = [];
  for (const [aid, list] of Object.entries(S.plugins.by_agent))
    for (const x of (list || [])) out.push(Object.assign({ agent: aid }, x));
  return out;
}
function pluginHay(x){
  const a = (S.state.agents.find(y => y.id === x.agent) || {});
  return norm([x.name, x.marketplace, x.source, x.version, x.path, x.install_path,
               a.name, a.vendor, a.id, x.enabled ? "启用" : "停用"].filter(Boolean).join(" "));
}
function pluginShown(){ return pluginAll().filter(x => matchQ(pluginHay(x), S.qp)); }
function pluginGroupHTML(id, list){
  const a = S.state.agents.find(x => x.id === id) || { name: id, color: "#9ca3af", vendor: "" };
  return '<div class="panel"><div class="toolbar">' +
    '<span class="agicon" style="background:' + a.color + '">' + svgPath(a.icon) + '</span>' +
    '<span class="mini-l"><b>' + esc(a.name) + '</b> · ' + esc(a.vendor) + ' · ' + list.length + ' 项</span></div>' +
    '<div class="rows">' + list.map(x =>
      '<div class="row"><span class="chip ' + (x.enabled ? "ok" : "mute") + '">' + (x.enabled ? "启用" : "停用") + '</span>' +
      '<span class="rname" style="min-width:280px">' + hl(x.name, S.qp) + '</span>' +
      '<span class="rdesc">' + hl(x.marketplace || x.source || "", S.qp) + '</span>' +
      '<span class="ract">' + (x.version ? '<span class="chip">' + hl(x.version, S.qp) + '</span>' : '') +
      (x.installed_at ? '<span class="chip mute">' + esc(x.installed_at.slice(0, 10)) + '</span>' : '') +
      '</span></div>').join("") + '</div></div>';
}
function pluginGroupsHTML(){
  const shown = pluginShown();
  const byAgent = {};
  for (const x of shown) (byAgent[x.agent] = byAgent[x.agent] || []).push(x);
  const ids = Object.keys(S.plugins.by_agent).filter(k => byAgent[k]);
  return ids.map(id => pluginGroupHTML(id, byAgent[id])).join("");
}
async function pluginsHTML(){
  S.plugins = S.plugins || await api("/api/plugins");
  const p = S.plugins;
  const total = pluginAll().length, nShown = pluginShown().length;
  return '' +
  '<div class="toolbar-top">' +
    '<div class="tabs"><button class="tab on">插件 ' + p.total + '</button></div>' +
    searchBox("qp", S.qp, "搜索插件：名称 / 市场 / 版本 / agent，空格分隔多词") +
    '<span class="hit" id="qphit"></span>' +
  '</div>' +
  (nShown !== total ? '<div class="panel"><div class="empty"><b>' +
        (nShown ? '匹配 ' + nShown + ' / ' + total + ' 个插件' : '没有匹配的插件') + '</b>' +
        (nShown ? '' : '「' + esc(S.qp) + '」不在任何名称 / 市场 / 版本 / agent 里') +
      '</div></div>' : '') +
  '<div class="panel"><div class="toolbar"><span class="mini-l"><b>为什么插件不统一</b> · 格式差异是硬约束</span></div>' +
   '<div class="rows">' +
    ['Codex 用 config.toml 的 [marketplaces.*] + [plugins."x@mp"] 开关，缓存落在 .codex\\plugins\\cache。',
     'Claude / WorkBuddy / Qoder 用 installed_plugins.json 清单 + 自管缓存目录，字段各不相同。',
     'Cursor / Trae / ZCode / Antigravity 又是独立的扩展或内置机制，写入他方格式没有意义。',
     '强行统一会撞上各 app 的自更新与签名校验；插件里真正有价值的技能部分，已由「技能」页完成统一。'
    ].map((s, i) => '<div class="row"><span class="num">' + (i + 1) + '</span><span class="rdesc" style="white-space:normal">' + s + '</span></div>').join("") +
   '</div></div>' +
  '<div id="plugroups">' + pluginGroupsHTML() + '</div>';
}

/* ---------------- 搜索绑定（只重绘列表容器，搜索框不重建 -> 焦点不丢） ---------------- */
function mcpListHTML(){
  const m = S.mcp, A = m.agents;
  if (!mcpShown())
    return '<div class="empty"><b>没有匹配的服务器</b>「' + esc(S.qm) + '」不在任何名称 / 命令 / 参数 / 路径里</div>';
  return '<table class="mx"><thead><tr><th><span class="nm">MCP 服务器</span></th>' + mcpHeads(A) +
         '<th class="op"></th></tr></thead><tbody>' + mcpRowsHTML() + '</tbody></table>';
}
function refreshMcpList(){
  const w = $("#mcpwrap"); if (!w) return;
  w.innerHTML = mcpListHTML();
  updCount("#qmhit", mcpShown(), S.mcp ? S.mcp.rows.length : 0);
}
function refreshPluginList(){
  const w = $("#plugroups"); if (!w) return;
  const n = pluginShown().length;
  w.innerHTML = n ? pluginGroupsHTML()
    : '<div class="panel"><div class="empty"><b>没有匹配的插件</b>「' + esc(S.qp) + '」不在任何名称 / 市场 / 版本 / agent 里</div></div>';
  updCount("#qphit", n, pluginAll().length);
}
function bindTabSearch(){
  if (S.tab === "skills"){
    bindSearch("q", () => { S.q = $("#q").value || ""; refreshSkillList(); }, "#qhit");
    updCount("#qhit", visibleSkills().length, S.state.skills.length);
  } else if (S.tab === "mcp"){
    bindSearch("qm", () => { S.qm = $("#qm").value || ""; refreshMcpList(); }, "#qmhit");
    updCount("#qmhit", mcpShown(), S.mcp ? S.mcp.rows.length : 0);
  } else if (S.tab === "plugin"){
    bindSearch("qp", () => { S.qp = $("#qp").value || ""; refreshPluginList(); }, "#qphit");
    updCount("#qphit", pluginShown().length, pluginAll().length);
  }
}
/* ---------------- 视图 · 收敛中心 ---------------- */
const OPNAME = {install:"灌入真源", link:"副本→联接", purge:"移除重复副本", relink:"重指联接", agents_home_link:"~/.agents 指向真源"};
function hubHTML(){
  const s = S.state.stats;
  const plan = S.plan;
  const cells = plan ? '<div class="plan">'+
      ['install','link','purge','agents_home_link'].map(op =>
        '<div class="pcell"><b>'+(plan.counts[op]||0)+'</b><span>'+OPNAME[op]+'</span></div>').join("")+
      '<div class="pcell"><b>'+fmtB(plan.bytes_saved)+'</b><span>预计释放</span></div></div>' : "";
  const detail = plan ? '<div class="rows">'+plan.actions.slice(0,220).map(a =>
      '<div class="row"><span class="chip '+(["install","relink"].includes(a.op)?"ok":a.op==="purge"?"mute":"warn")+'">'+(OPNAME[a.op]||a.op)+'</span>'+
      '<span class="rname" style="min-width:200px">'+esc(a.skill)+'</span>'+
      '<span class="rdesc">'+esc(shortPath(a.where||a.src||""))+'</span>'+
      '<span class="ract">'+(a.size?'<span class="chip">'+fmtB(a.size)+'</span>':'')+
        (a.same_content===false?'<span class="chip bad">择优版本</span>':'')+'</span></div>').join("")+'</div>' : "";
  return ''+
  '<div class="toolbar-top"><div class="tabs"><button class="tab on">收敛中心</button></div>'+
    '<div></div><button class="btn" data-act="plan">'+svg("refresh")+'生成计划</button></div>'+
  '<div class="stats">'+
    '<div class="stat"><b>'+s.unhosted+'</b><span>未托管技能</span></div>'+
    '<div class="stat"><b>'+s.drift+'</b><span>版本漂移</span></div>'+
    '<div class="stat"><b>'+s.real_copies+'</b><span>实体副本</span></div>'+
    '<div class="stat"><b>'+fmtB(s.bytes_wasted)+'</b><span>重复占用</span></div>'+
    '<div class="stat"><b>'+s.backups+'</b><span>已有备份 zip</span></div>'+
  '</div>'+
  '<div class="panel"><div class="toolbar"><span class="mini-l"><b>执行计划</b> · dry-run，不影响磁盘</span>'+
    (plan?'<span class="mini-l" style="margin-left:auto">共 '+plan.actions.length+' 项动作</span>':'')+'</div>'+
    '<div class="panel-bd">'+(plan ? cells+
      '<div class="sec-title"><h2>执行顺序</h2></div><div class="rows">'+
      ['比对所有副本的内容指纹，取「修改时间最新、体积最大」者为权威版本。',
       '把权威版本复制进真源 ' + esc(S.state.canonical_dir) + '\\<name>。',
       '每处实体副本先压缩备份到 data\\backups\\*.zip，再删除并就地创建 Junction 指向真源。',
       'Codex 经 ~/.agents 原生读取真源，其 .codex\\skills 下的重复副本会被移除（避免同一技能注入两遍）。',
       '最后把 ~/.agents\\skills 整体替换为指向真源的 Junction。',
       '保护清单不动：.codex\\skills\\.system、.trae-cn\\builtin_skills\\_shared 等程序目录。'
      ].map((x,i)=>'<div class="row"><span class="num">'+(i+1)+'</span><span class="rdesc" style="white-space:normal">'+x+'</span></div>').join("")+
      '</div>'+
      '<div class="sec-title"><h2>动作明细（前 220 条）</h2></div>'+detail+
      '<div class="apply-row"><button class="btn primary" data-act="apply">'+svg("bolt")+'备份后执行收敛</button>'+
        '<span class="mini-l">全部被替换的目录都会先压成 zip 存到 data\\backups，可人工回滚。</span></div>'+
      '<div id="apply-progress"></div>'
      : '<div class="empty"><b>尚未生成计划</b>点击右上「生成计划」查看将要执行的变更</div>')+'</div></div>';
}
async function loadPlan(){
  const bd = $("#view .panel-bd"); if (bd) bd.innerHTML = '<div class="empty"><b>正在比对全部副本…</b>计算权威版本与替换动作</div>';
  S.plan = await api("/api/plan");
  $("#view").innerHTML = hubHTML();
  toast("ok","计划已生成", Object.entries(S.plan.counts).filter(([k,n])=>n).map(([k,n])=>OPNAME[k]+" "+n).join(" · "));
}
function startApply(){
  if (!confirm("确定执行收敛？\n\n会创建真源目录、备份全部副本，并把各 agent 目录替换为目录联接。\n建议先退出正在运行的 agent，完成后重启。")) return;
  api("/api/consolidate/apply").then(r => pollJob(r.job)).catch(e => toast("bad","启动失败", e.message));
}
function pollJob(jid){
  const box = $("#apply-progress"); if (!box) return;
  box.innerHTML = '<div class="bar"><i style="width:0%"></i></div><div class="mini-l jtxt" style="margin-top:8px;display:block">准备中…</div>';
  const bar = box.querySelector(".bar i"), txt = box.querySelector(".jtxt");
  const t = setInterval(async () => {
    let j; try { j = await api("/api/job?id="+jid); } catch(e){ return; }
    const pct = j.total ? Math.round(j.done/j.total*100) : 4;
    bar.style.width = pct+"%";
    txt.textContent = (j.stage||j.current||"")+"  "+j.done+"/"+j.total+"  ("+pct+"%)";
    if (j.state === "done"){
      clearInterval(t);
      const r = j.result || {};
      txt.textContent = "完成：执行 "+r.done+" 项，失败 "+((r.failed||[]).length)+" 项，备份 "+((r.backups||[]).length)+" 份 zip";
      toast("ok","收敛完成", (r.failed||[]).length ? ("有 "+r.failed.length+" 项失败，见控制台日志") : "全部位置已改为联接");
      S.plan = null; S.state = await api("/api/state?fresh=1"); renderShell(); $("#view").innerHTML = hubHTML();
    } else if (j.state === "error"){
      clearInterval(t); txt.textContent = "失败："+j.error; toast("bad","收敛中断", j.error);
    }
  }, 500);
}


/* ---------------- 自动同步轮询 ---------------- */
/* 增量刷新：对比新旧快照，只重绘发生变化的行，避免整页重建导致滚动位置丢失 */
async function mergeState(){
  const prev = S.state;
  const next = await api("/api/state?fresh=1");
  S.state = next;
  if (!prev || !$("#view .mx-wrap")){ renderShell(); await render(true); return; }
  const before = {};
  for (const r of prev.skills) before[r.name] = r;
  const changed = [];
  for (const r of next.skills){
    const o = before[r.name];
    if (!o || o.canonical !== r.canonical || o.drift !== r.drift ||
        o.ignored !== r.ignored || o.agent_count !== r.agent_count ||
        JSON.stringify(o.locations) !== JSON.stringify(r.locations)) changed.push(r);
  }
  for (const n of next.skills) if (!before[n.name]) changed.push(n);
  const names = new Set(next.skills.map(r => r.name));
  const gone = Object.keys(before).filter(n => !names.has(n));
  const added = next.skills.filter(r => !before[r.name]);
  if (gone.length || added.length){
    renderShell(); await render(true); return;        // 行数变了，重建但保持滚动位置
  }
  for (const r of changed) applyRow(r);
  renderShell();
}

async function pollWatch(){
  if (document.hidden) return;
  try{
    const w = await api("/api/watch?since=" + (S.lastNoticeTs || 0));
    if (w.notices && w.notices.length){
      S.lastNoticeTs = Math.max(...w.notices.map(n=>n.ts));
      for (const n of w.notices) toast(n.kind==="err"?"bad":"ok", n.kind==="host"?"自动同步":"提示", n.text);
    }
    if (S.rev !== null && w.rev !== S.rev){
      S.rev = w.rev;
      if (S.tab==="mcp"){
        S.mcp = await api("/api/mcp"); $("#view").innerHTML = await mcpHTML();
      } else if (S.tab==="plugin"){
        S.plugins = await api("/api/plugins"); $("#view").innerHTML = await pluginsHTML();
      } else {
        await mergeState();
      }
      renderShell();
    } else if (S.rev === null){ S.rev = w.rev; }
    if (typeof w.auto_host === "boolean") S.autoHost = w.auto_host;
  }catch(e){ /* 服务未起时忽略 */ }
}

/* ---------------- 启动 ---------------- */
window.addEventListener("keydown", e => {
  if (e.key === "Escape") closeDrawer();
  if (e.key === "/" && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)){
    const id = {skills:"q", mcp:"qm", plugin:"qp"}[S.tab];
    const i = id && document.getElementById(id);
    if (i){ i.focus(); i.select(); e.preventDefault(); }
  }
  if (e.key === "Escape" && /INPUT/.test(document.activeElement.tagName||"")){
    const el = document.activeElement;
    if (el.id === "q" || el.id === "qm" || el.id === "qp"){ el.value = ""; el.dispatchEvent(new Event("input")); el.blur(); }
  }
});
const HASH2TAB = {skills:1, mcp:1, plugin:1, hub:1};
(async function boot(){
  const h = (location.hash||"").replace("#","");
  if (HASH2TAB[h]) S.tab = h;
  else if (h.startsWith("skill:")) S.tab = "skills";
  renderShell();
  await refreshAll();
  api("/api/mcp").then(d => { S.mcp = d; renderShell(); }).catch(()=>{});
  api("/api/plugins").then(d => { S.plugins = d; renderShell(); }).catch(()=>{});
  if (h.startsWith("skill:")) openDrawer(decodeURIComponent(h.slice(6)));
  setInterval(pollWatch, 2500);
})();
