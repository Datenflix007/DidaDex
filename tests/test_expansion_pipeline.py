import argparse, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent / "crawler" / "expansion"))
from crawler import run, STOP, connect, normalize

class PipelineOfflineTest(unittest.TestCase):
    def test_pipeline_persists_exports_and_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            td=Path(temp);url='https://lessons.test/unterricht/one';url2='https://lessons.test/unterricht/two'
            seeds=[{'url':url,'host':'lessons.test','allow_paths':['/unterricht/'],'group':'fixture','priority':5,'max_depth':2,'source_kind':'education','license':'CC BY'}]
            (td/'seeds.json').write_text(json.dumps(seeds))
            args=argparse.Namespace(seeds=str(td/'seeds.json'),db=str(td/'crawl.sqlite'),bpb_sitemap=False,workers=2,
                target_mib=500,hours=.002,max_bytes=300000,max_attempts=2,per_host=1,host_delay=1,
                max_links_page=10,max_sitemap_entries=100,max_sitemaps=5,export=str(td/'out.jsonl'),report=str(td/'r.json'))
            def fake_extract(task,policy,cap):
                return {'kind':'document','url':task['url'],'title':'Unterricht','text':('Material und Unterrichtsverlauf zu '+task['url']+' ')*15,
                        'headings':['Unterricht'],'doc_type':'teaching_activity','file_type':'html','links':[url2] if task['url']==url else [],'raw_bytes':1400}
            STOP.clear()
            with patch('crawler.extract',fake_extract):run(args)
            lines=[json.loads(x) for x in (td/'out.jsonl').read_text().splitlines()]
            self.assertEqual(len(lines),2)
            self.assertTrue((td/'r.json').exists())
            con=connect(td/'crawl.sqlite')
            self.assertEqual(con.execute('SELECT COUNT(*) FROM docs').fetchone()[0],2)
            con.close()
            with patch('crawler.extract',fake_extract):run(args)
            self.assertEqual(len((td/'out.jsonl').read_text().splitlines()),2)
            STOP.clear()

if __name__=='__main__':unittest.main()
