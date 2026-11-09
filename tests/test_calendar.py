import unittest
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from src import calendar_feed as c

class CalendarTests(unittest.TestCase):
    def test_daks_precise_time(self):
        html = ('<h1>Baurecht und Bauleitplanung</h1><div>Datum</div>'
                '<div>14. November 2026</div><div>Uhrzeit</div>'
                '<div>10:00 - 17:00</div><div>Ort</div>'
                '<div>Chemnitz</div><div>Ort 2</div>')
        event = c.detail_events(BeautifulSoup(html, "html.parser"),"daks","https://example.org/event")[0]
        self.assertEqual(event["start"].hour, 10)
        self.assertEqual(event["end"].hour, 17)

    def test_cancelled_rosalux(self):
        html = ('<h1>20. November 2026: abgesagt: Diskussion/Vortrag : Gemeinschaft in der Krise?</h1>'
                '<div>Veranstaltungsort</div><div>09111 Chemnitz</div>'
                '<div>Zeit</div><div>20.11.2026, 19:00 - 21:00 Uhr</div>'
                '<div>Beschreibung</div><p>Leider müssen wir die Veranstaltung kurzfristig absagen.</p>')
        e=c.detail_events(BeautifulSoup(html,"html.parser"),"rosalux","https://example.org/event")[0]
        self.assertEqual(e["status"],"CANCELLED")
        self.assertEqual(e["title"],"Gemeinschaft in der Krise?")
        self.assertEqual(e["start"].hour,19)

    def test_date_only_not_midnight(self):
        future=c.TODAY+timedelta(days=7)
        e={"source_id":"daks","title":"Baurecht","start":future.isoformat(),
           "location":"Chemnitz","url":"https://example.org"}
        self.assertIsNone(c.normalize(e))

    def test_stable_uid_after_date_change(self):
        e={"title":"Debatte","url":"https://example.org/event?ref=calendar",
           "start":"2027-01-10T18:00:00+01:00","city":"Leipzig"}
        f={**e,"start":"2027-01-11T18:00:00+01:00"}
        self.assertEqual(c.identity(e),c.identity(f))

    def test_ics_cancelled_label(self):
        future=c.TODAY+timedelta(days=7)
        e={"source_id":"rosalux","title":"Gespräch",
           "start":f"{future.isoformat()}T19:00:00+01:00",
           "end":f"{future.isoformat()}T20:00:00+01:00",
           "city":"Chemnitz","location":"Chemnitz","description":"",
           "url":"https://example.org/event","status":"CANCELLED"}
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"test.ics"
            c.write_ics(path,[e],"Test")
            content=path.read_text()
            self.assertIn("STATUS:CANCELLED",content)
            self.assertIn("[ABGESAGT]",content)

if __name__=="__main__":
    unittest.main()
