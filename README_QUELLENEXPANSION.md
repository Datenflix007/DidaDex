# DidaDex – Overlay fuer deine bestehende Projektstruktur

**Datum:** 11.11.2026. **Wichtig:** Die Dateien aus diesem Overlay kommen **direkt in den bestehenden Ordner `didadex/`**, nicht in einen zweiten verschachtelten `didadex/didadex/`-Ordner. Bestehende Dateien werden **nicht ersetzt**.

## Einfuegen (VS Code oder Windows-Explorer)

1. Alten Crawl in deiner GUI mit **„Sauber stoppen & exportieren“** beenden; vorher Projektordner sichern.
2. ZIP entpacken. **Inhalt** des Ordners `DidaDex_Overlay_didadex` markieren und in den vorhandenen Projektstamm `didadex/` einfuegen. Windows kann neue Dateien in bestehende Ordner `crawler/`, `docs/`, `tests/` hineinlegen. Die vorhandenen Dateien `engine.py`, `engine_desktop.py`, `crawler/crawler.ipynb`, `crawler/requirements_crawler.txt`, `README.md` und der Viewer bleiben UNBERUEHRT.
3. PowerShell im Verzeichnis `didadex/` starten und `./start_expansion_72h.ps1` bzw. unter Windows `.\start_expansion_72h.ps1` ausfuehren. Alternativ `crawler/crawler_expansion.ipynb` oeffnen und die Zellen ablaufen lassen.
4. Den Status ueber `.\status_expansion.ps1` abfragen. Zum Export `.\export_expansion.ps1` verwenden.
5. Nach dem Lauf fuer die spaetere Suche Daten vereinigen (Details unten). **Die neue Sammlung erscheint noch nicht automatisch im alten Tkinter-Viewer**.

## Neue und unveraenderte Projektdateien

```
didadex/
|-- .venv/                            [bestehend; wiederverwendet]
|-- crawledDataViewer/                [bestehend; unveraendert]
|-- crawler/
|   |-- crawler.ipynb                 [bestehend; unveraendert]
|   |-- requirements_crawler.txt     [bestehend; unveraendert]
|   |-- outputs/
|   |   `-- expansion/                [wird automatisch erzeugt]
|   |       |-- expanded.sqlite
|   |       |-- report.json
|   |       `-- documents.jsonl
|   |-- crawler_expansion.ipynb       [NEU: Jupyter-Alternative]
|   `-- expansion/                    [NEU: Quellen-/Langzeitcrawler]
|       |-- crawler.py
|       |-- build_seeds.py
|       |-- seeds.json
|       |-- log_derived_seeds.json
|       |-- merge_existing.py
|       |-- ingest_local_archives.py
|       `-- requirements_expansion.txt
|-- docs/
|   |-- quellenexpansion_architektur.md [NEU]
|   `-- quellenexpansion_auswertung.md  [NEU]
|-- tests/
|   |-- test_expansion_offline.py      [NEU]
|   |-- test_expansion_pipeline.py     [NEU]
|   `-- run_expansion_tests.ps1        [NEU]
|-- engine.py                         [bestehend; unveraendert]
|-- engine_desktop.py                 [bestehend; unveraendert]
|-- README.md                         [bestehend; unveraendert]
|-- start_expansion_24h.ps1           [NEU]
|-- start_expansion_72h.ps1           [NEU]
|-- start_expansion_7tage.ps1         [NEU]
|-- status_expansion.ps1              [NEU]
|-- export_expansion.ps1              [NEU]
`-- README_QUELLENEXPANSION.md       [NEU]
```

## Start bei einer blockierenden PowerShell-Execution-Policy

In deiner bestehenden PowerShell-Konsole ohne globale Policy-Aenderung:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\crawler\expansion\requirements_expansion.txt
.\.venv\Scripts\python.exe .\crawler\expansion\crawler.py run --hours 72 --target-mib 500 --workers 20 --per-host 1 --host-delay 2.5 --bpb-sitemap
```

Falls `.venv` noch nicht existiert: `py -3 -m venv .venv`.

## Die bestehende Sammlung nach dem Lauf beibehalten

- Neue SQLite: `crawler/outputs/expansion/expanded.sqlite`.
- Neue Dokumente: `crawler/outputs/expansion/documents.jsonl`.
- Neuer Monitoringbericht: `crawler/outputs/expansion/report.json`.
- Dein bisheriger Korpus unter `crawler/outputs/runs/...` bleibt davon unberuehrt.
- **NICHT** das alte `crawler_state.sqlite` oder die alte `crawler.ipynb` durch die neuen Dateien ersetzen.

Nach STOP des bisherigen Crawlers und nach dem Export der Expansion (PowerShell im Stamm):

```powershell
.\.venv\Scripts\python.exe .\crawler\expansion\merge_existing.py --existing '.\crawler\outputs\runs\DEIN-LAUF\documents.jsonl'
```

Die exakte alte Exportdatei kann anders heissen. Ist in deiner bestehenden Ausgabe nur eine SQLite vorhanden, kann die Merge-Funktion `documents`/`docs` mit Spalten `url`, `title`, `text` lesen. Vorher die alte GUI **sauber stoppen** und die echte `.sqlite` verwenden – eine `.sqlite-wal` allein reicht nicht.

Das Ergebnis heisst `crawler/outputs/expansion/merged_documents.jsonl`. Es wird **nicht** ungefragt in die bestehende SQLite-Datenbank geschrieben.

## Vor dem wochenlangen Betrieb

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_expansion_*.py' -v
```

Offline-Tests sind erfolgreich; ein realer Netzlauf wurde mit diesem Overlay noch nicht abgeschlossen. `20` globale Worker, `1` pro Host mit mindestens `2.5` Sekunden Abstand; User-Agent und robots.txt werden beachtet, HTTP 429 wird mit Wartezeit behandelt. 250 Wikipedia-Artikelkandidaten (5 × 50) sind im Seedbestand **als Referenztexte** markiert und werden nicht als Unterrichtsplaene etikettiert. Lizenz am Quellmaterial pruefen.

**300–500 MiB extrahierter Text bis morgen oder nach sieben Tagen sind kein garantierter Ertrag.** Ein Seed kann nicht erreichbar oder nur als Landingpage verfuegbar sein. `report.json` zeigt die reale Ausbeute und Ablehnungsgruende pro Host.
