# Politik & Gesellschaft – Sachsen (ICS-Abonnement)

Ein **technischer Prototyp** für abonnierbare Veranstaltungskalender aus Sachsen.
Themenschwerpunkte: Politik, gesellschaftskritische Kultur, Demokratie, Wirtschaft, Wissenschaft, Ökologie, Verkehr, Energie, Stadtentwicklung und gesellschaftliche Debatten.

## Enthalten

- 14 vom Nutzer genannte Quellen unter `config/sources.json`: 10 Websites und 4 Instagram-Profile.
- Konservative Extraktion von `schema.org/Event`-Daten, außerdem erste Parser für Rosa-Luxemburg-Stiftung Sachsen und DAKS Sachsen.
- Quellenübergreifende Prüfung von Ort, Datum und Uhrzeit, Duplikatvermeidung, Filter nach gesellschaftlichem Gehalt.
- Vier ICS-Dateien: `docs/sachsen.ics`, `docs/chemnitz.ics`, `docs/leipzig.ics`, `docs/dresden.ics`.
- Tägliche Aktualisierung über GitHub Actions vorbereitet (`.github/workflows/update.yml`).
- Manueller, **zum 9. November 2026 verifizierter** Startbestand in `data/manual_events.json`.
- Einfache Landingpage `docs/index.html` mit Links auf die Abonnements und Quellendiagnose.

## Einschränkungen (wichtig)

- **GitHub-Repository erstellt:** Für ein öffentliches ICS-Abonnement muss GitHub Pages unter Settings → Pages noch auf main /docs aktiviert und der erste Workflow-Lauf geprüft werden.
- Automatische Erfassung ist derzeit **teilweise** umgesetzt. Bei DAKS und Rosa-Luxemburg-Stiftung sind spezifische HTML-Strukturen berücksichtigt; andere HTML-Quellen werden nur soweit erfasst, wie maschinenlesbare `schema.org/Event`-Informationen vorliegen. Weiterdenken wird über Eventdetail-Links betrachtet, wenn diese direkt im HTML gelistet sind.
- Kreuzer lädt Inhalte clientseitig; ein stabiler Schnittstellenzugriff fehlt. Instagram-Profile können ohne berechtigten Zugang nicht zuverlässig automatisch ausgelesen werden. Diese Quellen sind vorerst nur in der Quellendokumentation.
- Die Parser konnten hier mangels Netzwerkzugang im ausführenden Container **nicht gegen die Live-Websites getestet** werden. Lokale Unit-Tests prüfen einzelne Erkennungsschritte, nicht die komplette Live-Abdeckung.
- Trotz Fehlerbehandlung kann eine Website-Strukturänderung die Aufnahme verhindern. Geplante Events bleiben dann gegebenenfalls bis zum Ablauf im Cache. Absagen werden nur übernommen, wenn die Quelle sie strukturiert meldet oder die Event-Seite ausdrücklich als abgesagt erkannt wird.
- **Kein KI-Filter aktiviert.** Die Auswahl erfolgt derzeit regelbasiert. Sensible Grenzfälle und neue Quellen müssen geprüft werden. Ein LLM-Filter wäre optional und würde einen eigenen API-Schlüssel benötigen.
- Eine landesweite Vollständigkeit ist nicht realistisch und wird nicht zugesagt.

## Lokal ausführen

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python -m src.calendar_feed
python -m pytest -q  # pytest separat installieren
```

## Online veröffentlichen – einmalige Schritte

1. Auf GitHub ein **eigenes öffentliches** Repository anlegen, z. B. `politik-gesellschaft-sachsen`. Keine vorhandenen privaten/unverbundenen Repositories zweckentfremden.
2. Sämtliche Dateien dieses Projekts in das Repository hochladen und auf `main` committen.
3. Unter **Settings → Pages → Build and deployment** `Deploy from a branch` / `main` / `/docs` auswählen.
4. Unter **Actions** die Workflow-Berechtigungen für Schreibzugriff aktivieren (`Settings → Actions → General → Workflow permissions → Read and write permissions`, falls erforderlich). Workflow `Veranstaltungskalender aktualisieren` einmal manuell starten.
5. Nach erfolgreicher Veröffentlichung die **HTTPS-Adresse** `https://<BENUTZER>.github.io/<REPO>/sachsen.ics` im Kalenderprogramm *per URL abonnieren*; für andere Regionen entsprechend `chemnitz.ics`, `leipzig.ics` und `dresden.ics`.
6. Nach dem ersten Live-Lauf unter `data/last_run.json` prüfen, welche Quellen erfolgreich erfasst werden. Bei eventuellen Quellenausfällen die Adapter verbessern. GitHub kann geplante Jobs bei Inaktivität in öffentlichen Repositories automatisch deaktivieren; daher den Workflowstatus gelegentlich kontrollieren.

## Kuration / Ergänzungen

Neue verifizierte Events in `data/manual_events.json` eintragen. Pflichtfelder sind `title`, `start` (ISO 8601 mit Zeitzone), `city` oder `location` mit sächsischem Ort, und möglichst `url`; die anderen Felder sind optional. Datum und tatsächlicher Ort müssen von der Veranstalterseite stammen. Nur bereits bestätigte Termine hinzufügen.

Quellenliste kann jederzeit erweitert werden. Die tatsächliche Veranstaltungslokation bestimmt die Zuordnung – nicht der Sitz des Veranstalters.