"""Вкладка «Тьютор» — продвинутое обучение чип-тюнингу.

Подключается к основному web-приложению (src/web.py) как APIRouter. Всё
интерактивное (курс по уровням, глоссарий, карточки, квиз, темы из архива,
поиск файлов) работает МГНОВЕННО, без ожидания LLM. Кнопки/чипы шлют вопрос
боту через вкладку «Чат» (`/?q=...`).

«Куча материала» = не 9 статичных уроков, а:
  • 20 уроков по 3 уровням (tutor_data.LESSONS),
  • ~70 терминов глоссария (+ определения из энциклопедии),
  • темы из catalog.db: 25 брендов и 16 семейств ЭБУ (реальные файлы архива),
  • поиск по 42 574 файлам каталога прямо тут.
"""
import sqlite3
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from . import config, glossary
from .tutor_data import LESSONS, LEVELS

cfg = config.load()
router = APIRouter()


def _db() -> Path:
    return Path(cfg["data_dir"]) / "catalog.db"


def topics() -> dict:
    """Бренды и семейства ЭБУ из каталога (реальные темы архива)."""
    db = _db()
    if not db.exists():
        return {"brands": [], "ecus": []}
    con = sqlite3.connect(db)
    try:
        brands = [{"name": b, "count": n} for b, n in con.execute(
            "SELECT brand,COUNT(*) FROM files WHERE brand IS NOT NULL AND is_dir=0 "
            "GROUP BY brand ORDER BY 2 DESC")]
        ecus = [{"name": e, "count": n} for e, n in con.execute(
            "SELECT ecu,COUNT(*) FROM files WHERE ecu IS NOT NULL AND is_dir=0 "
            "GROUP BY ecu ORDER BY 2 DESC")]
    finally:
        con.close()
    return {"brands": brands, "ecus": ecus}


def file_search(q: str, limit: int = 40) -> list[dict]:
    """Поиск по каталогу (FTS, мгновенно). Префиксует алфа-цифровые термины."""
    q = (q or "").strip()
    db = _db()
    if not q or not db.exists():
        return []
    terms = q.split()
    match = " ".join(f"{t}*" for t in terms) if all(t.isalnum() for t in terms) else q
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT f.path,f.archive,f.size,f.category,f.ecu,f.brand "
            "FROM files_fts fts JOIN files f ON f.id=fts.rowid "
            "WHERE files_fts MATCH ? AND f.is_dir=0 "
            "ORDER BY CASE f.category WHEN 'firmware' THEN 0 WHEN 'software' THEN 1 "
            "WHEN 'document' THEN 2 ELSE 3 END, f.size DESC LIMIT ?",
            [match, limit]).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()
    return [{"path": p, "archive": a, "size": s, "category": c, "ecu": e, "brand": b}
            for p, a, s, c, e, b in rows]


PAGE = """<!doctype html><html lang=ru><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>ChipTuner — Тьютор</title>
<style>
 :root{color-scheme:dark}
 body{font:15px/1.55 system-ui,Segoe UI,sans-serif;max-width:900px;margin:0 auto;padding:16px;background:#15171c;color:#e6e6e6}
 h1{font-size:19px;color:#7ec699;margin:0 0 4px}
 a{color:#7ec699}
 .nav{font-size:13px;margin-bottom:12px;color:#8a93a6}
 .tabs{display:flex;gap:6px;margin:10px 0 16px;flex-wrap:wrap}
 .tabs button{padding:8px 13px;border:1px solid #2c3142;border-radius:8px;background:#1e2230;color:#cdd3df;cursor:pointer;font-size:14px}
 .tabs button.on{background:#2e7d4f;border-color:#2e7d4f;color:#fff}
 .lvl{margin:18px 0 6px;font-size:14px;color:#7ec699;letter-spacing:.5px;text-transform:uppercase}
 .card{background:#1e2230;border:1px solid #2c3142;border-radius:10px;padding:14px 16px;margin:10px 0}
 .card h3{margin:0 0 6px;font-size:16px;color:#a9b4c9}
 .sum{color:#8a93a6;font-size:13px;margin-bottom:8px}
 .body{white-space:pre-wrap}
 .ask{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap}
 .ask a,.chip{font-size:13px;text-decoration:none;background:#243;border:1px solid #2e7d4f;color:#bfe6cf;padding:6px 10px;border-radius:16px;cursor:pointer;display:inline-block}
 .chip{background:#1e2230;border-color:#2c3142;color:#cdd3df}
 .chip b{color:#7ec699}
 .done{outline:2px solid #2e7d4f}
 .chk{float:right;font-size:13px;color:#8a93a6;cursor:pointer;user-select:none}
 input[type=search]{width:100%;padding:10px;border-radius:8px;border:1px solid #333;background:#0e1014;color:#fff;box-sizing:border-box}
 .term{font-weight:600;color:#cfe6d8}
 .src{font-size:12px;color:#c8b88a;margin-top:4px}
 .enc{margin-top:4px;color:#cdd3df}
 .muted{color:#8a93a6;font-size:13px}
 .flash{min-height:120px;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;cursor:pointer}
 .flash .hint{font-size:12px;color:#8a93a6;margin-top:10px}
 .row{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
 .row button{padding:8px 14px;border:0;border-radius:8px;background:#2e7d4f;color:#fff;cursor:pointer}
 .row button.sec{background:#2c3142}
 .opt{display:block;width:100%;text-align:left;margin:6px 0;padding:10px;border:1px solid #2c3142;border-radius:8px;background:#1a1d27;color:#e6e6e6;cursor:pointer}
 .opt.ok{background:#1e4d33;border-color:#2e7d4f}.opt.no{background:#4d2424;border-color:#a05050}
 .prog{height:8px;background:#2c3142;border-radius:6px;overflow:hidden;margin:6px 0}
 .prog>i{display:block;height:100%;background:#2e7d4f}
 .grid{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
 .fitem{font-size:13px;border-bottom:1px solid #232838;padding:6px 0}
 .fitem .p{color:#cdd3df}.fitem .m{color:#8a93a6}
</style></head><body>
<h1>🎓 ChipTuner — Тьютор</h1>
<div class=nav><a href="/">← Чат с ботом</a> · обучение мгновенно, без ожидания модели</div>
<div class=tabs>
 <button data-t=course class=on>📚 Курс</button>
 <button data-t=archive>🗂 Темы архива</button>
 <button data-t=files>🔎 Поиск файлов</button>
 <button data-t=gloss>📖 Глоссарий</button>
 <button data-t=cards>🃏 Карточки</button>
 <button data-t=quiz>❓ Квиз</button>
</div>
<div id=view></div>
<script>
const view=document.getElementById('view');
let LESSONS=[],GLOSS=[],TOPICS={brands:[],ecus:[]},cur='course';
const esc=s=>(s||'').replace(/</g,'&lt;');
const ask=q=>'/?q='+encodeURIComponent(q);
const prog=JSON.parse(localStorage.getItem('ct_progress')||'{}');
const saveProg=()=>localStorage.setItem('ct_progress',JSON.stringify(prog));

function tab(name){cur=name;document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('on',b.dataset.t===name));
 ({course:renderCourse,archive:renderArchive,files:renderFiles,gloss:renderGloss,cards:renderCards,quiz:renderQuiz})[name]();}
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>tab(b.dataset.t));

function renderCourse(){
 const total=LESSONS.length,done=LESSONS.filter(l=>prog[l.id]).length;
 let h='<div class=card><b>Прогресс курса:</b> '+done+'/'+total+
   '<div class=prog><i style="width:'+(total?done/total*100:0)+'%"></i></div>'+
   '<span class=muted>'+total+' уроков по 3 уровням. Отмечай «изучено» — сохраняется в браузере.</span></div>';
 const levels=[...new Set(LESSONS.map(l=>l.level))];
 for(const lv of levels){
   h+='<div class=lvl>'+esc(lv)+'</div>';
   for(const l of LESSONS.filter(x=>x.level===lv)){
     h+='<div class="card'+(prog[l.id]?' done':'')+'">'+
       '<span class=chk data-id="'+l.id+'">'+(prog[l.id]?'✅ изучено':'☐ отметить')+'</span>'+
       '<h3>'+esc(l.title)+'</h3><div class=sum>'+esc(l.summary)+'</div>'+
       '<div class=body>'+esc(l.body)+'</div>';
     if(l.ask&&l.ask.length){h+='<div class=ask>';
       for(const q of l.ask)h+='<a href="'+ask(q)+'">💬 '+esc(q)+'</a>';h+='</div>';}
     h+='</div>';
   }
 }
 view.innerHTML=h;
 view.querySelectorAll('.chk').forEach(c=>c.onclick=()=>{prog[c.dataset.id]=!prog[c.dataset.id];saveProg();renderCourse();});
}

function renderArchive(){
 let h='<div class=card><b>Темы прямо из архива «Кладезь».</b> '+
   '<span class=muted>Клик по бренду или ЭБУ — бот найдёт прошивки и мануалы по теме '+
   '('+TOPICS.brands.length+' брендов, '+TOPICS.ecus.length+' семейств ЭБУ).</span></div>';
 h+='<div class=lvl>Бренды</div><div class=grid>';
 for(const b of TOPICS.brands)h+='<a class=chip href="'+ask('Какие прошивки и материалы есть для '+b.name+'? Что важно знать при тюнинге.')+'"><b>'+esc(b.name)+'</b> · '+b.count+'</a>';
 h+='</div><div class=lvl>Семейства ЭБУ</div><div class=grid>';
 for(const e of TOPICS.ecus)h+='<a class=chip href="'+ask('Расскажи про ЭБУ '+e.name+': чем читать/прошивать, особенности, чек-сумма.')+'"><b>'+esc(e.name)+'</b> · '+e.count+'</a>';
 h+='</div>';
 view.innerHTML=h;
}

async function renderFiles(){
 view.innerHTML='<input type=search id=fs placeholder="Поиск по 42 574 файлам: EDC17, Combiloader, Mercedes…" autocomplete=off>'+
   '<div id=fres class=muted style="margin-top:10px">Введи запрос…</div>';
 const fs=document.getElementById('fs'),fres=document.getElementById('fres');
 let tmr;
 async function go(){const q=fs.value.trim();if(!q){fres.innerHTML='Введи запрос…';return;}
   fres.innerHTML='<span class=muted>ищу…</span>';
   const d=await (await fetch('/api/tutor/files?q='+encodeURIComponent(q))).json();
   if(!d.length){fres.innerHTML='<span class=muted>Ничего не найдено.</span>';return;}
   fres.innerHTML='<div class=muted>Найдено (до 40):</div>'+d.map(f=>'<div class=fitem>'+
     '<div class=p>'+esc(f.path)+'</div><div class=m>['+(f.size/1e6).toFixed(1)+' MB] '+
     esc(f.category||'')+(f.ecu?' · '+esc(f.ecu):'')+(f.brand?' · '+esc(f.brand):'')+
     ' · в архиве: '+esc(f.archive)+'</div></div>').join('');}
 fs.oninput=()=>{clearTimeout(tmr);tmr=setTimeout(go,300);};fs.focus();
}

function termCard(it){return '<div class=card><span class=term>'+esc(it.term)+'</span>'+
  '<div class=enc>'+esc(it.enc||it.short)+'</div>'+
  (it.enc&&it.short?'<div class=muted style="margin-top:4px">'+esc(it.short)+'</div>':'')+
  (it.source?'<div class=src>📄 источник: '+esc(it.source)+'</div>':'')+'</div>';}
async function renderGloss(){
 view.innerHTML='<input type=search id=gs placeholder="Поиск термина: ЭБУ, чек-сумма, TriCore…" autocomplete=off>'+
   '<div id=gres style="margin-top:10px"></div>';
 const gs=document.getElementById('gs'),gres=document.getElementById('gres');
 async function go(){const d=await (await fetch('/api/tutor/glossary?q='+encodeURIComponent(gs.value))).json();
   gres.innerHTML=d.length?'<div class=muted>'+d.length+' терминов</div>'+d.map(termCard).join(''):'<div class=muted>Ничего не найдено.</div>';}
 gs.oninput=go;gs.focus();go();
}

let ci=0,flip=false;
function renderCards(){
 if(!GLOSS.length){view.innerHTML='<div class=muted>Глоссарий пуст.</div>';return;}
 const it=GLOSS[ci%GLOSS.length];
 view.innerHTML='<div class="card flash" id=fc>'+
   (flip?'<div class=enc>'+esc(it.enc||it.short)+'</div>'+(it.source?'<div class=src>📄 '+esc(it.source)+'</div>':'')
        :'<div class=term style="font-size:22px">'+esc(it.term)+'</div>')+
   '<div class=hint>'+(flip?'клик — снова термин':'клик — показать определение')+'</div></div>'+
   '<div class=row><button class=sec id=prev>← назад</button><button id=next>дальше →</button>'+
   '<span class=muted style="align-self:center">'+((ci%GLOSS.length)+1)+'/'+GLOSS.length+'</span></div>';
 document.getElementById('fc').onclick=()=>{flip=!flip;renderCards();};
 document.getElementById('next').onclick=()=>{ci++;flip=false;renderCards();};
 document.getElementById('prev').onclick=()=>{ci=(ci-1+GLOSS.length)%GLOSS.length;flip=false;renderCards();};
}

let qScore=0,qTotal=0;
function renderQuiz(){
 const pool=GLOSS.filter(g=>g.enc||g.short);
 if(pool.length<4){view.innerHTML='<div class=muted>Мало терминов для квиза.</div>';return;}
 const correct=pool[Math.floor(Math.random()*pool.length)],opts=[correct];
 while(opts.length<4){const c=pool[Math.floor(Math.random()*pool.length)];if(!opts.includes(c))opts.push(c);}
 opts.sort(()=>Math.random()-0.5);
 let h='<div class=card><div class=muted>Счёт: '+qScore+'/'+qTotal+'</div>'+
   '<h3>Что такое: <span class=term>'+esc(correct.term)+'</span>?</h3>';
 opts.forEach((o,i)=>h+='<button class=opt data-i="'+i+'">'+esc((o.enc||o.short).slice(0,140))+'</button>');
 h+='</div><div class=row><button class=sec id=skip>пропустить →</button></div>';
 view.innerHTML=h;
 view.querySelectorAll('.opt').forEach((btn,i)=>btn.onclick=()=>{
   qTotal++;if(opts[i]===correct)qScore++;
   view.querySelectorAll('.opt').forEach((b,j)=>{if(opts[j]===correct)b.classList.add('ok');else if(j===i)b.classList.add('no');b.onclick=null;});
   setTimeout(renderQuiz,900);});
 document.getElementById('skip').onclick=renderQuiz;
}

(async()=>{
 LESSONS=await (await fetch('/api/tutor/lessons')).json();
 GLOSS=await (await fetch('/api/tutor/glossary')).json();
 TOPICS=await (await fetch('/api/tutor/topics')).json();
 const start=location.hash.slice(1);
 tab(['course','archive','files','gloss','cards','quiz'].includes(start)?start:'course');
})();
</script></body></html>"""


@router.get("/tutor", response_class=HTMLResponse)
def tutor_page():
    return PAGE


@router.get("/api/tutor/lessons")
def api_lessons():
    return JSONResponse(LESSONS)


@router.get("/api/tutor/glossary")
def api_glossary(q: str = ""):
    return JSONResponse(glossary.search(cfg, q))


@router.get("/api/tutor/topics")
def api_topics():
    return JSONResponse(topics())


@router.get("/api/tutor/files")
def api_files(q: str = ""):
    return JSONResponse(file_search(q))
