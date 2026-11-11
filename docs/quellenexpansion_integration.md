# Integration – Abgrenzung zum bestehenden DidaDex

Der von dir gezeigte Dateibaum enthaelt `engine.py`, `engine_desktop.py`, `crawler/crawler.ipynb` und die Viewer. Da ihr **Inhalt** nicht als Datei vorliegt, ist ein sicheres 1:1-Ersetzen technisch nicht moeglich. Dieses Overlay veraendert keine der alten Dateien und schreibt nur nach `crawler/outputs/expansion/`. Damit ist ein direkter Copy-&-Paste-Einbau ohne Migrationsrisiko moeglich. Die alte GUI zeigt den neuen Crawl nicht automatisch an; das separat installierte `status_expansion.ps1` und `report.json` uebernehmen das Monitoring. Ein echtes Zusammenfuehren in denselben GUI-Run erfordert die Originaldateien `engine.py`, `engine_desktop.py` und `crawler/crawler.ipynb`.

## Konsistenz und parallel laufende Prozesse

- Bestehende Crawler-Instanz vor Start des neuen Prozesses stoppen; sonst Requests auf dieselben Hosts in Summe zu schnell.
- Die Erweiterung verwendet eigene SQLite und eigene JSONL; keine Schreibzugriffe auf den bisherigen Zustand.
- `--per-host 1`/`--host-delay 2.5` sind Sicherheitsgrenzen **innerhalb** dieser Erweiterung. Sie gelten nicht fuer einen zeitgleich laufenden alten Crawler.
- Keine Sicherheit gegen Systemausfall oder volle Festplatte. Regelmaessig Dateisicherungen machen und auf freien Speicher achten.
- PowerShell-Startskripte nach dem Kopieren vom Projektstamm aus starten.
