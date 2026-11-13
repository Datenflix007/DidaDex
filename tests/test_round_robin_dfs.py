"""Offline-Regressionstests für DidaDex Round-Robin-DFS (keine Netzanfragen)."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

NOTEBOOK = Path(__file__).resolve().parents[1] / 'crawler' / 'crawler.ipynb'


def load_crawler():
    notebook = json.loads(NOTEBOOK.read_text(encoding='utf-8'))
    env = {'__name__': 'didadex_offline_test'}
    for cell_idx in (1, 5, 7, 9):
        exec(compile(''.join(notebook['cells'][cell_idx]['source']),
                     f'notebook_cell_{cell_idx}', 'exec'), env)
    env['SEEDS'] = ['https://a.test/root', 'https://b.test/root']
    env['ALLOWED_HOSTS'] = {'a.test', 'b.test'}
    env['HOST_TO_SOURCE'] = {'a.test': 'A', 'b.test': 'B'}
    env['SOURCES'] = {'A': {'hosts': ['a.test'], 'seeds': [env['SEEDS'][0]]},
                      'B': {'hosts': ['b.test'], 'seeds': [env['SEEDS'][1]]}}
    env['SITEMAPS_AKTIV'] = False
    env['MIN_TEXT_CHARS'] = 100
    env['DOWNLOAD_MATERIALS'] = False
    env['PROFILE'] = dict(max_pages=8, runtime_minutes=5, max_depth=50,
                          workers=1, max_per_host=100, max_queue=5000,
                          pages_per_seed_turn=3)
    env['DFS_DEPTH_STEP'] = 5
    env['DOWNLOAD_DELAY_SECONDS'] = 0
    env['DEPTH_HEATMAP_INTERVAL'] = 9999
    return env


def fake_html(links, title='Unterrichtseinheit Informatik'):
    inner = ('Unterrichtsverlauf: Erarbeitung und Sicherung. '
             'Arbeitsauftrag: Analysiere die Aufgabe. '
             'Methodische Hinweise zur Gruppenarbeit. ' * 10)
    anchors = ''.join(f'<a href="{link}">Weiteres Material</a>' for link in links)
    return (f'<!doctype html><html><head><title>{title}</title></head>'
            f'<body><main><h1>{title}</h1><p>{inner}</p>{anchors}</main></body></html>').encode('utf-8')


class RoundRobinDfsTests(unittest.TestCase):
    def setUp(self):
        self.env = load_crawler()
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def new_crawler(self):
        return self.env['TeachingCrawler'](self.folder)

    def test_deep_paths_are_visited_in_first_seed_turn(self):
        crawler = self.new_crawler()
        graph = {}
        for host in ('a', 'b'):
            nodes = [f'https://{host}.test/root' + ('/child' * i) for i in range(4)]
            for i, node in enumerate(nodes):
                graph[node] = fake_html([nodes[i+1]] if i+1<len(nodes) else [], title=f'Unterrichtseinheit Informatik: {node}')
        crawler.fetch = lambda url, kind: (url, graph[url], {'Content-Type': 'text/html; charset=utf-8'})
        visited=[]
        original_process=crawler._process_item
        def record_visit(item,seed):
            visited.append((seed,item[2]))
            return original_process(item,seed)
        crawler._process_item=record_visit
        try:
            crawler.crawl()
            rows = crawler.db.execute("SELECT url,depth,status,root_seed FROM frontier WHERE status='done' ORDER BY rowid").fetchall()
            depths = [d for _, d, _, _ in rows]
            self.assertEqual(len(rows), 8)
            self.assertEqual(set(depths), {0,1,2,3})
            self.assertEqual([d for _,d in visited[:3]], [0,1,2])  # DFS vor dem nächsten Seed
            self.assertEqual([d for _,d in visited[3:6]], [0,1,2])
            for url,depth,status,root in rows:
                self.assertEqual(root, f'https://{url.split(".")[0].split("//")[-1]}.test/root')
            self.assertEqual(crawler.db.execute("SELECT COUNT(*) FROM frontier").fetchone()[0], 8)
            self.assertGreaterEqual(crawler.db.execute("SELECT COUNT(*) FROM documents").fetchone()[0], 6)
        finally:
            crawler.close()
        resumed = self.new_crawler()
        try:
            self.assertEqual(resumed.processed,8)
            self.assertEqual(resumed.db.execute("SELECT COUNT(*) FROM frontier").fetchone()[0],8)
            # Alte Datensätze bleiben bei einem erneuten Start unangetastet.
            self.assertEqual(resumed.db.execute("SELECT COUNT(*) FROM documents").fetchone()[0],8)
        finally:
            resumed.close()

    def test_progressive_depth_cap_and_url_deduplication(self):
        crawler = self.new_crawler()
        try:
            seed = self.env['SEEDS'][0]
            deep = 'https://a.test/sehr/tiefer/inhalt'
            self.assertTrue(crawler.queue_url(deep,7,parent=seed,relevance=8))
            self.assertFalse(crawler.queue_url(deep,7,parent=seed,relevance=8))
            assignment = crawler.acquire_seed()
            self.assertEqual(assignment, (seed,5,1))
            self.assertEqual(crawler.claim_seed(seed,5)[0],seed)
            self.assertIsNone(crawler.claim_seed(seed,5))
            crawler.complete(seed,depth=0,host='a.test')
            crawler.release_seed(seed)
            # Seed B ist jetzt zuerst dran; nach der B-Runde folgt A mit Tiefe 10.
            second = crawler.acquire_seed()
            self.assertEqual(second[0],self.env['SEEDS'][1])
            b_item=crawler.claim_seed(second[0],second[1])
            crawler.complete(b_item[0],depth=0,host='b.test')
            crawler.release_seed(second[0])
            third = crawler.acquire_seed()
            self.assertEqual(third,(seed,10,2))
            self.assertEqual(crawler.claim_seed(seed,10)[0],deep)
            crawler.release_seed(seed)
        finally:
            crawler.close()

    def test_concurrent_leases_prefer_different_hosts(self):
        env=self.env
        env['SEEDS']=['https://a.test/root','https://a.test/also-root','https://b.test/root']
        crawler=self.new_crawler()
        try:
            first=crawler.acquire_seed()
            second=crawler.acquire_seed()
            self.assertEqual(first[0],env['SEEDS'][0])
            self.assertEqual(second[0],env['SEEDS'][2])
            crawler.release_seed(first[0]); crawler.release_seed(second[0])
        finally:
            crawler.close()

    def test_root_attribution_survives_redirected_pages(self):
        crawler=self.new_crawler()
        try:
            root=self.env['SEEDS'][0]
            # Die von einem Redirect gelieferte URL ist kein frontier-Knoten.
            redirected='https://b.test/redirected-lesson'
            child='https://b.test/next-lesson'
            data=fake_html([child],title='Unterrichtseinheit Informatik: Redirect')
            crawler.handle_html(redirected,data,{'Content-Type':'text/html'},1,
                                root_seed=root)
            parent=crawler.db.execute('SELECT root_seed,parent FROM frontier WHERE url=?',
                                      (child,)).fetchone()
            self.assertEqual(parent,(root,redirected))
        finally:
            crawler.close()

    def test_redirect_target_keeps_meaningful_terminal_slash(self):
        canon = self.env['canon']
        self.assertEqual(canon('https://a.test/lesson/'),
                         'https://a.test/lesson')
        self.assertEqual(canon('https://a.test/lesson/', preserve_trailing_slash=True),
                         'https://a.test/lesson/')
        self.assertEqual(canon('https://a.test//lesson///', preserve_trailing_slash=True),
                         'https://a.test/lesson/')

    def test_fetch_follows_terminal_slash_redirect_once(self):
        crawler = self.new_crawler()

        class Response:
            def __init__(self, status_code, headers=None, body=b''):
                self.status_code = status_code
                self.headers = headers or {}
                self.body = body
                self.closed = False

            def iter_content(self, _chunk_size):
                if self.body:
                    yield self.body

            def close(self):
                self.closed = True

        class Session:
            def __init__(self):
                self.calls = []

            def get(self, url, **_kwargs):
                self.calls.append(url)
                if url == 'https://a.test/lesson':
                    return Response(301, {'Location': '/lesson/'})
                if url == 'https://a.test/lesson/':
                    return Response(200, {'Content-Type': 'text/html'}, b'<html>OK</html>')
                raise AssertionError(f'unexpected request: {url}')

        session = Session()
        crawler.session = lambda: session
        crawler.robots_allow = lambda _url: (True, 0)
        try:
            actual, body, headers = crawler.fetch('https://a.test/lesson', 'html')
            self.assertEqual(actual, 'https://a.test/lesson/')
            self.assertEqual(body, b'<html>OK</html>')
            self.assertEqual(headers['Content-Type'], 'text/html')
            self.assertEqual(session.calls,
                             ['https://a.test/lesson', 'https://a.test/lesson/'])
        finally:
            crawler.close()

    def test_fetch_stops_an_actual_redirect_loop_after_first_repeat(self):
        crawler = self.new_crawler()

        class Response:
            status_code = 301
            headers = {'Location': '/loop'}

            def close(self):
                pass

        class Session:
            def __init__(self):
                self.calls = []

            def get(self, url, **_kwargs):
                self.calls.append(url)
                return Response()

        session = Session()
        crawler.session = lambda: session
        crawler.robots_allow = lambda _url: (True, 0)
        try:
            with self.assertRaisesRegex(ValueError, '^redirect_loop$'):
                crawler.fetch('https://a.test/loop', 'html')
            self.assertEqual(session.calls, ['https://a.test/loop'])
        finally:
            crawler.close()

    def test_resume_requeues_only_legacy_redirect_errors(self):
        crawler = self.new_crawler()
        try:
            old_redirect, other_error = self.env['SEEDS']
            crawler.db.execute("UPDATE frontier SET status='error', error='too_many_redirects' WHERE url=?",
                               (old_redirect,))
            crawler.db.execute("UPDATE frontier SET status='error', error='HTTP_404' WHERE url=?",
                               (other_error,))
            crawler.db.commit()
        finally:
            crawler.close()

        resumed = self.new_crawler()
        try:
            rows = dict(resumed.db.execute("SELECT url,status FROM frontier WHERE url IN (?,?)",
                                           (old_redirect, other_error)))
            self.assertEqual(resumed.requeued_legacy_redirects, 1)
            self.assertEqual(rows[old_redirect], 'queued')
            self.assertEqual(rows[other_error], 'error')
        finally:
            resumed.close()

    def test_heatmap_uses_interval_unless_forced(self):
        crawler = self.new_crawler()
        try:
            self.assertTrue(crawler.write_depth_heatmap())
            self.assertFalse(crawler.write_depth_heatmap())
            self.assertTrue(crawler.write_depth_heatmap(force=True))
        finally:
            crawler.close()

    def test_robots_redirect_discovers_only_allowed_declared_sitemap(self):
        self.env['SITEMAPS_AKTIV'] = True
        self.env['MODUS'] = 'STANDARD'
        crawler = self.new_crawler()

        class Response:
            def __init__(self, status_code, headers=None, text=''):
                self.status_code = status_code
                self.headers = headers or {}
                self.text = text

            def close(self):
                pass

        class Session:
            def __init__(self):
                self.calls = []

            def get(self, url, **_kwargs):
                self.calls.append(url)
                if url == 'https://a.test/robots.txt':
                    return Response(301, {'Location': 'https://b.test/robots.txt'})
                if url == 'https://b.test/robots.txt':
                    return Response(200, text=(
                        'User-agent: *\nAllow: /\n'
                        'Sitemap: https://b.test/sitemap-index.xml\n'
                        'Sitemap: https://outside.test/sitemap.xml\n'))
                raise AssertionError(f'unexpected request: {url}')

        session = Session()
        crawler.session = lambda: session
        try:
            self.assertEqual(crawler.robots_allow('https://a.test/lesson'), (True, 0.0))
            row = crawler.db.execute("SELECT kind FROM frontier WHERE url=?",
                                     ('https://b.test/sitemap-index.xml',)).fetchone()
            self.assertEqual(row, ('sitemap',))
            self.assertEqual(session.calls,
                             ['https://a.test/robots.txt', 'https://b.test/robots.txt'])
        finally:
            crawler.close()

    def test_multiple_workers_keep_unique_frontier_rows(self):
        self.env['PROFILE']['workers']=3
        self.env['PROFILE']['max_pages']=20
        self.env['PROFILE']['pages_per_seed_turn']=2
        crawler=self.new_crawler()
        graph={}
        for host in ('a','b'):
            nodes=[f'https://{host}.test/root' + ('/path' * i) for i in range(3)]
            for i,node in enumerate(nodes):
                graph[node]=fake_html([nodes[i+1]] if i+1<len(nodes) else [],
                                      title='Unterrichtsstunde: '+node)
        crawler.fetch=lambda u,kind:(u,graph[u],{'Content-Type':'text/html'})
        try:
            crawler.crawl()
            rows=crawler.db.execute("SELECT url,root_seed,status FROM frontier").fetchall()
            self.assertEqual(len(rows),6)
            self.assertEqual(len({url for url,_,_ in rows}),6)
            self.assertTrue(all(status=='done' for _,_,status in rows))
        finally:
            crawler.close()

    def test_migration_from_existing_frontier_without_root_seed(self):
        state=self.folder/'crawler_state.sqlite'
        with sqlite3.connect(state) as db:
            db.execute("""CREATE TABLE frontier (
                url TEXT PRIMARY KEY,kind TEXT,depth INTEGER,priority INTEGER,parent TEXT,
                inherited_license TEXT,status TEXT DEFAULT 'queued',error TEXT,relevance INTEGER DEFAULT 0)""")
            db.execute("INSERT INTO frontier (url,kind,depth,priority,parent,status) VALUES (?,?,?,?,?,?)",
                       ('https://a.test/root','html',0,10,'','done'))
            db.execute("INSERT INTO frontier (url,kind,depth,priority,parent,status) VALUES (?,?,?,?,?,?)",
                       ('https://a.test/root/child','html',1,10,'https://a.test/root','queued'))
        db.close()
        crawler=self.new_crawler()
        try:
            row=crawler.db.execute("SELECT root_seed FROM frontier WHERE url='https://a.test/root/child'").fetchone()
            self.assertEqual(row[0],'https://a.test/root')
            self.assertEqual(crawler.claim_seed('https://a.test/root',5)[2],1)
        finally:
            crawler.close()


if __name__ == '__main__':
    unittest.main()
