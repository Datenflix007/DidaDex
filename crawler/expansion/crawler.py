#!/usr/bin/env python3
"""DidaDex Quellenexpansion: unabhängiger, fortsetzbarer, rücksichtsvoller Lernmaterialcrawler.
Nicht identisch mit der bestehenden DidaDex-Tk-GUI! Ausgabe: JSONL + SQLite.
"""
from __future__ import annotations
import argparse, collections, concurrent.futures, hashlib, io, json, os, re, signal, sqlite3, sys, threading, time, urllib.robotparser, zipfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit, unquote
import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / 'outputs' / 'expansion'  # passt zum bestehenden didadex/crawler/outputs
UA = "DidaDexResearchBot/1.0 (+https://github.com/Datenflix007; academic information retrieval)"
DEFAULT_DELAY = 2.5  # Sekunden zwischen dem START zweier Anforderungen an denselben Host
SPECIAL_DELAY = {"de.wikipedia.org": 4.0, "www.bpb.de": 3.0}
BLOCK_PATH = re.compile(r"/(?:login|signin|signup|register|account|user/login|user/register|admin|cart|warenkorb|checkout|captcha|feed)(?:[/?#]|$)",re.I)
TRACKING = {"fbclid","gclid","msclkid","yclid","ref","source","sessionid","phpsessid"}
DROP_QUERY = {"q","query","search","sort","order","filter","token","session","session_id","auth","_ga","_gl","_gid","key"}  # id/tx_* bleiben erhalten
DOC_EXT = {".pdf",".docx",".pptx",".odt",".txt",".md"}
STOP = threading.Event()
TL = threading.local()
ROBOTS = {}
ROBOTS_DELAY = {}
ROBOT_HOST_LOCKS = collections.defaultdict(threading.Lock)


def normalize(url):
    try:
        p=urlsplit(url.strip()); scheme=p.scheme.lower(); host=(p.hostname or '').lower()
        if scheme not in ('http','https') or not host or p.username or p.password: return None
        port=(':'+str(p.port)) if p.port and p.port not in (80,443) else ''
        path=quote(unquote(p.path or '/'),safe='/%:@!$&\'()*+,;=-._~')
        path=re.sub(r'/+', '/',path)
        # Query ist Teil der Identität für Pagination, nicht jedoch Tracking.
        params=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True)[:12] if k.lower() not in TRACKING and k.lower() not in DROP_QUERY and not k.lower().startswith('utm_') and len(k)<100 and len(v)<300]
        query=urlencode(sorted(params))
        return urlunsplit((scheme,host+port,path,query,''))
    except (ValueError,UnicodeError): return None


def url_id(url): return hashlib.sha256(url.encode('utf-8')).hexdigest()

def ext(url): return Path(unquote(urlsplit(url).path)).suffix.lower()

def is_allowed(url, policy, *, direct=False):
    p=urlsplit(url); host=(p.hostname or '').lower()
    if host != policy['host'] and host not in policy.get('aliases',[]): return False
    if BLOCK_PATH.search(unquote(p.path)): return False
    if host!='de.wikipedia.org' and unquote(p.path).rstrip('/').lower() in ('/impressum','/datenschutz','/privacy','/kontakt'):return False
    if not direct and not any(unquote(p.path).startswith(x) for x in policy['allow_paths']): return False
    if p.path.startswith('/wiki/') and host.endswith('wikipedia.org'):
        if re.match(r'^(?:Spezial|Special|Kategorie|Category|Wikipedia|Datei|File|Benutzer|User|Hilfe|Help|Vorlage|Template|MediaWiki|Portal):',unquote(p.path[len('/wiki/'):]),re.I): return False
    if ext(url) in ('.zip','.7z','.rar','.exe','.mp4','.mp3','.iso','.dmg','.tar','.gz','.png','.jpg','.jpeg','.gif','.svg','.webp'):
        return False
    if '/search?' in url.lower() or 'action=edit' in url.lower(): return False
    return True


def session():
    if not hasattr(TL,'session'):
        s=requests.Session();s.headers.update({'User-Agent':UA,'Accept':'text/html,application/xhtml+xml,application/pdf,application/xml,text/xml,application/vnd.openxmlformats-officedocument.wordprocessingml.document,*/*;q=0.6','Accept-Language':'de,en;q=0.6'})
        TL.session=s
    return TL.session


def robots_allowed(url):
    p=urlsplit(url); host=p.netloc; origin=f'{p.scheme}://{host}'
    # Jede Kombination aus Scheme+Host separat prüfen, auch bei Redirects.
    with ROBOT_HOST_LOCKS[origin]:
        cached=ROBOTS.get(origin)
        if cached is not None and cached[2] < time.monotonic(): cached=None
        if cached is None:
            rp=urllib.robotparser.RobotFileParser(); rp.set_url(origin+'/robots.txt')
            try:
                r=session().get(origin+'/robots.txt',timeout=(8,15),allow_redirects=False)
                # robots.txt ist bei manchen Bildungsservern vom non-www- auf den www-Host umgeleitet.
                if r.status_code in (301,302,307,308):
                    target=normalize(urljoin(origin+'/robots.txt',r.headers.get('Location','')))
                    if target and (urlsplit(target).hostname or '').removeprefix('www.')==host.removeprefix('www.'):
                        r=session().get(target,timeout=(8,15),allow_redirects=False)
                if r.status_code==404:
                    cached=(None,True,time.monotonic()+3600)
                elif r.status_code==200 and len(r.content)<=1_000_000:
                    rp.parse(r.text.splitlines());cached=(rp,True,time.monotonic()+3600)
                    ROBOTS_DELAY[host]=float(rp.crawl_delay(UA) or 0)
                else: cached=(None,False,time.monotonic()+300) # fail closed bei 403/429/5xx
            except requests.RequestException:
                cached=(None,False,time.monotonic()+300)
            ROBOTS[origin]=cached
    if not cached[1]:raise RuntimeError('robots_temporarily_unavailable')
    return cached[0] is None or cached[0].can_fetch(UA,url)


def response_bytes(r, cap):
    buf=io.BytesIO()
    for chunk in r.iter_content(chunk_size=65536):
        if STOP.is_set(): break
        if chunk:
            buf.write(chunk)
            if buf.tell()>cap: return None
    return buf.getvalue()


def request_once(url, policy, cap):
    cur=url
    for _ in range(5):
        if not is_allowed(cur,policy,direct=True): return {'kind':'blocked','reason':'domain_or_path'}
        try: allowed=robots_allowed(cur)
        except RuntimeError: return {'kind':'retry','reason':'robots_unavailable','wait':300}
        if not allowed: return {'kind':'blocked','reason':'robots_disallow'}
        try:
            with session().get(cur,timeout=(12,30),allow_redirects=False,stream=True) as r:
                code=r.status_code
                if code in (301,302,303,307,308):
                    nxt=normalize(urljoin(cur,r.headers.get('Location','')))
                    if not nxt: return {'kind':'error','reason':'redirect_invalid'}
                    if not is_allowed(nxt,policy,direct=True): return {'kind':'blocked','reason':'redirect_other_host_or_path'}
                    cur=nxt;continue
                if code in (429,503):
                    wait=60
                    raw=r.headers.get('Retry-After')
                    if raw:
                        try:wait=max(5,min(3600,int(raw)))
                        except ValueError:
                            try:wait=max(5,min(3600,int((parsedate_to_datetime(raw)-datetime.now(timezone.utc)).total_seconds())))
                            except Exception:pass
                    return {'kind':'retry','reason':f'http_{code}','wait':wait}
                if code==403: return {'kind':'blocked','reason':'http_403'}
                if code==404: return {'kind':'skip','reason':'http_404'}
                if code>=400: return {'kind':'error','reason':f'http_{code}'}
                ctype=r.headers.get('Content-Type','').lower().split(';')[0].strip()
                data=response_bytes(r,cap)
                if data is None: return {'kind':'skip','reason':'response_too_large'}
                if STOP.is_set(): return {'kind':'retry','reason':'interrupted','wait':60}
                return {'kind':'ok','url':cur,'data':data,'ctype':ctype,'x_robots':r.headers.get('X-Robots-Tag','')}
        except requests.Timeout: return {'kind':'retry','reason':'timeout','wait':60}
        except requests.RequestException as e: return {'kind':'retry','reason':'request_error_'+e.__class__.__name__,'wait':90}
    return {'kind':'error','reason':'redirect_loop'}


def text_from_file(data, ctype, url):
    extension=ext(url)
    try:
        if extension=='.pdf' or 'application/pdf' in ctype or data.startswith(b'%PDF'):
            from pypdf import PdfReader
            reader=PdfReader(io.BytesIO(data),strict=False)
            # Große PDF nicht unbegrenzt verarbeiten; Messgröße = extrahierter TEXT.
            pages=[]
            for p in reader.pages[:100]:
                try:pages.append(p.extract_text(extraction_mode='plain') or '')
                except Exception:continue
            return '\n'.join(pages),'pdf'
        if extension=='.docx' or 'wordprocessingml' in ctype:
            from docx import Document
            d=Document(io.BytesIO(data));return '\n'.join([x.text for x in d.paragraphs if x.text.strip()]+[c.text for table in d.tables for row in table.rows for c in row.cells if c.text.strip()]),'docx'
        if extension=='.pptx' or 'presentationml' in ctype:
            from pptx import Presentation
            prs=Presentation(io.BytesIO(data))
            return '\n'.join(s.text for slide in prs.slides for s in slide.shapes if s.has_text_frame),'pptx'
        if extension=='.odt' or 'opendocument.text' in ctype:
            from xml.etree import ElementTree as ET
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                inf=z.getinfo('content.xml')
                if inf.file_size>10_000_000:return '', 'odt'
                root=ET.fromstring(z.read('content.xml'))
            return ' '.join((x.strip() for x in root.itertext() if x.strip())),'odt'
        if extension in ('.txt','.md') or ctype.startswith('text/plain'):
            return data.decode('utf-8',errors='replace'),'text'
    except Exception: return '','unreadable_material'
    return '', 'unsupported'


def parse_html(data,url,policy):
    soup=BeautifulSoup(data,'lxml')
    tag=soup.find('meta',attrs={'name':re.compile(r'^(?:robots|googlebot)$',re.I)})
    if tag and 'noindex' in tag.get('content','').lower():return '', '', [], []
    title=(soup.title.get_text(' ',strip=True) if soup.title else '')[:300]
    canonical=soup.find('link',rel=lambda v:v and 'canonical' in v)
    content_root=soup.select_one('main, article, #mw-content-text, .mw-parser-output, .main-content, #content, .content') or soup.body or soup
    # WICHTIG: Linkliste vor Entfernen der Navigationsbereiche gewinnen; findet Materialdownloads.
    links=[]
    for a in soup.select('a[href]'):
        h=normalize(urljoin(url,a.get('href','')))
        if h and is_allowed(h,policy) and h!=url:links.append(h)
    for tag in content_root.select('nav, footer, header, script, style, noscript, form, iframe, .breadcrumb, .breadcrumbs, .navigation, .sidebar, .cookie-banner, .toc, .mw-editsection, .printfooter'):
        tag.decompose()
    # Separates soup: beim Decompose beschädigen wir andernfalls Linktexte außerhalb des content_root nicht.
    text=content_root.get_text(' ',strip=True)
    text=re.sub(r'\s+',' ',text).strip()
    headings=[x.get_text(' ',strip=True)[:180] for x in content_root.select('h1,h2,h3')][:40]
    return title,text,headings,list(dict.fromkeys(links))[:150]


def extract(task,policy,cap):
    raw=request_once(task['url'],policy,cap)
    if raw['kind']!='ok':return raw
    ctype=raw['ctype'];url=raw['url']; data=raw['data']
    if 'noindex' in raw.get('x_robots','').lower():return {'kind':'skip','reason':'x_robots_noindex'}
    if (ext(url) in DOC_EXT and 'html' not in ctype) or any(x in ctype for x in ('pdf','officedocument','opendocument','text/plain')):
        content,typ=text_from_file(data,ctype,url);title=Path(unquote(urlsplit(url).path)).name;headings=[]; links=[]
    elif 'html' in ctype or (not ctype and b'<html' in data[:3000].lower()):
        title,content,headings,links=parse_html(data,url,policy);typ='html'
    else:return {'kind':'skip','reason':'unsupported_mime_'+ctype[:40]}
    if not content or len(content)<(300 if typ=='html' else 100):
        return {'kind':'skip','reason':'too_short_or_unreadable','links':links}
    # Kein unbegrenztes Aufblähen; Textmasse nicht künstlich duplizieren.
    content=content[:600_000]
    norm=re.sub(r'\s+',' ',content).strip()
    return {'kind':'document','url':url,'title':title,'text':norm,'headings':headings,'doc_type':'reference_article' if policy['source_kind']=='reference' else ('teaching_material' if typ!='html' else ('teaching_activity' if re.search(r'unterrichtsverlauf|arbeitsblatt|lernziel|unterrichtseinheit|kompetenzziel|aufgabenstellung|unterrichtsmaterial',norm,re.I) else 'education_content')),'file_type':typ,'links':links,'raw_bytes':len(data)}


def extract_sitemap(task, policy, cap):
    raw=request_once(task['url'],policy,cap)
    if raw['kind']!='ok':return raw
    from xml.etree import ElementTree as ET
    try:
        data=raw['data']
        if data[:2]==b'\x1f\x8b':
            import gzip
            data=gzip.decompress(data)
            if len(data)>cap:return {'kind':'skip','reason':'sitemap_too_large'}
        root=ET.fromstring(data)
        links=[]; sitemaps=[]
        for e in root.iter():
            if e.tag.endswith('loc') and e.text:
                u=normalize(e.text)
                if not u:continue
                if u.lower().endswith(('.xml','.xml.gz')) and (urlsplit(u).hostname in [policy['host']]+policy.get('aliases',[])):
                    sitemaps.append(u)
                elif is_allowed(u,policy):links.append(u)
        return {'kind':'sitemap','links':list(dict.fromkeys(links))[:15000],'sitemaps':list(dict.fromkeys(sitemaps))[:100]}
    except Exception:return {'kind':'error','reason':'sitemap_parse'}


def connect(db_path, reset_inflight=False):
    db_path.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(db_path,timeout=30)
    con.execute('PRAGMA journal_mode=WAL');con.execute('PRAGMA busy_timeout=30000')
    con.executescript('''
      CREATE TABLE IF NOT EXISTS queue (
      id TEXT PRIMARY KEY, url TEXT NOT NULL, host TEXT NOT NULL, grp TEXT NOT NULL,
      depth INTEGER NOT NULL, priority INTEGER NOT NULL, type TEXT NOT NULL DEFAULT 'page',
      state TEXT NOT NULL DEFAULT 'pending', ready REAL NOT NULL DEFAULT 0,
      attempts INTEGER NOT NULL DEFAULT 0, reason TEXT DEFAULT '', added REAL NOT NULL,
      updated REAL NOT NULL);
      CREATE INDEX IF NOT EXISTS queue_schedule ON queue(state,ready,priority,depth,added);
      CREATE TABLE IF NOT EXISTS docs (
      id TEXT PRIMARY KEY, url TEXT NOT NULL, grp TEXT NOT NULL, title TEXT NOT NULL,
      doc_type TEXT NOT NULL, file_type TEXT NOT NULL, content_hash TEXT NOT NULL UNIQUE,
      text TEXT NOT NULL, headings TEXT, license TEXT, raw_bytes INTEGER, crawled_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS events (host TEXT, reason TEXT, n INTEGER NOT NULL, PRIMARY KEY(host,reason));
    ''')
    if reset_inflight:con.execute("UPDATE queue SET state='pending' WHERE state='inflight'")
    con.commit();return con


def add_queue(con,url,policy,depth=0,typ='page',priority=None,group=None):
    u=normalize(url)
    if not u or not is_allowed(u,policy,direct=(depth==0)): return False
    # Nicht über zu breite Folgenavigationslinks crawlen.
    if depth>policy['max_depth']:return False
    now=time.time()
    cur=con.execute('INSERT OR IGNORE INTO queue(id,url,host,grp,depth,priority,type,added,updated) VALUES(?,?,?,?,?,?,?,?,?)',
      (url_id(u),u,policy['host'],group or policy['group'],depth,priority if priority is not None else policy['priority'],typ,now,now))
    return cur.rowcount==1


def policies_from_seeds(seeds):
    policies={}
    for item in seeds:
        host=item['host']
        if host not in policies:policies[host]=dict(item)
        else:
            p=policies[host];p['allow_paths']=list(set(p['allow_paths']+item['allow_paths']))
            p['max_depth']=max(p['max_depth'],item['max_depth']);p['priority']=max(p['priority'],item['priority'])
    # Zulässige Host-Aliase derselben offiziellen Plattform (keine Drittanbieter/CDNs).
    aliases={'www.bpb.de':['bpb.de'], 'lehrerfortbildung-bw.de':['www.lehrerfortbildung-bw.de'], 'inf-schule.de':['www.inf-schule.de'], 'segu-geschichte.de':['www.segu-geschichte.de'], 'digitallearninglab.de':['www.digitallearninglab.de'], 'bildungsserver.berlin-brandenburg.de':['www.bildungsserver.berlin-brandenburg.de']}
    for host,als in aliases.items():
        if host in policies:policies[host]['aliases']=als
    return policies


def load_seeds(con,seeds,policies, bpb_sitemap=False):
    new=0
    for seed in seeds:
        p=policies[seed['host']]
        new+=add_queue(con,seed['url'],p,0,typ=('sitemap' if seed.get('sitemap') else 'page'),priority=seed['priority'],group=seed['group'])
    if bpb_sitemap:
        # Der konkrete Sitemapindex stammt aus der bpb robots.txt vom 11.11.2026.
        url='https://www.bpb.de/sites/default/files/xmlsitemap/oWx2Pl033k1XFmYJFOs7sO0G3JasH0cjDbduvDwKuwo/index.xml'
        p=policies['www.bpb.de']
        # Sonder-Queue: nur initiale geprüfte Sitemap, deren Links wieder Pfadfilter unterliegen.
        now=time.time()
        con.execute('INSERT OR IGNORE INTO queue(id,url,host,grp,depth,priority,type,added,updated) VALUES(?,?,?,?,?,?,?,?,?)',
            (url_id(url),url,p['host'],p['group'],0,9,'sitemap',now,now));new+=1
    con.commit();return new


def event(con,host,reason):
    con.execute('INSERT INTO events(host,reason,n) VALUES(?,?,1) ON CONFLICT(host,reason) DO UPDATE SET n=n+1',(host,reason))


def stats(con):
    rows=dict(con.execute('SELECT state,COUNT(*) FROM queue GROUP BY state').fetchall()); d,n=con.execute('SELECT COUNT(*),COALESCE(SUM(LENGTH(CAST(text AS BLOB))),0) FROM docs').fetchone()
    return rows,d,n


def export_docs(con,out_path):
    out_path.parent.mkdir(parents=True,exist_ok=True);temp=out_path.with_suffix('.tmp')
    with temp.open('w',encoding='utf-8',newline='\n') as f:
        for row in con.execute('SELECT id,url,grp,title,doc_type,file_type,text,headings,license,raw_bytes,crawled_at FROM docs ORDER BY crawled_at,id'):
            ident,url,grp,title,dtype,ftype,body,headings,lic,raw,when=row
            f.write(json.dumps(dict(docno=ident,url=url,title=title,text=body,doc_type=dtype,source_group=grp,format=ftype,headings=json.loads(headings or '[]'),license=lic,raw_bytes=raw,crawled_at=when),ensure_ascii=False)+'\n')
    temp.replace(out_path)


def write_report(con,out_path):
    q,d,by=stats(con)
    values=con.execute("SELECT host,reason,n FROM events ORDER BY n DESC LIMIT 100").fetchall()
    hostdoc=con.execute('SELECT grp,COUNT(*),SUM(LENGTH(CAST(text AS BLOB))) FROM docs GROUP BY grp ORDER BY 3 DESC').fetchall()
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'queue_states':q,'documents':d,'text_corpus_mib':round(by/(1024**2),3),'bytes_extracted_text':by,'not_counted':'raw files, ZIP, metadata, sqlite overhead','top_reasons':[{'host':h,'reason':e,'count':n} for h,e,n in values],'by_source':[{'group':a,'documents':b,'mib':round(c/(1024**2),3)} for a,b,c in hostdoc]}
    out_path.parent.mkdir(parents=True,exist_ok=True);out_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


def run(args):
    seeds=json.loads(Path(args.seeds).read_text(encoding='utf-8'))
    policies=policies_from_seeds(seeds)
    con=connect(Path(args.db),reset_inflight=True);fresh=load_seeds(con,seeds,policies,args.bpb_sitemap)
    print('Neue Seeds:',fresh,'| Hosts:',len(policies),'| Worker:',args.workers,'| Ziel:',args.target_mib,'MiB TEXT',flush=True)
    print('Eine 429-Antwort pausiert den Host. Keine Proxy-Rotation, keine Schutzumgehung.',flush=True)
    deadline=time.monotonic()+args.hours*3600
    active={};host_next=collections.defaultdict(float);host_block_until=collections.defaultdict(float)
    futures={}; last_log=0; since_commit=0; processed=0
    def process(fut,task):
        nonlocal processed,since_commit
        host=task['host'];policy=policies[host]
        try:r=fut.result()
        except Exception as e:r={'kind':'error','reason':'worker_'+type(e).__name__}
        kind=r['kind'];reason=r.get('reason',kind)
        if kind=='retry':
            if task['attempts']<args.max_attempts:
                delay=max(float(r.get('wait',60)), min(3600,30*(2**task['attempts'])))
                host_block_until[host]=max(host_block_until[host],time.monotonic()+delay)
                con.execute("UPDATE queue SET state='pending',ready=?,reason=?,updated=? WHERE id=?",(time.time()+delay,reason,time.time(),task['id']))
            else:
                con.execute("UPDATE queue SET state='error',reason=?,updated=? WHERE id=?",('retries_exhausted_'+reason,time.time(),task['id']))
        elif kind in ('blocked','error','skip'):
            state='blocked' if kind=='blocked' else 'error' if kind=='error' else 'skipped'
            con.execute('UPDATE queue SET state=?,reason=?,updated=? WHERE id=?',(state,reason,time.time(),task['id']))
            if kind=='skip' and r.get('links'):
                for u in r['links'][:args.max_links_page]:add_queue(con,u,policy,task['depth']+1,group=task['grp'])
        else:
            con.execute("UPDATE queue SET state='done',reason=?,updated=? WHERE id=?",(kind,time.time(),task['id']))
            if kind=='document':
                content_hash=hashlib.sha256(r['text'].encode('utf-8')).hexdigest()
                res=con.execute('INSERT OR IGNORE INTO docs(id,url,grp,title,doc_type,file_type,content_hash,text,headings,license,raw_bytes,crawled_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                    (task['id'],r['url'],task['grp'],r['title'],r['doc_type'],r['file_type'],content_hash,r['text'],json.dumps(r['headings'],ensure_ascii=False),policy.get('license','check_at_source'),r['raw_bytes'],datetime.now(timezone.utc).isoformat()))
                if res.rowcount==0:reason='duplicate_content'
                for u in r['links'][:args.max_links_page]:
                    add_queue(con,u,policy,task['depth']+1,group=task['grp'])
            elif kind=='sitemap':
                limit=min(args.max_sitemap_entries,500) if task['grp'].startswith('legacy_') else args.max_sitemap_entries
                for u in r['links'][:limit]:add_queue(con,u,policy,0,priority=max(1,policy['priority']-1),group=task['grp'])
                for u in r['sitemaps'][:(3 if task['grp'].startswith('legacy_') else args.max_sitemaps)]:
                    # Sitemap-URL außerhalb Contentpfad benötigt explizite Sonderbehandlung.
                    if urlsplit(u).hostname in [host]+policy.get('aliases',[]):
                        t=time.time();con.execute('INSERT OR IGNORE INTO queue(id,url,host,grp,depth,priority,type,added,updated) VALUES(?,?,?,?,?,?,?,?,?)',
                            (url_id(u),u,host,policy['group'],0,2,'sitemap',t,t))
        event(con,host,reason)
        active[host]=max(0,active.get(host,1)-1)
        processed+=1;since_commit+=1
        if since_commit>=20:con.commit();since_commit=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        while not STOP.is_set() and time.monotonic()<deadline:
            if futures:
                done,_=concurrent.futures.wait(futures,timeout=0.01,return_when=concurrent.futures.FIRST_COMPLETED)
                for f in done:process(f,futures.pop(f))
            now=time.monotonic()
            if now-last_log>=20:
                con.commit();q,d,bytes_=stats(con)
                print(f"{datetime.now().strftime('%H:%M:%S')} | Aufträge:{processed} | Indiziert:{d} | TEXT:{bytes_/(1024**2):.2f}/{args.target_mib}MiB | offen:{q.get('pending',0)} | Fehler:{q.get('error',0)} | blockiert:{q.get('blocked',0)}",flush=True)
                write_report(con,Path(args.report)); last_log=now
                if bytes_>=args.target_mib*1024*1024:
                    print('Textziel erreicht; sauberer Export.',flush=True);break
            scheduled=0
            if len(futures)<args.workers:
                rows=con.execute('SELECT id,url,host,grp,depth,priority,type,attempts FROM queue WHERE state="pending" AND ready<=? ORDER BY priority DESC,depth ASC,added ASC LIMIT 2000',(time.time(),)).fetchall()
                for row in rows:
                    if len(futures)>=args.workers:break
                    ident,url,host,grp,depth,prio,typ,attempts=row
                    if active.get(host,0)>= (1 if host=='de.wikipedia.org' else args.per_host):continue
                    if now < max(host_next[host],host_block_until[host]):continue
                    pol=policies.get(host)
                    if not pol:continue
                    task={'id':ident,'url':url,'host':host,'grp':grp,'depth':depth,'priority':prio,'type':typ,'attempts':attempts}
                    con.execute('UPDATE queue SET state="inflight",attempts=attempts+1,updated=? WHERE id=?',(time.time(),ident))
                    f=pool.submit(extract_sitemap if typ=='sitemap' else extract,task,pol,args.max_bytes)
                    futures[f]=task;active[host]=active.get(host,0)+1
                    host_next[host]=now+max(SPECIAL_DELAY.get(host,args.host_delay),ROBOTS_DELAY.get(host,0))
                    scheduled+=1
            if not futures and not scheduled:
                q,d,_=stats(con)
                if q.get('pending',0)==0:print('Warteschlange ist leer.',flush=True);break
                time.sleep(2)
            elif not scheduled:time.sleep(0.05)
        if futures:
            print('Beende nach laufenden Requests (maximal Request-Timeout) ...',flush=True)
            STOP.set()
            for fut,task in list(futures.items()):
                try:process(fut,task)
                except Exception:pass
    con.commit();report=write_report(con,Path(args.report));export_docs(con,Path(args.export))
    print('ENDE:',report['documents'],'Dokumente',report['text_corpus_mib'],'MiB extrahierter Text')
    print('Export:',args.export,'| Bericht:',args.report)
    con.close()


def acquire_run_lock(path):
    """Sperrt parallele Crawler-Prozesse auf derselben DB; Lock fällt beim Prozessende weg."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    h=path.with_suffix(path.suffix+'.runlock').open('a+b')
    try:
        if os.name=='nt':
            import msvcrt
            h.seek(0);h.write(b'x');h.flush();h.seek(0)
            msvcrt.locking(h.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(h.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except (OSError,IOError):
        h.close();raise RuntimeError('Es läuft bereits ein Crawler mit dieser SQLite-Datei.')
    return h


def main():
    parser=argparse.ArgumentParser(description='DidaDex Quellenexpansion: Ausführung, Export oder Status')
    parser.add_argument('command',choices=['run','status','export'],nargs='?',default='run')
    parser.add_argument('--seeds',default=str(BASE/'seeds.json'))
    parser.add_argument('--db',default=str(DATA/'expanded.sqlite'))
    parser.add_argument('--export',default=str(DATA/'documents.jsonl'))
    parser.add_argument('--report',default=str(DATA/'report.json'))
    parser.add_argument('--hours',type=float,default=24)
    parser.add_argument('--target-mib',type=int,default=500)
    parser.add_argument('--workers',type=int,default=20)
    parser.add_argument('--per-host',type=int,default=1)
    parser.add_argument('--host-delay',type=float,default=2.5)
    parser.add_argument('--max-attempts',type=int,default=4)
    parser.add_argument('--max-bytes',type=int,default=24*1024*1024)
    parser.add_argument('--max-links-page',type=int,default=90)
    parser.add_argument('--max-sitemap-entries',type=int,default=8000)
    parser.add_argument('--max-sitemaps',type=int,default=80)
    parser.add_argument('--bpb-sitemap',action='store_true',help='bpb Sitemapindex (exakt robots.txt Stand 11.11.2026)')
    args=parser.parse_args()
    if args.workers<1 or args.workers>40 or args.per_host<1 or args.per_host>2 or args.host_delay<1 or args.max_bytes>50_000_000:
        parser.error('Limit: 1..40 Worker, 1..2 pro Host, Host-Abstand >=1 Sekunde, Dateicap <=50MB')
    if args.command=='run':
        signal.signal(signal.SIGINT,lambda *a: STOP.set())
        signal.signal(signal.SIGTERM,lambda *a: STOP.set())
        lock=acquire_run_lock(args.db)
        try:run(args)
        finally:lock.close()
    else:
        con=connect(Path(args.db))
        if args.command=='status':
            report=write_report(con,Path(args.report));print(json.dumps(report,ensure_ascii=False,indent=2))
        else:export_docs(con,Path(args.export));print('Export',args.export)
        con.close()

if __name__=='__main__':main()
