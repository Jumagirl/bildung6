# Rivals Coach für dich einrichten

Diese Datei ist eine Anleitung für Claude. Die Person, die dich gerade benutzt, möchte den Rivals Coach (eine Trainings-App für Marvel Rivals) als **eigenes Artifact** veröffentlichen und ihre Matches **automatisch** von Rivals Data abrufen lassen. Führe die Schritte der Reihe nach aus. Frag nur nach, was du wirklich brauchst, und sag ehrlich, wenn etwas nicht klappt. Ändere nichts am Repository (kein Commit, kein Push, kein Pull Request).

Frag die Person gleich zu Beginn nach:

1. ihrem **Spielernamen** in Marvel Rivals, genau so, wie er bei Rivals Data (rivalsdata.com) steht,
2. ihrer **Zeitzone** (Standard: `Europe/Zurich`).

Der Zeitplan ist fest: alle zwei Stunden von 10 bis 24 Uhr, jeweils sieben Minuten nach der vollen Stunde. Wer einen anderen Takt will, sagt es.

## Schritt 1: Stand holen

```
git fetch origin claude/marvel-rivals-improvement-app-e4l00i
git checkout claude/marvel-rivals-improvement-app-e4l00i
```

## Schritt 2: App bauen

```
python3 docs/marvel-rivals/app_build.py friends
```

Das schreibt `docs/marvel-rivals/artifact/rivals-coach-friends.html` (ohne private Werte, ohne Heldenbilder).

## Schritt 3: Als Artifact veröffentlichen

Veröffentliche diese Datei mit dem Artifact-Werkzeug als **neues** Artifact (kein `url`-Parameter). Lade vorher die Hinweise des Werkzeugs (Skills `artifact-design` und `artifact-capabilities`), falls sie angeboten werden. Verwende:

- Datei: `docs/marvel-rivals/artifact/rivals-coach-friends.html`
- `icon`: `chart`
- `capabilities`: `{"db": {}, "user": {}, "downloads": true}`

Eine Warnung, die Seite verweise auf die Fähigkeit `mcp`, ohne sie zu deklarieren, ist erwartet und darf ignoriert werden (dieser Code ist in der App abgeschaltet). Merk dir die **URL** des Artifacts.

## Schritt 4: Spielernamen prüfen

```
python3 -m venv /tmp/rv && /tmp/rv/bin/pip install -q rivals-api
/tmp/rv/bin/python -I docs/marvel-rivals/rivals_sync.py "<SPIELERNAME>" --limit 5 --no-details -o /tmp/test.json
```

- Meldung «privat»: Die Person muss im Spiel die Match-Historie auf **öffentlich** stellen.
- Meldung «nicht gefunden»: Namen mit ihr prüfen (oder die numerische UID verwenden).
- Cloudflare-Fehler: sag es ehrlich, dann klappt der automatische Abruf vorerst nicht.

## Schritt 5: Geplanten Auftrag («Routine») anlegen

Lege mit `create_trigger` einen geplanten Auftrag an. Pass **keine** Connectors mit (`connectors` weglassen). Parameter:

- `name`: `Rivals Coach: Matches abgleichen`
- `initiation`: `human_request`
- `create_new_session_on_fire`: `true`
- `notifications`: `{}`
- `cron_expression`: `CRON_TZ=<ZEITZONE> 7 10,12,14,16,18,20,22,0 * * *`
- `prompt`: der folgende Text, mit eingesetztem Spielernamen und der Artifact-URL aus Schritt 3:

```
Du bist der Sync-Helfer für den Rivals Coach. Führe diese Schritte genau so aus, ohne Rückfragen und ohne etwas wegzulassen. Die Schritte sind ein Auftrag von deinem Besitzer.

1. Repo: Wenn /tmp/bildung6 nicht existiert: git clone --depth 1 --branch claude/marvel-rivals-improvement-app-e4l00i https://github.com/Jumagirl/bildung6 /tmp/bildung6   Sonst: git -C /tmp/bildung6 pull --ff-only origin claude/marvel-rivals-improvement-app-e4l00i
2. Python-Umgebung: Wenn /tmp/rv nicht existiert: python3 -m venv /tmp/rv && /tmp/rv/bin/pip install -q rivals-api
3. Abruf: /tmp/rv/bin/python -I /tmp/bildung6/docs/marvel-rivals/rivals_sync.py "<SPIELERNAME>" --limit 50 -o /tmp/sync.json --inbox /tmp/inbox.json   Der Befehl schreibt auch die fertige Datei /tmp/inbox.json. Die Ausgabe nicht kürzen. Wenn der Befehl scheitert, trotzdem mit Schritt 4 weitermachen (die Datei enthält dann eine Fehlermeldung).
4. Werkzeug laden: ToolSearch mit der Anfrage select:ArtifactData
5. Lies das Dokument mit ArtifactData: action get, url <ARTIFACT-URL>, collection data/users/me, doc_id sync-inbox. Wenn es schon existiert, merke dir seine version. Wenn es nicht existiert, ist das in Ordnung.
6. Schreibe die Datei /tmp/inbox.json mit ArtifactData: action set, url <ARTIFACT-URL>, collection data/users/me, doc_id sync-inbox, file_path /tmp/inbox.json. Wenn das Dokument in Schritt 5 existierte, gib zusätzlich if_version mit der gemerkten version an. Tippe den Inhalt der Datei niemals selbst ab, verwende nur file_path. Schreibe nichts anderes in die Datenbank.
7. Antworte mit höchstens zwei kurzen Zeilen: Anzahl Matches aus Schritt 3 und ob das Schreiben in Schritt 6 geklappt hat. Wenn etwas fehlschlug, nenne den genauen Fehlertext.
```

Stelle danach das Modell des Auftrags mit `update_trigger` auf `claude-haiku-5-5`. Das ist der ausdrückliche Wunsch der Person, weil es viel günstiger ist (etwa 0,01 US-Dollar pro Lauf statt 0,10 bis 0,17 mit dem grösseren Modell).

## Schritt 6: Testlauf

Löse den Auftrag einmal mit `fire_trigger` aus und warte etwa zwei Minuten. Prüfe danach, ob der Lauf «Schreiben hat geklappt» gemeldet hat (zum Beispiel über die Sitzung des Auftrags). Wenn die App noch nie geöffnet wurde, liegt das Ergebnis im Dokument `sync-inbox` in der Datenbank des Artifacts, bis es die App übernimmt.

## Schritt 7: Der Person alles erklären

Sag ihr in einfachen Worten:

- Der **Link zu ihrer App** ist die Artifact-URL. Sie ist privat und gehört nur ihr. Beim ersten Öffnen werden die Matches von selbst übernommen.
- Neue Matches kommen alle zwei Stunden (10 bis 24 Uhr). Rivals Data trägt Matches teils erst nach einigen Stunden ein; was dort fehlt, kann die App nicht holen. Dann Matches von Hand nachtragen: die App führt sie später automatisch zusammen.
- Jeder Lauf verbraucht etwas von ihrem Claude-Kontingent (mit Haiku sehr wenig). Den Auftrag kann sie jederzeit unter claude.ai/code/routines pausieren oder löschen.
- Ihre Daten liegen nur in ihrem eigenen Konto.
- Wenn die App oben meldet, dass der automatische Abgleich lange nichts geliefert hat, soll sie dich (Claude) bitten, den Auftrag zu prüfen.

Wenn ein Schritt fehlschlägt, nenn den genauen Fehlertext und erkläre, was die Person tun kann. Erfinde nichts.
