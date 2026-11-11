import io, json, sqlite3, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent / "crawler" / "expansion"))
from crawler import normalize, is_allowed, parse_html, connect, add_queue, stats, export_docs, text_from_file, policies_from_seeds
from build_seeds import make_seeds
from merge_existing import merge

class CrawlerOfflineTests(unittest.TestCase):
    def test_250_wikipedia(self):
        seeds=make_seeds(); w=[s for s in seeds if s['source_kind']=='reference']
        self.assertEqual(len(w),250)
        self.assertEqual(len({s['url'] for s in w}),250)
        for group in set(s['discipline'] for s in w):self.assertEqual(len([s for s in w if s['discipline']==group]),50)
    def test_url_canonicalization(self):
        a=normalize('HTTPS://example.org/x?utm_source=a&p=2&fbclid=a#anchor')
        self.assertEqual(a,'https://example.org/x?p=2')
        self.assertNotEqual(normalize('https://example.org/x?page=2'),normalize('https://example.org/x?page=3'))
    def test_html_extraction(self):
        html=b'<html><head><title>Test</title></head><body><nav>XYZ</nav><main><h1>Geschichte</h1><p>Ein langer Inhalt mit Kompetenzen.</p><a href="/wiki/Unterricht">Unterricht</a></main></body></html>'
        p={'host':'unterrichten.zum.de','allow_paths':['/wiki/'],'group':'zum'}
        t,body,head,links=parse_html(html,'https://unterrichten.zum.de/wiki/Test',p)
        self.assertEqual(t,'Test');self.assertIn('Geschichte',body)
        self.assertNotIn('XYZ',body)
        self.assertIn('https://unterrichten.zum.de/wiki/Unterricht',links)
    def test_block_external_and_login(self):
        p={'host':'www.bpb.de','allow_paths':['/lernen/','/shop/materialien/']}
        self.assertFalse(is_allowed('https://www.bpb.de/user/login',p))
        self.assertFalse(is_allowed('https://evil.org/lernen/',p))
        self.assertTrue(is_allowed('https://www.bpb.de/lernen/materialsuche/',p))
    def test_archive_members_not_merged_away(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);one=td/'archives.jsonl';out=td/'merged.jsonl'
            records=[{'url':'https://site.test/material.zip#a.docx','archive_member':'a.docx','text':'Inhalt A','title':'a'},
                     {'url':'https://site.test/material.zip#b.docx','archive_member':'b.docx','text':'Inhalt B','title':'b'}]
            one.write_text(''.join(json.dumps(x)+'\n' for x in records),encoding='utf-8')
            merge([one],out)
            self.assertEqual(len(out.read_text().splitlines()),2)

    def test_sqlite_seed_dedupe_and_resume(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'a.sqlite';db=connect(path)
            p={'host':'x.de','group':'x','allow_paths':['/'],'priority':1,'max_depth':4}
            self.assertTrue(add_queue(db,'https://x.de/a',p))
            self.assertFalse(add_queue(db,'https://x.de/a',p))
            db.execute('UPDATE queue SET state="inflight"');db.commit();db.close()
            db=connect(path,reset_inflight=True)
            self.assertEqual(db.execute('SELECT state FROM queue').fetchone()[0],'pending')
            db.close()
    def test_export_and_merge(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            a=td/'a.jsonl';b=td/'b.jsonl';out=td/'out.jsonl'
            a.write_text(json.dumps({'url':'https://x.de/a','title':'A','text':'Test text'})+'\n',encoding='utf-8')
            b.write_text(json.dumps({'url':'https://x.de/a','title':'A2','text':'Test text'})+'\n'+json.dumps({'url':'https://x.de/b','title':'B','text':'Another text'})+'\n',encoding='utf-8')
            merge([a,b],out)
            self.assertEqual(len(out.read_text().strip().splitlines()),2)

if __name__=='__main__':unittest.main()
