(function(){
"use strict";
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const store = {get(k){try{return localStorage.getItem(k)}catch(e){return null}}, set(k,v){try{localStorage.setItem(k,v)}catch(e){}}};

/* ---------- Tuỳ chọn hiển thị (nhớ trên máy người đọc) ---------- */
const prefs = {fs: store.get("bb-fs") || "2", lh: store.get("bb-lh") || "normal", bg: store.get("bb-bg") || "auto"};
function applyPrefs(){
  const b = document.body;
  b.classList.remove("fs-1","fs-2","fs-3","fs-4","lh-wide","r-paper","r-sepia","r-dark");
  b.classList.add("fs-" + prefs.fs);
  if(prefs.lh === "wide") b.classList.add("lh-wide");
  if(prefs.bg !== "auto") b.classList.add("r-" + prefs.bg);
  [["#opt-fs","fs"],["#opt-lh","lh"],["#opt-bg","bg"]].forEach(([id,k]) => $$(id + " button").forEach(x => {
    const on = x.dataset.v === prefs[k]; x.classList.toggle("on", on); x.setAttribute("aria-pressed", on);
  }));
}
[["#opt-fs","fs"],["#opt-lh","lh"],["#opt-bg","bg"]].forEach(([id,k]) => $$(id + " button").forEach(x => x.addEventListener("click", () => {
  prefs[k] = x.dataset.v; store.set("bb-" + k, x.dataset.v); applyPrefs(); progress();
})));
applyPrefs();

/* ---------- Tiện ích ---------- */
let toastT;
function toast(msg){ const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => t.hidden = true, 2600); }
function copyText(text, msg){
  const done = () => toast(msg || "Đã sao chép. Dán vào Zalo hoặc email để gửi.");
  const fallback = () => {
    const ta = document.createElement("textarea"); ta.value = text; ta.style.cssText = "position:fixed;opacity:0";
    document.body.appendChild(ta); ta.select();
    try{ document.execCommand("copy") ? done() : toast("Chưa sao chép được — hãy bôi đen nội dung để chép."); }
    catch(e){ toast("Chưa sao chép được — hãy bôi đen nội dung để chép."); }
    ta.remove();
  };
  try{ navigator.clipboard.writeText(text).then(done, fallback); }catch(e){ fallback(); }
}
const fmt = d => d ? d.split("-").reverse().join("/") : "chưa nêu hạn";
const clean = el => el ? el.textContent.replace(/\s+/g, " ").trim() : "";
function reveal(el){ let p = el; while(p){ if(p.tagName === "DETAILS") p.open = true; p = p.parentElement; } }

/* ---------- Bảng trượt (mục lục, chia sẻ, hiển thị) ---------- */
let openSheet = null;
function showSheet(id){
  closeSheet(); openSheet = $("#" + id); if(!openSheet) return;
  openSheet.hidden = false; $("#sheet-bg").hidden = false;
  if(id === "sheet-toc") markHere();
  const f = openSheet.querySelector("button.on, a, button"); if(f) f.focus({preventScroll:true});
}
function closeSheet(){ if(openSheet){ openSheet.hidden = true; openSheet = null; } $("#sheet-bg").hidden = true; }
$$("[data-sheet]").forEach(b => b.addEventListener("click", () => showSheet(b.dataset.sheet)));
$$(".sheet .x").forEach(b => b.addEventListener("click", closeSheet));
$("#sheet-bg").addEventListener("click", closeSheet);
document.addEventListener("keydown", e => { if(e.key === "Escape"){ closeSheet(); closeSearch(); } });

/* ---------- Tiến độ đọc ---------- */
function progress(){
  const h = document.documentElement, max = h.scrollHeight - h.clientHeight;
  const p = max > 0 ? Math.min(1, Math.max(0, h.scrollTop / max)) : 1;
  $("#prog-bar").style.width = (p * 100).toFixed(1) + "%";
  const t = $("#prog-txt"); if(t) t.textContent = "Đã đọc " + Math.round(p * 100) + "%";
}
addEventListener("scroll", progress, {passive:true}); addEventListener("resize", progress);
function markHere(){
  const secs = $$(".sec"); let cur = secs[0];
  secs.forEach(s => { if(s.getBoundingClientRect().top < innerHeight * .35) cur = s; });
  $$("#sheet-toc-list a").forEach(a => a.classList.toggle("here", cur && a.getAttribute("href") === "#" + cur.id));
}

/* ---------- Tìm kiếm không dấu ---------- */
const fold = s => s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
const foldChar = c => { const f = fold(c); return f.length === 1 ? f : (f[0] || c.toLowerCase()); };
let hits = [], hi = -1;
function clearHits(){
  $$("mark.hit").forEach(m => { const t = document.createTextNode(m.textContent); m.replaceWith(t); });
  const c = $("#content"); if(c) c.normalize(); hits = []; hi = -1;
}
function search(q){
  clearHits();
  const nq = fold(q.trim()); if(nq.length < 2){ $("#q-count").textContent = "0/0"; return; }
  const walker = document.createTreeWalker($("#content"), NodeFilter.SHOW_TEXT, {acceptNode: n =>
    n.parentElement && !n.parentElement.closest("script,style,summary .cnt") && n.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT});
  const nodes = []; while(walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(node => {
    const src = node.nodeValue, folded = [...src].map(foldChar).join("");
    let i = folded.indexOf(nq), last = 0, frag = null;
    if(i < 0 || folded.length !== src.length) { if(i < 0) return; }
    frag = document.createDocumentFragment();
    while(i >= 0){
      frag.appendChild(document.createTextNode(src.slice(last, i)));
      const m = document.createElement("mark"); m.className = "hit"; m.textContent = src.slice(i, i + nq.length);
      frag.appendChild(m); hits.push(m); last = i + nq.length; i = folded.indexOf(nq, last);
    }
    frag.appendChild(document.createTextNode(src.slice(last)));
    node.replaceWith(frag);
  });
  hits.length ? go(0) : $("#q-count").textContent = "0/0";
}
function go(i){
  if(!hits.length) return;
  if(hi >= 0 && hits[hi]) hits[hi].classList.remove("cur");
  hi = (i + hits.length) % hits.length; const m = hits[hi];
  m.classList.add("cur"); reveal(m); m.scrollIntoView({block:"center"});
  $("#q-count").textContent = (hi + 1) + "/" + hits.length;
}
function openSearch(){ closeSheet(); $("#searchbar").hidden = false; $("#q").focus(); }
function closeSearch(){ if($("#searchbar").hidden) return; $("#searchbar").hidden = true; clearHits(); $("#q").value = ""; $("#q-count").textContent = "0/0"; }
let qT; $("#q").addEventListener("input", e => { clearTimeout(qT); qT = setTimeout(() => search(e.target.value), 180); });
$("#q").addEventListener("keydown", e => { if(e.key === "Enter"){ e.preventDefault(); go(hi + (e.shiftKey ? -1 : 1)); } });
$("#q-next").addEventListener("click", () => go(hi + 1));
$("#q-prev").addEventListener("click", () => go(hi - 1));
$("#q-close").addEventListener("click", closeSearch);
$("#open-search").addEventListener("click", openSearch);

/* ---------- Nội dung ---------- */
function init(){
  // Mục lục trong bảng trượt
  const list = $("#sheet-toc-list"); list.innerHTML = "";
  $$(".toc li").forEach(li => { const c = li.cloneNode(true); list.appendChild(c); });
  $$("#sheet-toc-list a, .toc a").forEach(a => a.addEventListener("click", e => {
    const t = document.querySelector(a.getAttribute("href")); if(!t) return;
    e.preventDefault(); closeSheet(); reveal(t); t.scrollIntoView({block:"start"});
  }));

  // Hạn chót: tô màu theo số ngày còn lại
  const today = new Date(); today.setHours(0,0,0,0);
  $$(".due").forEach(el => {
    const d = el.dataset.deadline; if(!d){ el.classList.add("none"); return; }
    const diff = Math.round((new Date(d + "T00:00:00") - today) / 86400000);
    let note;
    if(diff < 0){ el.classList.add("over"); note = "quá hạn " + (-diff) + " ngày"; }
    else if(diff <= 3){ el.classList.add("soon"); note = diff === 0 ? "hôm nay" : "còn " + diff + " ngày"; }
    else note = "còn " + diff + " ngày";
    el.textContent = el.textContent.trim() + " · " + note;
  });

  // Kế hoạch hành động: sắp theo hạn / theo người, sao chép
  const tl = $("#tasks"), items = tl ? [...tl.querySelectorAll(".task")] : [];
  const key = t => t.dataset.deadline || "9999";
  const sorted = () => items.slice().sort((a,b) => key(a).localeCompare(key(b)));
  function render(mode){
    if(!tl) return; tl.innerHTML = "";
    if(mode === "date"){ sorted().forEach(t => tl.appendChild(t)); return; }
    const groups = {}; items.forEach(t => (groups[t.dataset.owner] = groups[t.dataset.owner] || []).push(t));
    Object.keys(groups).sort((a,b) => a === "Chưa rõ" ? 1 : b === "Chưa rõ" ? -1 : a.localeCompare(b, "vi")).forEach(o => {
      const lab = document.createElement("li"); lab.className = "group-label"; lab.textContent = o + " · " + groups[o].length + " việc";
      tl.appendChild(lab); groups[o].sort((a,b) => key(a).localeCompare(key(b))).forEach(t => tl.appendChild(t));
    });
  }
  const setMode = m => { ["date","owner"].forEach(x => { const b = $("#by-" + x); if(b){ b.classList.toggle("on", x === m); b.setAttribute("aria-pressed", x === m); } }); render(m); };
  if($("#by-date")){ $("#by-date").onclick = () => setMode("date"); $("#by-owner").onclick = () => setMode("owner"); setMode("date"); }
  const planText = () => items.length
    ? "📌 KẾ HOẠCH HÀNH ĐỘNG\n" + BB.title + " (" + BB.date + ")\n\n" + sorted().map(t =>
        "• " + (t.dataset.owner === "Chưa rõ" ? "⚠️ Chưa rõ người nhận" : t.dataset.owner) + ": " + clean(t.querySelector(".what")) + "\n   ⏰ " + fmt(t.dataset.deadline)).join("\n")
    : "📌 " + BB.title + " (" + BB.date + ")\nCuộc họp không giao công việc cho người cụ thể.";
  if($("#copy-plan")) $("#copy-plan").onclick = () => copyText(planText());
  $("#copy-plan-2").onclick = () => copyText(planText());
  $("#copy-all").onclick = () => copyText(BB.plain);
  $$("[data-owner-copy]").forEach(b => b.onclick = () => {
    const o = b.dataset.ownerCopy, mine = sorted().filter(t => t.dataset.owner === o);
    copyText((o === "Chưa rõ" ? "⚠️ Việc chưa có người nhận" : "👋 Việc của " + o) + " — " + BB.title + "\n" +
      mine.map(t => "• " + clean(t.querySelector(".what")) + " (hạn: " + fmt(t.dataset.deadline) + ")").join("\n"));
  });

  // Gập/mở tất cả chủ đề diễn biến
  const fa = $("#fold-all");
  if(fa) fa.onclick = () => { const anyOpen = $$(".topic-fold").some(d => d.open); $$(".topic-fold").forEach(d => d.open = !anyOpen); fa.textContent = anyOpen ? "Mở tất cả" : "Thu gọn tất cả"; progress(); };
  progress();
}

/* ---------- Mở khoá (khi biên bản có mật khẩu) ---------- */
const b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
async function decrypt(pw){
  const E = BB.enc;
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(pw), "PBKDF2", false, ["deriveKey"]);
  const k = await crypto.subtle.deriveKey({name:"PBKDF2", salt:b64(E.salt), iterations:E.iter, hash:"SHA-256"}, base, {name:"AES-GCM", length:256}, false, ["decrypt"]);
  return new TextDecoder().decode(await crypto.subtle.decrypt({name:"AES-GCM", iv:b64(E.iv)}, k, b64(E.data)));
}
async function unlock(pw, silent){
  try{
    $("#content").innerHTML = await decrypt(pw);
    try{ sessionStorage.setItem("bb-pw", pw); }catch(e){}
    $("#gate").hidden = true; $("#app").hidden = false; $("#dock").hidden = false; init(); return true;
  }catch(e){ if(!silent) $("#err").textContent = "Mật khẩu chưa đúng. Kiểm tra chữ hoa, chữ thường rồi thử lại."; return false; }
}
if(BB.enc){
  $("#gate-form").addEventListener("submit", async e => {
    e.preventDefault(); $("#err").textContent = ""; $("#open-btn").textContent = "Đang mở…";
    if(!await unlock($("#pw").value, false)) $("#open-btn").textContent = "Mở biên bản";
  });
  (async () => { let s = null; try{ s = sessionStorage.getItem("bb-pw"); }catch(e){} if(s) await unlock(s, true); })();
} else {
  init();
}
})();
