"""DidaDex crawl monitoring: read-only SQLite stats and native Tkinter heatmap.

No Streamlit, browser engine, or third-party GUI dependency. All database reads
happen in a daemon thread, never on the Tk main loop. The generated HTML report
is a separate file from the crawler-owned depth_heatmap.html.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import queue
import sqlite3
import threading
import time
from tkinter import ttk
import tkinter as tk
from urllib.parse import urlsplit

POLL_SECONDS = 3.0
HTML_NAME = 'depth_heatmap_live.html'


def _blank_snapshot(run: Path) -> dict:
    return {'run': run.name, 'updated_at': '', 'visited': 0, 'indexed': 0,
            'queued': 0, 'running': 0, 'blocked': 0, 'errors': 0,
            'discovered': 0, 'hosts': 0, 'seeds': 0, 'seed_rounds': 0,
            'corpus_bytes': None, 'depth_max': 0, 'material_links': 0,
            'document_types': [], 'cells': [], 'pending': not (run / 'crawler_state.sqlite').exists()}


def read_snapshot(run: Path) -> dict:
    """Return actual persisted crawl counters (no fabricated estimates).

    SQLite opens read-only with WAL support, so crawler writes remain independent.
    The small 'crawler_live.json' file gives accurate in-memory corpus bytes
    without scanning all full-text BLOBs in every polling interval.
    """
    run = Path(run)
    result = _blank_snapshot(run)
    db_path = run / 'crawler_state.sqlite'
    if not db_path.is_file():
        return result
    con = sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True,
                          timeout=0.4)
    try:
        con.execute('PRAGMA busy_timeout=400')
        # Consistent point-in-time read even while threads commit elsewhere.
        con.execute('BEGIN')
        statuses = dict(con.execute('SELECT status,COUNT(*) FROM frontier GROUP BY status'))
        result['discovered'] = sum(statuses.values())
        result['queued'] = statuses.get('queued', 0)
        result['running'] = statuses.get('running', 0)
        result['errors'] = statuses.get('error', 0)
        result['blocked'] = statuses.get('blocked', 0)
        result['visited'] = statuses.get('done', 0) + result['errors'] + result['blocked']
        result['indexed'] = con.execute('SELECT COUNT(*) FROM documents').fetchone()[0]
        result['material_links'] = con.execute('SELECT COUNT(*) FROM material_links').fetchone()[0]
        result['document_types'] = con.execute('''SELECT COALESCE(NULLIF(doc_type,''),'unbekannt'),COUNT(*)
               FROM documents GROUP BY doc_type ORDER BY COUNT(*) DESC LIMIT 12''').fetchall()
        existing = {row[1] for row in con.execute('PRAGMA table_info(seed_schedule)')}
        if 'turns' in existing:
            result['seeds'], result['seed_rounds'] = con.execute(
                'SELECT COUNT(*),COALESCE(SUM(turns),0) FROM seed_schedule').fetchone()

        by_cell = defaultdict(lambda: {'done': 0, 'blocked': 0, 'error': 0, 'indexed': 0})
        for host, depth, status, n in con.execute('SELECT host,depth,status,count FROM crawl_depth_stats'):
            by_cell[(str(host or '?'), int(depth))][status] += int(n)
        # Canonical redirects can make documents.url differ from frontier.url.
        # Fall back to the stored crawl_depth metadata when necessary.
        for url, depth, meta in con.execute('''SELECT d.url,f.depth,d.metadata
                FROM documents d LEFT JOIN frontier f ON f.url=d.url'''):
            if depth is None:
                try:
                    depth = int(json.loads(meta or '{}').get('crawl_depth', 0))
                except (TypeError, ValueError, json.JSONDecodeError):
                    depth = 0
            host = urlsplit(url or '').hostname or '?'
            by_cell[(host, int(depth))]['indexed'] += 1
        result['cells'] = [{'host': host, 'depth': depth, **counts}
                           for (host, depth), counts in sorted(by_cell.items())]
        result['hosts'] = len({item['host'] for item in result['cells']})
        result['depth_max'] = max((row['depth'] for row in result['cells']), default=0)
        result['pending'] = False
        con.execute('COMMIT')
    finally:
        con.close()

    stat_file = run / 'crawler_live.json'
    try:
        live = json.loads(stat_file.read_text(encoding='utf-8'))
        # Avoid showing stale stats after the run folder has been repurposed.
        if isinstance(live, dict) and live.get('run') == run.name:
            count = live.get('document_bytes')
            if isinstance(count, int) and count >= 0:
                result['corpus_bytes'] = count
            result['updated_at'] = str(live.get('updated_at', ''))
    except (OSError, ValueError, TypeError):
        pass
    if not result['updated_at']:
        result['updated_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    return result


def html_report(snapshot: dict) -> str:
    """Self-contained, refreshable offline HTML overview of the same data."""
    rows = snapshot.get('cells') or []
    hosts = sorted({r['host'] for r in rows})
    maximum = max((r['indexed'] for r in rows), default=0) or 1
    by_key = {(r['host'], r['depth']): r for r in rows}
    cap = max(10, min(50, snapshot.get('depth_max', 0) + 2))
    cells = []
    for host in hosts:
        tds = []
        for depth in range(cap + 1):
            v = by_key.get((host, depth), {})
            indexed = v.get('indexed', 0)
            visited = sum(v.get(k, 0) for k in ('done', 'blocked', 'error'))
            color = (f'rgba(12,137,104,{0.13 + 0.87 * indexed / maximum:.3f})'
                     if indexed else ('#fee3e3' if v.get('error') else '#fff0c7' if visited else '#f4f6fa'))
            desc = (f'Tiefe {depth}; indexiert: {indexed}; abgeschlossen: {v.get("done", 0)}; '
                    f'blockiert: {v.get("blocked", 0)}; Fehler: {v.get("error", 0)}')
            tds.append(f'<td style="background:{color}" title="{html.escape(desc, quote=True)}">'
                       f'{indexed if indexed else ("·" if visited else "")}</td>')
        cells.append(f'<tr><th>{html.escape(host)}</th>{"".join(tds)}</tr>')
    head = ''.join(f'<th>{depth}</th>' for depth in range(cap + 1))
    indexed = int(snapshot.get('indexed', 0))
    visited = int(snapshot.get('visited', 0))
    stamp = html.escape(str(snapshot.get('updated_at', '')))
    stats = (f'{visited:,} abgearbeitet · {indexed:,} indexiert · '
             f'{snapshot.get("queued", 0):,} offen · '
             f'{snapshot.get("errors", 0):,} Fehler · '
             f'{snapshot.get("hosts", 0):,} Hosts')
    body = '\n'.join(cells) if cells else '<tr><td colspan="12">Noch keine Tiefenstatistik verfügbar.</td></tr>'
    return '''<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="6"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DidaDex · Live-Heatmap</title><style>
body{font:14px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;margin:24px;background:#f8fafc;color:#13233b}
h1{font-size:23px;margin-bottom:3px} .sub{color:#52647d;margin:0 0 20px}
.scroll{overflow:auto;max-height:74vh;border:1px solid #d5dce6;border-radius:9px;background:white}
table{border-collapse:separate;border-spacing:0;font-size:11px}
th,td{height:23px;min-width:24px;text-align:center;padding:3px;border-right:1px solid #e3e8ef;border-bottom:1px solid #e3e8ef}
thead th{position:sticky;top:0;background:#e9eff5;z-index:2} tbody th{position:sticky;left:0;z-index:1;min-width:192px;max-width:250px;overflow:hidden;text-overflow:ellipsis;text-align:left;background:#fff;white-space:nowrap}
.legend{margin:13px 0;color:#52647d;font-size:12px}
</style></head><body><h1>DidaDex – Live-Heatmap</h1>
<p class="sub">''' + html.escape(stats) + ' · ' + stamp + '''</p>
<p class="legend">Grün: indexierte Unterrichtsdokumente · Gelb: besucht, aber nicht indexiert · Rot: Fehler · Grau: noch kein Besuch. Die HTML-Datei aktualisiert sich im Browser alle sechs Sekunden.</p>
<div class="scroll"><table><thead><tr><th>Host / Tiefe</th>''' + head + '</tr></thead><tbody>' + body + '</tbody></table></div></body></html>'


def write_live_html(run: Path, snapshot: dict) -> Path:
    """Atomic replace avoids half-written files during browser refresh."""
    destination = Path(run) / HTML_NAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + '.tmp')
    temp.write_text(html_report(snapshot), encoding='utf-8')
    temp.replace(destination)
    return destination


class SnapshotMonitor:
    """Background read-only polling. UI only receives dicts through a Queue."""

    def __init__(self, run: Path, sink: queue.Queue, interval: float = POLL_SECONDS):
        self.run = Path(run)
        self.sink = sink
        self.interval = max(.5, float(interval))
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True, name='DidaDex-LiveDashboard')

    def start(self):
        self.thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                snapshot = read_snapshot(self.run)
                if not snapshot['pending']:
                    write_live_html(self.run, snapshot)
                self.sink.put(('snapshot', snapshot))
            except (OSError, sqlite3.Error, ValueError) as exc:
                self.sink.put(('warning', f'Live-Daten vorübergehend nicht verfügbar: {exc}'))
            self._stop.wait(self.interval)


class HeatmapCanvas(ttk.Frame):
    """Resizable, scrollable native heatmap with readable host and depth labels."""

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg='#ffffff', highlightthickness=0,
                                height=260, relief='flat')
        sy = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        sx = ttk.Scrollbar(self, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        sy.grid(row=0, column=1, sticky='ns')
        sx.grid(row=1, column=0, sticky='ew')
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.hover = tk.StringVar(value='Grün: indexiert  ·  Gelb: nur besucht  ·  Rot: Fehler')
        ttk.Label(self, textvariable=self.hover, font=('Segoe UI', 9),
                  wraplength=740).grid(row=2, column=0, sticky='ew', pady=(5, 0))
        self.cells = {}
        self._host_width = 220
        self._cell_width = 32
        self._header_height = 39
        self._row_height = 29
        self._last_snapshot = None
        self._resize_job = None
        self._last_canvas_width = 0
        self.canvas.bind('<Motion>', self._on_move)
        self.canvas.bind('<Leave>', self._clear_hover)
        self.canvas.bind('<MouseWheel>', self._scroll_vertical)
        self.canvas.bind('<Shift-MouseWheel>', self._scroll_horizontal)
        self.canvas.bind('<Configure>', self._on_resize)

    def _clear_hover(self, _event=None):
        self.hover.set('Grün: indexiert  ·  Gelb: nur besucht  ·  Rot: Fehler')

    def _on_resize(self, event):
        # Debounce resizing; the graph is redrawn only after dragging stops.
        if abs(event.width - self._last_canvas_width) < 12:
            return
        self._last_canvas_width = event.width
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, self._redraw_after_resize)

    def _redraw_after_resize(self):
        self._resize_job = None
        if self._last_snapshot is not None:
            self.render(self._last_snapshot)

    def _scroll_vertical(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
        return 'break'

    def _scroll_horizontal(self, event):
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, 'units')
        return 'break'

    def _on_move(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        row = int((y - self._header_height) // self._row_height)
        col = int((x - self._host_width) // self._cell_width)
        cell = self.cells.get((row, col))
        if cell:
            self.hover.set(f'{cell["host"]}  ·  Tiefe {cell["depth"]}  ·  '
                           f'{cell.get("indexed", 0)} indexiert  ·  '
                           f'{cell.get("done", 0)} abgeschlossen  ·  '
                           f'{cell.get("blocked", 0)} blockiert  ·  '
                           f'{cell.get("error", 0)} Fehler')

    def render(self, snapshot: dict):
        self._last_snapshot = snapshot
        canvas = self.canvas
        previous_x = canvas.xview()[0]
        previous_y = canvas.yview()[0]
        canvas.delete('all')
        self.cells.clear()
        by_host = defaultdict(dict)
        for item in snapshot.get('cells', []):
            by_host[item['host']][item['depth']] = item
        if not by_host:
            canvas.create_text(22, 36, anchor='nw', fill='#475569',
                               font=('Segoe UI', 11),
                               text='Noch keine Daten vorhanden. Die Heatmap erscheint nach den ersten Abrufen.')
            canvas.configure(scrollregion=(0, 0, max(400, canvas.winfo_width()), 230))
            return

        # Keep the most active hosts in view; the standalone HTML retains all.
        activity = lambda row: sum(x.get('done', 0) + x.get('indexed', 0) + x.get('error', 0)
                                   for x in row.values())
        hosts = sorted(by_host, key=lambda host: (-activity(by_host[host]), host))[:60]
        max_depth = min(50, max(10, snapshot.get('depth_max', 0) + 2))
        peak = max((row.get('indexed', 0) for row in snapshot.get('cells', [])), default=0) or 1
        available_width = max(440, canvas.winfo_width())
        self._host_width = min(246, max(180, round(available_width * .36)))
        # Maximize the readability of the first 11 columns on narrower windows.
        self._cell_width = min(46, max(28, (available_width - self._host_width - 24) // 11))
        host_width, cell_width = self._host_width, self._cell_width
        header_height, row_height = self._header_height, self._row_height
        table_width = host_width + (max_depth + 1) * cell_width
        canvas.create_rectangle(0, 0, table_width, header_height,
                                fill='#e6edf5', outline='')
        canvas.create_text(12, header_height // 2, text='Bildungsserver / Tiefe',
                           anchor='w', fill='#172a43', font=('Segoe UI', 10, 'bold'))
        for depth in range(max_depth + 1):
            canvas.create_text(host_width + depth * cell_width + cell_width / 2,
                               header_height // 2, text=str(depth),
                               fill='#3f5874', font=('Segoe UI', 9, 'bold'))
        for row_index, host in enumerate(hosts):
            top = header_height + row_index * row_height
            canvas.create_rectangle(0, top, host_width, top + row_height,
                                    fill='#f7fafc' if row_index % 2 else '#ffffff',
                                    outline='#e1e8f0')
            max_chars = max(15, (host_width - 18) // 7)
            caption = host if len(host) <= max_chars else host[:max_chars - 1] + '…'
            canvas.create_text(12, top + row_height / 2, text=caption,
                               anchor='w', fill='#20364e', font=('Segoe UI', 10))
            for depth in range(max_depth + 1):
                item = by_host[host].get(depth, {})
                indexed = item.get('indexed', 0)
                visited = item.get('done', 0) + item.get('blocked', 0) + item.get('error', 0)
                if indexed:
                    alpha = .19 + .73 * indexed / peak
                    color = '#%02x%02x%02x' % tuple(round(255 * (1 - alpha) + b * alpha)
                                                  for b in (12, 137, 104))
                elif item.get('error'):
                    color = '#f7dbda'
                elif visited:
                    color = '#fff0c9'
                else:
                    color = '#f1f4f8'
                x = host_width + depth * cell_width
                canvas.create_rectangle(x + 1, top + 1, x + cell_width - 1,
                                        top + row_height - 1,
                                        fill=color, outline='#dfe6ee')
                if indexed:
                    canvas.create_text(x + cell_width / 2, top + row_height / 2,
                                       text=str(indexed),
                                       font=('Segoe UI', 9, 'bold'), fill='#153c32')
                self.cells[(row_index, depth)] = {'host': host, 'depth': depth, **item}
        canvas.configure(scrollregion=(0, 0, table_width,
                                       header_height + len(hosts) * row_height))
        canvas.xview_moveto(previous_x)
        canvas.yview_moveto(previous_y)
        if len(by_host) > len(hosts):
            self.hover.set(f'{len(hosts)} von {len(by_host)} Hosts sichtbar · alle Hosts in der HTML-Heatmap')


class LiveDashboard(ttk.Frame):
    """Left half of the monitor: 2x3 KPI tiles and large scrollable heatmap."""

    def __init__(self, parent, on_stop, on_settings, on_html, on_viewer):
        super().__init__(parent, padding=(10, 8, 6, 8))
        header = ttk.Frame(self)
        header.pack(fill='x', pady=(0, 7))
        ttk.Label(header, text='Live-Monitoring',
                  font=('Segoe UI', 17, 'bold')).pack(side='left')

        actions = ttk.Frame(self)
        actions.pack(fill='x', pady=(0, 10))
        self.stop_button = ttk.Button(actions, text='Sauber stoppen & exportieren',
                                      command=on_stop)
        self.stop_button.pack(side='left', padx=(0, 6))
        ttk.Button(actions, text='Materialviewer', command=on_viewer).pack(side='left', padx=(0, 6))
        ttk.Button(actions, text='HTML-Heatmap', command=on_html).pack(side='left', padx=(0, 6))
        self.back_button = ttk.Button(actions, text='Einstellungen', command=on_settings)
        self.back_button.pack(side='left')

        # Two rows rather than six narrow columns: all values remain legible
        # when the user drags the splitter towards the monitor.
        tile_area = ttk.Frame(self)
        tile_area.pack(fill='x', pady=(0, 8))
        for column in range(3):
            tile_area.columnconfigure(column, weight=1, uniform='cards')
        self.tiles = {}
        pairs = (('visited', 'ABGEARBEITET'), ('indexed', 'INDEXIERT'),
                 ('queued', 'OFFEN'), ('errors', 'FEHLER'),
                 ('corpus', 'KORPUS (CA.)'), ('depth', 'MAX. TIEFE'))
        for index, (name, label) in enumerate(pairs):
            row, col = divmod(index, 3)
            card = tk.Frame(tile_area, bg='#f2f6fb', highlightbackground='#d8e3ed',
                            highlightthickness=1, padx=12, pady=9)
            card.grid(row=row, column=col, sticky='nsew', padx=(0, 7) if col < 2 else 0,
                      pady=(0, 7) if row == 0 else 0)
            tk.Label(card, text=label, bg='#f2f6fb', fg='#536783',
                     font=('Segoe UI', 9, 'bold')).pack(anchor='w')
            value = tk.StringVar(value='–')
            tk.Label(card, textvariable=value, bg='#f2f6fb', fg='#152b48',
                     font=('Segoe UI', 19, 'bold')).pack(anchor='w', pady=(3, 0))
            self.tiles[name] = value

        self.subtext = tk.StringVar(value='Warte auf den ersten Crawling-Status …')
        self._detail_label = ttk.Label(self, textvariable=self.subtext,
                                       font=('Segoe UI', 9), justify='left',
                                       wraplength=650)
        self._detail_label.pack(fill='x', pady=(0, 9))
        title = ttk.Frame(self)
        title.pack(fill='x', pady=(0, 6))
        ttk.Label(title, text='Verteilung nach Bildungsserver und Crawling-Tiefe',
                  font=('Segoe UI', 11, 'bold')).pack(side='left')
        self.chart = HeatmapCanvas(self)
        self.chart.pack(fill='both', expand=True)
        self.bind('<Configure>', self._on_resize)

    def _on_resize(self, event):
        if event.widget is self:
            try:
                if self._detail_label.winfo_exists():
                    self._detail_label.configure(wraplength=max(250, event.width - 35))
            except tk.TclError:
                # The window can be destroyed while a Configure is queued.
                pass

    def set_running(self, running: bool):
        self.back_button.configure(state='disabled' if running else 'normal')
        self.stop_button.configure(state='normal' if running else 'disabled')

    def update_snapshot(self, data: dict):
        def fmt(n):
            return f'{n:,}'.replace(',', '.')

        self.tiles['visited'].set(fmt(data['visited']))
        self.tiles['indexed'].set(fmt(data['indexed']))
        self.tiles['queued'].set(fmt(data['queued']))
        self.tiles['errors'].set(fmt(data['errors']))
        self.tiles['depth'].set(str(data.get('depth_max', 0)))
        size = data.get('corpus_bytes')
        self.tiles['corpus'].set(f'{size / 1024**2:.2f} MiB' if size is not None else '–')
        top = ', '.join(f'{name}: {fmt(count)}' for name, count in data.get('document_types', [])[:4])
        self.subtext.set(f'{fmt(data["discovered"])} URLs entdeckt · '
                         f'{fmt(data["blocked"])} blockiert · '
                         f'{fmt(data["hosts"])} Hosts · '
                         f'{fmt(data["seed_rounds"])} Seed-Runden · '
                         f'{fmt(data["material_links"])} Materiallinks'
                         + (f'\nDokumenttypen: {top}' if top else ''))
        self.chart.render(data)
