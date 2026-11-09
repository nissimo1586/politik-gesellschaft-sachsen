"""Öffentlicher ICS-Kalender für politische Veranstaltungen in Sachsen."""
import hashlib
import html
import json
import logging
import re
import unicodedata
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from dateutil.parser import isoparse

ROOT = Path(__file__).resolve().parents[1]
ZONE = ZoneInfo("Europe/Berlin")
TODAY = datetime.now(ZONE).date()
CITIES = ("Chemnitz", "Leipzig", "Dresden", "Zwickau", "Glauchau", "Görlitz",
          "Freiberg", "Plauen", "Bautzen", "Zittau", "Meißen", "Pirna", "Riesa",
          "Delitzsch", "Grimma", "Mittweida", "Döbeln", "Torgau", "Kamenz",
          "Annaberg-Buchholz", "Radebeul", "Wurzen", "Markkleeberg", "Löbau",
          "Hoyerswerda", "Aue-Bad Schlema", "Schwarzenberg")
MONTHS = dict(zip(("januar februar märz april mai juni juli august september oktober "
                    "november dezember").split(), range(1, 13)))
DATE_DE = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(20\d{2})")
DATE_WORD = re.compile(r"(\d{1,2})\.?\s+(" + "|".join(MONTHS) + r")\s+(20\d{2})", re.I)
TIME = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
KEYWORDS = ("politik", "demokrati", "kritik", "vortrag", "diskussion", "lesung",
            "gesellschaft", "klima", "energie", "ökolog", "naturschutz", "verkehr",
            "mobilität", "feminism", "antifasch", "rassism", "migration", "sozial",
            "kapital", "gerecht", "erinnerung", "nationalsozial", "krieg",
            "frieden", "menschenrecht", "wohnen", "stadtentwick", "agrar",
            "umwelt", "podium", "wissenschaft", "wirtschaft", "protest",
            "vergesellschaft", "queer", "geschlecht", "kolonial", "ungleich")
LOG = logging.getLogger(__name__)

def clean(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()

def when(value):
    if not value: return None
    if isinstance(value, datetime): result = value
    else:
        try: result = isoparse(str(value))
        except (ValueError, TypeError): return None
    return result.replace(tzinfo=ZONE) if not result.tzinfo else result.astimezone(ZONE)

def find_city(location):
    for city in CITIES:
        if re.search(r"(?<!\w)" + re.escape(city) + r"(?!\w)", location, re.I):
            return city
    if re.search(r"\bonline\b", location, re.I): return "Online"
    return ""

def relevant(event):
    text = (event["title"] + " " + event.get("description", "")).casefold()
    if any(word in event["title"].casefold() for word in
           ("party", "stammtisch", "vorstandssitzung", "pflegeeinsatz", "diskothek")):
        return False
    if event.get("source_id") in ("daks", "rosalux", "weiterdenken"): return True
    return any(word in text for word in KEYWORDS)

def normalize(e):
    # Ein datumsloser oder nur tagesgenauer Schema.org-Wert ist KEINE Uhrzeit.
    raw_start = e.get("start")
    if isinstance(raw_start, str) and not re.search(r"(?:T|\s)\d{1,2}:\d{2}", raw_start):
        return None
    start = when(raw_start)
    if (start and start.hour == 0 and start.minute == 0 and
            e.get("source_id") in ("daks", "rosalux")):
        return None
    title = clean(e.get("title"))
    if not start or not title or not TODAY <= start.date() <= TODAY + timedelta(days=270):
        return None
    loc = clean(e.get("location"))
    city = clean(e.get("city")) or find_city(loc)
    if city not in CITIES and city != "Online":
        # Unknown Saxon towns allowed with Saxon postcodes, not arbitrary foreign cities.
        m = re.search(r"\b((?:01|02|04|08|09)\d{3})\s+([A-Za-zÄÖÜäöüß-]+)", loc)
        if not m: return None
        city = m.group(2)
    end = when(e.get("end"))
    if not end or end <= start: end = start + timedelta(hours=2)
    url = e.get("url", "")
    if url and urlparse(url).scheme not in ("https", "http"): return None
    return dict(source_id=e.get("source_id",""), title=title,
                start=start.isoformat(), end=end.isoformat(), location=loc,
                city=city, description=clean(e.get("description"))[:1200],
                url=url, status=e.get("status","CONFIRMED"))

def jsonld_events(soup, source_id, url):
    events = []
    def walk(node):
        if isinstance(node, list):
            for part in node: yield from walk(part)
        elif isinstance(node, dict):
            if "Event" in str(node.get("@type", "")): yield node
            for key in ("@graph", "mainEntity", "itemListElement"):
                if key in node: yield from walk(node[key])
    for script in soup.select('script[type="application/ld+json"]'):
        try: data=json.loads(script.string or script.get_text())
        except (ValueError, TypeError): continue
        for item in walk(data):
            loc=item.get("location","")
            if isinstance(loc,list): loc=loc[0] if loc else ""
            if isinstance(loc,dict):
                addr=loc.get("address","")
                if isinstance(addr,dict):
                    addr=" ".join(str(addr.get(k,"")) for k in
                                  ("streetAddress","postalCode","addressLocality"))
                loc=clean(str(loc.get("name",""))+" "+str(addr))
            events.append(dict(source_id=source_id,title=item.get("name",""),
                start=item.get("startDate"),end=item.get("endDate"),
                location=loc,description=BeautifulSoup(str(item.get("description","")),
                "html.parser").get_text(" ",strip=True),
                url=item.get("url") if isinstance(item.get("url"),str) else url,
                status="CANCELLED" if "Cancelled" in str(item.get("eventStatus",""))
                else "CONFIRMED"))
    return events

def parse_date(text):
    m=DATE_DE.search(text)
    if m:
        try: return date(int(m[3]),int(m[2]),int(m[1]))
        except ValueError: return None
    m=DATE_WORD.search(text)
    if m:
        try: return date(int(m[3]),MONTHS[m[2].lower()],int(m[1]))
        except ValueError: return None
    return None

def detail_events(soup, source_id, url):
    """Liest Datum/Uhrzeit vom Veranstalter statt datumsloser JSON-LD-Angaben."""
    lines = [clean(s) for s in soup.stripped_strings]
    heading = clean(soup.h1.get_text(" ", strip=True)) if soup.h1 else ""
    def section(label, stop):
        for i, s in enumerate(lines):
            if s.casefold() == label.casefold():
                result = []
                for part in lines[i + 1:]:
                    if part.casefold() in stop: break
                    result.append(part)
                    if len(result) >= 10: break
                return " ".join(result)
        return ""

    if source_id == "rosalux":
        loc = section("Veranstaltungsort",
                      {"zeit", "beschreibung", "themenbereiche"})
        raw = section("Zeit",
                      {"beschreibung", "themenbereiche", "zugeordnete dateien"})
        title = re.sub(r"^.*?20\d{2}\s*:\s*", "", heading)
        title = re.sub(r"^(?:abgesagt\s*:\s*)?", "", title, flags=re.I)
        title = re.sub(r"^[^:]{1,45}:\s*", "", title).strip()
        description = section("Beschreibung",
                     {"ort", "kontakt", "ähnliche veranstaltungen", "weitere informationen"})[:750]
    elif source_id == "daks":
        loc = section("Ort", {"ort 2", "kategorie", "referent*in", "anmelden", "labels"})
        if not loc:
            loc = section("Standort", {"standort 2", "kategorie", "referent*in", "labels"})
        raw = section("Datum", {"uhrzeit", "ort", "standort", "kategorie"})
        raw += " " + section("Uhrzeit",
                       {"ort", "ort 2", "standort", "kategorie", "labels"})
        title = heading
        article = soup.find("article") or soup.find("main")
        paragraphs = [clean(p.get_text(" ", strip=True)) for p in article.find_all("p")] if article else []
        description = " ".join(p for p in paragraphs if len(p) >= 45)[:750]
        # Viele DAKS-Detailseiten nennen die Stadt sichtbar, aber die Straße nur in JSON-LD.
        address = jsonld_events(soup, source_id, url)
        for structured in address:
            full = clean(structured.get("location"))
            if len(full) > len(loc) and find_city(full) == find_city(loc):
                loc = full
                break
    else:
        return []
    day = parse_date(raw) or parse_date(heading)
    times = TIME.findall(raw)
    if not day or not times or not loc or not find_city(loc):
        return []
    start = datetime(day.year, day.month, day.day, *map(int, times[0]), tzinfo=ZONE)
    end = (datetime(day.year, day.month, day.day, *map(int, times[1]), tzinfo=ZONE)
           if len(times) > 1 else start + timedelta(hours=2))
    if end <= start: end = start + timedelta(hours=2)
    excerpt = (heading + " " + description[:220]).casefold()
    cancelled = ("abgesagt" in heading.casefold() or
                 "leider müssen wir die veranstaltung" in excerpt or
                 "veranstaltung fällt aus" in excerpt)
    return [dict(source_id=source_id, title=title, start=start, end=end,
                 location=loc, description=description,
                 url=url, status="CANCELLED" if cancelled else "CONFIRMED")]

def fetch(url):
    try:
        r=requests.get(url,timeout=16,headers={"User-Agent":"PolitikGesellschaftSachsen/0.2 (public events)"})
        r.raise_for_status()
        if len(r.content)>2_000_000: return None
        return BeautifulSoup(r.text,"html.parser")
    except requests.RequestException as ex:
        LOG.warning("Quelle nicht erreichbar %s: %s",url,ex)
        return None

def source_events(src):
    if src["adapter"] == "manual":
        return None, "nur manuelle Erfassung"
    page = fetch(src["url"])
    if page is None:
        return None, "Abruf fehlgeschlagen"
    found = jsonld_events(page, src["id"], src["url"])
    detail_links = []
    for a in page.select("a[href]"):
        u = urljoin(src["url"], a["href"])
        host = urlparse(u).hostname or ""
        path = urlparse(u).path
        if (src["id"] == "rosalux" and host.endswith("rosalux.de") and
                "/veranstaltung/es_detail/" in path) or (
                src["id"] == "daks" and host.endswith("daks-sachsen.de") and
                "/event/" in path):
            if u not in detail_links:
                detail_links.append(u)
    for u in detail_links[:70]:
        detail = fetch(u)
        if detail is None:
            continue
        # Bei DAKS sind JSON-LD-Zeiten teilweise nur Tageswerte;
        # die sichtbaren Detailangaben haben daher Vorrang.
        parsed = detail_events(detail, src["id"], u)
        found.extend(parsed if parsed else jsonld_events(detail, src["id"], u))
    verified = [event for e in found
                if (event := normalize(e)) and relevant(event)]
    if not verified:
        return None, "keine validierten Termine"
    return verified, f"{len(verified)} validierte Termine"

def identity(e):
    key=e["url"].split("?")[0] or "|".join((e["title"],e["start"][:10],e["city"]))
    return hashlib.sha256(key.encode()).hexdigest()[:24]+"@politik-gesellschaft-sachsen"

def dedupe(events):
    output={}
    for e in events:
        e=normalize(e)
        if not e or not relevant(e): continue
        title=unicodedata.normalize("NFKD",e["title"].casefold()).encode("ascii","ignore").decode()
        key=(re.sub("[^a-z0-9]","",title),e["start"][:16],e["city"])
        output.setdefault(key,e)
    return sorted(output.values(),key=lambda e:(e["start"],e["title"]))

def escape(value):
    return str(value or "").replace("\\","\\\\").replace("\n","\\n").replace(",","\\,").replace(";","\\;")

def fold(text):
    chunks=[];part=""
    for c in text:
        if len((part+c).encode())>(75 if not chunks else 74):
            chunks.append(part);part=c
        else: part+=c
    chunks.append(part)
    return "\r\n ".join(chunks)

def write_ics(path,events,name):
    now=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines=["BEGIN:VCALENDAR","VERSION:2.0",
           "PRODID:-//Politik und Gesellschaft Sachsen//DE","CALSCALE:GREGORIAN",
           "METHOD:PUBLISH","X-WR-CALNAME:"+escape(name),
           "X-PUBLISHED-TTL:PT12H"]
    for e in events:
        start=datetime.fromisoformat(e["start"]).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        end=datetime.fromisoformat(e["end"]).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines += ["BEGIN:VEVENT","UID:"+identity(e),"DTSTAMP:"+now,
                  "DTSTART:"+start,"DTEND:"+end,
                  "SUMMARY:"+escape("["+e["city"]+"] "+("[ABGESAGT] " if e["status"]=="CANCELLED" else "")+e["title"]),
                  "LOCATION:"+escape(e["location"] or e["city"]),
                  "DESCRIPTION:"+escape(e["description"]+"\n\nQuelle: "+e["url"]),
                  "STATUS:"+e["status"]]
        if e["url"]: lines.append("URL:"+e["url"])
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    path.write_bytes(("\r\n".join(map(fold,lines))+"\r\n").encode())

def main():
    logging.basicConfig(level=logging.INFO)
    sources=json.loads((ROOT/"config/sources.json").read_text())
    manual=json.loads((ROOT/"data/manual_events.json").read_text())
    cache_file=ROOT/"data/cache.json"
    cache=json.loads(cache_file.read_text()) if cache_file.exists() else {}
    status={};updated={}
    for src in sources:
        try: fresh,message=source_events(src)
        except Exception as ex:
            LOG.exception("Fehler bei %s",src["id"])
            fresh,message=None,str(ex)
        updated[src["id"]]=fresh if fresh is not None else cache.get(src["id"],[])
        status[src["id"]]=message
        LOG.info("%s: %s",src["id"],message)
    live=[item for group in updated.values() for item in group]
    live_urls={e.get("url","").split("?")[0] for e in live}
    events=dedupe(live+[e for e in manual if e.get("url","").split("?")[0] not in live_urls])
    docs=ROOT/"docs"
    docs.mkdir(exist_ok=True)
    for city in ("Sachsen","Chemnitz","Leipzig","Dresden"):
        subset=events if city=="Sachsen" else [e for e in events if e["city"]==city]
        write_ics(docs/(city.lower()+".ics"),subset,"Politik & Gesellschaft – "+city)
    links="".join(f'<li><a href="{city.lower()}.ics">{city} abonnieren (ICS)</a></li>'
                  for city in ("Sachsen","Chemnitz","Leipzig","Dresden"))
    items="".join(f'<li>{html.escape(e["start"][:16])} – {html.escape(e["city"])} – '
                  f'<a href="{html.escape(e["url"],quote=True)}">{html.escape(e["title"])}</a></li>'
                  for e in events)
    docs.joinpath("index.html").write_text(
        '<!doctype html><html lang="de"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Politik & Gesellschaft – Sachsen</title>'
        '<style>body{font:17px/1.5 system-ui;max-width:850px;margin:3em auto;padding:0 1em}'
        'a{color:#0758a5}li{margin:.5em 0}</style>'
        '<h1>Politik & Gesellschaft – Sachsen</h1>'
        '<p>Politische und gesellschaftskritische Veranstaltungen. '
        'Abonnieren Sie die ICS-URL in Ihrer Kalenderanwendung statt die Datei einmalig zu importieren. '
        'Die automatische Erfassung ist teilweise implementiert; Instagram wird noch nicht importiert.</p>'
        '<h2>Kalender</h2><ul>'+links+'</ul><h2>Termine</h2><ul>'+items+'</ul>'
        '<p>Stand: '+datetime.now(ZONE).strftime("%d.%m.%Y %H:%M")+'</p></html>',
        encoding="utf8")
    cache_file.write_text(json.dumps(updated,ensure_ascii=False,indent=2)+"\n")
    (ROOT/"data/last_run.json").write_text(json.dumps({
        "at":datetime.now(ZONE).isoformat(),
        "counts":{c:sum(e["city"]==c for e in events) for c in ("Chemnitz","Leipzig","Dresden")},
        "total":len(events),"sources":status
    },ensure_ascii=False,indent=2)+"\n")
    LOG.info("Termine: %s",len(events))

if __name__=="__main__": main()
