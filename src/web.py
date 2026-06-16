"""Web-UI для ChipTuner Assistant (FastAPI + SSE стрим).

Запуск:
    python -m src.web              # http://localhost:8000
Нужен поднятый LM Studio (localhost:1234) и заполненный индекс (python -m src.ingest).
"""
import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from . import config, lmstudio, optimize, rag, tutor

cfg = config.load()
_col = None

# Папки, файлы из которых разрешено открывать кликом (источники RAG лежат тут).
_ALLOWED_DIRS = [Path(d).resolve() for d in cfg.get("docs_dirs", [])]


def _is_allowed(p: Path) -> bool:
    try:
        rp = p.resolve()
    except OSError:
        return False
    return any(rp == a or a in rp.parents for a in _ALLOWED_DIRS)


def col():
    global _col
    if _col is None:
        _col = rag.get_collection(cfg)
    return _col


app = FastAPI(title="ChipTuner Assistant")
app.include_router(tutor.router)

PAGE = r"""<!doctype html><html lang=ru><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>ChipTuner Assistant</title>
<style>
 :root{color-scheme:dark}
 body{font:15px/1.5 system-ui,Segoe UI,sans-serif;max-width:860px;margin:0 auto;padding:16px;background:#15171c;color:#e6e6e6}
 h1{font-size:18px;color:#7ec699}
 #log{margin:12px 0}
 .msg{padding:10px 14px;border-radius:10px;margin:8px 0;white-space:pre-wrap}
 .q{background:#243; align-self:flex-end}
 .a{background:#1e2230;border:1px solid #2c3142}
 .meta{font-size:12px;color:#8a93a6;margin-top:8px}
 .meta b{color:#a9b4c9}
 .meta a.srcfile{color:#7ec699;cursor:pointer;text-decoration:underline;word-break:break-all}
 .meta a.srcfile:hover{color:#a9e6bf}
 .a strong{color:#dfe7f1}
 .a em{color:#cdd3df;font-style:italic}
 .a .h{display:block;color:#7ec699;margin:8px 0 2px}
 .a code{background:#0e1014;padding:1px 5px;border-radius:4px;color:#d8b48a;font-size:13px}
 .a hr{border:0;border-top:1px solid #2c3142;margin:8px 0}
 form{display:flex;gap:8px;position:sticky;bottom:0;background:#15171c;padding:8px 0}
 input{flex:1;padding:10px;border-radius:8px;border:1px solid #333;background:#0e1014;color:#fff}
 button{padding:10px 16px;border:0;border-radius:8px;background:#2e7d4f;color:#fff;cursor:pointer}
 button:disabled{opacity:.5}
 .files div{font-size:12px;color:#c8b88a}
</style></head><body>
<h1>🔧 ChipTuner Assistant</h1>
<div style="font-size:13px;margin-bottom:8px"><a href="/tutor" style="color:#7ec699">🎓 Новичок? Открыть тьютор →</a></div>
<div id=log></div>
<form id=f><input id=q placeholder="Напр.: чем прошить EDC17?" autocomplete=off>
<button id=b>Спросить</button></form>
<script>
const log=document.getElementById('log'),q=document.getElementById('q'),b=document.getElementById('b'),f=document.getElementById('f');
// прокрутка: держимся низа, пока юзер сам не пролистнул вверх (тогда не мешаем)
let stick=true;
function atBottom(){return (window.innerHeight+window.scrollY)>=document.documentElement.scrollHeight-100;}
function toBottom(){if(stick)window.scrollTo(0,document.documentElement.scrollHeight);}
window.addEventListener('scroll',()=>{stick=atBottom();},{passive:true});
function add(cls,html){const d=document.createElement('div');d.className='msg '+cls;d.innerHTML=html;log.appendChild(d);return d}
// клик по источнику -> открыть файл локально (делегирование, переживает перерисовку)
log.addEventListener('click',e=>{const t=e.target.closest('.srcfile');if(!t)return;e.preventDefault();
 t.style.opacity=.5;
 fetch('/api/open?path='+t.dataset.p).then(r=>r.json()).then(d=>{t.style.opacity=1;
   if(!d.ok)alert('Не удалось открыть: '+(d.error||'неизвестно'));}).catch(()=>{t.style.opacity=1;alert('Ошибка открытия');});});
// мини-рендер Markdown: жирный **x**, курсив *x*, `код`, ### заголовки, --- линия, списки
function md(s){
 s=s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
 s=s.replace(/`([^`]+)`/g,'<code>$1</code>');
 s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
 s=s.replace(/(^|[^*])\*([^*]+)\*(?!\*)/g,'$1<em>$2</em>');
 return s.split('\n').map(ln=>{
   const h=ln.match(/^#{1,6}\s+(.*)$/);
   if(h)return '<span class=h>'+h[1]+'</span>';
   if(/^\s*---+\s*$/.test(ln))return '<hr>';
   if(/^\s*[-*]\s+/.test(ln))return '• '+ln.replace(/^\s*[-*]\s+/,'');
   return ln;
 }).join('\n');
}
f.onsubmit=async e=>{e.preventDefault();const text=q.value.trim();if(!text)return;
 add('q',text.replace(/</g,'&lt;'));q.value='';b.disabled=true;
 stick=true;toBottom();
 const a=add('a','<i>⏳ ждёт модель…</i>');let body='',think='',metaHtml='',t0=Date.now();
 const timer=setInterval(()=>{if(body||think){clearInterval(timer);return;}
   a.innerHTML='<i style="color:#8a93a6">⏳ генерирую ответ… '+Math.round((Date.now()-t0)/1000)+'с '+
   '<span style="opacity:.6">(локальная модель; на Intel Arc первый токен ~30-40с)</span></i>';toBottom();},1000);
 const render=()=>{a.innerHTML='<div class=ans>'+md(body)+'</div>'+metaHtml;toBottom();};
 const es=new EventSource('/api/stream?q='+encodeURIComponent(text));
 es.addEventListener('think',ev=>{if(body)return;think+=JSON.parse(ev.data);
   a.innerHTML='<div style="color:#8a93a6;font-size:13px">💭 думает… <span style="opacity:.7">'+think.slice(-160).replace(/</g,'&lt;')+'</span></div>';toBottom();});
 es.addEventListener('token',ev=>{body+=JSON.parse(ev.data);render();});
 es.addEventListener('meta',ev=>{const m=JSON.parse(ev.data);let h='';
   if(m.sources&&m.sources.length){h+='<div class=meta><b>📄 Источники ответа</b> <span style="opacity:.7">(клик — открыть файл):</span><br>'+
     m.sources.map(s=>'<a href="#" class=srcfile data-p="'+encodeURIComponent(s.path)+'">'+s.name.replace(/</g,'&lt;')+'</a>').join('<br>')+'</div>';}
   if(m.files&&m.files.length){h+='<div class="meta files"><b>🗂 Файлы в архиве по теме:</b>'+m.files.map(x=>'<div>['+(x.size/1e6).toFixed(1)+' MB] '+(x.ecu||x.brand||x.category)+' — '+x.path.replace(/</g,'&lt;')+'</div>').join('')+'</div>';}
   metaHtml=h;if(body)render();});
 es.addEventListener('done',()=>{clearInterval(timer);es.close();b.disabled=false;q.focus();});
 es.onerror=()=>{clearInterval(timer);es.close();b.disabled=false;if(body==='')a.innerHTML='<span style=color:#e88>Ошибка: LM Studio не отвечает?</span>';};
};
const pq=new URLSearchParams(location.search).get('q');
if(pq){q.value=pq;history.replaceState(null,'','/');f.requestSubmit();}
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


@app.get("/api/open")
def open_file(path: str):
    """Открыть файл-источник в системной программе по умолчанию (локально, Windows).
    Разрешены только файлы внутри docs_dirs."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return JSONResponse({"ok": False, "error": "файл не найден на диске"}, status_code=404)
    if not _is_allowed(p):
        return JSONResponse({"ok": False, "error": "путь вне разрешённых папок"}, status_code=403)
    try:
        os.startfile(str(p))  # noqa: S606 — Windows, открыть в дефолтной программе
        return {"ok": True}
    except OSError as ex:
        return JSONResponse({"ok": False, "error": str(ex)}, status_code=500)


@app.get("/api/stream")
def stream(q: str):
    def gen():
        optimize.ensure_optimized(cfg)   # переоптимизация, если сменили модель в LM Studio
        hits = rag.retrieve(cfg, col(), q)
        files = rag.catalog_files(cfg, q)
        seen, sources = set(), []   # уникальные файлы-источники (чанки одного файла схлопываем)
        for h in hits:
            if h["path"] in seen:
                continue
            seen.add(h["path"])
            sources.append({"name": h["name"], "path": h["path"], "score": round(h["score"], 3)})
        meta = {"sources": sources, "files": files}
        yield f"event: meta\ndata: {json.dumps(meta, ensure_ascii=False)}\n\n"
        if not hits:
            yield "event: token\ndata: " + json.dumps("В индексе нет данных.") + "\n\n"
            yield "event: done\ndata: {}\n\n"
            return
        ctx = rag.build_context(hits, cfg.get("max_context_chars", 3500))
        messages = [
            {"role": "system", "content": rag.SYSTEM_PROMPT},
            {"role": "user", "content": f"Фрагменты:\n{ctx}\n\nВопрос: {q}"},
        ]
        got_content = False
        try:
            for kind, delta in lmstudio.stream_deltas(cfg["lmstudio"], messages):
                ev = "think" if kind == "think" else "token"
                if kind != "think":
                    got_content = True
                yield f"event: {ev}\ndata: {json.dumps(delta, ensure_ascii=False)}\n\n"
        except Exception as ex:  # noqa: BLE001
            yield "event: token\ndata: " + json.dumps(f"[ошибка LM Studio: {ex}]") + "\n\n"
            got_content = True
        if not got_content:
            yield "event: token\ndata: " + json.dumps(
                "Модель ушла в размышления и не выдала ответ (reasoning исчерпал бюджет). "
                "Подними max_tokens или загрузи instruct-модель (напр. ministral-3-3b).") + "\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def main():
    import uvicorn
    print("=== ChipTuner: проверка железа и авто-оптимизация LLM ===", flush=True)
    if lmstudio.is_up(cfg["lmstudio"]["base_url"]):
        print(optimize.ensure_optimized(cfg, verbose=False), flush=True)
    else:
        print(f"! LM Studio не отвечает на {cfg['lmstudio']['base_url']} — подними сервер "
              "(Developer → Start Server). Оптимизация применится при первом запросе.", flush=True)
    optimize.start_background(cfg)   # держим настройки тёплыми, путь запроса не ждёт API LM Studio
    # прогрев эмбеддинг-модели в фоне, чтобы ПЕРВЫЙ вопрос не ждал её холодную загрузку (~10с)
    import threading
    threading.Thread(target=lambda: rag.retrieve(cfg, col(), "разогрев"),
                     daemon=True, name="embed-warm").start()
    print("ChipTuner web-UI: http://localhost:8000  (Ctrl+C — выход)", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
