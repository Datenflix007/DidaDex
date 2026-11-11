"""Didaktisch-methodischer Crawl-Viewer mit Seitenranking.
Start: python -m streamlit run material_viewer_ranked.py -- --root outputs/runs
Installation: python -m pip install streamlit pandas
"""
import argparse
import html
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit, parse_qsl, urlencode

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Didaktischer Materialviewer", page_icon="📚", layout="wide")

@st.cache_data(show_spinner=False)
def read_jsonl(path, mtime, max_rows=200_000):
    rows = []
    try:
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    try:
                        item = json.loads(line)
                        if isinstance(item, dict):
                            rows.append(item)
                    except json.JSONDecodeError:
                        pass
                if len(rows) >= max_rows:
                    break
    except OSError:
        pass
    return rows

@st.cache_data(show_spinner=False)
def read_json(path, mtime):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

def jsonl(folder, name):
    path = folder / name
    return read_jsonl(str(path), path.stat().st_mtime_ns) if path.is_file() else []

def metadata_json(folder, name):
    path = folder / name
    return read_json(str(path), path.stat().st_mtime_ns) if path.is_file() else {}

def runs_in(root):
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir() and any(
        (p / f).is_file() for f in ("crawl.jsonl", "search_documents.jsonl", "run_info.json")
    )), reverse=True)

def normalize_url(url):
    try:
        parts = urlsplit(str(url or ""))
        if not parts.netloc:
            return str(url or "")
        # Relevante Parameter erhalten; Trackingparameter entfernen.
        ignored = {"fbclid", "gclid", "utm_source", "utm_medium", "utm_campaign"}
        query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query)
                                 if k.casefold() not in ignored))
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                           unquote(parts.path).rstrip("/"), query, ""))
    except ValueError:
        return str(url or "")

def extracted_text(doc):
    for key in ("search_text", "main_text", "text", "text_excerpt", "content"):
        content = doc.get(key)
        if isinstance(content, str) and content.strip():
            return content
    return ""

def fields_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(fields_text(x) for x in value)
    if isinstance(value, dict):
        return " ".join(fields_text(x) for x in value.values())
    return ""

# Konservative Klassifikation: allgemeine Begriffs-Erwähnungen sind KEIN Materialnachweis.
BAD_PATHS = re.compile(
    r"(?:^|/)(?:impressum|datenschutz|privacy|privacy-policy|cookie-policy|"
    r"nutzungsbedingungen|kontakt|login|register|anmelden|registrieren|"
    r"account|profil|profile|user|benutzer|spezial:|special:|"
    r"hilfe:|help:|diskussion:|talk:|code_of_conduct|code-of-conduct)(?:$|/)", re.I)
BAD_TITLES = re.compile(r"^(?:datenschutz|datenschutzerklärung|impressum|privacy|"
                        r"kontakt|nutzungsbedingungen|code of conduct)(?:\s*[-–|].*)?$", re.I)
NAV_TITLES = re.compile(r"^(?:unterrichtsideen|methoden?|kategorien?|"
                        r"startseite|hauptseite|oer|materialien|übersicht)(?:\s*[-–|].*)?$", re.I)
TASK = re.compile(r"(?:^|[.!?\n]\s*)(?:aufgabe\s*\d*\s*[:.]\s*)?"
                  r"(?:erstellt?|beschreibt?|erklärt?|diskutiert?|analysiert?|"
                  r"vergleicht?|ordnet?|bearbeitet?|modelliert?|programmiert?|"
                  r"berechnet?|untersucht?|begründet?|recherchiert?|"
                  r"zeichnet?|entwickelt?|arbeitet?|lesen\s+sie|"
                  r"lies|nenne|nennt|schreibe|schreibt|markiert?)\b", re.I)
PHASE = re.compile(r"\b(?:einstieg|erarbeitung|sicherung|reflexion|"
                   r"unterrichtsphase|stundenverlauf|verlaufsplan)\b", re.I)
METHOD = re.compile(r"\b(?:gruppenarbeit|partnerarbeit|einzelarbeit|plenum|"
                    r"stationenlernen|rollenspiel|think.pair.share|"
                    r"methode|sozialform|methodische hinweise)\b", re.I)
OBJECTIVE = re.compile(r"\b(?:lernziel(?:e)?|kompetenz(?:en)?|"
                       r"die schülerinnen und schüler können|die lernenden können)\b", re.I)
SOLUTION = re.compile(r"\b(?:musterlösung|erwartungshorizont|"
                      r"lösungshinweise|lösungsblatt)\b", re.I)
TEACHING_FILE = re.compile(r"\.(?:pdf|docx?|pptx?|odt|odp|ods|ipynb|py|"
                           r"h5p|sb3|md)(?:$|[?#])", re.I)
FILE_TYPES = {"pdf", "doc", "docx", "ppt", "pptx", "odt", "odp", "ipynb", "py", "h5p"}

def evaluate(doc, has_index=False, has_download=False):
    url = str(doc.get("url") or doc.get("source_page") or "")
    parsed = urlsplit(url)
    path = unquote(parsed.path).casefold()
    query = dict(parse_qsl(parsed.query))
    title = str(doc.get("title") or "").strip()
    text = extracted_text(doc)
    head = fields_text(doc.get("headings") or [])
    first = text[:35_000]
    links = doc.get("material_links") or []
    if not isinstance(links, list):
        links = []
    mime = str(doc.get("content_type") or doc.get("mime_type") or "")
    doc_type = str(doc.get("document_type") or doc.get("page_type") or "").casefold()
    reasons = []

    if (BAD_PATHS.search(path) or BAD_TITLES.match(title)
            or re.search(r"(?:^|/)[^/]*:(?:datenschutz|impressum|privacy)(?:$|/)", path, re.I)
            or re.search(r"(?:^|[^\w])(?:datenschutz|datenschutzerklärung|impressum)\s*[-–]\s*zum-unterrichten$", title, re.I)
            or query.get("action", "").lower() in {"edit", "history", "info", "delete"}
            or re.search(r"(?:^|/)(?:spezial:|special:|benutzer:|diskussion:)", path, re.I)):
        return {"score": 0, "class": "Unbrauchbar", "why": ["Verwaltungs-, Datenschutz- oder technische Seite"],
                "signals": {}, "excluded": True}

    score = 0
    signals = {
        "Konkreter Arbeitsauftrag": bool(TASK.search(first)),
        "Unterrichtsablauf / Phase": bool(PHASE.search(first)),
        "Methodische Hinweise": bool(METHOD.search(first)),
        "Lernziele / Kompetenzen": bool(OBJECTIVE.search(first)),
        "Lösungen / Erwartungshorizont": bool(SOLUTION.search(first)),
        "Strukturierte Überschriften": bool(head.strip()),
        "Materiallinks": bool(links),
        "Datei mit Materialformat": bool(TEACHING_FILE.search(url) or any(x in mime.lower() for x in ("pdf", "presentation", "wordprocessing"))
                                     or doc_type in FILE_TYPES),
        "Im Suchindex": has_index,
        "Datei heruntergeladen": has_download,
    }
    for name, weight in (("Konkreter Arbeitsauftrag", 4), ("Unterrichtsablauf / Phase", 2),
                         ("Methodische Hinweise", 1), ("Lernziele / Kompetenzen", 1),
                         ("Lösungen / Erwartungshorizont", 2), ("Materiallinks", 2),
                         ("Datei mit Materialformat", 4), ("Datei heruntergeladen", 3)):
        if signals[name]:
            score += weight
            reasons.append(name)
    if len(first.strip()) >= 350 and signals["Konkreter Arbeitsauftrag"]:
        score += 2
        reasons.append("Arbeitsauftrag in längerem Inhalt")
    if signals["Strukturierte Überschriften"] and score > 0:
        score += 1
    if NAV_TITLES.match(title) or doc_type in {"landingpage", "index", "category", "overview", "navigation"}:
        score -= 6
        reasons.append("Wahrscheinlich Navigations- oder Übersichtsseite")
    if re.search(r"\b(?:inhalt[s]?verzeichnis|alle kategorien|letzte änderungen|"
                 r"seiten in der kategorie)\b", first[:2000], re.I):
        score -= 3
        reasons.append("Hinweise auf Navigationsinhalt")
    # Hoher Score ist noch kein Beweis: Nur Unterrichtshandlung oder echte Materialdatei.
    has_core = signals["Konkreter Arbeitsauftrag"] or signals["Datei mit Materialformat"] or has_download
    if has_core and score >= 6:
        group = "Unterrichtsmaterial"
    elif score <= 1 or (not has_core and score <= 3):
        group = "Unbrauchbar"
    else:
        group = "Prüfen"
    return {"score": max(0, score), "class": group, "why": reasons or ["Keine belastbaren Materialsignale"],
            "signals": signals, "excluded": False}

def build_items(raw, docs, assets):
    # Alle Rohseiten erhalten; indexierte Dokumente derselben URL werden zugeordnet.
    by_url = {}
    for doc in docs:
        by_url.setdefault(normalize_url(doc.get("url")), []).append(doc)
    asset_urls = {normalize_url(a.get("url") or a.get("source_url")) for a in assets
                  if a.get("local_file") or a.get("downloaded")}
    result = []
    seen_urls = set()
    for i, page in enumerate(raw):
        key = normalize_url(page.get("url"))
        seen_urls.add(key)
        matching = by_url.get(key, [])
        combined = dict(page)
        if matching:
            # Ergänzen, aber Rohfelder nicht überschreiben; längeren extrahierten Text vorziehen.
            for k, v in matching[0].items():
                if not combined.get(k):
                    combined[k] = v
            if len(extracted_text(matching[0])) > len(extracted_text(page)):
                combined["search_text"] = extracted_text(matching[0])
        rank = evaluate(combined, bool(matching), key in asset_urls or bool(combined.get("local_file")))
        result.append({"id": f"raw-{i}", "doc": combined, "source": "Rohcrawl", "rank": rank})
    for i, doc in enumerate(docs):
        key = normalize_url(doc.get("url"))
        if key not in seen_urls:
            rank = evaluate(doc, True, key in asset_urls or bool(doc.get("local_file")))
            result.append({"id": f"index-{i}", "doc": doc, "source": "Nur Suchindex", "rank": rank})
    return sorted(result, key=lambda x: (-x["rank"]["score"], x["doc"].get("title") or ""))


# Laufbezogene, dauerhafte manuelle Labels (nicht in Crawl-Rohdaten schreiben).
LABEL_FILE = "manual_labels.json"
CLASSES = ["Unterrichtsmaterial", "Prüfen", "Unbrauchbar"]


def load_labels(run):
    path = run / LABEL_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_labels(run, labels):
    """Atomisch schreiben, damit ein Streamlit-Rerun keine halbe Datei hinterlässt."""
    target = run / LABEL_FILE
    fd, tmp = tempfile.mkstemp(prefix=".manual_labels_", suffix=".json", dir=str(run))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(labels, stream, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def apply_labels(items, labels):
    """Score bleibt als Heuristik erhalten; manuelle Kategorie hat Vorrang."""
    for item in items:
        auto = item["rank"]
        item["auto_class"] = auto["class"]
        label = labels.get(item["id"])
        item["manual_label"] = label if isinstance(label, dict) and label.get("category") in CLASSES else None
        if item["manual_label"]:
            item["rank"] = dict(auto, **{"class": item["manual_label"]["category"]})
    return items


def manual_editor(item, run, labels, context="all"):
    st.markdown("#### Manuelle Einstufung")
    existing = item.get("manual_label") or {}
    original = item.get("auto_class", item["rank"]["class"])
    st.caption(f"Automatischer Vorschlag: {original} · Manuelle Einstufung überschreibt nur die Kategorie, nicht den Score.")
    with st.form(key=f"label_form_{context}_{run.name}_{item['id']}"):
        choice = st.radio("Kategorie", CLASSES,
                          index=CLASSES.index(existing.get("category", original)), horizontal=True)
        note = st.text_area("Begründung / Kommentar (optional)",
                            value=existing.get("note", ""),
                            placeholder="z. B. echte Arbeitsaufträge vorhanden oder nur eine Linkliste",
                            height=85)
        col1, col2 = st.columns(2)
        save = col1.form_submit_button("Bewertung speichern", type="primary", use_container_width=True)
        clear = col2.form_submit_button("Manuelle Bewertung entfernen", use_container_width=True,
                                        disabled=not bool(existing))
    if save:
        labels[item["id"]] = {
            "category": choice, "note": note.strip(),
            "title": item["doc"].get("title"), "url": item["doc"].get("url"),
            "source": item["source"],
            "automated_category": original,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        save_labels(run, labels)
        st.rerun()
    if clear:
        labels.pop(item["id"], None)
        save_labels(run, labels)
        st.rerun()
    if existing:
        st.caption("Bereits manuell gespeichert" + (f": {existing.get('updated_at_utc')}" if existing.get('updated_at_utc') else ""))

def safe_path(value, run):
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    candidates = [path] if path.is_absolute() else [run / path, Path.cwd() / path]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(run.resolve())
            if resolved.is_file():
                return resolved
        except (OSError, ValueError):
            continue
    return None

def render_details(item, run, labels, context="all"):
    doc, rank = item["doc"], item["rank"]
    title = str(doc.get("title") or "(ohne Titel)")
    st.subheader(title)
    color = {"Unterrichtsmaterial": "#fff0ae", "Unbrauchbar": "#e4e4e4", "Prüfen": "#dceafa"}[rank["class"]]
    st.markdown(f'<div style="padding:12px;border-radius:8px;background:{color};color:#222">'
                f'<b>{html.escape(rank["class"])}</b> · Ranking {rank["score"]} Punkte · '
                f'{html.escape(item["source"])}</div>', unsafe_allow_html=True)
    st.caption("Heuristische Einschätzung – kein Nachweis didaktischer Qualität. Manuelle Korrekturen haben Vorrang.")
    manual_editor(item, run, labels, context)
    url = str(doc.get("url") or "")
    if urlsplit(url).scheme in ("https", "http"):
        st.link_button("Originalquelle öffnen", url)
    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### Einzelne gecrawlte Seite – lesbarer Inhalt")
        text = extracted_text(doc)
        if text:
            st.components.v1.html(
                '<article style="font:15px/1.65 system-ui;color:#222;background:#fff;'
                'white-space:pre-wrap;overflow-wrap:anywhere;padding:16px">'
                + html.escape(text[:250_000]) + '</article>', height=570, scrolling=True)
            st.caption(f"{len(text):,} Zeichen; Vorschau maximal 250.000 Zeichen")
        else:
            st.info("Kein extrahierter Haupttext vorhanden.")
        local = safe_path(doc.get("local_file"), run)
        if local:
            st.download_button("Lokale Materialdatei herunterladen", local.read_bytes(), file_name=local.name)
    with right:
        st.markdown("#### Warum diese Einstufung?")
        for reason in rank["why"]:
            st.write("• " + reason)
        st.markdown("#### Didaktische Merkmale")
        for label, present in rank["signals"].items():
            st.write(("✓ " if present else "— ") + label)
        st.markdown("#### Erfasste Metadaten")
        st.json(doc.get("metadata") or {}, expanded=False)
        st.markdown("#### Didaktische Kategorien")
        st.json(doc.get("didactic_categories") or {}, expanded=False)
        st.markdown("#### Materialverweise")
        st.json(doc.get("material_links") or [], expanded=False)
        with st.expander("Vollständigen Rohdatensatz anzeigen"):
            st.json(doc)

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--root", default="outputs/runs")
options, _ = parser.parse_known_args()

st.title("Didaktisch-methodischer Materialviewer")
st.caption("Alle erfassten Webseiten einzeln prüfen, nach Materialrelevanz ranken und mit dem Suchindex vergleichen.")
with st.sidebar:
    st.header("Suchläufe")
    root = Path(st.text_input("Crawl-Verzeichnis", str(Path(options.root).expanduser()))).expanduser()
    runs = runs_in(root)
    if not runs:
        st.warning("Keine Laufordner gefunden. Erwartet: outputs/runs/<Zeitstempel>/crawl.jsonl")
        st.stop()
    chosen = st.selectbox("Suchlauf auswählen", runs, format_func=lambda p: p.name)
    st.caption(f"{len(runs)} Suchläufe")
    st.code(str(chosen.resolve()), language=None)

info = metadata_json(chosen, "run_info.json")
report = metadata_json(chosen, "corpus_size_report.json")
quality = metadata_json(chosen, "quality_report.json")
raw = jsonl(chosen, "crawl.jsonl")
docs = jsonl(chosen, "search_documents.jsonl")
assets = jsonl(chosen, "material_manifest.jsonl")
labels = load_labels(chosen)
items = apply_labels(build_items(raw, docs, assets), labels)
counts = Counter(x["rank"]["class"] for x in items)

st.subheader(f"Suchlauf {chosen.name}")
st.caption(f"Start: {info.get('start_utc', 'unbekannt')} · Profil: {info.get('profile', 'unbekannt')} · Status: {info.get('status', 'unbekannt')}")
for col, (label, value) in zip(st.columns(6), [
    ("Rohseiten", len(raw)), ("Indexdokumente", len(docs)),
    ("Dateimanifest", len(assets)), ("Gelb: Materialien", counts["Unterrichtsmaterial"]),
    ("Grau: irrelevant", counts["Unbrauchbar"]), ("Zu prüfen", counts["Prüfen"]) ]):
    col.metric(label, value)

st.markdown('<span style="background:#fff0ae;color:#222;padding:5px 10px;border-radius:5px">Gelb = wahrscheinlich Material</span> '
            '<span style="background:#e4e4e4;color:#222;padding:5px 10px;border-radius:5px">Grau = irrelevant</span> '
            '<span style="background:#dceafa;color:#222;padding:5px 10px;border-radius:5px">Blau = manuell prüfen</span>',
            unsafe_allow_html=True)

t1, t2, t3, t4 = st.tabs(["Alle Seiten & Ranking", "Suchindex-Materialien", "Didaktische Analyse", "Laufmetadaten"])
with t1:
    st.markdown("### Alle gecrawlten Seiten – mit Ranking")
    st.caption("Die Tabelle umfasst alle Zeilen aus crawl.jsonl plus Suchindexeinträge, deren URL im Rohcrawl fehlt. Gleiche URLs aus dem Rohcrawl werden nicht zusammengelegt.")
    c1, c2, c3 = st.columns([2, 1, 1])
    query = c1.text_input("Suchen", placeholder="Titel, URL, Inhalt", key="all_search")
    state = c2.selectbox("Bewertung", ["Alle", "Unterrichtsmaterial", "Prüfen", "Unbrauchbar"])
    order = c3.selectbox("Sortieren", ["Score absteigend", "Score aufsteigend", "Titel"])
    shown = [x for x in items if (state == "Alle" or x["rank"]["class"] == state)
             and (not query or query.casefold() in
                  (str(x["doc"].get("title") or "") + " " + str(x["doc"].get("url") or "")
                   + " " + extracted_text(x["doc"])).casefold())]
    if order == "Score aufsteigend":
        shown.sort(key=lambda x: x["rank"]["score"])
    elif order == "Titel":
        shown.sort(key=lambda x: str(x["doc"].get("title") or "").casefold())
    st.caption(f"{len(shown)} von {len(items)} Einträgen · {sum(bool(i.get('manual_label')) for i in items)} manuell bewertet")
    if shown:
        frame = pd.DataFrame([{
            "Rang": i + 1, "Bewertung": x["rank"]["class"],
            "Manuell": "Ja" if x.get("manual_label") else "",
            "Punkte": x["rank"]["score"],
            "Titel": x["doc"].get("title") or "(ohne Titel)",
            "Seitenart": x["doc"].get("page_type") or x["doc"].get("document_type") or "–",
            "Quelle": x["source"], "URL": x["doc"].get("url") or "",
        } for i, x in enumerate(shown)])

        def shade(row):
            bg = {"Unterrichtsmaterial": "#fff0ae", "Unbrauchbar": "#e4e4e4", "Prüfen": "#dceafa"}[row["Bewertung"]]
            return [f"background-color:{bg};color:#222" for _ in row]

        st.caption("**Zeile anklicken**, um direkt darunter die Seite und ihre manuelle Bewertung zu öffnen.")
        # Auswahl ist an den aktuell gefilterten DataFrame gekoppelt.
        event = st.dataframe(
            frame.style.apply(shade, axis=1),
            hide_index=True, use_container_width=True, height=450,
            on_select="rerun", selection_mode="single-row",
            key=f"rank_table_{chosen.name}",
        )
        selected_rows = event.selection.rows
        if selected_rows:
            selected = int(selected_rows[0])
            if 0 <= selected < len(shown):
                st.divider()
                st.markdown("### Ausgewählter Crawl-Datensatz")
                render_details(shown[selected], chosen, labels)
        else:
            st.info("Wähle eine beliebige Tabellenzeile aus, um ihren Inhalt und die manuelle Kategorisierung anzuzeigen.")
    else:
        st.info("Keine passenden Seiten gefunden.")

with t2:
    st.markdown("### Nur Datensätze des Suchindex")
    st.caption("Zeigt die tatsächlich exportierten Suchdokumente; zusätzlich bewertet durch die neue Viewer-Heuristik.")
    indexed = [x for x in items if x["source"] == "Nur Suchindex"
               or normalize_url(x["doc"].get("url")) in
               {normalize_url(d.get("url")) for d in docs}]
    if indexed:
        chosen_index = st.selectbox("Suchdokument", range(len(indexed)),
            format_func=lambda i: f"{indexed[i]['rank']['class']} · {indexed[i]['doc'].get('title') or '(ohne Titel)'}",
            key="indexed_selected")
        render_details(indexed[chosen_index], chosen, labels, context="index")
    else:
        st.info("Kein Suchindex für diesen Lauf vorhanden.")

with t3:
    st.markdown("### Materialrelevanz im gesamten Crawl")
    if labels:
        export_rows = [{"datensatz_id": key, **value} for key, value in labels.items() if isinstance(value, dict)]
        st.download_button("Manuelle Bewertungen als JSON exportieren",
                           data=json.dumps(export_rows, ensure_ascii=False, indent=2).encode("utf-8"),
                           file_name=f"labels_{chosen.name}.json", mime="application/json")
    st.bar_chart(pd.Series(counts).rename("Anzahl"))
    st.markdown("#### Didaktische Hinweise unter wahrscheinlich brauchbaren Treffern")
    useful = [x for x in items if x["rank"]["class"] == "Unterrichtsmaterial"]
    if useful:
        signals = Counter(label for x in useful for label, found in x["rank"]["signals"].items() if found)
        st.bar_chart(pd.Series(signals).rename("Seiten"))
    else:
        st.warning("Kein eindeutiger Unterrichtsmaterial-Kandidat. Prüfe die Rohseiten und Crawling-Regeln.")
    st.markdown("#### Wichtige Grenzen")
    st.write("Das Ranking erkennt Muster in Metadaten und Texten. Es prüft weder die pädagogische Eignung "
             "noch die Vollständigkeit eines Arbeitsblatts. Für belastbare Aussagen braucht ihr eine manuell "
             "bewertete Stichprobe. Eine Downloadfreigabe ist keine automatische Lizenzfreigabe.")
    if quality:
        with st.expander("Original-Qualitätsbericht des Crawlers"):
            st.json(quality)

with t4:
    st.markdown("### Laufdaten und Materialmanifest")
    st.json(info, expanded=False)
    st.json(report, expanded=False)
    if assets:
        st.dataframe(pd.DataFrame(assets), use_container_width=True)
    else:
        st.info("Kein Materialmanifest vorhanden oder keine Dateien erkannt.")
