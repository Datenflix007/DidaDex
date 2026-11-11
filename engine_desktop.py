"""DidaDex Desktop: Round-Robin-DFS, native viewer and widescreen live monitoring.

Run from repository root: python engine_desktop.py
The existing engine.py and crawler notebook are required and remain unchanged.
"""
from __future__ import annotations

import queue
import sys
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk

import engine as _engine
from engine import DidaDex, OUTPUT_ROOT
from crawledDataViewer.viewer_tk import MaterialViewer
from crawledDataViewer.live_dashboard import LiveDashboard, SnapshotMonitor, HTML_NAME

_ORIGINAL_CONFIG_SOURCE = _engine.config_source


def _config_with_round_robin(config: dict) -> str:
    base = _ORIGINAL_CONFIG_SOURCE(config)
    step = int(config.get('dfs_depth_step', 5))
    pages = int(config.get('seed_pages', 15))
    return base + (f'\nDFS_DEPTH_STEP = {step}\n'
                   f'PROFILE["pages_per_seed_turn"] = {pages}\n')


_engine.config_source = _config_with_round_robin


class DidaDexDesktop(DidaDex):
    """Desktop UI with resizable left monitoring and right full-height console."""

    def __init__(self):
        self._monitor = None
        self._dashboard_queue = queue.Queue()
        self._monitor_warning = ''
        self._dashboard_visible = False
        self._sash_positioned = False
        super().__init__()
        self.minsize(1040, 650)
        self.after_idle(self._maximize_window)

    def _maximize_window(self):
        """Use a maximized *window*, keeping title bar and OS taskbar visible."""
        if sys.platform == 'win32':
            try:
                self.state('zoomed')
                return
            except tk.TclError:
                pass
        else:
            try:
                self.attributes('-zoomed', True)
                if self.winfo_screenwidth() > 1300:
                    return
            except tk.TclError:
                pass
        # Fallback for window managers without zoom / virtual displays.
        width = max(1040, self.winfo_screenwidth() - 70)
        height = max(650, self.winfo_screenheight() - 95)
        self.geometry(f'{width}x{height}+20+20')

    def _viewer_tab(self, tab):
        self.native_viewer = MaterialViewer(tab, root=OUTPUT_ROOT)
        self.native_viewer.pack(fill='both', expand=True)

    def _crawler_tab(self, tab):
        # The original engine still owns notebook execution, event parsing and
        # the settings panel. Its old progress panel is retained as fallback.
        super()._crawler_tab(tab)
        self.seed_pages = tk.IntVar(master=self, value=15)
        self.dfs_depth_step = tk.IntVar(master=self, value=5)
        self._crawler_panel = tab
        panels = [w for w in tab.winfo_children() if isinstance(w, ttk.LabelFrame)]
        self._settings_panel = next((w for w in panels if 'Einstellungen' in w.cget('text')), None)
        self._legacy_progress = next((w for w in panels if 'Live-Fortschritt' in w.cget('text')), None)
        if self._settings_panel is None or self._legacy_progress is None:
            raise RuntimeError('Das erwartete Crawler-Layout der bisherigen Engine fehlt.')
        self._legacy_log = self.log
        self._legacy_pbar = self.pbar

        section = ttk.Frame(self._settings_panel)
        section.grid(row=10, column=0, columnspan=8, sticky='w', pady=(8, 0))
        ttk.Label(section, text='DFS: Seiten pro Seed-Runde').pack(side='left', padx=(0, 5))
        ttk.Entry(section, textvariable=self.seed_pages, width=7).pack(side='left', padx=(0, 18))
        ttk.Label(section, text='Tiefenschritt pro Runde').pack(side='left', padx=(0, 5))
        ttk.Entry(section, textvariable=self.dfs_depth_step, width=7).pack(side='left')

        # Keep the original settings/progress visible *before* a crawl. After
        # starting, hide BOTH and show a full-tab horizontal Panedwindow.
        self._dashboard_shell = ttk.Frame(tab)
        self._dashboard_shell.grid(row=0, column=0, rowspan=2, sticky='nsew')
        self._dashboard_shell.rowconfigure(0, weight=1)
        self._dashboard_shell.columnconfigure(0, weight=1)
        self._split = ttk.Panedwindow(self._dashboard_shell, orient='horizontal')
        self._split.grid(row=0, column=0, sticky='nsew')
        self._monitor_panel = ttk.Frame(self._split)
        self._console_panel = ttk.Frame(self._split, padding=(8, 8, 8, 8))
        self._split.add(self._monitor_panel, weight=3)
        self._split.add(self._console_panel, weight=2)

        self._dashboard = LiveDashboard(
            self._monitor_panel,
            on_stop=self.stop_crawl,
            on_settings=self._show_settings,
            on_html=self._open_live_heatmap,
            on_viewer=self.start_viewer,
        )
        self._dashboard.pack(fill='both', expand=True)
        self._make_console(self._console_panel)
        self._dashboard_shell.grid_remove()

    def _make_console(self, parent):
        """Dedicated console, with original StringVars used by base engine."""
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)
        header = ttk.Frame(parent)
        header.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        ttk.Label(header, text='Konsolenausgabe', font=('Segoe UI', 15, 'bold')).pack(side='left')
        ttk.Label(header, text='LIVE', foreground='#0b8067',
                  font=('Segoe UI', 9, 'bold')).pack(side='right', padx=6)

        progress = ttk.LabelFrame(parent, text='Crawler-Status', padding=(12, 9))
        progress.grid(row=1, column=0, sticky='ew', pady=(0, 9))
        progress.columnconfigure(0, weight=1)
        ttk.Label(progress, textvariable=self.status, font=('Segoe UI', 11, 'bold'),
                  wraplength=450).grid(row=0, column=0, sticky='w', pady=(0, 5))
        ttk.Label(progress, textvariable=self.step, wraplength=450).grid(
            row=1, column=0, sticky='w', pady=(0, 5))
        ttk.Label(progress, textvariable=self.metrics, wraplength=450).grid(
            row=2, column=0, sticky='w', pady=(0, 7))
        self.pbar = ttk.Progressbar(progress, maximum=100, mode='determinate')
        self.pbar.grid(row=3, column=0, sticky='ew')

        log_frame = ttk.Frame(parent)
        log_frame.grid(row=2, column=0, sticky='nsew')
        log_frame.rowconfigure(1, weight=1)
        log_frame.columnconfigure(0, weight=1)
        ttk.Label(log_frame, text='Terminal · fortlaufendes Protokoll',
                  font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, sticky='w', pady=(0, 7))
        self.log = tk.Text(log_frame, wrap='word', bg='#101c2b', fg='#e5ebf5',
                           insertbackground='white', selectbackground='#375574',
                           font=('Consolas', 10), relief='flat', padx=12, pady=12,
                           state='disabled')
        self.log.grid(row=1, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=self.log.yview)
        scrollbar.grid(row=1, column=1, sticky='ns')
        self.log.configure(yscrollcommand=scrollbar.set)
        footer = ttk.Frame(parent)
        footer.grid(row=3, column=0, sticky='ew', pady=(8, 0))
        self._auto_scroll = tk.BooleanVar(master=self, value=True)
        ttk.Checkbutton(footer, text='Automatisch zum Ende scrollen',
                        variable=self._auto_scroll).pack(side='left')
        ttk.Button(footer, text='Protokoll kopieren',
                   command=self._copy_log).pack(side='right')

    def _copy_log(self):
        value = self.log.get('1.0', 'end-1c')
        self.clipboard_clear()
        self.clipboard_append(value)

    def _append_log(self, line):
        """Preserve console scroll position when auto-scroll is switched off."""
        if not hasattr(self, '_auto_scroll') or self._auto_scroll.get():
            super()._append_log(line)
        else:
            pos = self.log.yview()[0]
            super()._append_log(line)
            self.log.yview_moveto(pos)

    def _on_mode(self, *args):
        super()._on_mode(*args)
        self.seed_pages.set({'TEST': 15, 'STANDARD': 50, 'NACHT': 100}[self.mode.get()])

    def _settings(self):
        result = super()._settings()
        pages = self.seed_pages.get()
        step = self.dfs_depth_step.get()
        if not 1 <= pages <= 1000:
            raise ValueError('Seiten pro Seed-Runde: Wert zwischen 1 und 1000 nötig.')
        if not 1 <= step <= 50:
            raise ValueError('Tiefenschritt pro Runde: Wert zwischen 1 und 50 nötig.')
        result['seed_pages'] = pages
        result['dfs_depth_step'] = step
        return result

    def start_crawl(self):
        if self.running:
            return
        super().start_crawl()
        # Invalid config leaves running=False and the settings visible.
        if not self.running:
            return
        self._show_dashboard()
        if self._monitor:
            self._monitor.stop()
        self._dashboard_queue = queue.Queue()
        self._monitor = SnapshotMonitor(OUTPUT_ROOT / self.run_name.get(), self._dashboard_queue)
        self._monitor.start()

    def _show_dashboard(self):
        self._settings_panel.grid_remove()
        self._legacy_progress.grid_remove()
        self._dashboard_shell.grid()
        self._crawler_panel.rowconfigure(0, weight=1)
        self._crawler_panel.rowconfigure(1, weight=0)
        self._dashboard_visible = True
        self._dashboard.set_running(self.running)
        # Set only once per crawl: users can drag the sash without fighting a
        # repeated resize callback. Default: left 60%, right 40%.
        self._sash_positioned = False
        self.after(80, self._set_initial_sash)
        self._dashboard.focus_set()

    def _set_initial_sash(self):
        if self._sash_positioned or not self._dashboard_visible:
            return
        width = self._split.winfo_width()
        if width < 500:
            self.after(150, self._set_initial_sash)
            return
        try:
            self._split.sashpos(0, round(width * 0.60))
            self._sash_positioned = True
        except tk.TclError:
            self.after(150, self._set_initial_sash)

    def _show_settings(self):
        if self.running:
            messagebox.showinfo('Crawler aktiv', 'Bitte den Crawl erst sauber abschließen.')
            return
        if self._monitor:
            self._monitor.stop()
            self._monitor = None
        self._dashboard_shell.grid_remove()
        self._settings_panel.grid()
        self._legacy_progress.grid()
        self._crawler_panel.rowconfigure(0, weight=0)
        self._crawler_panel.rowconfigure(1, weight=1)
        self._dashboard_visible = False
        # Reuse the old progress widget for the settings screen. Keep a copy
        # of the last messages without moving widgets between Tk parents.
        self._legacy_pbar['value'] = self.pbar['value']
        self._legacy_log.configure(state='normal')
        self._legacy_log.delete('1.0', 'end')
        self._legacy_log.insert('end', self.log.get('1.0', 'end-1c'))
        self._legacy_log.see('end')
        self._legacy_log.configure(state='disabled')

    def _open_live_heatmap(self):
        path = OUTPUT_ROOT / self.run_name.get() / HTML_NAME
        if not path.is_file():
            messagebox.showinfo('Noch keine Heatmap',
                                'Die HTML-Heatmap wird erstellt, sobald Crawl-Daten vorliegen.')
            return
        webbrowser.open(path.resolve().as_uri())

    def _pump(self):
        # The inherited pump owns crawl process events, including terminal
        # output; the monitoring queue is safely drained on the Tk main thread.
        super()._pump()
        newest = None
        for _ in range(100):
            try:
                kind, payload = self._dashboard_queue.get_nowait()
            except queue.Empty:
                break
            if kind == 'snapshot':
                newest = payload
            elif kind == 'warning' and payload != self._monitor_warning:
                self._monitor_warning = payload
                self._append_log('[Dashboard] ' + payload)
        if newest is not None and self._dashboard_visible:
            self._dashboard.update_snapshot(newest)
        if self._dashboard_visible:
            self._dashboard.set_running(self.running)

    def start_viewer(self):
        self.tabs.select(1)
        self.native_viewer.refresh_runs(initial_run=self.run_name.get())
        self.viewer_status.set('Lokaler Tkinter-Viewer im Tab „Crawled Data Viewer“.')

    def _close(self):
        if not self.running and self._monitor:
            self._monitor.stop()
        super()._close()


if __name__ == '__main__':
    DidaDexDesktop().mainloop()
