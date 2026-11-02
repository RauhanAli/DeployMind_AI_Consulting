"""Enterprise Knowledge Assistant runtime.

A small, stateless service deployed per environment. It authenticates to the DeployMind platform with a
per-deployment token and forwards questions to the platform's grounded RAG runtime endpoint, which enforces
tenant isolation, retrieval ACLs and telemetry. It serves a minimal chat UI for end users.

Environment:
  PLATFORM_URL       base URL of the DeployMind API (e.g. http://host.docker.internal:8000)
  DEPLOYMENT_TOKEN   per-deployment bearer token (injected at deploy time, never logged)
  APP_ID, APP_NAME, ENVIRONMENT, APP_VERSION
"""

import os
import time

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

PLATFORM_URL = os.environ.get("PLATFORM_URL", "http://host.docker.internal:8000").rstrip("/")
TOKEN = os.environ.get("DEPLOYMENT_TOKEN", "")
APP_NAME = os.environ.get("APP_NAME", "Knowledge Assistant")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
VERSION = os.environ.get("APP_VERSION", "dev")
STARTED = time.time()

app = FastAPI(title=APP_NAME, version=VERSION)


class Ask(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    conversation_id: str | None = None


def _client() -> httpx.Client:
    return httpx.Client(base_url=PLATFORM_URL, timeout=60, headers={"Authorization": f"Bearer {TOKEN}"})


def health_payload(platform_ok: bool, detail: str | None) -> dict:
    return {"status": "ok" if platform_ok and TOKEN else "degraded", "service": "knowledge-assistant",
            "version": VERSION, "environment": ENVIRONMENT, "platform_reachable": platform_ok,
            "token_configured": bool(TOKEN), "uptime_seconds": int(time.time() - STARTED), "detail": detail}


@app.get("/health")
def health():
    try:
        with _client() as c:
            r = c.get("/api/v1/runtime/health")
        ok, detail = r.status_code == 200, None if r.status_code == 200 else f"platform returned {r.status_code}"
    except httpx.HTTPError as exc:
        ok, detail = False, f"platform unreachable: {exc.__class__.__name__}"
    return health_payload(ok, detail)


@app.post("/ask")
def ask(body: Ask):
    try:
        with _client() as c:
            r = c.post("/api/v1/runtime/ask", json=body.model_dump())
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Platform unreachable: {exc.__class__.__name__}")
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.json().get("error", {}).get("message", "Platform error"))
    return r.json()


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__NAME__</title><style>
body{font-family:system-ui,sans-serif;margin:0;background:#f7f7f8;color:#111}main{max-width:760px;margin:0 auto;padding:24px 16px}
h1{font-size:20px}.env{font-size:12px;color:#555}#log{display:flex;flex-direction:column;gap:12px;margin:16px 0}
.m{padding:12px 14px;border-radius:10px;background:#fff;border:1px solid #e5e5e5;white-space:pre-wrap}.u{background:#eef2ff}
.c{font-size:12px;color:#444;margin-top:8px}form{display:flex;gap:8px}input{flex:1;padding:10px;border:1px solid #ccc;border-radius:8px}
button{padding:10px 16px;border:0;border-radius:8px;background:#1d4ed8;color:#fff}</style></head><body><main>
<h1>__NAME__</h1><div class="env">Environment: __ENV__ · Version __VER__ · Answers are grounded in your organisation's documents.</div>
<div id="log"></div><form id="f"><input id="q" placeholder="Ask a question..." required minlength="2"><button>Ask</button></form></main>
<script>
const log=document.getElementById('log');let conv=null;
function add(t,cls){const d=document.createElement('div');d.className='m '+cls;d.textContent=t;log.appendChild(d);return d}
document.getElementById('f').onsubmit=async e=>{e.preventDefault();const q=document.getElementById('q');const text=q.value;q.value='';
add(text,'u');const d=add('Thinking...','a');
try{const r=await fetch('ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:text,conversation_id:conv})});
const j=await r.json();if(!r.ok)throw new Error(j.detail||'Error');conv=j.conversation_id;d.textContent=j.answer;
if(j.citations&&j.citations.length){const c=document.createElement('div');c.className='c';c.textContent='Sources: '+j.citations.map(x=>'['+x.index+'] '+x.title).join('  ');d.appendChild(c)}}
catch(err){d.textContent='Error: '+err.message}}
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE.replace("__NAME__", APP_NAME).replace("__ENV__", ENVIRONMENT).replace("__VER__", VERSION)
