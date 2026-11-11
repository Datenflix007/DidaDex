"""GUI smoke tests (run on Windows or under xvfb-run on Linux).

No network crawl is started. Tests layout and basic controls only.
"""
from __future__ import annotations

import unittest
import tkinter as tk
from engine_desktop import DidaDexDesktop


class WidescreenLayoutTests(unittest.TestCase):
    def setUp(self):
        try:
            self.app = DidaDexDesktop()
        except tk.TclError as exc:
            self.skipTest(f'Kein grafischer Bildschirm verfügbar: {exc}')
        self.app.geometry('1450x860')
        self.app.update_idletasks()

    def tearDown(self):
        if getattr(self, 'app', None) is not None:
            try:
                # The viewer also polls Tk 'after'. Cancel callbacks before
                # destroying the test root to avoid stale Tcl callbacks.
                for job in self.app.tk.call('after', 'info'):
                    self.app.after_cancel(job)
                self.app.destroy()
            except tk.TclError:
                pass

    def test_horizontal_panels_and_settings_round_trip(self):
        self.assertEqual(str(self.app._split.cget('orient')), 'horizontal')
        self.app.running = True
        self.app._show_dashboard()
        self.app.update()
        self.assertTrue(self.app._dashboard_shell.winfo_ismapped())
        self.assertFalse(self.app._settings_panel.winfo_ismapped())
        self.assertFalse(self.app._legacy_progress.winfo_ismapped())
        self.assertTrue(self.app._monitor_panel.winfo_ismapped())
        self.assertTrue(self.app._console_panel.winfo_ismapped())
        self.assertGreater(self.app._split.winfo_width(), 800)
        self.assertGreater(self.app._split.sashpos(0), 400)
        self.app.running = False
        self.app._show_settings()
        self.app.update_idletasks()
        self.assertTrue(self.app._settings_panel.winfo_ismapped())
        self.assertFalse(self.app._dashboard_shell.winfo_ismapped())

    def test_live_log_goes_to_right_console(self):
        self.app.running = True
        self.app._show_dashboard()
        self.app._append_log('DidaDex GUI Testmeldung')
        self.assertIn('DidaDex GUI Testmeldung', self.app.log.get('1.0', 'end-1c'))
        self.app._auto_scroll.set(False)
        self.app._append_log('Zweite Testmeldung')
        self.assertIn('Zweite Testmeldung', self.app.log.get('1.0', 'end-1c'))

    def test_heatmap_and_metrics_render(self):
        self.app.running = True
        self.app._show_dashboard()
        self.app._dashboard.update_snapshot({
            'visited': 91, 'indexed': 12, 'queued': 44, 'errors': 2,
            'blocked': 1, 'discovered': 138, 'hosts': 1,
            'seed_rounds': 3, 'material_links': 5, 'depth_max': 4,
            'corpus_bytes': 1024 * 1024, 'document_types': [('lesson_plan', 12)],
            'cells': [{'host': 'unterrichten.zum.de', 'depth': 4,
                       'done': 8, 'indexed': 6, 'blocked': 0, 'error': 0}],
        })
        self.app.update_idletasks()
        self.assertEqual(self.app._dashboard.tiles['indexed'].get(), '12')
        self.assertEqual(self.app._dashboard.tiles['depth'].get(), '4')
        self.assertGreater(len(self.app._dashboard.chart.cells), 0)


if __name__ == '__main__':
    unittest.main()
