# DidaDex

## Start (Windows, Python 3.10+)
`python engine.py` im Projekt-Root. Python benötigt Tkinter (unter Windows normalerweise enthalten).

Die Engine legt bei Bedarf `.venv` an und installiert Abhängigkeiten. Den Crawler über den Tab **Crawler** starten, Modus und Fächer vorher wählen. Kein Fach gewählt = alle. TEST läuft maximal 10 Minuten Netzwerk-Crawl. START/STOP wird im UI angezeigt.

Die Notebook-Alternative: In `crawler/` mit Jupyter öffnen und in Zelle 1 `SUBJECT_FILTER = ["Informatik"]` einstellen. Der Notebook-Lauf verwendet die vom Notebook geladenen Abhängigkeiten.

**Daten:** `crawler/outputs/runs/<RUN_NAME>/crawl.jsonl`. SQLite-Status und Heatmap im selben Ordner; nur `crawl.jsonl` ist der Korpus. Beim Fortsetzen denselben Laufnamen verwenden. Wähle neue Namen für unabhängige Versuche.

**Fächer:** Heuristische, textbasierte Zuordnung. Die Auswahl beeinflusst die Priorität von Links sowie den Indexfilter. Allgemeine Unterrichtsmethoden können optional fachübergreifend aufgenommen werden. Nicht zugeordnete Übersichtsseiten bleiben für die Navigation zugänglich. 100% Vollständigkeit oder 500 MiB sind nicht garantiert.

**Lizenzen:** `ONLY_OPEN_LICENSE_MATERIALS` kontrolliert Materialdateien, ist kein vollständiger Rechtsnachweis für alle gespeicherten HTML-Texte. Vor Verbreitung den Lizenzstatus der Daten prüfen.

**Viewer:** Über Engine starten; vorhandener Viewer unterstützt `crawl.jsonl`, ältere zusätzliche Dateien sind optional.

**Sicherheit:** robots.txt wird berücksichtigt und der Crawl bleibt auf freigegebene Hosts beschränkt.
