from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .model import ControlRequest

MAX_BODY = 16 * 1024
DEFAULT_HOST = "127.0.0.1"

DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>DARWIN ZERO-0 Owner Ops</title>
<style>
:root{--bg:#070a0f;--panel:#0e141d;--panel2:#121b27;--line:#253247;--text:#eef4ff;--muted:#8fa1b8;--ok:#45d483;--warn:#ffbf47;--bad:#ff6577}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 10% 0,#101b2b 0,#070a0f 32%,#05070b 100%);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;min-height:100vh}
.shell{max-width:1180px;margin:auto;padding:28px 18px 42px}.top{display:flex;gap:18px;align-items:center;justify-content:space-between;margin-bottom:22px}
.brand h1{font-size:clamp(24px,4vw,38px);letter-spacing:.04em;margin:0}.brand p{color:var(--muted);margin:5px 0 0}.toolbar{display:flex;gap:10px;align-items:center}
button{background:#152238;color:var(--text);border:1px solid #2a4162;border-radius:10px;padding:9px 13px;cursor:pointer}.pill{border:1px solid var(--line);border-radius:999px;padding:7px 11px;font-size:13px;background:#0b1119}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.hero{display:grid;grid-template-columns:2fr 1fr;gap:14px;margin-bottom:14px}
.card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:17px;box-shadow:0 12px 30px rgba(0,0,0,.22)}
.label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.11em}.value{font-size:20px;font-weight:700;margin-top:7px;word-break:break-word}.sub{color:var(--muted);font-size:13px;margin-top:7px;line-height:1.45}
.progress{height:10px;background:#09101a;border-radius:999px;overflow:hidden;margin-top:14px;border:1px solid #1c2a3d}.progress>div{height:100%;background:linear-gradient(90deg,#468df7,#54d78c);width:0;transition:width .35s ease}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.kv{display:grid;grid-template-columns:auto 1fr;gap:7px 12px;margin-top:12px;font-size:13px}.kv span:nth-child(odd){color:var(--muted)}.kv span:nth-child(even){text-align:right;overflow-wrap:anywhere}
.footer{color:var(--muted);font-size:12px;margin-top:16px;display:flex;justify-content:space-between;gap:10px}
@media(max-width:850px){.hero,.grid{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}.toolbar{width:100%;justify-content:space-between}}
</style>
</head>
<body>
<div class="shell">
  <div class="top">
    <div class="brand"><h1>DARWIN ZERO-0</h1><p>Owner Operations · local control-plane view</p></div>
    <div class="toolbar"><span id="systemPill" class="pill">Loading</span><button id="refresh">Refresh</button></div>
  </div>
  <section class="hero">
    <article class="card"><div class="label">Current task</div><div id="taskName" class="value">Loading…</div><div id="taskMeta" class="sub"></div><div class="progress"><div id="progressBar"></div></div></article>
    <article class="card"><div class="label">Board progress</div><div id="progressText" class="value">—</div><div id="taskCounts" class="sub">—</div></article>
  </section>
  <section class="grid">
    <article class="card"><div class="label">Control</div><div id="controlState" class="value">—</div><div id="controlMeta" class="kv"></div></article>
    <article class="card"><div class="label">Budget</div><div id="budgetState" class="value">—</div><div id="budgetMeta" class="kv"></div></article>
    <article class="card"><div class="label">Model</div><div id="modelState" class="value">—</div><div id="modelMeta" class="kv"></div></article>
    <article class="card"><div class="label">Recovery</div><div id="recoveryState" class="value">—</div><div id="recoveryMeta" class="kv"></div></article>
    <article class="card"><div class="label">Security</div><div id="securityState" class="value">—</div><div id="securityMeta" class="kv"></div></article>
    <article class="card"><div class="label">Git / Context</div><div id="gitState" class="value">—</div><div id="gitMeta" class="kv"></div></article>
  </section>
  <div class="footer"><span>No LLM rendering · localhost only · 60s light refresh</span><span id="updated">—</span></div>
</div>
<script>
const $=id=>document.getElementById(id);
const txt=(v,fallback="—")=>v===undefined||v===null||v===""?fallback:String(v);
function pair(el,items){el.replaceChildren();for(const [k,v] of items){const a=document.createElement("span");a.textContent=k;const b=document.createElement("span");b.textContent=txt(v);el.append(a,b)}}
function tone(el,value){el.classList.remove("ok","warn","bad");const x=String(value||"").toUpperCase();el.classList.add(x.includes("OK")||x.includes("RUN")||x.includes("AVAILABLE")?"ok":x.includes("BLOCK")||x.includes("DEGRADED")||x.includes("MISSING")?"bad":"warn")}
async function refresh(){
  try{
    const r=await fetch("/api/status",{cache:"no-store"});if(!r.ok)throw new Error("HTTP "+r.status);
    const x=await r.json(),s=x.sections||{},t=s.task||{},sys=s.system||{},ctl=s.control||{},b=s.budget||{},m=s.model||{},rec=s.recovery||{},sec=s.security||{},g=s.git||{},ctx=s.context||{};
    $("taskName").textContent=txt(t.name,"No active task");
    $("taskMeta").textContent=[txt(t.task_status,"none"),txt(t.assignee,"unassigned"),t.task_id?("ID "+t.task_id):""].filter(Boolean).join(" · ");
    const pct=Math.max(0,Math.min(100,Number(t.progress_percent)||0));$("progressBar").style.width=pct+"%";$("progressText").textContent=txt(t.progress,pct+"%");
    const c=t.counts||{};$("taskCounts").textContent=`${txt(c.done,0)} done · ${txt(c.running,0)} running · ${txt(c.blocked,0)} blocked · ${txt(c.total,0)} total`;
    $("systemPill").textContent=`${txt(sys.state)} · Safety ${txt(sys.safety_version)}`;tone($("systemPill"),sys.state);
    $("controlState").textContent=txt(ctl.state);tone($("controlState"),ctl.state);pair($("controlMeta"),[["Approvals",ctl.approvals_mode],["Supervisor",ctl.supervisor]]);
    $("budgetState").textContent=txt(b.status);tone($("budgetState"),b.status);pair($("budgetMeta"),[["Spend",b.spend],["Source",b.source]]);
    $("modelState").textContent=txt(m.model);tone($("modelState"),m.usage_ledger);pair($("modelMeta"),[["Router",m.router],["Usage ledger",m.usage_ledger],["Skills",m.skill_registry]]);
    $("recoveryState").textContent=txt(rec.status);tone($("recoveryState"),rec.status);pair($("recoveryMeta"),[["Latest",rec.latest]]);
    $("securityState").textContent=txt(sec.telemetry);tone($("securityState"),sec.telemetry);pair($("securityMeta"),[["Alert",sec.last_alert],["Truth",sec.source_of_truth]]);
    $("gitState").textContent=(txt(g.commit)).slice(0,12);pair($("gitMeta"),[["CI",g.ci],["Context",ctx.status],["Mode",ctx.mode]]);
    $("updated").textContent="Updated "+new Date((Number(x.generated_at)||0)*1000).toLocaleTimeString();
  }catch(e){$("systemPill").textContent="UI DEGRADED";$("systemPill").className="pill bad";$("updated").textContent="Refresh failed"}
}
$("refresh").addEventListener("click",refresh);refresh();setInterval(refresh,60000);
</script>
</body>
</html>"""

class LocalAPI:
    def __init__(self, read_model, dispatcher, trusted_local_authorizer=None):
        self.read_model = read_model
        self.dispatcher = dispatcher
        self.trusted_local_authorizer = trusted_local_authorizer
    def status(self):
        return self.read_model.snapshot()
    def control(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("invalid request")
        if self.trusted_local_authorizer is None:
            raise PermissionError("local controls disabled until trusted runtime binding")
        request = self.trusted_local_authorizer(payload)
        if not isinstance(request, ControlRequest):
            raise PermissionError("invalid trusted local authorization result")
        return self.dispatcher.dispatch(request.validate())

def build_local_server(api, host=DEFAULT_HOST, port=8765):
    if host != DEFAULT_HOST:
        raise ValueError("Owner Ops may bind only to 127.0.0.1 by default")
    if isinstance(port, bool) or not isinstance(port, int) or not (port == 0 or 1024 <= port <= 65535):
        raise ValueError("invalid local port")

    class Handler(BaseHTTPRequestHandler):
        server_version = "DARWINOwnerOps/1"
        def _headers(self, content_type, length):
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.send_header("Content-Length", str(length))

        def _json(self, status, payload):
            blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            self.send_response(status); self._headers("application/json", len(blob)); self.end_headers(); self.wfile.write(blob)

        def do_GET(self):
            if self.path == "/":
                blob = DASHBOARD_HTML.encode("utf-8")
                self.send_response(200); self._headers("text/html; charset=utf-8", len(blob)); self.end_headers(); self.wfile.write(blob)
            elif self.path == "/api/status":
                self._json(200, api.status())
            else:
                self._json(404, {"error":"not found"})

        def do_POST(self):
            if self.path != "/api/control":
                self._json(404, {"error":"not found"}); return
            try:
                length = int(self.headers.get("Content-Length","0"))
            except ValueError:
                self._json(400, {"error":"invalid content length"}); return
            if length <= 0 or length > MAX_BODY:
                self._json(413, {"error":"request too large"}); return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                self._json(200, api.control(payload))
            except Exception as exc:
                self._json(403, {"error": type(exc).__name__})

        def log_message(self, *_):
            return

    return ThreadingHTTPServer((host, port), Handler)
