"""Deterministische Seeds: 250 Wikipedia-Lemmata plus geprüfte Portaleinstiege.
Wikipedia-Lemmata sind Kandidaten, nicht einzeln durch HTTP verifiziert; 404 werden protokolliert.
"""
from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import quote

TERMS = {
"Geschichtsunterricht": '''Altsteinzeit|Jungsteinzeit|Bronzezeit|Eisenzeit|Altes Ägypten|Römisches Reich|Römische Republik|Römische Kaiserzeit|Antikes Griechenland|Alexander der Große|Christianisierung|Frankenreich|Karl der Große|Lehnswesen|Grundherrschaft|Ständegesellschaft|Kreuzzug|Investiturstreit|Hanse|Heiliges Römisches Reich|Reformation|Martin Luther|Dreißigjähriger Krieg|Absolutismus|Aufklärung|Französische Revolution|Napoleon Bonaparte|Wiener Kongress|Vormärz|Deutsche Revolution 1848/1849|Industrielle Revolution|Soziale Frage|Deutsches Kaiserreich|Imperialismus|Kolonialismus|Erster Weltkrieg|Novemberrevolution|Weimarer Republik|Weltwirtschaftskrise|Nationalsozialismus|Holocaust|Zweiter Weltkrieg|Kalter Krieg|Deutsche Teilung|Deutsche Demokratische Republik|Berliner Mauer|Friedliche Revolution (DDR)|Deutsche Wiedervereinigung|Europäische Integration|Europäische Union''',
"Informatikunterricht": '''Algorithmus|Datenstruktur|Liste (Datenstruktur)|Stapel (Datenstruktur)|Warteschlange (Datenstruktur)|Binärbaum|Graph (Graphentheorie)|Sortierverfahren|Quicksort|Mergesort|Insertionsort|Suchalgorithmus|Binäre Suche|Rekursion|Komplexitätstheorie|Landau-Symbole|Endlicher Automat|Deterministischer endlicher Automat|Nichtdeterministischer endlicher Automat|Kellerautomat|Turingmaschine|Formale Sprache|Regulärer Ausdruck|Kontextfreie Grammatik|Datenbank|Relationale Datenbank|Entity-Relationship-Modell|SQL|Normalisierung (Datenbank)|Objektorientierte Programmierung|Vererbung (Programmierung)|Polymorphie (Programmierung)|Programmiersprache|Python (Programmiersprache)|Java (Programmiersprache)|Scratch (Programmiersprache)|Binärsystem|Boolesche Algebra|Logikgatter|Von-Neumann-Architektur|Betriebssystem|Rechnernetz|Internetprotokoll|Kryptographie|RSA-Kryptosystem|Datenschutz|Informationssicherheit|Künstliche Intelligenz|Maschinelles Lernen|Neuronales Netz''',
"Pädagogik": '''Pädagogik|Erziehungswissenschaft|Bildung|Erziehung|Sozialisation|Didaktik|Allgemeine Didaktik|Unterricht|Unterrichtsplanung|Lehrplan|Curriculum|Kompetenz (Pädagogik)|Kompetenzorientierung|Lernziel|Lernprozess|Konstruktivismus (Lernpsychologie)|Lerntheorie|Behaviorismus|Kognitivismus|Lernen am Modell|Motivation|Selbstbestimmungstheorie|Selbstreguliertes Lernen|Metakognition|Lernstrategie|Binnendifferenzierung|Inklusion (Pädagogik)|Sonderpädagogik|Diagnostik (Pädagogik)|Leistungsbewertung|Feedback|Formative Beurteilung|Klassenführung|Kooperatives Lernen|Projektunterricht|Problemorientiertes Lernen|Entdeckendes Lernen|Handlungsorientierter Unterricht|Offener Unterricht|Lernen durch Lehren|Flipped Classroom|Blended Learning|Mediendidaktik|Medienpädagogik|Bildung für nachhaltige Entwicklung|Interkulturelle Pädagogik|Reformpädagogik|Montessoripädagogik|John Dewey|Wolfgang Klafki''',
"Geschichtsdidaktik": '''Geschichtsdidaktik|Geschichtsbewusstsein|Geschichtskultur|Geschichtsunterricht|Historisches Lernen|Historisches Denken|Historische Kompetenz|Quellenkritik|Historische Quelle|Geschichtsschreibung|Historiographie|Public History|Erinnerungskultur|Kollektives Gedächtnis|Geschichtspolitik|Zeitzeuge|Zeitzeugenschaft|Oral History|Bildquelle|Karikatur|Historische Karte|Geschichtsatlas|Geschichtsmuseum|Museumspädagogik|Gedenkstättenpädagogik|Holocaust Education|Politische Bildung|Demokratiebildung|Urteilsbildung|Multiperspektivität|Kontroversität|Beutelsbacher Konsens|Narrativität|Historische Erzählung|Periodisierung|Chronologie|Geschichtstheorie|Alltagsgeschichte|Sozialgeschichte|Mentalitätsgeschichte|Geschlechtergeschichte|Globalgeschichte|Regionalgeschichte|Lokalgeschichte|Mikrogeschichte|Digital History|Digital Humanities|Geschichtsrevisionismus|Historische Erinnerung|Archäologie''',
"Informatikdidaktik": '''Didaktik der Informatik|Informatik|Informatikunterricht|Informatische Bildung|Medienbildung|Digitale Bildung|Medienkompetenz|Digitale Kompetenz|Computational Thinking|Problemorientierung|Problemlösen|Modellbildung|Modellierung|Abstraktion (Informatik)|Algorithmisches Denken|Programmierunterricht|Programmieren|Visuelle Programmiersprache|Blockbasierte Programmierung|CS Unplugged|Maker Education|Physical Computing|Mikrocontroller|Calliope mini|micro:bit|Arduino|Robotik|Lernsoftware|Lernplattform|Learning Management System|E-Learning|Gamification|Serious Game|Lernspiel|Simulation|Digitale Lernumgebung|Intelligentes tutorielles System|Automatisierte Bewertung|E-Assessment|Künstliche Intelligenz in der Bildung|KI-Kompetenz|Datenkompetenz|Data Literacy|Information Literacy|Informationskompetenz|Cybermobbing|Netzpolitik|Digitale Ethik|Urheberrecht|Open Educational Resources'''
}

# 'families' sind in einer Seeddatei bewusst getrennt: pro Host flexible Pfadgrenzen.
SITES = [
    ("bpb", "https://www.bpb.de/lernen/materialsuche/", "www.bpb.de", ["/lernen/", "/shop/materialien/"], 8),
    ("bpb", "https://www.bpb.de/shop/materialien/themenblaetter/", "www.bpb.de", ["/lernen/", "/shop/materialien/"], 8),
    ("bpb", "https://www.bpb.de/shop/materialien/thema-im-unterricht/", "www.bpb.de", ["/lernen/", "/shop/materialien/"], 8),
    ("bpb", "https://www.bpb.de/shop/materialien/themen-und-materialien/", "www.bpb.de", ["/lernen/", "/shop/materialien/"], 8),
    ("bpb", "https://www.bpb.de/lernen/angebote/", "www.bpb.de", ["/lernen/", "/shop/materialien/"], 8),
    ("zum", "https://unterrichten.zum.de/wiki/Kategorie:Unterrichtsidee", "unterrichten.zum.de", ["/wiki/", "/index.php"], 6),
    ("zum", "https://unterrichten.zum.de/wiki/Kategorie:Methode", "unterrichten.zum.de", ["/wiki/", "/index.php"], 6),
    ("zum", "https://unterrichten.zum.de/wiki/Kategorie:Lernpfad", "unterrichten.zum.de", ["/wiki/", "/index.php"], 6),
    ("zum", "https://unterrichten.zum.de/wiki/Informatik/Unterrichtsideen", "unterrichten.zum.de", ["/wiki/", "/index.php"], 6),
    ("zum", "https://unterrichten.zum.de/wiki/Geschichte", "unterrichten.zum.de", ["/wiki/", "/index.php"], 6),
    ("zum_deutsch", "https://deutsch-lernen.zum.de/wiki/Kategorie:Methoden", "deutsch-lernen.zum.de", ["/wiki/", "/index.php"], 5),
    ("segu", "https://segu-geschichte.de/lernmodule/", "segu-geschichte.de", ["/"], 5),
    ("segu", "https://segu-geschichte.de/arbeitsblaetter/", "segu-geschichte.de", ["/"], 5),
    ("segu", "https://segu-geschichte.de/informationen-lehrer/", "segu-geschichte.de", ["/"], 3),
    ("inf_schule", "https://inf-schule.de/", "inf-schule.de", ["/"], 9),
    ("inf_schule", "https://inf-schule.de/algorithmen", "inf-schule.de", ["/"], 9),
    ("inf_schule", "https://inf-schule.de/automatensprachen", "inf-schule.de", ["/"], 9),
    ("lfb_bw", "https://lehrerfortbildung-bw.de/u_matnatech/informatik/gym/bp2016/fb2/", "lehrerfortbildung-bw.de", ["/u_matnatech/"], 7),
    ("lfb_bw", "https://lehrerfortbildung-bw.de/u_matnatech/imp/gym/bp2016/fb1/", "lehrerfortbildung-bw.de", ["/u_matnatech/"], 7),
    ("lfb_bw", "https://lehrerfortbildung-bw.de/u_matnatech/imp/gym/bp2016/fb2/", "lehrerfortbildung-bw.de", ["/u_matnatech/"], 7),
    ("lfb_bw", "https://lehrerfortbildung-bw.de/u_matnatech/informatik/gym/bp2016/", "lehrerfortbildung-bw.de", ["/u_matnatech/"], 7),
    ("bebb", "https://bildungsserver.berlin-brandenburg.de/unterricht/faecher/mathematik-naturwissenschaften/informatik/unterrichtsmaterialien-und-fachthemen", "bildungsserver.berlin-brandenburg.de", ["/"], 7),
    ("bebb", "https://bildungsserver.berlin-brandenburg.de/material-inf/", "bildungsserver.berlin-brandenburg.de", ["/"], 7),
    ("bebb", "https://bildungsserver.berlin-brandenburg.de/unterricht/faecher/gesellschaftswissenschaften/geschichte/didaktik-1", "bildungsserver.berlin-brandenburg.de", ["/"], 7),
    ("bebb", "https://bildungsserver.berlin-brandenburg.de/inf-mat-jahre", "bildungsserver.berlin-brandenburg.de", ["/"], 7),
    ("serlo", "https://de.serlo.org/informatik", "de.serlo.org", ["/informatik", "/geschichte", "/community"], 5),
    ("digital_learning_lab", "https://digitallearninglab.de/unterrichtsbausteine", "digitallearninglab.de", ["/unterrichtsbausteine", "/materialien"], 6),
    ("klicksafe", "https://www.klicksafe.de/materialien", "www.klicksafe.de", ["/materialien", "/themen"], 5),
    ("medien_schule", "https://www.medien-in-die-schule.de/unterrichtseinheiten", "www.medien-in-die-schule.de", ["/unterrichtseinheiten", "/downloads"], 6),
    ("umwelt", "https://www.umwelt-im-unterricht.de/unterrichtsvorschlaege", "www.umwelt-im-unterricht.de", ["/unterrichtsvorschlaege", "/materialien"], 7),
    ("umwelt", "https://www.umwelt-im-unterricht.de/materialien", "www.umwelt-im-unterricht.de", ["/unterrichtsvorschlaege", "/materialien"], 7),
    ("lehrer_online", "https://www.lehrer-online.de/unterricht/", "www.lehrer-online.de", ["/unterricht/"], 5),
    ("zum_anderes", "https://www.wirlernenonline.de/oer/", "www.wirlernenonline.de", ["/oer/", "/fachportale/"], 3),
    ("ph_community", "https://www.e-teaching.org/didaktik", "www.e-teaching.org", ["/didaktik", "/technik", "/praxis"], 3),
    ("bildung_rlp", "https://bildung.rlp.de/unterricht/faecher", "bildung.rlp.de", ["/unterricht/"], 4),
    ("bildung_hessen", "https://lernarchiv.bildung.hessen.de/", "lernarchiv.bildung.hessen.de", ["/"], 4),
    ("schule_bw_geschichte", "https://www.schule-bw.de/faecher-und-schularten/gesellschaftswissenschaftliche-und-philosophische-faecher/geschichte/unterricht/index.html", "www.schule-bw.de", ["/faecher-und-schularten/gesellschaftswissenschaftliche-und-philosophische-faecher/geschichte/"], 9),
    ("schule_bw_geschichte", "https://www.schule-bw.de/faecher-und-schularten/gesellschaftswissenschaftliche-und-philosophische-faecher/geschichte/unterrichtsmaterialien/index.html", "www.schule-bw.de", ["/faecher-und-schularten/gesellschaftswissenschaftliche-und-philosophische-faecher/geschichte/"], 9),
    ("schule_bw_geschichte", "https://www.schule-bw.de/faecher-und-schularten/gesellschaftswissenschaftliche-und-philosophische-faecher/geschichte/unterrichtsmaterialien/methodische-zugaenge", "www.schule-bw.de", ["/faecher-und-schularten/gesellschaftswissenschaftliche-und-philosophische-faecher/geschichte/"], 9),
]

def make_seeds():
    rows=[]
    for name,url,host,paths,priority in SITES:
        rows.append(dict(url=url,group=name,host=host,allow_paths=paths,priority=priority,max_depth=7 if name not in ('bpb','lfb_bw') else 6,license=("CC BY-SA 4.0 (segu; Material einzeln prüfen)" if name=='segu' else "check_at_source"),source_kind="education"))
    for category,s in TERMS.items():
        titles=[x.strip() for x in s.split('|') if x.strip()]
        assert len(titles)==50,(category,len(titles))
        for title in titles:
            url="https://de.wikipedia.org/wiki/"+quote(title.replace(' ','_'), safe="()_-,:/")
            rows.append(dict(url=url,group="wikipedia_"+category.lower().replace('ä','ae'),host="de.wikipedia.org",allow_paths=["/wiki/"],priority=3,max_depth=0,source_kind="reference",license="CC BY-SA (Attribution erforderlich)",lemma=title,discipline=category))
    assert len(set(r['url'] for r in rows if r['source_kind']=='reference'))==250, "Wikipedia: doppelte Lemmata"
    log_seeds=Path(__file__).with_name('log_derived_seeds.json')
    if log_seeds.exists():
        existing={r['url'] for r in rows}
        for item in json.loads(log_seeds.read_text(encoding='utf-8')):
            if item['url'] not in existing:
                rows.append(item);existing.add(item['url'])
    return rows

if __name__=='__main__':
    out=Path(__file__).with_name('seeds.json')
    rows=make_seeds()
    out.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"{out}: {len(rows)} Seeds; 250 Wikipedia (5x50)")
