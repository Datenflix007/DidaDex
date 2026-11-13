# Live-Dashboard im DidaDex-Desktop

## Zweck und Start

Der Tab **Crawler** hat zwei Ansichten. Vor dem Lauf ist die bestehende Konfiguration mit `TEST / STANDARD / NACHT`, Fächern, Workern und Round-Robin-DFS sichtbar. Nach **Crawler starten** wird diese Konfiguration ausgeblendet. Oben erscheinen reale Crawl-Kennzahlen, mittig die Heatmap und darunter das unveränderte, fortlaufende Terminalprotokoll.

```powershell
python engine_desktop.py
```

Die Ansicht lässt sich während des Laufs **nicht** zurück zu den Einstellungen schalten. **Sauber stoppen & exportieren** löst denselben geordneten Stoppprozess aus wie die bisherige Engine. Nach dem Crawl bleibt das Dashboard zur Kontrolle sichtbar; mit **Einstellungen** geht es zurück zur Konfiguration. `engine.py` enthält jetzt die vereinheitlichte Oberfläche; `engine_desktop.py` bleibt als kompatibler Starter. Der Materialviewer bleibt im zweiten Tab.

## Live-Daten: Herkunft und Bedeutung

Alle drei Sekunden liest `crawledDataViewer/live_dashboard.py` die SQLite-Datenbank des aktiven Laufs unter `crawler/outputs/runs/<RUN_NAME>/crawler_state.sqlite` schreibgeschützt. Es greift *nicht* in die Datenbankoperationen des Crawlers ein.

| KPI | Quelle | Bedeutung |
|---|---|---|
| Abgearbeitet | `frontier.status` (`done`, `blocked`, `error`) | Abgeschlossene URL-Vorgänge, nicht zwingend erfolgreiche Downloads |
| Indexiert | `documents` | Tatsächlich zur Suche aufgenommene Dokumente |
| Offen | `frontier.status=queued` | Noch nicht abgearbeitete URLs |
| Fehler | `frontier.status=error` | Fehlerhafter Crawl-Vorgang |
| Max. Tiefe | `crawl_depth_stats` und zugeordnetes Dokument | Höchste **beobachtete** Tiefe (kein eingestelltes Limit) |
| Korpus (ca.) | `crawler_live.json` | Vorläufige, crawlerseitige Schätzung der JSONL-Textmenge; kein exakter Exportwert |
| Dokumenttypen | `documents.doc_type` | Tatsächlich indexierte Typen, keine manuelle Qualitätsbewertung |
| Materiallinks | `material_links` | Erkannte Verweise; noch keine Garantie, dass die Datei heruntergeladen wurde |

Die Heatmap basiert ebenfalls auf SQLite: **Grün** bedeutet indexierte Dokumente, **Gelb** einen besuchten Bereich ohne Indexierung, **Rot** aufgetretene Fehler, **Grau** keine erfassten Besuche. Die native Vorschau zeigt zugunsten der Leistung höchstens 32 Hosts nach Aktivität, die HTML-Datei enthält alle Hosts. Horizontal und vertikal ist Scrollen möglich.

**Hinweis:** Abgearbeitete URLs und indexierte Dokumente sind bewusst unterschiedliche Werte. Nach einer kurzen Laufzeit (z. B. zwei Minuten) können die indexierten Treffer weiterhin nur wenige Dokumente sein, obwohl bereits viele URLs gesichtet wurden. Bei mehrfach vorkommenden/umgeleiteten Adressen kann die Heatmap-Aggregation vom Gesamtzähler abweichen. Die Zahl `Korpus (ca.)` basiert auf der bisherigen Notebook-Schätzung und ist **nicht** die Dateigröße von `crawl.jsonl` nach Export.

## Dateien und Aktualisierung

`crawler.py` erstellt zusätzlich während des Crawls spätestens etwa alle zwei Sekunden (sofern neue URLs abgearbeitet werden) die kleine Statusdatei `crawler_live.json` per atomarem Ersetzen. Sie enthält nur technische Zähler, **keine Volltexte**. Der Monitor aktualisiert alle drei Sekunden eine **separate** lokale Datei:

`crawler/outputs/runs/<RUN_NAME>/depth_heatmap_live.html`

Die HTML-Datei ist vollständig offline lesbar, benötigt kein Streamlit, keine externen CDNs und aktualisiert sich beim Öffnen im Browser alle sechs Sekunden. Der HTML-Button ist optional; die eigentliche Heatmap bleibt **im Python-Fenster** als Tkinter-Canvas sichtbar.

Die bestehenden Ausgaben des Crawlers `depth_heatmap.html`, `depth_heatmap.json`, `depth_heatmap.tsv` und `crawl.jsonl` werden **nicht ersetzt**. `depth_heatmap_live.html` ist nur eine Momentaufnahme des Monitorings.

## Performance, Fehler und Sicherheit

- Datenbankabfragen und HTML-Generierung laufen in einem separaten Daemon-Thread; Tkinter wird ausschließlich vom Hauptthread aktualisiert.
- SQLite wird mit `mode=ro`, WAL-Unterstützung und kurzem Busy-Timeout geöffnet. Falls der Laufordner noch nicht existiert, zeigt das Dashboard Platzhalter statt erfundener Werte.
- Ein kurzzeitiger Datenbank-Lesefehler erscheint einmalig im Terminal und wird beim nächsten Intervall erneut versucht. Der Crawl wird deswegen nicht beendet.
- Statusdateien werden atomar ersetzt. Wenn die optionale Statusdatei nicht schreibbar ist, läuft der Crawler weiter.
- Der Monitor läuft nach Abschluss bis zur Rückkehr zu den Einstellungen weiter, um die Export-Zahlen zu aktualisieren.
- `engine_desktop.py` bleibt als kompatibler Startweg; der Streamlit-Viewer bleibt als Fallback im Repository.

## Prüfung

```powershell
python -m unittest discover -s tests -v
```

Insbesondere `tests/test_live_dashboard.py` prüft persistierte SQLite-Zähler, kanonische URLs, HTML-Escaping, atomisches Schreiben und Polling ohne externe Netzverbindung. Die grafische Darstellung wurde separat unter einer virtuellen Anzeige getestet. Ein echter Windows-Netzlauf ist damit noch nicht vollständig abgedeckt.

## Update: Widescreen-Ansicht (11.11.2026)

Die Live-Ansicht belegt jetzt den gesamten **Crawler-Tab** und ist in zwei vertikal angeordnete **Spalten** unterteilt:

- **Links (anfangs 60 %):** Live-Monitoring mit sechs Kennzahlen in zwei Reihen, Statusdetails und vergrößerter, responsiver Heatmap. Die Heatmap kann horizontal/vertikal gescrollt werden. Die 60 aktivsten Hosts sind in der Desktop-Ansicht sichtbar; die HTML-Heatmap enthält weiterhin alle Hosts.
- **Rechts (anfangs 40 %):** Crawler-Status, Fortschrittsbalken und eine **vollständig sichtbare Konsole** mit automatischem Scrollen sowie einer Schaltfläche zum Kopieren des Protokolls.

Das Hauptfenster startet unter Windows maximiert (`state('zoomed')`); die Windows-Taskleiste und die normale Titelleiste bleiben erhalten. Bei anderen Fenstersystemen wird möglichst die verfügbare Bildschirmfläche genutzt.

Die **Trennlinie zwischen Heatmap und Konsole lässt sich mit der Maus verschieben**. Die Aufteilung wird nur beim Wechsel zum Dashboard initial auf 60:40 gestellt, nicht bei jedem Polling. Damit bleibt eine manuell gewählte Breite während des Laufs bestehen.

Die Einstellungsmaske und das bisherige Fortschrittsfeld werden **nur während des Crawls ausgeblendet**. Nach Laufende stellt **Einstellungen** beide wieder her. Der Crawler, die Round-Robin-DFS-Logik, das SQLite-Schema und die Exportdateien werden nicht verändert. In der ZIP werden ausschließlich die UI-Dateien und diese Dokumentation ersetzt.

### Erneute Prüfung

```powershell
python -m unittest discover -s tests -v
```

Ohne grafische Anzeige werden die drei GUI-Tests übersprungen; unter Windows bzw. mit Xvfb werden Fensteraufteilung, Umschalten, Konsole und Live-Metriken geprüft. Ein echter Windows-Netzlauf ist kein Bestandteil dieser Tests.
