"""OPTIONAL: lokal heruntergeladenes Unterrichts-ZIP sicher als durchsuchbare Texte erschließen.
Lädt selbst keine ZIPs herunter; nie ausführbare Programme ausführen oder entpacken.
"""
import argparse, hashlib, json, re, zipfile
from pathlib import Path
from urllib.parse import quote
from crawler import text_from_file
EXT={'.pdf','.docx','.pptx','.odt','.txt','.md'}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('archives',nargs='+',help='Lokal gespeicherte, rechtmäßig bezogene ZIPs')
    ap.add_argument('--out',default=str(Path(__file__).resolve().parent.parent/'outputs'/'expansion'/'archive_documents.jsonl'))
    ap.add_argument('--source-url',required=True,help='Webadresse des offiziell angebotenen Archivs')
    ap.add_argument('--license',default='check_at_source')
    ap.add_argument('--max-files',type=int,default=20000)
    ap.add_argument('--max-member-mib',type=int,default=20)
    a=ap.parse_args()
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    count=0;done=set();size=0;skipped=0
    with out.open('w',encoding='utf-8') as f:
        for filename in a.archives:
            with zipfile.ZipFile(filename) as z:
                for info in z.infolist():
                    if count>=a.max_files:break
                    name=info.filename
                    suffix=Path(name).suffix.lower()
                    if (info.is_dir() or suffix not in EXT or info.flag_bits & 1 or
                        info.file_size> a.max_member_mib*1024*1024 or
                        info.compress_size<=0 or info.file_size/max(info.compress_size,1)>150 or
                        '../' in name.replace('\\','/') or name.startswith('/')):
                        skipped+=1;continue
                    try:
                        with z.open(info,'r') as stream:
                            data=stream.read(a.max_member_mib*1024*1024+1)
                        if len(data)>a.max_member_mib*1024*1024:skipped+=1;continue
                        body,typ=text_from_file(data,'',name)
                        body=re.sub(r'\s+',' ',body).strip()[:600000]
                        if len(body)<100:skipped+=1;continue
                        digest=hashlib.sha256(body.encode()).hexdigest()
                        if digest in done:skipped+=1;continue
                        done.add(digest)
                        url=a.source_url+'#'+quote(name,safe='/')
                        item={'docno':hashlib.sha256(url.encode()).hexdigest(),'url':url,'title':Path(name).name,'text':body,
                              'doc_type':'teaching_material','source_group':'local_archive','format':typ,
                              'license':a.license,'archive_name':Path(filename).name,'archive_member':name}
                        f.write(json.dumps(item,ensure_ascii=False)+'\n')
                        count+=1;size+=len(body.encode('utf-8'))
                    except Exception:
                        skipped+=1
    print(f'{count} Texte extrahiert, {skipped} ausgelassen, {size/1024**2:.2f} MiB Text (NICHT ZIP-Größe)')
    print('Ausgabe:',out)
if __name__=='__main__':main()
