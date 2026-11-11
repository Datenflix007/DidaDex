"""Native Tkinter viewer for DidaDex crawl.jsonl collections (Python 3.10+).

Used by engine_desktop.py inside the desktop application, or independently:
    python crawledDataViewer/viewer_tk.py --root crawler/outputs/runs

Requires only the Python standard library (tkinter included in normal Windows Python).
Does not start a web server, Streamlit, or a browser window.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import queue
import re
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse

DISPLAY_LIMIT = 250
EXCERPT_CHARS = 6000
MAX_DOCUMENTS = 500_000
LABELS_NAME = 'manual_labels.json'
CLASSES = ('Alle Bewertungen', 'Unterrichtsmaterial', 'Prüfen', 'Unbrauchbar')


def document_key(doc: dict) -> str:
    return str(doc.get('id') or doc.get('docno') or doc.get('url') or '')


def descriptive_class(doc: dict) -> str:
    """Quality-score bands are viewer aids, not objective relevance judgements."""
    try:
        score = int(doc.get('quality_score') or 0)
    except (TypeError, ValueError):
        score = 0
    if score >= 10:
        return 'Unterrichtsmaterial'
    if score >= 6:
        return 'Prüfen'
    return 'Unbrauchbar'


def normalize_fields(doc: dict, byte_offset: int) -> dict:
    text = next((doc[k] for k in ('text', 'search_text', 'main_text', 'text_excerpt')
                 if isinstance(doc.get(k), str) and doc[k].strip()), '')
    subjects = doc.get('subjects_mentioned') or doc.get('subjects') or []
    if isinstance(subjects, str):
        subjects = [subjects]
    if not isinstance(subjects, list):
        subjects = []
    materials = doc.get('material_links') or []
    if not isinstance(materials, list):
        materials = []
    try:
        score = int(doc.get('quality_score') or 0)
    except (ValueError, TypeError):
        score = 0
    return {
        'key': document_key(doc), 'offset': byte_offset,
        'title': str(doc.get('title') or '(ohne Titel)'),
        'url': str(doc.get('url') or ''),
        'score': score, 'class': descriptive_class(doc),
        'type': str(doc.get('doc_type') or doc.get('document_type') or 'unbekannt'),
        'source': str(doc.get('source') or 'unbekannt'),
        'subjects': ', '.join(str(v) for v in subjects),
        'depth': str(doc.get('crawl_depth') if doc.get('crawl_depth') is not None else '-'),
        'excerpt': text[:EXCERPT_CHARS], 'material_count': len(materials),
    }


def scan_jsonl(path: Path, progress=None, max_documents=MAX_DOCUMENTS):
    """Scan JSONL once, retaining only small descriptors and byte offsets.

    Full text is read on demand via seek() when the user selects a row.
    Invalid lines are skipped and reported, not treated as fatal errors.
    """
    entries = []
    invalid = 0
    processed = 0
    with Path(path).open('rb') as stream:
        while len(entries) < max_documents:
            offset = stream.tell()
            line = stream.readline()
            if not line:
                break
            processed += 1
            try:
                doc = json.loads(line)
                if not isinstance(doc, dict):
                    invalid += 1
                    continue
                entries.append(normalize_fields(doc, offset))
            except (UnicodeDecodeError, ValueError, TypeError):
                invalid += 1
            if progress and processed % 5000 == 0:
                progress(processed)
    return entries, invalid, processed


def load_document(path: Path, offset: int) -> dict:
    with Path(path).open('rb') as stream:
        stream.seek(offset)
        doc = json.loads(stream.readline())
    if not isinstance(doc, dict):
        raise ValueError('Datensatz ist kein JSON-Objekt.')
    return doc


def read_labels(folder: Path) -> dict:
    if not folder:
        return {}
    path = folder / LABELS_NAME
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        # Also retain labels from the original Streamlit viewer. Those entries
        # are dictionaries keyed by raw-N / index-N, and must not be deleted.
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def label_category(labels: dict, key: str, url: str = '') -> str | None:
    value = labels.get(key)
    if isinstance(value, str) and value in CLASSES:
        return value
    if isinstance(value, dict) and value.get('category') in CLASSES:
        return value['category']
    # Compatibility: original Streamlit viewer used position-dependent IDs.
    if url:
        for entry in labels.values():
            if (isinstance(entry, dict) and entry.get('url') == url and
                    entry.get('category') in CLASSES):
                return entry['category']
    return None


def write_labels(folder: Path, labels: dict):
    path = folder / LABELS_NAME
    tmp = folder / (LABELS_NAME + '.tmp')
    tmp.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def runs_in(root: Path):
    if not root.is_dir():
        return []
    return sorted([p for p in root.iterdir() if p.is_dir() and (p / 'crawl.jsonl').is_file()],
                  key=lambda p: p.stat().st_mtime, reverse=True)


class MaterialViewer(ttk.Frame):
    """Embeddable read-only corpus viewer with optional separate manual labels."""

    def __init__(self, parent, root: Path, initial_run: str | None = None):
        super().__init__(parent, padding=10)
        self.root_dir = Path(root).resolve()
        self.path: Path | None = None
        self.rows: list[dict] = []
        self.labels: dict = {}
        self.url_labels: dict[str, str] = {}
        self.filtered: list[int] = []
        self.current_index: int | None = None
        self.selected_doc: dict = {}
        self.page = 0
        self.job_id = 0
        self.events: queue.Queue = queue.Queue()
        self.debounce = None
        self.sort_desc = True
        self.sort_key = 'score'
        self.run_paths = {}
        self.search_var = tk.StringVar()
        self.type_var = tk.StringVar(value='Alle Typen')
        self.subject_var = tk.StringVar(value='Alle Fächer')
        self.class_var = tk.StringVar(value='Alle Bewertungen')
        self.run_var = tk.StringVar()
        self.info_var = tk.StringVar(value='Noch keine Datei geladen')
        self.detail_var = tk.StringVar(value='Dokument auswählen')
        self._build()
        self.refresh_runs(initial_run)
        self.after(100, self._poll)

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        ttk.Label(self, text='DidaDex – Crawled Data Viewer', font=('Segoe UI', 16, 'bold')).grid(
            row=0, column=0, sticky='w', pady=(0, 8))
        runbar = ttk.Frame(self)
        runbar.grid(row=1, column=0, sticky='ew', pady=(0, 6))
        runbar.columnconfigure(1, weight=1)
        ttk.Label(runbar, text='Lauf:').grid(row=0, column=0, padx=(0, 6))
        self.run_selector = ttk.Combobox(runbar, textvariable=self.run_var, state='readonly')
        self.run_selector.grid(row=0, column=1, sticky='ew')
        self.run_selector.bind('<<ComboboxSelected>>', lambda _: self.load_run())
        ttk.Button(runbar, text='Läufe aktualisieren', command=self.refresh_runs).grid(row=0, column=2, padx=6)
        ttk.Button(runbar, text='JSONL öffnen', command=self.select_file).grid(row=0, column=3)
        filters = ttk.Frame(self)
        filters.grid(row=2, column=0, sticky='ew', pady=(0, 8))
        filters.columnconfigure(0, weight=1)
        self.search = ttk.Entry(filters, textvariable=self.search_var)
        self.search.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        for j, (variable, width) in enumerate(((self.type_var, 20), (self.subject_var, 19),
                                                (self.class_var, 20)), 1):
            cb = ttk.Combobox(filters, textvariable=variable, state='readonly', width=width)
            cb.grid(row=0, column=j, padx=3)
            cb.bind('<<ComboboxSelected>>', lambda _: self.apply_filters())
            if j == 1:
                self.types_box = cb
            elif j == 2:
                self.subjects_box = cb
            else:
                self.classes_box = cb
        self.classes_box['values'] = CLASSES
        self.search_var.trace_add('write', lambda *_: self.schedule_filter())
        self.pane = ttk.Panedwindow(self, orient='horizontal')
        self.pane.grid(row=3, column=0, sticky='nsew')
        left = ttk.Frame(self.pane)
        right = ttk.Frame(self.pane)
        self.pane.add(left, weight=3)
        self.pane.add(right, weight=4)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(left, columns=('score', 'type', 'source', 'depth', 'title'),
                                 show='headings', selectmode='browse')
        for name, heading, width in (('score', 'Score', 60), ('type', 'Dokumenttyp', 135),
                                     ('source', 'Quelle', 120), ('depth', 'Tiefe', 50),
                                     ('title', 'Titel', 350)):
            self.tree.heading(name, text=heading, command=lambda n=name: self.change_sort(n))
            self.tree.column(name, width=width, minwidth=50,
                             anchor='e' if name == 'score' else 'w', stretch=(name == 'title'))
        self.tree.grid(row=0, column=0, sticky='nsew')
        vscroll = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview)
        vscroll.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=vscroll.set)
        self.tree.bind('<<TreeviewSelect>>', self.show_selected)
        paging = ttk.Frame(left)
        paging.grid(row=1, column=0, columnspan=2, sticky='ew', pady=5)
        ttk.Button(paging, text='◀ Zurück', command=self.prev_page).pack(side='left')
        self.page_label = ttk.Label(paging, text='')
        self.page_label.pack(side='left', padx=10)
        ttk.Button(paging, text='Weiter ▶', command=self.next_page).pack(side='left')
        ttk.Button(paging, text='CSV exportieren', command=self.export_csv).pack(side='right')
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        ttk.Label(right, textvariable=self.detail_var, font=('Segoe UI', 11, 'bold'),
                  wraplength=570).grid(row=0, column=0, sticky='w', padx=10, pady=5)
        tools = ttk.Frame(right)
        tools.grid(row=1, column=0, sticky='ew', padx=10)
        ttk.Button(tools, text='Quellseite öffnen', command=self.open_url).pack(side='left', padx=(0, 5))
        ttk.Button(tools, text='URL kopieren', command=self.copy_url).pack(side='left', padx=(0, 5))
        self.label_var = tk.StringVar(value='Kein manuelles Label')
        self.label_box = ttk.Combobox(tools, textvariable=self.label_var, state='readonly',
                                      values=('Kein manuelles Label', *CLASSES[1:]), width=21)
        self.label_box.pack(side='left', padx=5)
        self.label_box.bind('<<ComboboxSelected>>', lambda _: self.set_label())
        textframe = ttk.Frame(right)
        textframe.grid(row=2, column=0, sticky='nsew', padx=10, pady=8)
        textframe.columnconfigure(0, weight=1)
        textframe.rowconfigure(0, weight=1)
        self.details = tk.Text(textframe, wrap='word', font=('Consolas', 10), padx=12, pady=10,
                               borderwidth=0, state='disabled')
        self.details.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(textframe, command=self.details.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.details.configure(yscrollcommand=scroll.set)
        self.details.tag_configure('link', foreground='#1261a0', underline=True)
        self.details.tag_bind('link', '<Button-1>', self._link_click)
        self.details.tag_bind('link', '<Enter>', lambda _: self.details.configure(cursor='hand2'))
        self.details.tag_bind('link', '<Leave>', lambda _: self.details.configure(cursor=''))
        ttk.Label(self, textvariable=self.info_var).grid(row=4, column=0, sticky='w', pady=(8, 0))

    def refresh_runs(self, initial_run=None):
        runs = runs_in(self.root_dir)
        self.run_paths = {p.name: p / 'crawl.jsonl' for p in runs}
        previous = self.run_var.get()
        self.run_selector['values'] = list(self.run_paths)
        choice = (initial_run if initial_run in self.run_paths else
                  previous if previous in self.run_paths else
                  next(iter(self.run_paths), ''))
        if choice:
            self.run_var.set(choice)
            self.load_run()
        elif not self.path:
            self.info_var.set('Kein Lauf gefunden – wähle eine crawl.jsonl-Datei über „JSONL öffnen“.')

    def select_file(self):
        selected = filedialog.askopenfilename(parent=self, title='crawl.jsonl öffnen',
                                               initialdir=str(self.root_dir),
                                               filetypes=[('JSON Lines', '*.jsonl'), ('Alle Dateien', '*.*')])
        if selected:
            self.run_var.set(Path(selected).parent.name)
            self.open_file(Path(selected))

    def load_run(self):
        path = self.run_paths.get(self.run_var.get())
        if path:
            self.open_file(path)

    def open_file(self, path: Path):
        path = Path(path)
        if not path.is_file():
            messagebox.showerror('Datei fehlt', str(path), parent=self)
            return
        self.job_id += 1
        task = self.job_id
        self.path = path
        self.rows = []
        self.filtered = []
        self.labels = read_labels(path.parent)
        self.url_labels = {
            v.get('url'): v['category'] for v in self.labels.values()
            if isinstance(v, dict) and isinstance(v.get('url'), str) and
               v.get('category') in CLASSES
        }
        self.info_var.set(f'Lese {path.name} im Hintergrund …')
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.detail_var.set('Lade Dokumente …')
        def background():
            try:
                result = scan_jsonl(path, progress=lambda n: self.events.put(('progress', task, n)))
                self.events.put(('loaded', task, result))
            except (OSError, ValueError) as exc:
                self.events.put(('error', task, str(exc)))
        threading.Thread(target=background, daemon=True).start()

    def _poll(self):
        try:
            for _ in range(80):
                kind, task, payload = self.events.get_nowait()
                if task != self.job_id:
                    continue
                if kind == 'progress':
                    self.info_var.set(f'Lese Dokumente: {payload:,} Zeilen …')
                elif kind == 'error':
                    self.info_var.set('Fehler beim Laden: ' + payload)
                    messagebox.showerror('JSONL konnte nicht geladen werden', payload, parent=self)
                elif kind == 'loaded':
                    self.rows, invalid, processed = payload
                    self.invalid_count = invalid
                    self.truncated = len(self.rows) >= MAX_DOCUMENTS
                    self.types_box['values'] = ['Alle Typen', *sorted({r['type'] for r in self.rows})]
                    names = set()
                    for r in self.rows:
                        names.update(x.strip() for x in r['subjects'].split(',') if x.strip())
                    self.subjects_box['values'] = ['Alle Fächer', *sorted(names)]
                    self.type_var.set('Alle Typen')
                    self.subject_var.set('Alle Fächer')
                    self.class_var.set('Alle Bewertungen')
                    self.apply_filters()
                    self.info_var.set(f'{len(self.rows):,} Dokumente geladen; {invalid} ungültige Zeilen; '
                                      f'{self.path.name} ({self.path.stat().st_size / 1024**2:.1f} MiB).')
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def schedule_filter(self):
        if self.debounce is not None:
            self.after_cancel(self.debounce)
        self.debounce = self.after(220, self.apply_filters)

    def _manual_class(self, row):
        direct = self.labels.get(row['key'])
        if isinstance(direct, str) and direct in CLASSES:
            return direct
        if isinstance(direct, dict) and direct.get('category') in CLASSES:
            return direct['category']
        return self.url_labels.get(row['url'])

    def apply_filters(self):
        self.debounce = None
        query = self.search_var.get().strip().casefold()
        terms = query.split()
        selected_type = self.type_var.get()
        selected_subject = self.subject_var.get()
        selected_class = self.class_var.get()
        hits = []
        for i, r in enumerate(self.rows):
            if selected_type not in ('', 'Alle Typen') and r['type'] != selected_type:
                continue
            if selected_subject not in ('', 'Alle Fächer') and selected_subject not in r['subjects'].split(', '):
                continue
            label = self._manual_class(r) or r['class']
            if selected_class not in ('', 'Alle Bewertungen') and selected_class != label:
                continue
            if terms:
                haystack = (r['title'] + ' ' + r['url'] + ' ' + r['source'] + ' ' +
                            r['subjects'] + ' ' + r['excerpt']).casefold()
                if not all(term in haystack for term in terms):
                    continue
            hits.append(i)
        if self.sort_key == 'score':
            hits.sort(key=lambda i: (self.rows[i]['score'], self.rows[i]['title'].casefold()), reverse=self.sort_desc)
        else:
            key = {'title': 'title', 'type': 'type', 'source': 'source', 'depth': 'depth'}.get(self.sort_key, 'title')
            hits.sort(key=lambda i: self.rows[i][key].casefold(), reverse=self.sort_desc)
        self.filtered = hits
        self.page = 0
        self.draw_page()

    def change_sort(self, column):
        if self.sort_key == column:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key = column
            self.sort_desc = column == 'score'
        self.apply_filters()

    def draw_page(self):
        self.tree.delete(*self.tree.get_children())
        start = self.page * DISPLAY_LIMIT
        current = self.filtered[start:start + DISPLAY_LIMIT]
        for index in current:
            item = self.rows[index]
            self.tree.insert('', 'end', iid=str(index), values=(item['score'], item['type'],
                             item['source'], item['depth'], item['title']))
        pages = max(1, (len(self.filtered) + DISPLAY_LIMIT - 1) // DISPLAY_LIMIT)
        self.page_label.configure(text=f'Seite {self.page+1}/{pages} · {len(self.filtered):,} Treffer')
        if current:
            self.tree.selection_set(str(current[0]))
            self.tree.focus(str(current[0]))
            self.show_selected()
        else:
            self.current_index = None
            self.detail_var.set('Keine passenden Dokumente')
            self._set_text('Passe die Suchbegriffe oder Filter an.')

    def prev_page(self):
        if self.page > 0:
            self.page -= 1
            self.draw_page()

    def next_page(self):
        if (self.page + 1) * DISPLAY_LIMIT < len(self.filtered):
            self.page += 1
            self.draw_page()

    def show_selected(self, _event=None):
        selected = self.tree.selection()
        if not selected or not self.path:
            return
        index = int(selected[0])
        self.current_index = index
        row = self.rows[index]
        try:
            doc = load_document(self.path, row['offset'])
        except (ValueError, OSError) as exc:
            self._set_text(f'Dokument konnte nicht gelesen werden: {exc}')
            return
        self.selected_doc = doc
        self.detail_var.set(row['title'])
        self.label_var.set(self._manual_class(row) or 'Kein manuelles Label')
        metadata = (
            f"Score: {row['score']} (heuristisch)  |  Bewertung: {self._manual_class(row) or row['class']}\n"
            f"Typ: {row['type']}  |  Quelle: {row['source']}  |  Tiefe: {row['depth']}\n"
            f"Fächer (Textsignale): {row['subjects'] or 'keine'}\n"
            f"Jahrgang: {doc.get('grade_evidence') or 'nicht angegeben'}\n"
            f"Unterrichtsphasen: {', '.join(doc.get('phases_mentioned') or []) or 'keine'}\n"
            f"Sozialformen: {', '.join(doc.get('social_forms_mentioned') or []) or 'keine'}\n"
            f"Lizenzhinweis: {doc.get('license') or 'nicht angegeben / ungeprüft'}\n"
            f"Crawl-Zeit: {doc.get('crawled_at') or 'unbekannt'}\n"
            f"Dokument-ID: {row['key']}\n\n"
        )
        content = doc.get('text') or doc.get('search_text') or doc.get('main_text') or ''
        self._set_text(metadata + 'QUELLSEITE\n' + row['url'] + '\n\n' +
                       'MATERIALLINKS\n' + '\n'.join(str(x) for x in doc.get('material_links') or []) +
                       '\n\nVOLLSTÄNDIGER EXTRAHIERTER TEXT\n\n' + content)
        self._mark_links()

    def _set_text(self, content):
        self.details.configure(state='normal')
        self.details.delete('1.0', 'end')
        self.details.insert('1.0', content)
        self.details.configure(state='disabled')

    def _mark_links(self):
        self.details.configure(state='normal')
        text = self.details.get('1.0', 'end-1c')
        for match in re.finditer(r'https?://[^\s<>"\']+', text):
            a, b = match.span()
            self.details.tag_add('link', f'1.0+{a}c', f'1.0+{b}c')
        self.details.configure(state='disabled')

    def _link_click(self, event):
        index = self.details.index(f'@{event.x},{event.y}')
        ranges = self.details.tag_prevrange('link', f'{index}+1c')
        if ranges:
            url = self.details.get(*ranges).rstrip('.,;)')
            if url.startswith(('https://', 'http://')):
                webbrowser.open(url)

    def open_url(self):
        if self.current_index is not None:
            url = self.rows[self.current_index]['url']
            if url.startswith(('https://', 'http://')):
                webbrowser.open(url)

    def copy_url(self):
        if self.current_index is not None:
            self.clipboard_clear()
            self.clipboard_append(self.rows[self.current_index]['url'])

    def set_label(self):
        if self.current_index is None or not self.path:
            return
        key = self.rows[self.current_index]['key']
        if not key:
            messagebox.showwarning('Keine ID', 'Dieses Dokument hat weder ID noch URL.', parent=self)
            return
        label = self.label_var.get()
        row = self.rows[self.current_index]
        if label == 'Kein manuelles Label':
            # Remove stale legacy Streamlit labels for the same URL as well.
            self.labels.pop(key, None)
            for old_key, value in list(self.labels.items()):
                if isinstance(value, dict) and value.get('url') == row['url']:
                    self.labels.pop(old_key, None)
            self.url_labels.pop(row['url'], None)
        else:
            # Compatible with the old viewer's metadata-rich label format.
            self.labels[key] = {'category': label, 'title': row['title'],
                                'url': row['url'], 'source': row['source']}
            self.url_labels[row['url']] = label
        try:
            write_labels(self.path.parent, self.labels)
        except OSError as exc:
            messagebox.showerror('Label konnte nicht gespeichert werden', str(exc), parent=self)
        self.apply_filters()

    def export_csv(self):
        if not self.path or not self.filtered:
            return
        dest = filedialog.asksaveasfilename(parent=self, title='Aktuelle Treffer als CSV exportieren',
                                             initialfile='didadex_treffer.csv', defaultextension='.csv',
                                             filetypes=[('CSV', '*.csv')])
        if not dest:
            return
        try:
            with open(dest, 'w', encoding='utf-8-sig', newline='') as handle:
                columns = ('title', 'url', 'score', 'class', 'type', 'source', 'subjects', 'depth', 'material_count')
                writer = csv.DictWriter(handle, fieldnames=columns, extrasaction='ignore')
                writer.writeheader()
                for i in self.filtered:
                    row = dict(self.rows[i])
                    row['class'] = self._manual_class(row) or row['class']
                    writer.writerow(row)
            self.info_var.set(f'Exportiert: {len(self.filtered):,} Treffer nach {dest}')
        except OSError as exc:
            messagebox.showerror('Export fehlgeschlagen', str(exc), parent=self)


def main():
    parser = argparse.ArgumentParser(description='DidaDex Materialviewer als lokales Tkinter-Fenster')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1] / 'crawler' / 'outputs' / 'runs')
    parser.add_argument('--file', type=Path, help='Beliebige crawl.jsonl-Datei direkt öffnen')
    args = parser.parse_args()
    app = tk.Tk()
    app.title('DidaDex – Materialviewer (ohne Streamlit)')
    app.geometry('1320x800')
    app.minsize(900, 550)
    viewer = MaterialViewer(app, args.root)
    viewer.pack(fill='both', expand=True)
    if args.file:
        viewer.open_file(args.file)
    app.mainloop()


if __name__ == '__main__':
    main()
