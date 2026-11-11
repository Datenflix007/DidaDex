"""Local-only regression tests; no network calls or Tk display required."""
import json
from pathlib import Path
import queue
import sqlite3
import tempfile
import unittest

from crawledDataViewer.live_dashboard import (HTML_NAME, SnapshotMonitor,
                                              html_report, read_snapshot, write_live_html)


class LiveDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.run = Path(self.temp.name) / 'a_live_run'
        self.run.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def _database(self):
        with sqlite3.connect(self.run / 'crawler_state.sqlite') as db:
            db.executescript('''
                CREATE TABLE frontier(url TEXT PRIMARY KEY,depth INT,status TEXT,root_seed TEXT);
                CREATE TABLE documents(url TEXT UNIQUE, doc_type TEXT, metadata TEXT);
                CREATE TABLE material_links(url TEXT);
                CREATE TABLE seed_schedule(root_seed TEXT,turns INT);
                CREATE TABLE crawl_depth_stats(host TEXT,depth INT,status TEXT,count INT);
            ''')
            db.executemany('INSERT INTO frontier VALUES (?,?,?,?)', [
                ('https://a.test/seed',0,'done','https://a.test/seed'),
                ('https://a.test/seed/lesson',1,'done','https://a.test/seed'),
                ('https://b.test/seed',0,'error','https://b.test/seed'),
                ('https://b.test/seed/task',1,'queued','https://b.test/seed'),
            ])
            db.executemany('INSERT INTO documents VALUES (?,?,?)', [
                ('https://a.test/seed','lesson',json.dumps({'crawl_depth':0})),
                ('https://a.test/seed/lesson','worksheet',json.dumps({'crawl_depth':1})),
                # A document may have a canonical URL not in frontier.
                ('https://a.test/canonical','worksheet',json.dumps({'crawl_depth':2})),
            ])
            db.execute('INSERT INTO material_links VALUES (?)', ('https://a.test/work.pdf',))
            db.executemany('INSERT INTO seed_schedule VALUES (?,?)',
                           [('https://a.test/seed',2),('https://b.test/seed',1)])
            db.executemany('INSERT INTO crawl_depth_stats VALUES (?,?,?,?)', [
                ('a.test',0,'done',1),('a.test',1,'done',1),('b.test',0,'error',1)])
        (self.run / 'crawler_live.json').write_text(
            json.dumps({'run':self.run.name,'updated_at':'2026-11-11T12:34:00Z',
                        'document_bytes':31215}), encoding='utf-8')

    def test_before_database_is_created(self):
        status = read_snapshot(self.run)
        self.assertTrue(status['pending'])
        self.assertEqual(status['indexed'], 0)

    def test_exact_sqlite_statistics_and_canonical_redirect(self):
        self._database()
        snap = read_snapshot(self.run)
        self.assertEqual((snap['discovered'],snap['visited'],snap['queued'],snap['errors']), (4,3,1,1))
        self.assertEqual((snap['indexed'],snap['material_links'],snap['seed_rounds']), (3,1,3))
        self.assertEqual(snap['corpus_bytes'],31215)
        matrix = {(x['host'],x['depth']):x for x in snap['cells']}
        self.assertEqual(matrix['a.test',2]['indexed'],1)
        self.assertEqual(matrix['b.test',0]['error'],1)

    def test_html_is_escaped_and_written_atomically(self):
        self._database()
        snap = read_snapshot(self.run)
        snap['cells'].append({'host':'<script>alert(1)</script>', 'depth':1, 'indexed':1})
        html = html_report(snap)
        self.assertNotIn('<script>',html)
        self.assertIn('&lt;script&gt;',html)
        out = write_live_html(self.run,snap)
        self.assertEqual(out.name,HTML_NAME)
        self.assertTrue(out.is_file())
        self.assertFalse((self.run/(HTML_NAME+'.tmp')).exists())

    def test_snapshot_monitor_writes_live_html(self):
        self._database()
        sink = queue.Queue()
        monitor = SnapshotMonitor(self.run,sink,interval=.5)
        monitor.start()
        try:
            kind, snapshot = sink.get(timeout=3)
            self.assertEqual(kind,'snapshot')
            self.assertEqual(snapshot['indexed'],3)
            self.assertTrue((self.run / HTML_NAME).exists())
        finally:
            monitor.stop()
            monitor.thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
