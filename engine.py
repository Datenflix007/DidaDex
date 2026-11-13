"""DidaDex – desktop launcher for the canonical Python crawler.

Place this file in the project root beside crawler/ and crawledDataViewer/.
Python 3.10+; tkinter is provided by standard Python on Windows.
Run: python engine.py
"""
from __future__ import annotations

# The legacy base launcher and desktop dashboard are intentionally unified here.

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from crawledDataViewer.live_dashboard import HTML_NAME, LiveDashboard, SnapshotMonitor
from crawledDataViewer.viewer_tk import MaterialViewer

ROOT = Path(__file__).resolve().parent
CRAWLER_DIR = ROOT / 'crawler'
VIEWER_DIR = ROOT / 'crawledDataViewer'
CRAWLER_SCRIPT = CRAWLER_DIR / 'crawler.py'
OUTPUT_ROOT = CRAWLER_DIR / 'outputs' / 'runs'
VENV_DIR = ROOT / '.venv'
PYTHON = VENV_DIR / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
CRAWLER_REQUIREMENTS = CRAWLER_DIR / 'requirements_crawler.txt'
VIEWER_REQUIREMENTS = VIEWER_DIR / 'requirements_material_viewer.txt'
CRAWLER_FALLBACK = ('requests>=2.31,<3', 'beautifulsoup4>=4.12,<5',
                    'lxml>=5,<7', 'pypdf>=5,<7', 'fonttools>=4.50,<5',
                    'python-docx>=1,<2', 'python-pptx>=1,<2')
VIEWER_FALLBACK = ('streamlit>=1.35', 'pandas>=2.0')

PRESETS = {
    'TEST': {'runtime_minutes': 10, 'max_pages': 2500, 'max_depth': 50, 'workers': 5,
             'max_per_host': 400, 'max_queue': 40000},
    'STANDARD': {'runtime_minutes': 180, 'max_pages': 25000, 'max_depth': 50, 'workers': 6,
                 'max_per_host': 7000, 'max_queue': 150000},
    'NACHT': {'runtime_minutes': 720, 'max_pages': 250000, 'max_depth': 50, 'workers': 8,
              'max_per_host': 50000, 'max_queue': 500000},
}


def crawl_config_payload(config: dict) -> dict:
    """Serialize GUI settings for the canonical crawler.py runtime."""
    cfg = dict(config)
    profile = {key: int(cfg[key]) for key in (
        'runtime_minutes', 'max_pages', 'max_depth', 'workers', 'max_per_host', 'max_queue'
    )}
    default_turns = {'TEST': 15, 'STANDARD': 50, 'NACHT': 100}[cfg['mode']]
    return {
        'schema_version': 1,
        'mode': cfg['mode'],
        'run_name': cfg['run_name'],
        'target_mib': int(cfg['target_mib']),
        'profile': profile,
        'seed_pages': int(cfg.get('seed_pages', default_turns)),
        'dfs_depth_step': int(cfg.get('dfs_depth_step', 5)),
        'DEPTH_SOFT_START': 5,
        'DEPTH_HARD_LIMIT': 50,
        'DEPTH_HEATMAP_INTERVAL': 30,
        'RETRY_LEGACY_REDIRECT_ERRORS': True,
        'MAX_ROBOTS_SITEMAPS_PER_HOST': 4,
        'STORE_CRAWL_EDGES': False,
        'DOWNLOAD_DELAY_SECONDS': float(cfg['DOWNLOAD_DELAY_SECONDS']),
        'MIN_TEXT_CHARS': int(cfg['MIN_TEXT_CHARS']),
        'MAX_MATERIAL_MIB': int(cfg['MAX_MATERIAL_MIB']),
        'MAX_TEXT_CHARS': int(cfg['MAX_TEXT_CHARS']),
        'subjects': list(cfg['subjects']),
        **{key: bool(cfg[key]) for key in (
            'DOWNLOAD_MATERIALS', 'ONLY_OPEN_LICENSE_MATERIALS', 'CHECK_LICENSE_IN_PDFS',
            'SITEMAPS_AKTIV', 'QUELLEN_UEBERGREIFEND', 'STORE_BINARY_MATERIALS',
            'DYNAMIC_DEPTH', 'FAIR_HOST_SCHEDULING', 'INCLUDE_GENERAL_METHODS',
        )},
    }


class DidaDex(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('DidaDex – Crawler, Materialviewer und Suche')
        self.geometry('1050x760')
        self.minsize(800, 610)
        self.configure(bg='#f5f7fb')
        self.events = queue.Queue()
        self.process = None
        self.viewer_process = None
        self.stop_file = None
        self.config_file = None
        self.running = False
        self.started_at = None
        self.crawl_started_at = None
        self.active_profile = None
        self._last_error = ''
        self.mode = tk.StringVar(value='TEST')
        self.run_name = tk.StringVar(value=datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))
        self.runtime = tk.IntVar(value=10)
        self.pages = tk.IntVar(value=2500)
        self.depth = tk.IntVar(value=50)
        self.workers = tk.IntVar(value=5)
        self.per_host = tk.IntVar(value=400)
        self.queue_limit = tk.IntVar(value=40000)
        self.target = tk.IntVar(value=500)
        self.delay = tk.DoubleVar(value=1.5)
        self.min_chars = tk.IntVar(value=500)
        self.max_chars = tk.IntVar(value=400000)
        self.max_material = tk.IntVar(value=24)
        self.download = tk.BooleanVar(value=True)
        self.license_only = tk.BooleanVar(value=True)
        self.license_pdf = tk.BooleanVar(value=True)
        self.sitemaps = tk.BooleanVar(value=True)
        self.cross_hosts = tk.BooleanVar(value=False)
        self.save_binary = tk.BooleanVar(value=False)
        self.dynamic_depth = tk.BooleanVar(value=True)
        self.fair_hosts = tk.BooleanVar(value=True)
        self.include_general_methods = tk.BooleanVar(value=True)
        self.subject_flags = {name: tk.BooleanVar(value=False) for name in (
            'Informatik','Geschichte','Deutsch','Mathematik','Physik','Chemie','Biologie',
            'Geographie','Ethik','Politik','Englisch','Kunst','Musik','Religion','Sport',
            'Sachunterricht','Medienbildung')}

        self.status = tk.StringVar(value='Bereit')
        self.step = tk.StringVar(value='Noch kein Lauf gestartet')
        self.metrics = tk.StringVar(value='Abrufe: 0  |  Dokumente: 0  |  Korpus: 0 MiB')
        self.viewer_status = tk.StringVar(value='Materialviewer noch nicht gestartet')
        self._make_ui()
        self.mode.trace_add('write', self._on_mode)
        self.after(120, self._pump)
        self.protocol('WM_DELETE_WINDOW', self._close)

    def _make_ui(self):
        style = ttk.Style(self)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('TNotebook.Tab', padding=(18, 9))
        style.configure('Accent.TButton', padding=(15, 8))
        style.configure('TButton', padding=(10, 6))
        style.configure('TLabel', background='#f5f7fb')
        header = tk.Frame(self, bg='#172a43', padx=20, pady=16)
        header.pack(fill='x')
        tk.Label(header, text='DidaDex', bg='#172a43', fg='white', font=('Segoe UI', 23, 'bold')).pack(anchor='w')
        tk.Label(header, text='Didaktisch-methodische Suchmaschine – Projektzentrale', bg='#172a43',
                 fg='#c4d4e9', font=('Segoe UI', 10)).pack(anchor='w')
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True, padx=16, pady=12)
        crawler = ttk.Frame(self.tabs)
        viewer = ttk.Frame(self.tabs)
        search = ttk.Frame(self.tabs)
        self.tabs.add(crawler, text='Crawler')
        self.tabs.add(viewer, text='Crawled Data Viewer')
        self.tabs.add(search, text='Suchmaschine (später)')
        self._crawler_tab(crawler)
        self._viewer_tab(viewer)
        self._search_tab(search)

    def _crawler_tab(self, tab):
        tab.rowconfigure(1, weight=1)
        tab.columnconfigure(0, weight=1)
        config = ttk.LabelFrame(tab, text='1. Einstellungen vor dem Start', padding=12)
        config.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        for i in range(8):
            config.columnconfigure(i, weight=1)
        ttk.Label(config, text='Modus').grid(row=0, column=0, sticky='w')
        ttk.Combobox(config, textvariable=self.mode, values=list(PRESETS), state='readonly', width=13).grid(row=1, column=0, sticky='ew', padx=(0, 8))
        ttk.Label(config, text='Laufname (gleicher Name = fortsetzen)').grid(row=0, column=1, columnspan=3, sticky='w')
        ttk.Entry(config, textvariable=self.run_name).grid(row=1, column=1, columnspan=3, sticky='ew', padx=(0, 8))
        ttk.Label(config, text='Ziel (MiB)').grid(row=0, column=4, sticky='w')
        ttk.Entry(config, textvariable=self.target, width=9).grid(row=1, column=4, sticky='ew', padx=(0, 8))
        ttk.Label(config, text='Zeitlimit (min)').grid(row=0, column=5, sticky='w')
        ttk.Entry(config, textvariable=self.runtime, width=10).grid(row=1, column=5, sticky='ew', padx=(0, 8))
        ttk.Label(config, text='Max. Seiten').grid(row=0, column=6, sticky='w')
        ttk.Entry(config, textvariable=self.pages, width=11).grid(row=1, column=6, columnspan=2, sticky='ew')
        for c, (title, var) in enumerate((('Max. Tiefe', self.depth), ('Worker', self.workers),
                                         ('Pro Host', self.per_host), ('Warteschlange', self.queue_limit),
                                         ('Pause/Host (s)', self.delay), ('Min. Textzeichen', self.min_chars),
                                         ('Max. Textzeichen', self.max_chars), ('Max. Material (MiB)', self.max_material))):
            ttk.Label(config, text=title).grid(row=2, column=c, sticky='w', pady=(12, 2))
            ttk.Entry(config, textvariable=var, width=12).grid(row=3, column=c, sticky='ew', padx=(0, 6))
        checks = (('Materialtext extrahieren', self.download), ('Nur offene Lizenzen', self.license_only),
                  ('PDF-Lizenz prüfen', self.license_pdf), ('Sitemaps', self.sitemaps),
                  ('Freigegebene Hosts verbinden (optional)', self.cross_hosts), ('Binärdateien speichern', self.save_binary))
        for c, (title, var) in enumerate(checks):
            ttk.Checkbutton(config, text=title, variable=var).grid(row=4+c//3, column=(c%3)*2,
                                                                   columnspan=2, sticky='w', pady=3)
        subjects_frame=ttk.LabelFrame(config,text='Fächerauswahl – keine Auswahl = alle Fächer',padding=7)
        subjects_frame.grid(row=6,column=0,columnspan=8,sticky='ew',pady=(8,0))
        for idx,(name,flag) in enumerate(self.subject_flags.items()):
            ttk.Checkbutton(subjects_frame,text=name,variable=flag).grid(row=idx//6,column=idx%6,sticky='w',padx=7,pady=2)
        options_frame=ttk.Frame(config)
        options_frame.grid(row=7,column=0,columnspan=8,sticky='ew')
        ttk.Checkbutton(options_frame,text='Dynamische Tiefe bis 50',variable=self.dynamic_depth).pack(side='left',padx=5)
        ttk.Checkbutton(options_frame,text='Faire Host-Verteilung',variable=self.fair_hosts).pack(side='left',padx=5)
        ttk.Checkbutton(options_frame,text='Allgemeine Methoden einbeziehen',variable=self.include_general_methods).pack(side='left',padx=5)
        bar = ttk.Frame(config)
        bar.grid(row=8, column=0, columnspan=8, sticky='ew', pady=(10, 0))
        self.start_btn = ttk.Button(bar, text='Crawler starten', command=self.start_crawl)
        self.start_btn.pack(side='left', padx=(0, 8))
        self.stop_btn = ttk.Button(bar, text='Sauber stoppen und exportieren', command=self.stop_crawl, state='disabled')
        self.stop_btn.pack(side='left', padx=(0, 8))
        ttk.Button(bar, text='Ausgabeordner öffnen', command=self.open_output).pack(side='left')
        progress = ttk.LabelFrame(tab, text='2. Live-Fortschritt aus crawler.py', padding=12)
        progress.grid(row=1, column=0, sticky='nsew')
        progress.rowconfigure(4, weight=1)
        progress.columnconfigure(0, weight=1)
        ttk.Label(progress, textvariable=self.status, font=('Segoe UI', 11, 'bold')).grid(row=0, column=0, sticky='w')
        ttk.Label(progress, textvariable=self.step).grid(row=1, column=0, sticky='w', pady=3)
        ttk.Label(progress, textvariable=self.metrics).grid(row=2, column=0, sticky='w', pady=3)
        self.pbar = ttk.Progressbar(progress, maximum=100, mode='determinate')
        self.pbar.grid(row=3, column=0, sticky='ew', pady=(4, 10))
        logframe = ttk.Frame(progress)
        logframe.grid(row=4, column=0, sticky='nsew')
        logframe.columnconfigure(0, weight=1)
        logframe.rowconfigure(0, weight=1)
        self.log = tk.Text(logframe, wrap='word', bg='#101c2b', fg='#e5ebf5',
                           insertbackground='white', font=('Consolas', 9), state='disabled')
        self.log.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(logframe, command=self.log.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.log.configure(yscrollcommand=scroll.set)

    def _viewer_tab(self, tab):
        frame = ttk.Frame(tab, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Crawled Data Viewer', font=('Segoe UI', 17, 'bold')).pack(anchor='w', pady=(0, 10))
        ttk.Label(frame, text='Startet deinen vorhandenen Streamlit-Viewer im Browser. Der Viewer liest die Laufordner unter crawler/outputs/runs.').pack(anchor='w', pady=4)
        ttk.Button(frame, text='Viewer starten / im Browser öffnen', command=self.start_viewer).pack(anchor='w', pady=12)
        ttk.Label(frame, textvariable=self.viewer_status).pack(anchor='w', pady=7)
        ttk.Label(frame, text='Hinweis: Im neuen Crawler enthält crawl.jsonl bereits die gefilterten Suchdokumente; ältere Läufe können weitere JSONL-Dateien haben.', wraplength=650).pack(anchor='w', pady=15)

    def _search_tab(self, tab):
        frame = ttk.Frame(tab, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='DidaDex Suche', font=('Segoe UI', 17, 'bold')).pack(anchor='w', pady=(0, 10))
        ttk.Label(frame, text='Platzhalter für den zukünftigen Suchindex (z. B. BM25). Noch keine Suchfunktion angebunden.').pack(anchor='w')
        ttk.Label(frame, text='Vorgesehene Quelle: crawler/outputs/runs/<laufname>/crawl.jsonl').pack(anchor='w', pady=10)

    def _on_mode(self, *_):
        profile = PRESETS[self.mode.get()]
        for name, variable in (('runtime_minutes', self.runtime), ('max_pages', self.pages),
                               ('max_depth', self.depth), ('workers', self.workers),
                               ('max_per_host', self.per_host), ('max_queue', self.queue_limit)):
            variable.set(profile[name])
        self.run_name.set(datetime.now().strftime('%Y-%m-%d_%H-%M-%S'))

    def _settings(self):
        name = self.run_name.get().strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError('Laufname: nur A-Z, a-z, 0-9, _ und -.')
        d = dict(mode=self.mode.get(), run_name=name, target_mib=self.target.get(),
                 runtime_minutes=self.runtime.get(), max_pages=self.pages.get(),
                 max_depth=self.depth.get(), workers=self.workers.get(),
                 max_per_host=self.per_host.get(), max_queue=self.queue_limit.get(),
                 DOWNLOAD_DELAY_SECONDS=self.delay.get(), MIN_TEXT_CHARS=self.min_chars.get(),
                 MAX_TEXT_CHARS=self.max_chars.get(), MAX_MATERIAL_MIB=self.max_material.get(),
                 DOWNLOAD_MATERIALS=self.download.get(), ONLY_OPEN_LICENSE_MATERIALS=self.license_only.get(),
                 CHECK_LICENSE_IN_PDFS=self.license_pdf.get(), SITEMAPS_AKTIV=self.sitemaps.get(),
                 QUELLEN_UEBERGREIFEND=self.cross_hosts.get(), STORE_BINARY_MATERIALS=self.save_binary.get(),
                 DYNAMIC_DEPTH=self.dynamic_depth.get(), FAIR_HOST_SCHEDULING=self.fair_hosts.get(),
                 INCLUDE_GENERAL_METHODS=self.include_general_methods.get(),
                 subjects=[name for name,flag in self.subject_flags.items() if flag.get()])
        for k in ('target_mib', 'runtime_minutes', 'max_pages', 'max_depth', 'workers',
                  'max_per_host', 'max_queue', 'MIN_TEXT_CHARS', 'MAX_TEXT_CHARS', 'MAX_MATERIAL_MIB'):
            if d[k] < (0 if k == 'max_depth' else 1):
                raise ValueError(f'{k} muss positiv sein (Tiefe darf 0 sein).')
        if not 0 <= d['max_depth'] <= 50:
            raise ValueError('Die maximale Tiefe darf 50 nicht überschreiten.')
        if not 0 <= d['DOWNLOAD_DELAY_SECONDS'] <= 300:
            raise ValueError('Pause/Host muss zwischen 0 und 300 Sekunden liegen.')
        if d['mode'] == 'TEST' and d['runtime_minutes'] > 10:
            raise ValueError('TEST ist auf höchstens 10 Minuten beschränkt.')
        return d

    def _post(self, kind, payload=''):
        self.events.put((kind, payload))

    def _append_log(self, line):
        self.log.configure(state='normal')
        self.log.insert('end', line.rstrip() + '\n')
        if int(self.log.index('end-1c').split('.')[0]) > 5500:
            self.log.delete('1.0', '500.0')
        self.log.see('end')
        self.log.configure(state='disabled')

    def start_crawl(self):
        if self.running:
            return
        config_file = None
        try:
            cfg = self._settings()
            if not CRAWLER_SCRIPT.is_file():
                raise FileNotFoundError(f'Crawler-Skript nicht gefunden: {CRAWLER_SCRIPT}')
            stop_marker = CRAWLER_DIR / f'.didadex_stop_{cfg["run_name"]}'
            config_file = CRAWLER_DIR / f'.didadex_config_{cfg["run_name"]}.json'
            config_file.write_text(
                json.dumps(crawl_config_payload(cfg), ensure_ascii=False, indent=2) + '\n',
                encoding='utf-8',
            )
        except Exception as exc:
            if config_file:
                config_file.unlink(missing_ok=True)
            messagebox.showerror('Ungültige Konfiguration', str(exc))
            return
        self.stop_file = stop_marker
        self.config_file = config_file
        self.stop_file.unlink(missing_ok=True)
        self.running = True
        self.started_at = time.monotonic()
        self.crawl_started_at = None
        self.active_profile = cfg
        self.start_btn.configure(state='disabled')
        self.stop_btn.configure(state='normal')
        self.pbar['value'] = 0
        self._last_error = ''
        self.status.set('Initialisierung ...')
        self.step.set('Virtuelle Umgebung und Abhängigkeiten prüfen')
        self.metrics.set('Abrufe: 0  |  Dokumente: 0  |  Korpus: 0 MiB')
        self._append_log(f'--- START: {cfg["mode"]} / {cfg["run_name"]} | Fächer: {cfg["subjects"] or ["Alle"]} ---')
        threading.Thread(target=self._run_crawler, args=(config_file,), daemon=True).start()

    def _run_cmd(self, args, cwd, label, env=None):
        self._post('step', label)
        p = subprocess.Popen(args, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding='utf-8', errors='replace', bufsize=1, env=env)
        self.process = p
        assert p.stdout is not None
        for line in p.stdout:
            self._post('line', line.rstrip('\n'))
        code = p.wait()
        self.process = None
        if code != 0:
            raise RuntimeError(f'{label}: Prozess mit Exit-Code {code} beendet.')

    def _run_crawler(self, config_file: Path):
        try:
            if not PYTHON.exists():
                self._post('line', 'Erstelle projektweite virtuelle Umgebung ...')
                self._run_cmd([sys.executable, '-m', 'venv', str(VENV_DIR)], ROOT, 'Virtuelle Umgebung anlegen')
            requirements = [str(x) for x in CRAWLER_FALLBACK]
            pip_args = [str(PYTHON), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(CRAWLER_REQUIREMENTS)] if CRAWLER_REQUIREMENTS.is_file() else [str(PYTHON), '-m', 'pip', 'install', '--disable-pip-version-check', *requirements]
            self._run_cmd(pip_args, ROOT, 'Crawler-Abhängigkeiten installieren')
            if CRAWLER_REQUIREMENTS.is_file():
                self._run_cmd([str(PYTHON), '-m', 'pip', 'install', '--disable-pip-version-check', *requirements], ROOT, 'Crawler-Laufzeitabhängigkeiten prüfen')
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            self._run_cmd([
                str(PYTHON), '-u', str(CRAWLER_SCRIPT), '--config', str(config_file),
                '--stop-file', str(self.stop_file),
            ], CRAWLER_DIR, 'Crawler ausführen', env=env)
            self._post('completed')
        except Exception as exc:
            self._post('error', str(exc))
        finally:
            config_file.unlink(missing_ok=True)
            self.config_file = None
            if self.stop_file:
                self.stop_file.unlink(missing_ok=True)
            self._post('finished')

    def stop_crawl(self):
        if not self.running or not self.stop_file:
            return
        self.stop_file.touch()
        self.status.set('Stopp angefordert – Crawl wird abgeschlossen und exportiert')
        self.stop_btn.configure(state='disabled')
        self._append_log('Stopp angefordert. Laufende Anfragen werden abgeschlossen; anschließend Export.')
        # During dependency setup no crawler has started; do not claim graceful stop there.

    def _pump(self):
        for _ in range(250):
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'line':
                if payload.startswith('@@STEP@@ '):
                    self.step.set(payload.removeprefix('@@STEP@@ '))
                elif payload == '@@DONE@@':
                    self.step.set('Crawler vollständig ausgeführt')
                else:
                    self._append_log(payload)
                    self._parse_progress(payload)
            elif kind == 'step':
                self.step.set(payload)
                self._append_log('>> ' + payload)
            elif kind == 'completed':
                self.status.set('Crawl und Export erfolgreich abgeschlossen')
                self.pbar['value'] = 100
            elif kind == 'error':
                self._last_error = payload
                self.status.set('Fehler: ' + payload)
                self._append_log('FEHLER: ' + payload)
            elif kind == 'viewer_ready':
                self.viewer_status.set('Viewer läuft: http://localhost:8501')
                webbrowser.open('http://localhost:8501')
            elif kind == 'viewer_error':
                self.viewer_status.set('Viewer-Fehler: ' + payload)
            elif kind == 'finished':
                self.running = False
                self.start_btn.configure(state='normal')
                self.stop_btn.configure(state='disabled')
                if not self._last_error and self.pbar['value'] != 100:
                    self.status.set('Lauf beendet')
        if self.running and self.crawl_started_at and self.active_profile:
            elapsed = time.monotonic() - self.crawl_started_at
            secs = self.active_profile['runtime_minutes'] * 60
            if 'Netzlauf' in self.step.get():
                self.pbar['value'] = min(98, max(self.pbar['value'], elapsed / secs * 100))
        self.after(120, self._pump)

    def _parse_progress(self, line):
        if 'START ' in line and 'Seeds' in line:
            self.status.set('Crawler läuft')
            self.crawl_started_at = time.monotonic()
            self.step.set('Netzlauf – HTML, Unterrichtsinhalte und Materialien')
        m = re.search(r'Fortschritt:\s*(\d+) Abrufe,\s*(\d+) Dokumente,\s*([\d.]+)/([\d.]+) MiB', line)
        if m:
            crawled, docs, mib, target = m.groups()
            self.metrics.set(f'Abrufe: {crawled}  |  Dokumente: {docs}  |  Korpus: {mib}/{target} MiB')
            if float(target) > 0:
                self.pbar['value'] = min(98, max(self.pbar['value'], float(mib)/float(target)*100))
        if line.startswith('EXPORT:'):
            self.step.set('Export abgeschlossen – gefilterte crawl.jsonl erstellt')

    def open_output(self):
        name = self.run_name.get().strip()
        folder = OUTPUT_ROOT / name if re.fullmatch(r'[A-Za-z0-9_-]+', name) else OUTPUT_ROOT
        folder.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            os.startfile(str(folder))
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(folder)])
        else:
            subprocess.Popen(['xdg-open', str(folder)])

    def start_viewer(self):
        if self.viewer_process and self.viewer_process.poll() is None:
            webbrowser.open('http://localhost:8501')
            self.viewer_status.set('Viewer läuft: http://localhost:8501')
            return
        viewer = VIEWER_DIR / 'viewer.py'
        if not viewer.is_file():
            messagebox.showerror('Viewer fehlt', f'Datei nicht gefunden: {viewer}')
            return
        self.viewer_status.set('Viewer wird vorbereitet ...')
        threading.Thread(target=self._viewer_background, args=(viewer,), daemon=True).start()

    def _viewer_background(self, viewer):
        try:
            if not PYTHON.exists():
                self._run_cmd([sys.executable, '-m', 'venv', str(VENV_DIR)], ROOT, 'Virtuelle Umgebung für Viewer anlegen')
            args = [str(PYTHON), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(VIEWER_REQUIREMENTS)] if VIEWER_REQUIREMENTS.is_file() else [str(PYTHON), '-m', 'pip', 'install', '--disable-pip-version-check', *VIEWER_FALLBACK]
            self._run_cmd(args, ROOT, 'Viewer-Abhängigkeiten installieren')
            # Streamlit does not need to modify cwd: absolute root path forwarded.
            self.viewer_process = subprocess.Popen(
                [str(PYTHON), '-m', 'streamlit', 'run', str(viewer), '--server.headless=true',
                 '--server.port=8501', '--', '--root', str(OUTPUT_ROOT)], cwd=str(ROOT),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)
            if self.viewer_process.poll() is not None:
                raise RuntimeError('Viewer konnte nicht starten; Port 8501 möglicherweise belegt.')
            self._post('viewer_ready')
        except Exception as exc:
            self._post('viewer_error', str(exc))

    def _close(self):
        if self.running:
            if not messagebox.askyesno('Crawler läuft', 'Crawler läuft noch. Stopp anfordern und Fenster schließen?\nHinweis: Sofortiges Schließen kann den Export unterbrechen.'):
                return
            self.stop_crawl()
            messagebox.showinfo('Stopp angefordert', 'Warte auf den Export im geöffneten Fenster. Schließe die Anwendung danach.')
            return
        if self.viewer_process and self.viewer_process.poll() is None:
            self.viewer_process.terminate()
        self.destroy()


_BaseDidaDex = DidaDex


class DidaDexDesktop(_BaseDidaDex):
    """Desktop UI with native viewer and a widescreen live dashboard."""

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
        """Use a maximized window while keeping the title bar and taskbar."""
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
        width = max(1040, self.winfo_screenwidth() - 70)
        height = max(650, self.winfo_screenheight() - 95)
        self.geometry(f'{width}x{height}+20+20')

    def _viewer_tab(self, tab):
        self.native_viewer = MaterialViewer(tab, root=OUTPUT_ROOT)
        self.native_viewer.pack(fill='both', expand=True)

    def _crawler_tab(self, tab):
        # The base engine still owns crawler execution, settings and events.
        super()._crawler_tab(tab)
        self.seed_pages = tk.IntVar(master=self, value=15)
        self.dfs_depth_step = tk.IntVar(master=self, value=5)
        self._crawler_panel = tab
        panels = [widget for widget in tab.winfo_children() if isinstance(widget, ttk.LabelFrame)]
        self._settings_panel = next((panel for panel in panels
                                     if 'Einstellungen' in panel.cget('text')), None)
        self._legacy_progress = next((panel for panel in panels
                                      if 'Live-Fortschritt' in panel.cget('text')), None)
        if self._settings_panel is None or self._legacy_progress is None:
            raise RuntimeError('Das erwartete Crawler-Layout der Basis-Engine fehlt.')
        self._legacy_log = self.log
        self._legacy_pbar = self.pbar

        section = ttk.Frame(self._settings_panel)
        section.grid(row=9, column=0, columnspan=8, sticky='w', pady=(8, 0))
        ttk.Label(section, text='DFS: Seiten pro Seed-Runde').pack(side='left', padx=(0, 5))
        ttk.Entry(section, textvariable=self.seed_pages, width=7).pack(side='left', padx=(0, 18))
        ttk.Label(section, text='Tiefenschritt pro Runde').pack(side='left', padx=(0, 5))
        ttk.Entry(section, textvariable=self.dfs_depth_step, width=7).pack(side='left')

        # Before a crawl keep the original settings and progress visible. Once
        # running, they are replaced by a full-tab horizontal split view.
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
        """Dedicated console, retaining the base engine's StringVars."""
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
        ttk.Label(log_frame, text='Terminal - fortlaufendes Protokoll',
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
        """Preserve console scroll position when auto-scroll is disabled."""
        if not hasattr(self, '_auto_scroll') or self._auto_scroll.get():
            super()._append_log(line)
        else:
            position = self.log.yview()[0]
            super()._append_log(line)
            self.log.yview_moveto(position)

    def _on_mode(self, *args):
        super()._on_mode(*args)
        self.seed_pages.set({'TEST': 15, 'STANDARD': 50, 'NACHT': 100}[self.mode.get()])

    def _settings(self):
        result = super()._settings()
        pages = self.seed_pages.get()
        step = self.dfs_depth_step.get()
        if not 1 <= pages <= 1000:
            raise ValueError('Seiten pro Seed-Runde: Wert zwischen 1 und 1000 noetig.')
        if not 1 <= step <= 50:
            raise ValueError('Tiefenschritt pro Runde: Wert zwischen 1 und 50 noetig.')
        result['seed_pages'] = pages
        result['dfs_depth_step'] = step
        return result

    def start_crawl(self):
        if self.running:
            return
        super().start_crawl()
        # Invalid input leaves the settings screen untouched.
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
            messagebox.showinfo('Crawler aktiv', 'Bitte den Crawl erst sauber abschliessen.')
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
        # Keep a copy of the last dashboard messages in the legacy log.
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
        # The base pump owns process events. Drain the monitoring queue on Tk's
        # main thread afterwards.
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
        self.viewer_status.set('Lokaler Tkinter-Viewer im Tab Crawled Data Viewer.')

    def _close(self):
        if not self.running and self._monitor:
            self._monitor.stop()
        super()._close()


if __name__ == '__main__':
    DidaDexDesktop().mainloop()
