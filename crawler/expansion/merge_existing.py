"""Vereinigt neue Expansion-JSONL mit dem bestehenden DidaDex-JSONL oder DB-Export.
Nur nach Beenden/sauberem Export des bestehenden Crawlers verwenden.
"""
from __future__ import annotations
import argparse, hashlib, json, sqlite3
from pathlib import Path
from crawler import normalize


def records(path):
    path=Path(path)
    if path.suffix.lower() in ('.jsonl','.ndjson'):
        with path.open(encoding='utf-8') as f:
            for n,line in enumerate(f,1):
                try: obj=json.loads(line)
                except ValueError: continue
                if isinstance(obj,dict): yield obj
    elif path.suffix.lower() in ('.sqlite','.db'):
        # Verlässliche Datenbank-Snapshots nur bei gestopptem Ursprungsprozess.
        db=sqlite3.connect(f'file:{path.resolve().as_posix()}?mode=ro',uri=True)
        tables=[x[0] for x in db.execute('SELECT name FROM sqlite_master WHERE type="table"')]
        table=next((x for x in ('documents','docs') if x in tables),None)
        if not table: raise RuntimeError('Weder documents noch docs als Tabelle gefunden')
        columns=[x[1] for x in db.execute(f'PRAGMA table_info({table})')]
        if not {'url','title','text'} <= set(columns):
            raise RuntimeError(f'{table}: Keine Spalten url/title/text. Bitte JSONL-Export des Originalcrawlers wählen. Vorhanden: {columns}')
        for row in db.execute(f'SELECT * FROM {table}'):
            yield dict(zip(columns,row))
        db.close()
    else:raise ValueError(f'Unbekannter Dateityp: {path}')


def merge(inputs,out):
    seen_urls,seen_text=set(),set();count=0;repeated=0;bytes_=0
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',encoding='utf-8',newline='\n') as f:
        for path in inputs:
            for obj in records(path):
                raw_url=obj.get('url') or ''
                url=normalize(raw_url)
                if url and obj.get('archive_member'):
                    # Distinkte Datei im selben ZIP; Fragment ist nicht Bestandteil des HTTP-Abrufs.
                    url=url+'#archive-'+hashlib.sha256(obj['archive_member'].encode('utf-8')).hexdigest()[:20]
                body=obj.get('text') or obj.get('search_text') or obj.get('content') or ''
                if not isinstance(body,str) or not body.strip() or not url:continue
                digest=hashlib.sha256(' '.join(body.split()).encode('utf-8')).hexdigest()
                if url in seen_urls or digest in seen_text: repeated+=1;continue
                seen_urls.add(url);seen_text.add(digest)
                ident=hashlib.sha256(url.encode('utf-8')).hexdigest()
                obj.update({'docno':ident,'url':url,'text':body})
                f.write(json.dumps(obj,ensure_ascii=False)+'\n');count+=1;bytes_+=len(body.encode('utf-8'))
    print(f'Dokumente: {count:,} | Duplikate ausgelassen: {repeated:,} | Textkorpus: {bytes_/1024**2:.2f} MiB')
    print('Ausgabe:',out)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--existing',required=True,help='Bisheriges documents.jsonl bzw. originale SQLite (NACH STOP)')
    p.add_argument('--expanded',default=str(Path(__file__).resolve().parent.parent/'outputs'/'expansion'/'documents.jsonl'))
    p.add_argument('--out',default=str(Path(__file__).resolve().parent.parent/'outputs'/'expansion'/'merged_documents.jsonl'))
    a=p.parse_args();merge([a.existing,a.expanded],a.out)
