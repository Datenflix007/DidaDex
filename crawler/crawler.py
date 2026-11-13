"""Canonical DidaDex crawler runtime.

The desktop launcher executes this file directly. Runtime settings are read from a
small JSON file; seed catalogues and subject aliases live in ``config/`` so that
the crawler code remains independent of the former Jupyter notebook.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parent
CONFIG_DIR = CRAWLER_DIR / "config"
MAX_RUNTIME_HOURS = 60
MAX_RUNTIME_MINUTES = MAX_RUNTIME_HOURS * 60
DEFAULT_PROFILES = {
    "TEST": dict(max_pages=2500, runtime_minutes=10, max_depth=50,
                 workers=5, max_per_host=400, max_queue=40000, pages_per_seed_turn=15),
    "STANDARD": dict(max_pages=25000, runtime_minutes=180, max_depth=50,
                     workers=6, max_per_host=7000, max_queue=150000, pages_per_seed_turn=50),
    "NACHT": dict(max_pages=250000, runtime_minutes=720, max_depth=50,
                  workers=8, max_per_host=50000, max_queue=500000, pages_per_seed_turn=100),
}


def _read_json_file(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"{label} nicht lesbar: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} enthaelt ungueltiges JSON: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} muss ein JSON-Objekt sein: {path}")
    return value


def _member(path: Path, name: str, label: str):
    value = _read_json_file(path, label).get(name)
    if not isinstance(value, dict):
        raise RuntimeError(f"{label}: Schluessel {name!r} fehlt oder ist ungueltig.")
    return value


def _setting(raw: dict, *names: str, default):
    for name in names:
        if name in raw:
            return raw[name]
    return default


def _apply_runtime_config(raw: dict | None = None, stop_file: Path | None = None) -> None:
    raw = dict(raw or {})
    mode = str(_setting(raw, "mode", "MODUS", default="TEST")).upper()
    if mode not in DEFAULT_PROFILES:
        raise ValueError("MODUS muss TEST, STANDARD oder NACHT sein.")
    defaults = DEFAULT_PROFILES[mode]
    supplied_profile = _setting(raw, "profile", "PROFILE", default={})
    if not isinstance(supplied_profile, dict):
        raise ValueError("profile muss ein Objekt sein.")

    def profile_value(name: str) -> int:
        return int(supplied_profile.get(name, raw.get(name, defaults[name])))

    profile = {name: profile_value(name) for name in (
        "runtime_minutes", "max_pages", "max_depth", "workers", "max_per_host", "max_queue"
    )}
    profile["pages_per_seed_turn"] = int(_setting(
        raw, "seed_pages", "pages_per_seed_turn", default=defaults["pages_per_seed_turn"]
    ))
    run_name = str(_setting(
        raw, "run_name", "RUN_NAME", default=datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    ))
    subjects = _setting(raw, "subjects", "SUBJECT_FILTER", default=[])
    if not isinstance(subjects, list):
        raise ValueError("subjects muss eine Liste sein.")
    aliases = globals().get("SUBJECT_ALIASES", {})
    if aliases:
        subjects = [str(subject) for subject in subjects if str(subject) in aliases]

    values = {
        "MODUS": mode,
        "START_CRAWL": bool(_setting(raw, "start_crawl", "START_CRAWL", default=True)),
        "RUN_NAME": run_name,
        "TARGET_MIB": int(_setting(raw, "target_mib", "TARGET_MIB", default=500)),
        "DOWNLOAD_MATERIALS": bool(_setting(raw, "DOWNLOAD_MATERIALS", default=True)),
        "ONLY_OPEN_LICENSE_MATERIALS": bool(_setting(raw, "ONLY_OPEN_LICENSE_MATERIALS", default=True)),
        "CHECK_LICENSE_IN_PDFS": bool(_setting(raw, "CHECK_LICENSE_IN_PDFS", default=True)),
        "SITEMAPS_AKTIV": bool(_setting(raw, "SITEMAPS_AKTIV", default=True)),
        "MAX_ROBOTS_SITEMAPS_PER_HOST": int(_setting(raw, "MAX_ROBOTS_SITEMAPS_PER_HOST", default=4)),
        "QUELLEN_UEBERGREIFEND": bool(_setting(raw, "QUELLEN_UEBERGREIFEND", default=False)),
        "RETRY_LEGACY_REDIRECT_ERRORS": bool(_setting(raw, "RETRY_LEGACY_REDIRECT_ERRORS", default=True)),
        "MIN_TEXT_CHARS": int(_setting(raw, "MIN_TEXT_CHARS", default=500)),
        "MAX_MATERIAL_MIB": int(_setting(raw, "MAX_MATERIAL_MIB", default=24)),
        "DOWNLOAD_DELAY_SECONDS": float(_setting(raw, "DOWNLOAD_DELAY_SECONDS", default=1.5)),
        "MAX_TEXT_CHARS": int(_setting(raw, "MAX_TEXT_CHARS", default=400000)),
        "DYNAMIC_DEPTH": bool(_setting(raw, "DYNAMIC_DEPTH", default=True)),
        "DEPTH_SOFT_START": int(_setting(raw, "DEPTH_SOFT_START", default=5)),
        "DEPTH_HARD_LIMIT": int(_setting(raw, "DEPTH_HARD_LIMIT", default=200)),
        "DFS_DEPTH_STEP": int(_setting(raw, "dfs_depth_step", "DFS_DEPTH_STEP", default=5)),
        "DEPTH_HEATMAP_INTERVAL": int(_setting(raw, "DEPTH_HEATMAP_INTERVAL", default=30)),
        "FAIR_HOST_SCHEDULING": bool(_setting(raw, "FAIR_HOST_SCHEDULING", default=True)),
        "STORE_BINARY_MATERIALS": bool(_setting(raw, "STORE_BINARY_MATERIALS", default=False)),
        "STORE_CRAWL_EDGES": bool(_setting(raw, "STORE_CRAWL_EDGES", default=False)),
        "SUBJECT_FILTER": subjects,
        "INCLUDE_GENERAL_METHODS": bool(_setting(raw, "INCLUDE_GENERAL_METHODS", default=True)),
        "PROFILE": profile,
        "_DIDA_STOP_FILE": Path(stop_file) if stop_file else CRAWLER_DIR / ".didadex_stop_manual",
    }
    if not run_name.replace("_", "").replace("-", "").isalnum():
        raise ValueError("RUN_NAME enthaelt ungueltige Zeichen.")
    if not 0 < values["DEPTH_HARD_LIMIT"] <= 200:
        raise ValueError("DEPTH_HARD_LIMIT muss zwischen 1 und 200 liegen.")
    if not 0 <= values["DEPTH_SOFT_START"] < values["DEPTH_HARD_LIMIT"]:
        raise ValueError("DEPTH_SOFT_START muss kleiner als DEPTH_HARD_LIMIT sein.")
    if not 1 <= values["DFS_DEPTH_STEP"] <= 200:
        raise ValueError("DFS_DEPTH_STEP muss zwischen 1 und 200 liegen.")
    if not 1 <= profile["pages_per_seed_turn"] <= 1000:
        raise ValueError("pages_per_seed_turn muss zwischen 1 und 1000 liegen.")
    if not 1 <= profile["runtime_minutes"] <= MAX_RUNTIME_MINUTES:
        raise ValueError(
            f"runtime_minutes muss zwischen 1 und {MAX_RUNTIME_MINUTES} liegen "
            f"(maximal {MAX_RUNTIME_HOURS} Stunden)."
        )
    globals().update(values)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="DidaDex crawler runtime")
    parser.add_argument("--config", type=Path, help="JSON-Datei mit Laufkonfiguration")
    parser.add_argument("--stop-file", type=Path, help="vom Launcher gesetztes Stoppsignal")
    return parser.parse_args(argv)


def _format_runtime(minutes: int) -> str:
    hours, remaining_minutes = divmod(int(minutes), 60)
    if hours and remaining_minutes:
        return f"{hours} h {remaining_minutes} min"
    if hours:
        return f"{hours} h"
    return f"{remaining_minutes} min"


_apply_runtime_config({})

# Seed catalogues are data, not executable runner source.
from urllib.parse import urlsplit

_CATALOG = _read_json_file(CONFIG_DIR / "sources.json", "Quellkatalog")
SOURCES = _CATALOG.get("sources")
if not isinstance(SOURCES, dict):
    raise RuntimeError("Quellkatalog: sources fehlt oder ist ungueltig.")


def add_source(source_id, priority, hosts, seeds):
    entry = SOURCES.setdefault(
        source_id,
        {"priority": priority, "hosts": [], "seeds": []},
    )
    entry["priority"] = min(entry.get("priority", "P3"), priority)
    seed_hosts = [
        (urlsplit(seed).hostname or "").lower()
        for seed in seeds
        if (urlsplit(seed).hostname or "")
    ]
    entry["hosts"] = list(dict.fromkeys(entry["hosts"] + hosts + seed_hosts))
    entry["seeds"] = list(dict.fromkeys(entry["seeds"] + seeds))


for row in _CATALOG.get("extended_sources", []):
    if not isinstance(row, dict):
        raise RuntimeError("Quellkatalog: ungueltiger erweiterter Quelleneintrag.")
    add_source(row["source_id"], row["priority"], row["hosts"], row["seeds"])

SEED_EXTENSIONS = _member(CONFIG_DIR / "seed_extensions.json", "extensions", "Seed-Ergaenzungen")
for source_id, more_seeds in SEED_EXTENSIONS.items():
    if source_id in SOURCES:
        add_source(
            source_id,
            SOURCES[source_id].get("priority", "P1"),
            SOURCES[source_id]["hosts"],
            more_seeds,
        )

SEEDS = list(dict.fromkeys(url for cfg in SOURCES.values() for url in cfg["seeds"]))
HOST_TO_SOURCE = {host.lower(): source_id for source_id, cfg in SOURCES.items() for host in cfg["hosts"]}
ALLOWED_HOSTS = set(HOST_TO_SOURCE)
SITE_LICENSE = _CATALOG.get("site_license", {})
if not isinstance(SITE_LICENSE, dict):
    raise RuntimeError("Quellkatalog: site_license ist ungueltig.")


def print_source_summary():
    print(f"{len(SEEDS)} Seed-URLs, {len(SOURCES)} Quellengruppen, {len(ALLOWED_HOSTS)} freigegebene Hostnamen", flush=True)
    for source_id, cfg in SOURCES.items():
        print(f" - {source_id}: {len(cfg['seeds'])} Seeds", flush=True)


import concurrent.futures, gzip, hashlib, html, io, json, re, sqlite3, threading, time
import urllib.robotparser, zipfile
from collections import Counter, defaultdict
from csv import writer as csv_writer
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, urljoin, parse_qsl, urlencode
from xml.etree import ElementTree as ET
import requests
from bs4 import BeautifulSoup

USER_AGENT = 'EducationalIRCrawler/1.0 (academic educational materials research; respects robots.txt)'
TRACKING = {'fbclid','gclid','_ga','_gl','msclkid','ref_src'}
SUFFIXES = ('.pdf','.docx','.pptx','.odt','.odp','.txt')
NEG_URL = re.compile(r'(^|[/_?&=-])(datenschutz|impressum|login|logout|register|registrierung|anmelden|cookie|privacy|agb|faq|kontakt|contact|profil|account|newsletter|user:|benutzer:|hilfe:|help:|vorlage:|template:|spezial:|special:|discussion|diskussion)([/_?&=-]|$)', re.I)
NEG_TITLE = re.compile(r'^(datenschutz|impressum|kontakt|faq|cookies|agb|registrieren|links auf diese seite|benutzer:|vorlage:|hilfe:|spezial:)',re.I)
OVERVIEW = re.compile(r'(überblick|übersicht|startseite|inhaltsverzeichnis|alle materialien|themenblätter im unterricht|methoden- und spielekiste|materialien für mehr sicherheit im netz|fachzeitschriften|literaturverzeichnis|linkliste|linksammlung|webkatalog|fachportale)',re.I)
PATH_OVERVIEW = {'/','/unterrichtseinheiten','/wiki/unterrichtsmethoden','/unterrichtsmethoden','/wiki/unterrichtsideen','/wiki/methode','/lernen/angebote','/shop/materialien/themenblaetter','/downloads','/materialien','/arbeitsblaetter','/unterrichtsbausteine','/unterrichtsvorschlaege'}
LINK_HINT = re.compile(r'unterricht|arbeitsblatt|material|methode|didakt|lernpfad|lernbaustein|lernmodul|verlauf|stundenentwurf|bildung|schule|oer|download|aufgabe|geschichte|informatik|physik|chemie|geographie|mathematik|politik|lesson|worksheet|wiki|uebung|übung',re.I)
# Spezifische Linksignale für *tiefe* Navigation; "wiki" oder "schule"
# allein sind zu unspezifisch für eine Relevanzentscheidung.
DEEP_LINK_HINT = re.compile(r'arbeitsblatt|unterrichtseinheit|unterrichtsstunde|stundenentwurf|'
    r'aufgabe|lernmodul|lernpfad|lernstation|unterrichtsmaterial|'
    r'didakt|method|kompetenz|material|download|ueber|übung|worksheet|lesson',re.I)
GRADE_PATTERN = re.compile(r'\b(?:klasse|klassenstufe|jahrgangsstufe|jahrgang)\s*(?:\d{1,2})(?:\s*[-–]\s*\d{1,2})?',re.I)
PHASE_TERMS = ('einstieg','erarbeitung','sicherung','reflexion','transfer')
SOCIAL_TERMS = ('einzelarbeit','partnerarbeit','gruppenarbeit','plenum','gruppenpuzzle','stationenlernen')
SUBJECT_ALIASES = _member(CONFIG_DIR / "subject_aliases.json", "subjects", "Fach-Aliase")
SUBJECT_TERMS = tuple(x.lower() for x in SUBJECT_ALIASES)
SUBJECT_FILTER = [x for x in globals().get('SUBJECT_FILTER', []) if x in SUBJECT_ALIASES]
INCLUDE_GENERAL_METHODS = bool(globals().get('INCLUDE_GENERAL_METHODS', True))
def subject_evidence(title='', url='', headings=(), text=''):
    """Konservative zweistufige Erkennung: stärkere Evidenz in Titel/URL/Überschriften."""
    strong=' '.join([title,url,*headings]).casefold()
    short=text[:10000].casefold()
    results={}
    for subject,aliases in SUBJECT_ALIASES.items():
        hits=[];score=0
        for alias in aliases:
            pat=r'(?<!\w)'+re.escape(alias.casefold())+r'(?!\w)'
            if re.search(pat,strong):score+=4;hits.append('Titel/URL: '+alias)
            elif re.search(pat,short):score+=1;hits.append('Text: '+alias)
        if score:results[subject]={'score':score,'evidence':hits[:5]}
    return results

def subject_decision(title,url,headings,text,kind=''):
    """Unbekannte Themen bleiben zur Navigation zugelassen, nicht im Fachindex."""
    detected=subject_evidence(title,url,headings,text)
    if not SUBJECT_FILTER:return True,detected
    if any(detected.get(x,{}).get('score',0)>=2 for x in SUBJECT_FILTER):return True,detected
    generic_method = kind in ('teaching_method','didactic_guide') and not any(
        info['score']>=4 for info in detected.values())
    return bool(INCLUDE_GENERAL_METHODS and generic_method),detected


def didactic_metadata(title, text, headings):
    """Nur belegbare Textsignale ausgeben; keine Modellvermutungen."""
    intro=' '.join([title]+list(headings))+'\n'+text[:18000]
    grade=GRADE_PATTERN.search(intro)
    return {'grade_evidence':grade.group(0) if grade else None,
            'subjects_mentioned':[x for x in SUBJECT_TERMS if re.search(r'\b'+x+r'\b',intro,re.I)],
            'phases_mentioned':[x for x in PHASE_TERMS if re.search(r'\b'+x+r'\b',intro,re.I)],
            'social_forms_mentioned':[x for x in SOCIAL_TERMS if re.search(r'\b'+x+r'\b',intro,re.I)]}

TASK = re.compile(r'arbeitsauftr[aä]g|arbeitsanweis|aufgabenstellung|aufgabe\s*\d+|bearbeite|analysiere|vergleiche|diskutiere|untersuche|recherchiere|erarbeite|arbeitsblatt|lernauftrag|worksheet',re.I)
LESSON = re.compile(r'unterrichtsverlauf|verlaufsplan|stundenverlauf|stundenentwurf|unterrichtsphase|einstiegsphase|erarbeitungsphase|sicherungsphase|zeitbedarf|unterrichtseinheit|unterrichtsstunde|unterrichtsmodul|45\s*min|90\s*min',re.I)
METHOD = re.compile(r'methodische\s+(hinweise|anregungen|umsetzung)|methodenbeschreibung|sozialform|gruppenpuzzle|partnerarbeit|gruppenarbeit|stationenlernen|rollenspiel|fishbowl|methodik|methodisch.didaktisch',re.I)
DIDACTIC = re.compile(r'didaktische\s+(hinweise|anregungen|kommentar|handreichung)|lehrerhandreichung|handreichung\s+f[uü]r|unterrichtsvorschlag|lernziel|lernziele|kompetenzziel|differenzierung|sekundarstufe|unterrichtsmaterial|lehrkr[aä]fte',re.I)
DOCUMENT_TITLE = re.compile(r'unterricht|arbeitsblatt|lernpfad|methode|aufgabe|handreichung|stunde|unterrichtsvorschlag',re.I)
CC = re.compile(r'\b(?:CC[ -]?(?:BY(?:[ -](?:SA|NC(?:[ -]SA)?))?|0)|CC0|public domain)\b',re.I)


def utc(): return datetime.now(timezone.utc).isoformat()


def canon(url,preserve_trailing_slash=False):
    try:
        u=html.unescape(url or '').strip()
        p=urlsplit(u)
        h=(p.hostname or '').lower()
        if p.scheme not in ('http','https') or not h or h not in ALLOWED_HOSTS or p.username or p.password or p.port not in (None,80,443) or len(u)>2048:
            return ''
        path=re.sub(r'/{2,}','/',p.path or '/')
        # Ein abschließender Slash kann bei CMS eine andere Route bedeuten.
        # Nur für die Redirect-Folge bewahren wir ihn; die Frontier bleibt
        # weiterhin bei der bisherigen, slashlosen Deduplizierung.
        if not preserve_trailing_slash:path=path.rstrip('/') or '/'
        query=urlencode([(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if k.lower() not in TRACKING and not k.lower().startswith(('utm_','mtm_','pk_'))])
        return urlunsplit(('https',h,path,query,''))
    except Exception:return ''
canonical=canon


def relevant_path(u,seed=False):
    p=urlsplit(u); path=p.path.lower()
    if NEG_URL.search(path+'?'+p.query): return False
    if path.endswith(('.css','.js','.jpg','.jpeg','.png','.webp','.gif','.svg','.mp3','.mp4','.zip','.exe','.woff','.woff2','.ico')):return False
    if seed or path.endswith(SUFFIXES):return True
    if re.search(r'/(?:api|wp-json|feed|rss|atom|search|suche)(?:/|$)',path,re.I):return False
    if re.search(r'(?:^|[?&])(?:action|oldid|diff|printable|format|output)=',p.query,re.I):return False
    # Kein bloßes Schlagwort-Gate: auch Lektionen, Kapitel und PDF-Verweise
    # in scheinbar generischen URL-Pfaden erreichen.
    return True


def clean_text(text):
    lines=[re.sub(r'\s+',' ',x).strip() for x in (text or '').splitlines()]
    return '\n'.join(x for x in lines if x)[:MAX_TEXT_CHARS]


def license_from_html(soup, u):
    if urlsplit(u).hostname in SITE_LICENSE:return SITE_LICENSE[urlsplit(u).hostname]
    for tag in soup.select('link[rel~=license],a[rel~=license],meta[name*=license],meta[name*=rights],meta[property*=license]'):
        value=tag.get('href') or tag.get('content') or tag.get_text(' ',strip=True)
        if value and ('creativecommons.org/licenses/' in value.lower() or CC.search(value)):
            return value[:250]
    return ''


def license_from_pdf_text(text):
    for match in CC.finditer(text):
        around=text[max(0,match.start()-150):match.end()+100].lower()
        if re.search(r'lizen[sz]iert|lizenz|creative commons|dieses werk|dieses material|steht unter|veröffentlicht unter|licensed under',around):
            return match.group().upper()
    return ''


def parse_html(raw,u):
    soup=BeautifulSoup(raw,'lxml')
    title=soup.title.get_text(' ',strip=True) if soup.title else ''
    h1=soup.find('h1')
    if h1 and (h1.get_text(' ',strip=True).lower() not in title.lower()):title=h1.get_text(' ',strip=True)
    lic=license_from_html(soup,u)
    main=None
    for css in ('.mw-parser-output','article .entry-content','article','main','[role=main]','#content','.content'):
        choice=soup.select_one(css)
        if choice and len(choice.get_text(' ',strip=True))>=140:
            main=choice;break
    main=main or soup.body or soup
    links=[]
    for a in main.select('a[href]'):
        link=canon(urljoin(u,a['href']))
        if link:links.append((link,a.get_text(' ',strip=True)[:130]))
    for node in main.select('script,style,noscript,header,footer,nav,aside,form,button,svg,iframe,.mw-editsection,.toc,.navbox,.catlinks,.printfooter,.breadcrumb,.breadcrumbs,.sidebar,.social-share,[role=navigation]'):
        node.decompose()
    headings=[x.get_text(' ',strip=True) for x in main.select('h1,h2,h3')][:55]
    canonical_tag=soup.select_one('link[rel=canonical]')
    declared=canon(urljoin(u,canonical_tag.get('href',''))) if canonical_tag else ''
    return {'title':title or urlsplit(u).path.split('/')[-1], 'text':clean_text(main.get_text('\n',strip=True)),
            'headings':headings,'links':list(dict.fromkeys(links)), 'license':lic,'canonical':declared or u}


def classify(title,u,text,headings,links):
    path=urlsplit(u).path.lower().rstrip('/') or '/'
    base=re.split(r'\s+[|–—]\s+',title,maxsplit=1)[0].strip().lower()
    if NEG_URL.search(path) or NEG_TITLE.search(title):return 'excluded',0,['negative_title_or_url'],False
    if re.search(r'\b(?:standards|suchergebnisse|suchresultate|trefferliste|fachzeitschriften|rahmenlehrplan)\b',base,re.I) or ('/suche' in path and 'material' in path):
        return 'overview',0,['curriculum_or_search_results'],False
    if path in PATH_OVERVIEW or OVERVIEW.search(base) or re.search(r"(?:^|/)(?:kategorie:|category:|tag/)",path,re.I) or base in ('unterrichtsmethoden','unterrichtsideen','angebote'):
        return 'overview',0,['overview_navigation_only'],False
    # Große Linklisten und reine Kategorien enthalten häufig zufällig Wörter wie
    # "Aufgabe", "Unterricht", etc., sind aber selbst kein Unterrichtsmaterial.
    link_density=len(links)/max(1,len(text)/1000)
    if (re.search(r'(?:/wiki/)?(?:kategorie:|category:)',path,re.I)
        or (len(links)>=35 and link_density>=12 and not TASK.search(text[:2200]))):
        return 'overview',0,['link_collection'],False
    blob=' '.join([title,*headings,text]);ev={
        'task':bool(TASK.search(blob)),
        'lesson':bool(LESSON.search(blob)) or bool(re.search(r'\bmodul\s*\d+\b',blob[:1200],re.I) and re.search(r'\bUE[- –]?[a-z]\b|material. und arbeitsblätter',blob,re.I)),
        'method':bool(METHOD.search(blob)), 'didactic':bool(DIDACTIC.search(blob)),
        'attachment':any(urlsplit(x).path.lower().endswith(SUFFIXES) for x,_ in links)}
    score=3*sum(ev[k] for k in ('task','lesson','method','didactic'))+int(ev['attachment'])+int(len(text)>1600)+int(bool(DOCUMENT_TITLE.search(title)))
    reasons=[k for k,v in ev.items() if v]
    accepted=(len(text)>=MIN_TEXT_CHARS and sum(ev[k] for k in ('task','lesson','method','didactic'))>=2 and score>=7 and link_density<28)
    # Ein Fachartikel darf nicht allein wegen vieler zufälliger didaktischer
    # Wörter als Stundenentwurf gelten. Konkrete Aktivität ODER methodische Anleitung.
    has_concrete = bool(TASK.search(text[:14000])) or bool(LESSON.search(text[:14000])) or bool(METHOD.search(title+' '+' '.join(headings)))
    accepted = accepted and has_concrete
    if not accepted:return ('review_candidate' if reasons else 'other'),score,reasons,False
    if ev['task'] and ev['lesson']:kind='lesson_plan'
    elif ev['method'] and ev['didactic']:kind='didactic_guide'
    elif ev['task'] and re.search(r'arbeitsblatt|worksheet',title,re.I):kind='worksheet'
    elif ev['method']:kind='teaching_method'
    elif ev['didactic'] and ev['lesson']:kind='didactic_guide'
    else:kind='teaching_activity'
    return kind,score,reasons,True


def parse_document(raw,ext):
    if ext=='.pdf':
        if not raw.startswith(b'%PDF'):raise ValueError('invalid pdf')
        from pypdf import PdfReader
        return clean_text('\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(raw),strict=False).pages[:250]))
    if ext=='.docx':
        from docx import Document
        doc=Document(io.BytesIO(raw))
        return clean_text('\n'.join([p.text for p in doc.paragraphs]+[' | '.join(c.text for c in r.cells) for t in doc.tables for r in t.rows]))
    if ext=='.pptx':
        from pptx import Presentation
        slides=Presentation(io.BytesIO(raw)).slides
        return clean_text('\n'.join(sh.text for sl in slides for sh in sl.shapes if sh.has_text_frame))
    if ext in ('.odt','.odp'):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:root=ET.fromstring(z.read('content.xml'))
        return clean_text('\n'.join(' '.join(e.itertext()) for e in root.iter() if e.tag.endswith(('}p','}h'))))
    if ext=='.txt':return clean_text(raw.decode('utf-8-sig',errors='replace'))
    raise ValueError('unsupported document')


def ext_from(u,headers):
    path=urlsplit(u).path.lower()
    for x in SUFFIXES:
        if path.endswith(x):return x
    mime=headers.get('Content-Type','').lower()
    for m,x in [('application/pdf','.pdf'),('wordprocessingml','.docx'),('presentationml','.pptx'),('opendocument.text','.odt'),('text/plain','.txt')]:
        if m in mime:return x
    return ''

class TeachingCrawler:
    def __init__(self,out):
        # Older saved runtime configs can omit this key; retain a safe default.
        globals()['DFS_DEPTH_STEP']=int(globals().get('DFS_DEPTH_STEP',5))
        PROFILE.setdefault('pages_per_seed_turn', {'TEST':15,'STANDARD':50,'NACHT':100}.get(MODUS,20))
        self.dir=Path(out);self.dir.mkdir(parents=True,exist_ok=True)
        self.material_dir=self.dir/'materials';self.material_dir.mkdir(exist_ok=True)
        self.db=sqlite3.connect(self.dir/'crawler_state.sqlite',check_same_thread=False,timeout=40)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA busy_timeout=40000')
        self.db.execute("""CREATE TABLE IF NOT EXISTS frontier (
            url TEXT PRIMARY KEY,kind TEXT,depth INTEGER,priority INTEGER,parent TEXT,
            inherited_license TEXT,status TEXT DEFAULT 'queued',error TEXT)""")
        # Migration: vorhandene Läufe bleiben wiederaufnehmbar.
        frontier_columns={r[1] for r in self.db.execute('PRAGMA table_info(frontier)')}
        if 'relevance' not in frontier_columns:
            self.db.execute('ALTER TABLE frontier ADD COLUMN relevance INTEGER DEFAULT 0')
        # Neue, ausschließlich additive Spalte: Ein URL gehört genau einem Seed-
        # Suchbaum (erste Entdeckung gewinnt). Bestehende URLs bleiben erhalten.
        migrated_roots = 'root_seed' not in frontier_columns
        if migrated_roots:
            self.db.execute('ALTER TABLE frontier ADD COLUMN root_seed TEXT')
        self.db.execute("CREATE INDEX IF NOT EXISTS frontier_pick ON frontier(status,depth,priority DESC)")
        self.db.execute("CREATE INDEX IF NOT EXISTS frontier_seed_dfs ON frontier(root_seed,status,depth DESC,priority DESC)")
        self.db.execute("""CREATE TABLE IF NOT EXISTS seed_schedule (
            root_seed TEXT PRIMARY KEY, ordinal INTEGER NOT NULL,
            turns INTEGER NOT NULL DEFAULT 0,
            claimed_pages INTEGER NOT NULL DEFAULT 0)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS documents (
            docno TEXT PRIMARY KEY,url TEXT UNIQUE,title TEXT,body TEXT,fingerprint TEXT UNIQUE,
            doc_type TEXT,source TEXT,license TEXT,parent TEXT,metadata TEXT)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS crawl_depth_stats (
            host TEXT NOT NULL, depth INTEGER NOT NULL, status TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(host,depth,status))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS crawl_edges (
            parent_url TEXT NOT NULL, child_url TEXT NOT NULL,
            anchor TEXT, depth INTEGER, PRIMARY KEY(parent_url,child_url))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS material_links (
            url TEXT PRIMARY KEY,parent TEXT,license TEXT,created TEXT)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS files (
            url TEXT PRIMARY KEY,path TEXT,size INTEGER,text_chars INTEGER,status TEXT,license TEXT,parent TEXT)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS crawl_decisions (
            url TEXT PRIMARY KEY, host TEXT, depth INTEGER, decision TEXT, reason TEXT,
            subject_score INTEGER DEFAULT 0)""")
        self.db.execute("UPDATE frontier SET status='queued' WHERE status='running'")
        self._prepare_seed_schedule(migrate=migrated_roots)
        self.requeued_legacy_redirects=0
        if globals().get('RETRY_LEGACY_REDIRECT_ERRORS',True):
            cur=self.db.execute("UPDATE frontier SET status='queued',error='' WHERE status='error' AND error='too_many_redirects'")
            self.requeued_legacy_redirects=max(0,cur.rowcount)
        self.db.commit()
        self.lock=threading.RLock();self.stop=threading.Event()
        self.active_seed_roots=set()
        self.sessions=threading.local();self.host_locks=defaultdict(threading.Lock)
        self.host_last=defaultdict(float);self.robots={};self.robot_sitemap_urls=set();self.host_count=Counter();self.stats=Counter()
        self.start_time=time.monotonic();self.last_progress=0;self.last_heatmap=0
        self.last_live_status=0
        self.seen_count=self.db.execute('SELECT COUNT(*) FROM frontier').fetchone()[0]
        self.processed=self.db.execute("SELECT COUNT(*) FROM frontier WHERE status IN ('done','error','blocked') AND kind!='sitemap'").fetchone()[0]
        for (u,) in self.db.execute("SELECT url FROM frontier WHERE status='done'"):
            self.host_count[urlsplit(u).hostname]+=1
        self.subject_filter = SUBJECT_FILTER[:]
        self.document_bytes=0
        for id_,u,t,body in self.db.execute('SELECT docno,url,title,body FROM documents'):
            self.document_bytes+=len((json.dumps({'docno':id_,'url':u,'title':t,'text':body},ensure_ascii=False)+'\n').encode('utf-8'))
        self.log_file=(self.dir/'progress.log').open('a',encoding='utf-8')
        if self.requeued_legacy_redirects:
            self.log(f'Resume: {self.requeued_legacy_redirects} alte Redirectfehler werden mit korrigierter URL-Behandlung erneut versucht.')
        # Auch beim Resume neue Seeds erfassen (dedupliziert).
        self.seed_frontier()
        self.write_live_status(force=True)
        self.log(f'Bereit: {self.seen_count} URLs in der Warteschlange, {self.processed} verarbeitet, '
                 f'{self.db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]} indexiert')

    def _prepare_seed_schedule(self, migrate=False):
        """Persistente Seed-Zuordnung. Migriert alte SQLite-Läufe ohne Re-Crawl.

        Die Zuordnung ist pro URL eindeutig: Ein späterer zweiter Seed kann
        dieselbe URL nicht erneut enqueuen. Für ältere Läufe wird die bekannte
        Elternkette höchstens 50 Tiefenstufen nachverfolgt.
        """
        self.default_seed_for_host={}
        self.curated_seeds_set={canon(seed) for seed in SEEDS if canon(seed)}
        for order, seed in enumerate(SEEDS):
            normalized=canon(seed)
            if not normalized: continue
            host=urlsplit(normalized).hostname
            self.default_seed_for_host.setdefault(host,normalized)
            self.db.execute('INSERT OR IGNORE INTO seed_schedule(root_seed,ordinal) VALUES (?,?)',
                            (normalized,order))
        if migrate:
            for seed in SEEDS:
                normalized=canon(seed)
                if normalized:
                    self.db.execute('UPDATE frontier SET root_seed=? WHERE url=? AND root_seed IS NULL',
                                    (normalized,normalized))
            # Tiefen-0-Einträge aus alten Sitemaps erhalten einen regulären
            # Seed ihres Hosts, statt tausende künstliche neue Seeds zu bilden.
            roots=self.db.execute('SELECT url FROM frontier WHERE depth=0 AND root_seed IS NULL').fetchall()
            for (u,) in roots:
                assigned=self.default_seed_for_host.get(urlsplit(u).hostname,u)
                self.db.execute('UPDATE frontier SET root_seed=? WHERE url=?',(assigned,u))
            for depth in range(1,DEPTH_HARD_LIMIT+1):
                self.db.execute("""UPDATE frontier SET root_seed=(
                     SELECT parent_node.root_seed FROM frontier AS parent_node
                     WHERE parent_node.url=frontier.parent)
                     WHERE root_seed IS NULL AND depth=? AND parent IS NOT NULL""", (depth,))
            # Nach Redirects fehlen gelegentlich Eltern-URLs in der Frontier.
            # Diese Altlasten werden nach Host einem kuratierten Seed zugeordnet.
            for (u,) in self.db.execute('SELECT url FROM frontier WHERE root_seed IS NULL').fetchall():
                assigned=self.default_seed_for_host.get(urlsplit(u).hostname,u)
                self.db.execute('UPDATE frontier SET root_seed=? WHERE url=?',(assigned,u))
        # Wiederaufgenommene Laufdaten können alte/zusätzliche Roots enthalten.
        roots=self.db.execute('SELECT DISTINCT root_seed FROM frontier WHERE root_seed IS NOT NULL').fetchall()
        for i,(root,) in enumerate(roots):
            self.db.execute('INSERT OR IGNORE INTO seed_schedule(root_seed,ordinal) VALUES (?,?)',
                            (root,len(SEEDS)+i))

    def _root_for_new_url(self, url, parent='', root_seed=None, seed=False):
        """Explizite Zuordnung ist bei Redirects nötig (Parent ggf. nicht gespeichert)."""
        if root_seed:
            return root_seed
        if seed and url in self.curated_seeds_set:
            return url
        if parent:
            row=self.db.execute('SELECT root_seed FROM frontier WHERE url=?',(parent,)).fetchone()
            if row and row[0]: return row[0]
        return self.default_seed_for_host.get(urlsplit(url).hostname,url)

    def acquire_seed(self):
        """Wählt faire Seed-Runde; höchstens ein Worker bearbeitet denselben Seed.

        Jeder Seed hat eine separate DFS-Frontier. Weniger oft bediente Seeds
        kommen zuerst; bei Gleichstand gilt die Reihenfolge der Seed-Liste.
        """
        with self.lock:
            pending=self.db.execute("""
                SELECT s.root_seed,s.turns FROM seed_schedule AS s
                WHERE EXISTS(SELECT 1 FROM frontier f
                             WHERE f.root_seed=s.root_seed AND f.status='queued')
                ORDER BY s.turns ASC,s.ordinal ASC""").fetchall()
            # Unterschiedliche Hosts parallel: Die Host-Sperre würde ansonsten
            # alle Worker am zuerst gelisteten Bildungsserver blockieren.
            active_hosts={urlsplit(seed).hostname for seed in self.active_seed_roots}
            for seed, turns in pending:
                if seed in self.active_seed_roots or (FAIR_HOST_SCHEDULING and
                        urlsplit(seed).hostname in active_hosts):
                    continue
                self.active_seed_roots.add(seed)
                self.db.execute('UPDATE seed_schedule SET turns=turns+1 WHERE root_seed=?',(seed,))
                self.db.commit()
                depth_cap=min(DEPTH_HARD_LIMIT,PROFILE['max_depth'],
                              max(0, (turns+1)*DFS_DEPTH_STEP))
                return seed,depth_cap,turns+1
            return None

    def release_seed(self,seed):
        with self.lock:
            self.active_seed_roots.discard(seed)

    def claim_seed(self,seed,depth_cap):
        """DFS: tiefste offene URL zuerst; Relevanz bricht Gleichstände.

        ORDER BY depth DESC ist absichtlich anders als bisheriges BFS (ASC).
        Das Limit je Seed-Runde und der wechselnde Seed verhindern Monopole.
        """
        with self.lock:
            row=self.db.execute("""SELECT url,kind,depth,priority,parent,inherited_license,relevance
                FROM frontier WHERE root_seed=? AND status='queued' AND depth<=?
                ORDER BY depth DESC,priority DESC,rowid DESC LIMIT 1""",
                (seed,depth_cap)).fetchone()
            if not row:return None
            self.db.execute("UPDATE frontier SET status='running' WHERE url=?",(row[0],))
            self.db.execute('UPDATE seed_schedule SET claimed_pages=claimed_pages+1 WHERE root_seed=?',(seed,))
            self.db.commit()
            return row

    def log(self,message):
        with self.lock:
            line=f'[{datetime.now().strftime("%H:%M:%S")}] {message}'
            print(line,flush=True);self.log_file.write(line+'\n');self.log_file.flush()

    def write_live_status(self, force=False):
        """Kleine, atomare Statusdatei für das Tkinter-Live-Dashboard.

        Alle Zahlen stammen aus dem tatsächlichen SQLite-/Crawler-Zustand.
        Die Statusdatei ist KEIN zweiter Korpus und enthält keine Volltexte.
        Ein Throttle vermeidet zusätzliche I/O-Last pro Seite.
        """
        now=time.monotonic()
        if not force and now-self.last_live_status<2.0:
            return
        with self.lock:
            now=time.monotonic()
            if not force and now-self.last_live_status<2.0:
                return
            self.last_live_status=now
            payload={'run':RUN_NAME,'updated_at':utc(),
                     'processed':int(self.processed),
                     'indexed':int(self.db.execute('SELECT COUNT(*) FROM documents').fetchone()[0]),
                     'document_bytes':int(self.document_bytes),
                     'active_seed_roots':len(self.active_seed_roots),
                     'errors':int(self.stats['fetch_or_parse_error']),
                     'target_mib':int(TARGET_MIB)}
            output=self.dir/'crawler_live.json'
            temp=self.dir/'crawler_live.json.tmp'
            try:
                temp.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
                temp.replace(output)
            except OSError:
                # Telemetry is optional; a status-file failure must not abort
                # a productive crawl or interfere with the SQLite corpus.
                self.stats['live_status_io_error']+=1

    def adaptive_allow(self, depth, relevance, kind='html'):
        # Profil- und harte Obergrenze verhindern einen endlosen Crawl.
        if depth > DEPTH_HARD_LIMIT or depth > PROFILE['max_depth']:
            return False
        if not DYNAMIC_DEPTH or depth <= DEPTH_SOFT_START or kind in ('material','sitemap'):
            return True
        threshold = 1 if depth <= 12 else (2 if depth <= 25 else (4 if depth <= 40 else 6))
        return relevance >= threshold

    def queue_url(self,u,depth,priority=0,kind=None,parent='',license_='',seed=False,relevance=0,anchor='',root_seed=None,commit=True):

        u=canon(u)
        if not u or depth>DEPTH_HARD_LIMIT or depth>PROFILE['max_depth']:return False
        if not kind:kind='material' if urlsplit(u).path.lower().endswith(SUFFIXES) else 'html'
        if kind=='material':
            if not DOWNLOAD_MATERIALS:return False
            pdf_check=CHECK_LICENSE_IN_PDFS and urlsplit(u).path.lower().endswith('.pdf')
            if ONLY_OPEN_LICENSE_MATERIALS and not (license_ or SITE_LICENSE.get(urlsplit(u).hostname) or pdf_check):return False
        elif kind!='sitemap' and not relevant_path(u,seed):return False
        if not self.adaptive_allow(depth,relevance,kind):
            self.stats['adaptive_depth_pruned']+=1;return False
        with self.lock:
            if self.seen_count>=PROFILE['max_queue'] or self.stop.is_set():return False
            root=self._root_for_new_url(u,parent=parent,root_seed=root_seed,seed=seed)
            cur=self.db.execute("INSERT OR IGNORE INTO frontier (url,kind,depth,priority,parent,inherited_license,status,relevance,root_seed) VALUES (?,?,?,?,?,?,'queued',?,?)",
                                (u,kind,depth,priority,parent,license_,relevance,root))
            if cur.rowcount:
                self.seen_count+=1
                self.db.execute('INSERT OR IGNORE INTO seed_schedule(root_seed,ordinal) VALUES (?,?)',
                                (root,len(SEEDS)+self.seen_count))
                if parent and globals().get('STORE_CRAWL_EDGES',False):
                    self.db.execute('INSERT OR IGNORE INTO crawl_edges VALUES (?,?,?,?)',(parent,u,anchor[:250],depth))
                if commit:self.db.commit()
                return True
        return False

    def seed_frontier(self):
        # Alle kuratierten Seeds bleiben als Einstieg bestehen: die Seitentiefe
        # bestimmt die Fachzugehörigkeit nicht zuverlässig. Fachnahe Seeds zuerst.
        for seed in SEEDS:
            weight=max((subject_evidence('',seed).get(subj,{}).get('score',0)
                        for subj in SUBJECT_FILTER),default=0)
            self.queue_url(seed,0,priority=25+weight*6,kind='html',seed=True,relevance=weight,commit=False)
        if SITEMAPS_AKTIV and MODUS!='TEST':
            for host in sorted(ALLOWED_HOSTS):self.queue_url('https://'+host+'/sitemap.xml',0,-30,kind='sitemap',seed=True,commit=False)
        with self.lock:self.db.commit()

    def session(self):
        if not hasattr(self.sessions,'http'):
            self.sessions.http=requests.Session()
            self.sessions.http.headers.update({'User-Agent':USER_AGENT})
        return self.sessions.http

    def queue_robots_sitemaps(self,robots_text,origin_host):
        if not SITEMAPS_AKTIV or MODUS=='TEST':return
        queued=0;limit=max(0,int(globals().get('MAX_ROBOTS_SITEMAPS_PER_HOST',4)))
        for raw in re.findall(r'^\s*sitemap\s*:\s*(\S+)',robots_text,re.I|re.M):
            if queued>=limit:break
            sitemap=canon(raw)
            if not sitemap or urlsplit(sitemap).hostname!=origin_host:continue
            with self.lock:
                if sitemap in self.robot_sitemap_urls:continue
                self.robot_sitemap_urls.add(sitemap)
            if self.queue_url(sitemap,0,-35,kind='sitemap',seed=True,commit=False):queued+=1
        self.stats['robots_sitemaps_queued']+=queued

    def robots_allow(self,u):
        host=urlsplit(u).hostname
        if host not in self.robots:
            self.robots[host]=(False,0)
            robots_url=f'https://{host}/robots.txt';seen=set()
            try:
                for _ in range(3):
                    if robots_url in seen:break
                    seen.add(robots_url)
                    r=self.session().get(robots_url,timeout=(7,18),allow_redirects=False)
                    if r.status_code in (301,302,303,307,308):
                        target=canon(urljoin(robots_url,r.headers.get('Location','')),preserve_trailing_slash=True)
                        r.close()
                        if not target or urlsplit(target).path.rstrip('/').lower()!='/robots.txt':break
                        robots_url=target;continue
                    if r.status_code in (404,410):self.robots[host]=(None,0)
                    elif r.status_code==200:
                        robots_text=r.text
                        rp=urllib.robotparser.RobotFileParser();rp.parse(robots_text.splitlines())
                        self.robots[host]=(rp,rp.crawl_delay(USER_AGENT) or rp.crawl_delay('*') or 0)
                        self.queue_robots_sitemaps(robots_text,urlsplit(robots_url).hostname)
                    r.close();break
            except requests.RequestException:self.robots[host]=(False,0)
        rp,delay=self.robots[host]
        return (rp is None or (rp is not False and rp.can_fetch(USER_AGENT,u))),float(delay)

    def fetch(self,u,kind):
        redirects=set()
        for redirect in range(5):
            if u in redirects:raise ValueError('redirect_loop')
            redirects.add(u)
            host=urlsplit(u).hostname
            if host not in ALLOWED_HOSTS:raise PermissionError('redirect_outside_curated_domains')
            with self.host_locks[host]:
                # Pro Host existiert bereits eine Sperre. robots.txt muss NICHT
                # unter dem globalen DB-/Status-Lock geladen werden: Sonst
                # blockiert ein langsamer Host alle parallelen Worker.
                allowed,crawl_delay=self.robots_allow(u)
                if not allowed:raise PermissionError('robots_disallow_or_unavailable')
                delay=max(DOWNLOAD_DELAY_SECONDS,crawl_delay)
                remain=delay-(time.monotonic()-self.host_last[host])
                if remain>0:time.sleep(remain)
                self.host_last[host]=time.monotonic()
                response=self.session().get(u,timeout=(8,35),allow_redirects=False,stream=True)
                if response.status_code in (301,302,303,307,308):
                    target=canon(urljoin(u,response.headers.get('Location','')),preserve_trailing_slash=True)
                    response.close()
                    if not target:raise PermissionError('unapproved_redirect')
                    u=target;continue
                if response.status_code!=200:
                    status=response.status_code;response.close();raise ValueError(f'HTTP_{status}')
                maxbytes=MAX_MATERIAL_MIB*1024**2 if kind=='material' else 4*1024**2
                if int(response.headers.get('Content-Length',0) or 0)>maxbytes:
                    response.close();raise ValueError('file_too_large')
                body=bytearray()
                try:
                    for part in response.iter_content(65536):
                        body.extend(part)
                        if len(body)>maxbytes:raise ValueError('response_too_large')
                    headers=dict(response.headers)
                finally:response.close()
                return u,bytes(body),headers
        raise ValueError('redirect_limit_exceeded')

    def complete(self,u,status='done',error='',depth=0,host=None):
        with self.lock:
            self.db.execute('UPDATE frontier SET status=?,error=? WHERE url=?',(status,error[:250],u))
            self.processed+=1
            if host:
                self.db.execute("""INSERT INTO crawl_depth_stats(host,depth,status,count) VALUES (?,?,?,1)
                  ON CONFLICT(host,depth,status) DO UPDATE SET count=count+1""",(host,depth,status))
            self.db.commit()
            self.write_live_status()

    def index(self,rec):
        body=rec['text'];digest=hashlib.sha256(re.sub(r'\s+',' ',body).encode('utf-8')).hexdigest()
        id_=hashlib.sha256(rec['url'].encode('utf-8')).hexdigest()
        meta={k:v for k,v in rec.items() if k not in ('url','title','text','doc_type','source','license','parent')}
        with self.lock:
            cur=self.db.execute('INSERT OR IGNORE INTO documents VALUES(?,?,?,?,?,?,?,?,?,?)',
                (id_,rec['url'],rec['title'],body,digest,rec['doc_type'],rec.get('source'),rec.get('license'),
                 rec.get('parent'),json.dumps(meta,ensure_ascii=False)))
            if cur.rowcount:
                self.stats['indexed']+=1
                self.document_bytes+=len((json.dumps({'docno':id_,'url':rec['url'],'title':rec['title'],'text':body},ensure_ascii=False)+'\n').encode('utf-8'))
                if self.document_bytes>=TARGET_MIB*1024**2*1.08:self.stop.set()
                return True
            self.stats['duplicate_index']+=1;return False

    def handle_html(self,u,data,headers,depth,parent='',relevance=0,root_seed=None):
        ct=headers.get('Content-Type','').lower()
        if 'html' not in ct and not data[:100].lstrip().lower().startswith((b'<html',b'<!doctype html')):
            self.stats['wrong_content_type']+=1;return
        enc=re.search(r'charset=([\w-]+)',ct)
        parsed=parse_html(data.decode(enc.group(1) if enc else 'utf-8',errors='replace'),u)
        title=parsed['title'];text=parsed['text'];links=parsed['links'];lic=parsed['license']
        category,score,signals,indexed=classify(title,u,text,parsed['headings'],links)
        attachments=[link for link,_ in links if urlsplit(link).path.lower().endswith(SUFFIXES)]
        with self.lock:
            for link in set(attachments):
                self.db.execute('INSERT OR IGNORE INTO material_links VALUES (?,?,?,?)',(link,u,lic,utc()))
        self.stats['html_'+category]+=1
        subject_ok, subject_hits=subject_decision(title,u,parsed['headings'],text,category)
        if indexed and not subject_ok:
            self.stats['subject_filtered']+=1
        if indexed and subject_ok:
            self.index({'url':parsed['canonical'],'title':title,'text':text,'doc_type':category,
                        'source':HOST_TO_SOURCE.get(urlsplit(u).hostname),'license':lic,'parent':parent,
                        'quality_score':score,'evidence':signals,'material_links':sorted(set(attachments)),
                        'headings':parsed['headings'],**didactic_metadata(title,text,parsed['headings']),'crawl_depth':depth,'crawl_parent':parent,'crawled_at':utc()})
        if depth<min(PROFILE['max_depth'],DEPTH_HARD_LIMIT):
            links.sort(key=lambda pair: (bool(LINK_HINT.search(pair[0]+' '+pair[1])),
                                         urlsplit(pair[0]).hostname==urlsplit(u).hostname),reverse=True)
            for target,anchor in links[:800]:
                if not QUELLEN_UEBERGREIFEND and urlsplit(target).hostname!=urlsplit(u).hostname:continue
                isfile=urlsplit(target).path.lower().endswith(SUFFIXES)
                if isfile:
                    self.stats['material_links_seen']+=1
                    self.queue_url(target,depth+1,70,kind='material',parent=u,license_=lic,relevance=max(relevance,score//3),anchor=anchor,root_seed=root_seed,commit=False)
                else:
                    # Signal aus der URL / dem Linktext und aus dem Inhalt der
                    # übergeordneten Seite. Auf Navigationsseiten trotzdem
                    # bis DEPTH_SOFT_START + einige Übergänge verzweigen.
                    hint=bool(DEEP_LINK_HINT.search(target+' '+anchor))
                    subject_hits=subject_evidence(anchor,target)
                    subject_weight=max((subject_hits.get(subj,{}).get('score',0)
                                        for subj in SUBJECT_FILTER),default=0)
                    child_relevance=min(12,max(0,relevance-1)+(3 if hint else 0)
                                        +(2 if indexed else 0)+min(5,subject_weight))
                    self.queue_url(target,depth+1,(35 if hint else 2)+subject_weight*8,parent=u,
                                   relevance=child_relevance,anchor=anchor,root_seed=root_seed,commit=False)

    def handle_material(self,u,raw,headers,parent,license_):
        ext=ext_from(u,headers)
        if ext not in SUFFIXES:return
        license_basis='parent_or_site_policy' if license_ else 'unknown'
        if not license_:
            license_=SITE_LICENSE.get(urlsplit(u).hostname,'')
            if license_:license_basis='site_policy'
        if ONLY_OPEN_LICENSE_MATERIALS and not license_ and not (CHECK_LICENSE_IN_PDFS and ext=='.pdf'):
            self.stats['not_open_licensed']+=1;return
        try:body=parse_document(raw,ext)
        except Exception as exc:
            self.stats['material_parse_failed']+=1
            body=''
        if CHECK_LICENSE_IN_PDFS and ext=='.pdf':
            embedded=license_from_pdf_text(body)
            if embedded:
                license_=embedded
                license_basis='pdf_text'
        if ONLY_OPEN_LICENSE_MATERIALS and not license_:
            self.stats['not_open_licensed']+=1;return
        digest=hashlib.sha256(raw).hexdigest()
        dest=self.material_dir/(digest+ext)
        if STORE_BINARY_MATERIALS and not dest.exists():dest.write_bytes(raw)
        status='saved_no_search_text'
        if len(body)>=max(100,MIN_TEXT_CHARS//2):
            title=Path(urlsplit(u).path).name
            kind,score,signals,accepted=classify(title,u,body,[],[])
            # Material muss relevante Substanz haben, nicht nur einen Dateinamen.
            usable=(bool(TASK.search(body[:40000]) or LESSON.search(body[:40000]) or
                         METHOD.search(body[:40000]) or DIDACTIC.search(body[:40000])))
            if (accepted or (usable and len(body)>=MIN_TEXT_CHARS)) and subject_decision(title,u,[],body,kind)[0]:
                if not accepted:
                    kind='worksheet' if TASK.search(body) else 'didactic_material'
                    score=max(score,4)
                    signals=list(dict.fromkeys(signals+['material_text_signal']))
                status='indexed' if self.index({'url':u,'title':title,'text':body,'doc_type':kind,
                    'source':HOST_TO_SOURCE.get(urlsplit(u).hostname),'license':license_,
                    'parent':parent,'subject_evidence':subject_evidence(title,u,[],body),'subject_filter':SUBJECT_FILTER[:],'license_basis':license_basis,'file_extension':ext,'original_file_bytes':len(raw),'sha256':digest,'quality_score':score,'evidence':signals,**didactic_metadata(title,body,[]),'crawled_at':utc()}) else 'duplicate'
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?)',(u,str(dest),len(raw),len(body),status,license_,parent))
            # Nur SQLite-Metadaten, keine zweite abzugebende JSONL-Datei
        self.stats['material_saved']+=1

    def handle_sitemap(self,u,raw,depth,root_seed=None):
        try:
            if raw.startswith(b'\x1f\x8b'):raw=gzip.decompress(raw)
            root=ET.fromstring(raw)
        except Exception:self.stats['invalid_sitemap']+=1;return
        n=0
        for child in root.iter():
            if child.tag.endswith('}loc') or child.tag=='loc':
                loc=canon((child.text or '').strip())
                if not loc:continue
                n+=1
                if n>1800:break
                if loc.lower().endswith(('.xml','.xml.gz')):
                    if depth<2:self.queue_url(loc,depth+1,-30,kind='sitemap',seed=True,root_seed=root_seed,commit=False)
                else:self.queue_url(loc,0,-10,seed=False,root_seed=root_seed,commit=False)
        self.stats['sitemap_links']+=n
    def _process_item(self,item,root_seed):
        u,kind,depth,priority,parent,license_,relevance=item
        host=urlsplit(u).hostname
        try:
            if self.host_count[host]>=PROFILE['max_per_host']:
                self.complete(u,'blocked','max_host_pages',depth,host);return
            if kind=='material' and ONLY_OPEN_LICENSE_MATERIALS and not (
                license_ or SITE_LICENSE.get(host) or
                (CHECK_LICENSE_IN_PDFS and u.lower().endswith('.pdf'))):
                self.complete(u,'blocked','no_licence',depth,host);return
            actual,data,headers=self.fetch(u,kind)
            if kind=='sitemap':
                self.handle_sitemap(actual,data,depth,root_seed=root_seed)
            elif kind=='material':
                self.handle_material(actual,data,headers,parent,license_)
            else:
                self.handle_html(actual,data,headers,depth,parent,relevance,root_seed=root_seed)
            self.host_count[host]+=1
            self.complete(u,depth=depth,host=host)
        except PermissionError as exc:
            self.stats['robots_or_redirect_blocked']+=1
            self.complete(u,'blocked',str(exc),depth,host)
        except Exception as exc:
            self.stats['fetch_or_parse_error']+=1
            self.complete(u,'error',str(exc),depth,host)
        if self.processed%25==0 or time.monotonic()-self.last_progress>60:
            with self.lock:
                if time.monotonic()-self.last_progress>2:
                    self.last_progress=time.monotonic()
                    docs=self.db.execute('SELECT COUNT(*) FROM documents').fetchone()[0]
                    self.write_depth_heatmap()
                    self.log(f'Fortschritt: {self.processed} Abrufe, {docs} Dokumente, '
                             f'{self.document_bytes/1024**2:.2f}/{TARGET_MIB} MiB, '
                             f'{self.stats["material_saved"]} gespeicherte Materialdateien')

    def worker(self):
        """Round-Robin über Seeds; innerhalb eines Seeds begrenzte LIFO-DFS.

        Tiefe pro Seed-Runde wächst schrittweise (5/10/15/...), bereits verarbeitete
        URLs werden nicht erneut abgerufen. Aktiver Seed ist exklusiv je Worker.
        """
        while not self.stop.is_set():
            if time.monotonic()-self.start_time>PROFILE['runtime_minutes']*60 or \
                    self.processed>=PROFILE['max_pages']:
                self.stop.set();break
            lease=self.acquire_seed()
            if not lease:
                with self.lock:
                    active=bool(self.active_seed_roots)
                    queued=self.db.execute("SELECT 1 FROM frontier WHERE status='queued' LIMIT 1").fetchone()
                if not queued and not active:break
                if not active and queued:
                    self.log('WARNUNG: offene URLs ohne zugeordneten Seed – Scheduler angehalten.')
                    break
                time.sleep(.2);continue
            root_seed,depth_cap,round_number=lease
            try:
                budget=PROFILE['pages_per_seed_turn']
                self.log(f'Seed-Runde {round_number}: {root_seed} | DFS bis Tiefe {depth_cap}, Budget {budget} Abrufe')
                for _ in range(budget):
                    if self.stop.is_set():break
                    if time.monotonic()-self.start_time>PROFILE['runtime_minutes']*60 or \
                            self.processed>=PROFILE['max_pages']:
                        self.stop.set();break
                    item=self.claim_seed(root_seed,depth_cap)
                    if item is None:break
                    self._process_item(item,root_seed)
            finally:
                self.release_seed(root_seed)

    def write_depth_heatmap(self,force=False):
        """Persistiert unabhängige Heatmap als JSON, TSV und offline HTML.
        Während des Laufs entsteht für jeden Host x Tiefe eine Statusverteilung.
        """
        with self.lock:
            now=time.monotonic()
            if not force and now-self.last_heatmap<max(1,DEPTH_HEATMAP_INTERVAL):return False
            self.last_heatmap=now
            data=self.db.execute("SELECT host,depth,status,count FROM crawl_depth_stats ORDER BY host,depth,status").fetchall()
            rows={}
            for host,depth,status,count in data:
                cell=rows.setdefault((host,depth),{'host':host,'depth':depth,'done':0,'blocked':0,'error':0,'indexed':0})
                cell[status]=cell.get(status,0)+count
            for host,depth,count in self.db.execute("""SELECT
                 substr(d.url, instr(d.url,'//')+2, instr(substr(d.url,instr(d.url,'//')+2),'/')-1),
                 f.depth,COUNT(*) FROM documents d JOIN frontier f ON f.url=d.url
                 GROUP BY 1,2"""):
                cell=rows.setdefault((host,depth),{'host':host,'depth':depth,'done':0,'blocked':0,'error':0,'indexed':0})
                cell['indexed']+=count
            for url,depth,status in self.db.execute('SELECT url,depth,status FROM frontier'):
                host=urlsplit(url).hostname
                cell=rows.setdefault((host,depth),{'host':host,'depth':depth,'done':0,'blocked':0,'error':0,'indexed':0})
                cell['discovered']=cell.get('discovered',0)+1
                if status=='queued':cell['queued']=cell.get('queued',0)+1
            matrix=sorted(rows.values(),key=lambda x:(x['host'],x['depth']))
            payload={'run':RUN_NAME,'mode':MODUS,'generated_at':utc(),
                     'depth_limit':DEPTH_HARD_LIMIT,'soft_start':DEPTH_SOFT_START,
                     'selected_subjects':SUBJECT_FILTER[:],'total_indexed':self.db.execute('SELECT COUNT(*) FROM documents').fetchone()[0],
                     'cells':matrix}
            output=self.dir/'depth_heatmap.json'
            tmp=output.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(output)
            tsv=self.dir/'depth_heatmap.tsv'
            ttmp=tsv.with_suffix('.tsv.tmp')
            with ttmp.open('w',encoding='utf-8',newline='') as f:
                f.write('host\tdepth\tdiscovered\tqueued\tdone\tblocked\terror\tindexed\n')
                for c in matrix:f.write('\t'.join(str(c.get(k,0)) for k in ('host','depth','discovered','queued','done','blocked','error','indexed'))+'\n')
            ttmp.replace(tsv)
            # Farbskala: indexierte Dokumente je Tiefenstufe/Host (kein CDN).
            import html as html_module
            hosts=sorted({r['host'] for r in matrix}); by={(x['host'],x['depth']):x for x in matrix}
            peak=max((r['indexed'] for r in matrix),default=0)
            table=['<table><thead><tr><th>Host / Tiefe</th>'+''.join('<th>'+str(i)+'</th>' for i in range(DEPTH_HARD_LIMIT+1))+'</tr></thead><tbody>']
            for host in hosts:
                table.append('<tr><th>'+html_module.escape(host)+'</th>')
                for depth in range(DEPTH_HARD_LIMIT+1):
                    c=by.get((host,depth),{});n=c.get('indexed',0);visits=c.get('done',0)+c.get('blocked',0)+c.get('error',0)
                    alpha=(0.10+0.9*n/max(1,peak)) if n else 0
                    bg=f'rgba(27,132,103,{alpha:.3f})' if n else ('#fff2cf' if visits else '#f3f4f6')
                    tip=f'Tiefe {depth} | entdeckt {c.get("discovered",0)}, offen {c.get("queued",0)}, indexiert {n}, besucht {visits}, Fehler {c.get("error",0)}'
                    table.append(f'<td title="{tip}" style="background:{bg}">{n or ("·" if visits else "")}</td>')
                table.append('</tr>')
            table.append('</tbody></table>')
            html_doc="""<!doctype html><html lang="de"><meta charset="utf-8"><title>DidaDex Tiefen-Heatmap</title>
<style>body{font:14px system-ui;margin:24px;color:#1e293b} .scroll{overflow:auto;max-height:75vh}
table{border-collapse:collapse;font-size:11px}td,th{border:1px solid #cbd5e1;min-width:21px;text-align:center;padding:4px}
thead th{position:sticky;top:0;background:#e2e8f0}tbody th{position:sticky;left:0;background:#fff;min-width:170px;text-align:left}</style>
<h1>DidaDex – Tiefen-Heatmap</h1><p>Indexierte Dokumente nach Host und Crawl-Tiefe. Grün = viele Dokumente;
Gelb = besucht, aber nichts indexiert. Hover zeigt Details.</p><div class="scroll">"""+''.join(table)+'</div></html>'
            htmp=self.dir/'depth_heatmap.html.tmp'
            htmp.write_text(html_doc,encoding='utf-8');htmp.replace(self.dir/'depth_heatmap.html')
        return True

    def crawl(self):
        self.log(f'Fachfilter: {SUBJECT_FILTER or ["Alle Fächer"]}; allgemeine Methoden={INCLUDE_GENERAL_METHODS}')
        self.log(f'START {MODUS}: {len(SEEDS)} Seeds, {PROFILE["workers"]} parallele Worker, '
                 f'Round-Robin-DFS ({PROFILE["pages_per_seed_turn"]} URLs/Seed-Runde, '
                 f'Tiefenschritt {DFS_DEPTH_STEP}), Materialdownload={DOWNLOAD_MATERIALS}')
        with concurrent.futures.ThreadPoolExecutor(max_workers=PROFILE['workers']) as pool:
            for f in [pool.submit(self.worker) for _ in range(PROFILE['workers'])]:f.result()
        self.write_depth_heatmap(force=True)
        self.write_live_status(force=True)
        self.log(f'ENDE: {self.processed} Seiten, {self.document_bytes/1024**2:.2f} MiB bereinigte Daten')

    def close(self):
        with self.lock:
            for f in (self.log_file,):
                try:f.flush();f.close()
                except Exception:pass
            self.db.commit();self.db.close()


def export_reports(db_path,out,target):
    """Einziger exportierter Datensatz: gefiltertes crawl.jsonl; DB bleibt Resume-State."""
    out=Path(out)
    db=sqlite3.connect(db_path)
    # Nur valide, deduplizierte indexierte Dokumente; vollständiger extrahierter Text.
    export_path=out/'crawl.jsonl'
    temp_path=out/'crawl.jsonl.tmp'
    counts=Counter(); sources=Counter(); exported=0; bytes_written=0
    max_bytes=target*1024**2
    with temp_path.open('w',encoding='utf-8',newline='\n') as f:
        for id_,u,t,body,fp,kind,src,lic,parent,meta in db.execute(
                'SELECT * FROM documents ORDER BY docno'):
            if len(body)<MIN_TEXT_CHARS:continue
            obj={'id':id_,'url':u,'title':t,'text':body,
                 'doc_type':kind,'source':src,'license':lic or None,
                 'parent_url':parent or None,'content_sha256':fp}
            obj.update(json.loads(meta or '{}'))
            line=json.dumps(obj,ensure_ascii=False,sort_keys=True)+'\n'
            size=len(line.encode('utf-8'))
            if bytes_written+size>max_bytes:continue
            f.write(line);bytes_written+=size;exported+=1
            counts[kind]+=1;sources[src or 'unbekannt']+=1
    temp_path.replace(export_path)
    report={'exported_documents':exported,'document_types':dict(counts),
            'sources':dict(sources),'crawl_jsonl_bytes':bytes_written,
            'crawl_jsonl_mib':round(bytes_written/1024**2,3),
            'target_mib':target,'target_reached':bytes_written>=max_bytes,
            'queued':db.execute("SELECT COUNT(*) FROM frontier WHERE status='queued'").fetchone()[0],
            'generated_utc':utc()}
    db.close()
    # Alte redundante Exporte desselben RUN_NAME entfernen.
    for stale in ('documents.jsonl','search_documents.jsonl','material_manifest.jsonl',
                  'material_links_discovered.jsonl','quality_report.json','corpus_size_report.json','run_info.json'):
        (out/stale).unlink(missing_ok=True)
    print('EXPORT:',exported,'gefilterte Dokumente,',report['crawl_jsonl_mib'],
          'MiB; Ziel:',target,'MiB',flush=True)
    print('Abgabedatei:',export_path.resolve(),flush=True)
    print('Weitere URLs in Warteschlange:',report['queued'],flush=True)
    print('Heatmap: depth_heatmap.html, depth_heatmap.json, depth_heatmap.tsv',flush=True)
    return report,report

def _run_offline_checks():
    # Der Test arbeitet ohne Internet und legt keine Crawl-Ausgabe an.
    unit = """<!doctype html><html><head><title>Unterricht: Quellenauswertung</title></head>
    <body><main><h1>Unterrichtseinheit: Quellen auswerten</h1><h2>Unterrichtsverlauf</h2>
    <p>Arbeitsauftrag: Analysiere die Quellen und vergleiche die Ergebnisse in Gruppenarbeit.</p>
    <h2>Methodische Hinweise</h2><p>Lernziel und Einstiegsphase: Die Schülerinnen und Schüler
    erschließen historisches Quellenmaterial.</p>""" + "<p>Die Arbeitsblätter werden in Partnerarbeit verglichen und die Ergebnisse im Plenum diskutiert.</p>"*8 + """
    <a href="https://segu-geschichte.de/files/quellenanalyse.pdf">Arbeitsblatt als PDF</a></main></body></html>"""
    parsed=parse_html(unit,'https://segu-geschichte.de/unterrichtsmaterial/quellenanalyse')
    result=classify(parsed['title'],'https://segu-geschichte.de/unterrichtsmaterial/quellenanalyse',
                    parsed['text'],parsed['headings'],parsed['links'])
    assert result[-1] is True, ('Unterrichtseinheit nicht erkannt',result)
    assert any(link.endswith('.pdf') for link,_ in parsed['links']), 'Materiallink nicht erkannt'
    bad=classify('Datenschutz – ZUM-Unterrichten','https://unterrichten.zum.de/wiki/Datenschutz',
                 'Arbeitsblatt Unterrichtsverlauf für den Unterricht '+('Lorem ipsum '*150),[],[])
    assert bad[-1] is False, 'Datenschutz-Fehlklassifikation'
    overview=classify('Unterrichtsmethoden – ZUM Deutsch Lernen','https://deutsch-lernen.zum.de/wiki/Unterrichtsmethoden',
                 'Methoden und Lernziele in Gruppenarbeit '+('Lorem ipsum '*150),[],[])
    assert overview[-1] is False, 'Methodenübersicht sollte nicht im Suchindex landen'
    u1=canonical('https://segu-geschichte.de/arbeitsblaetter/?utm_source=test#top')
    u2=canonical('https://segu-geschichte.de/arbeitsblaetter/')
    assert u1==u2, ('URL-Deduplizierung falsch',u1,u2)
    print('Offline-Tests bestanden: Unterrichtseinheit, Materiallink, Datenschutz, Navigation, URL-Normalisierung.',flush=True)

    # Adaptive Tiefen-Gates: Vorprüfung ohne Datenbank
    assert 0 < DEPTH_HARD_LIMIT <= 200
    assert TeachingCrawler.adaptive_allow(None, 50, 6)
    assert not TeachingCrawler.adaptive_allow(None, 51, 10)
    assert not TeachingCrawler.adaptive_allow(None, 42, 2)
    assert TeachingCrawler.adaptive_allow(None, 7, 2)
    print('Adaptive Tiefenregel: OK',flush=True)

    meta=didactic_metadata('Informatik Klasse 10', 'Einstieg mit Partnerarbeit und Reflexion', [])
    assert meta['grade_evidence']=='Klasse 10' and 'partnerarbeit' in meta['social_forms_mentioned']
    assert not classify('Fachzeitschriften für den Deutschunterricht',
        'https://unterrichten.zum.de/wiki/Fachzeitschriften_für_den_Deutschunterricht',
        'Unterricht Arbeitsblatt Einstieg '*200,[],[])[-1]
    print('Metadatenextraktion und Übersichtsfilter: OK',flush=True)


def main(argv=None):
    args = _parse_args(argv)
    runtime_config = _read_json_file(args.config, "Laufkonfiguration") if args.config else {}
    _apply_runtime_config(runtime_config, args.stop_file)
    print(f"Konfiguration: {MODUS}, {_format_runtime(PROFILE['runtime_minutes'])}, Ziel {TARGET_MIB} MiB", flush=True)
    print_source_summary()
    print("@@STEP@@ Offline-Selbsttests", flush=True)
    _run_offline_checks()
    print("@@STEP@@ Netzlauf", flush=True)
    from pathlib import Path
    from datetime import datetime, timezone
    OUTPUT_DIR = CRAWLER_DIR / "outputs" / "runs" / RUN_NAME
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Ausgabeverzeichnis:", OUTPUT_DIR.resolve(), flush=True)
    if START_CRAWL:
        runner = TeachingCrawler(OUTPUT_DIR)
        def _watch_stop():
            while not runner.stop.is_set():
                if _DIDA_STOP_FILE.exists():
                    print('Stoppsignal empfangen - Abschluss und Export werden vorbereitet.', flush=True)
                    runner.stop.set()
                    break
                time.sleep(0.3)
        threading.Thread(target=_watch_stop, daemon=True).start()
        try:
            runner.crawl()
        except KeyboardInterrupt:
            print("Crawl unterbrochen. SQLite-Zustand bleibt erhalten; Export startet mit bisherigen Dokumenten.",flush=True)
        except Exception as exc:
            print("Crawl-Fehler:",repr(exc),"– Export der bisherigen Daten startet trotzdem.",flush=True)
        finally:
            runner.close()
        print("Netzlauf abgeschlossen oder beendet. Export startet.", flush=True)
    else:
        print("START_CRAWL=False: Netzlauf ausdrücklich übersprungen.", flush=True)
    print("@@STEP@@ JSONL-Export", flush=True)
    import sqlite3
    sqlite_path = OUTPUT_DIR / "crawler_state.sqlite"
    if sqlite_path.exists():
        quality_report, size_report = export_reports(sqlite_path, OUTPUT_DIR, TARGET_MIB)
    else:
        print("Noch keine Datenbank vorhanden – Crawl zuerst starten.")
    print("@@DONE@@", flush=True)


if __name__ == "__main__":
    main()
