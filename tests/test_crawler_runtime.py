"""Offline checks for the canonical crawler.py runtime and its JSON catalogues."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRAWLER_SCRIPT = ROOT / 'crawler' / 'crawler.py'


def load_runtime():
    spec = importlib.util.spec_from_file_location('didadex_crawler_runtime_test', CRAWLER_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Crawler-Skript nicht importierbar: {CRAWLER_SCRIPT}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CrawlerRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.crawler = load_runtime()

    def test_external_catalogues_preserve_the_current_source_catalogue(self):
        self.assertEqual(len(self.crawler.SOURCES), 150)
        self.assertEqual(len(self.crawler.SEEDS), 406)
        self.assertEqual(len(self.crawler.ALLOWED_HOSTS), 228)
        self.assertIn('Informatik', self.crawler.SUBJECT_ALIASES)
        self.assertIn('zum_unterrichten', self.crawler.SEED_EXTENSIONS)

    def test_json_runtime_config_controls_the_canonical_crawler(self):
        self.crawler._apply_runtime_config({
            'mode': 'TEST', 'run_name': 'runtime_test', 'target_mib': 1,
            'profile': {
                'runtime_minutes': 1, 'max_pages': 2, 'max_depth': 3,
                'workers': 1, 'max_per_host': 4, 'max_queue': 5,
            },
            'seed_pages': 2, 'dfs_depth_step': 3,
            'subjects': ['Informatik', 'NichtVorhanden'],
            'QUELLEN_UEBERGREIFEND': False,
            'MAX_ROBOTS_SITEMAPS_PER_HOST': 4,
            'STORE_CRAWL_EDGES': False,
        })
        self.assertEqual(self.crawler.PROFILE['pages_per_seed_turn'], 2)
        self.assertEqual(self.crawler.DFS_DEPTH_STEP, 3)
        self.assertEqual(self.crawler.SUBJECT_FILTER, ['Informatik'])
        self.assertFalse(self.crawler.QUELLEN_UEBERGREIFEND)

    def test_runtime_accepts_up_to_sixty_hours_and_rejects_more(self):
        self.crawler._apply_runtime_config({
            'mode': 'NACHT', 'profile': {'runtime_minutes': 60 * 60},
        })
        self.assertEqual(self.crawler.PROFILE['runtime_minutes'], 60 * 60)
        with self.assertRaisesRegex(ValueError, 'maximal 60 Stunden'):
            self.crawler._apply_runtime_config({
                'mode': 'NACHT', 'profile': {'runtime_minutes': 60 * 60 + 1},
            })

    def test_desktop_payload_is_accepted_by_the_canonical_crawler(self):
        from engine import MAX_RUNTIME_HOURS, crawl_config_payload, runtime_minutes_from_selection

        self.assertEqual(MAX_RUNTIME_HOURS, 60)
        self.assertEqual(runtime_minutes_from_selection('5 min'), 5)
        self.assertEqual(runtime_minutes_from_selection('60 h'), 60 * 60)
        with self.assertRaises(ValueError):
            runtime_minutes_from_selection('61 h')

        payload = crawl_config_payload({
            'mode': 'TEST', 'run_name': 'desktop_runtime_test', 'target_mib': 1,
            'runtime_minutes': 60 * 60, 'max_pages': 2, 'max_depth': 3,
            'workers': 1, 'max_per_host': 4, 'max_queue': 5,
            'DOWNLOAD_DELAY_SECONDS': 0, 'MIN_TEXT_CHARS': 1,
            'MAX_TEXT_CHARS': 100, 'MAX_MATERIAL_MIB': 1,
            'DOWNLOAD_MATERIALS': False, 'ONLY_OPEN_LICENSE_MATERIALS': True,
            'CHECK_LICENSE_IN_PDFS': True, 'SITEMAPS_AKTIV': True,
            'QUELLEN_UEBERGREIFEND': False, 'STORE_BINARY_MATERIALS': False,
            'DYNAMIC_DEPTH': True, 'FAIR_HOST_SCHEDULING': True,
            'INCLUDE_GENERAL_METHODS': True, 'subjects': ['Informatik'],
            'seed_pages': 2, 'dfs_depth_step': 3,
        })
        self.crawler._apply_runtime_config(payload)
        self.assertEqual(self.crawler.RUN_NAME, 'desktop_runtime_test')
        self.assertEqual(self.crawler.PROFILE['runtime_minutes'], 60 * 60)
        self.assertEqual(self.crawler.PROFILE['pages_per_seed_turn'], 2)
        self.assertEqual(self.crawler.DFS_DEPTH_STEP, 3)


if __name__ == '__main__':
    unittest.main()
