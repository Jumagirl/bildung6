# Rivals Video

Ein Programm für deinen Windows-PC. Es wertet deine Marvel-Rivals-Aufnahmen aus, lernt aus deinen Antworten und gibt die Ergebnisse an Rivals Coach weiter. Alles bleibt auf deinem PC.

## Einmal einrichten

1. Lade **RivalsVideo.exe** herunter (Seite «Releases» im Repository, Datei unter «Assets»).
2. Leg die Datei an einen festen Ort, zum Beispiel in deinen Ordner «Claude».
3. Doppelklick. Beim ersten Start warnt Windows, weil das Programm nicht signiert ist: **«Weitere Informationen» → «Trotzdem ausführen»**.
4. Es öffnet sich ein schwarzes Fenster und dein Browser mit der Oberfläche. **Das schwarze Fenster offen lassen**, solange du das Programm nutzt.
5. Das Programm legt den Ordner **Videos\Rivals Videos** an, darin **Neu** und **Ausgewertet**. Einen anderen Ordner wählst du links mit «Anderen Ordner wählen».

## So nutzt du es

1. Kopier deine Aufnahmen vom USB-Stick in **Neu**. Auf der PS5 am besten: MP4, 1080p, HDR aus. Seit Version 0.2.0 gehen auch HDR-Aufnahmen: Das Programm rechnet sie auf normale Farben um.
2. Das Programm wertet jedes neue Video von selbst aus (Tode, deine Kills, deine Ults).
3. Wähl links ein Video. Bei jedem Fund: **Stimmt** oder **Stimmt nicht**. Bei einem Tod wählst du die Ursache: Ein Tipp auf die Gruppe reicht, unter «Genauer» stehen die genauen Ursachen für deine Rolle (wie in Rivals Coach). Bei «Gegnerische Ult» und bei «Gegner-Ult» wählst du, **wessen Ult** es war; die zuletzt gewählten Helden stehen als Knöpfe bereit. Liegt die Zeit daneben, spulst du genau an deinen Tod und tippst **«Tod ist hier»**.
4. **Fights (Versuch):** Liegen mindestens zwei deiner Kills, Tode oder Ults höchstens 8 Sekunden auseinander, schlägt das Programm einen Fight vor. Antworte mit **Gewonnen**, **Verloren** oder **Kein Fight**. Gewonnen und verloren werden zu Markierungen und zählen in Rivals Coach als Fight.
5. **Kurz-Review** spielt nur die wichtigen Stellen: jeden Tod mit den 10 Sekunden davor, jede Ult, jeden Kill, jeden Fight.
6. **Auswertung abschliessen** verschiebt das Video nach «Ausgewertet» und nennt es «Ausgewertet JJJJ-MM-TT HH-MM-SS».

Tasten wie in Rivals Coach: T Tod, K Kill, U Ult, G Gegner-Ult, W und V Fight gewonnen oder verloren, B gut gemacht, N Notiz, Leertaste Pause, Pfeiltasten 5 Sekunden.

## Lernen

Jede Antwort speichert das Programm mit den Messwerten. Daraus stellt es nach:

- wie stark ein Merkmal sein muss, damit es als Tod, Kill oder Ult zählt,
- wie viele Sekunden der Tod vor dem Auftauchen der gelben Zahl liegt (aus deinen «Tod ist hier»),
- ob ein Fight gewonnen oder verloren ist (Versuch): ab je 3 Antworten «Gewonnen» und «Verloren» vergleicht es die Farben in der Kill-Anzeige. Trennen sie sich deutlich, schätzt es den Ausgang neuer Fights selbst und zeigt, wie oft es bei deinen Antworten richtig lag. Ob das zuverlässig klappt, ist offen.

Markierst du Tode, die das Programm übersehen hat, und lagen sie alle unter seiner Schwelle, senkt es die Schwelle und findet beim nächsten Auswerten mehr.

Mit «Alle Videos mit neuem Wissen neu auswerten» wendet es das Gelernte auf alle Videos an. Deine Antworten bleiben.

## Verbindung zu Rivals Coach

In Rivals Coach: **Review → Video-Review → «Ganzen Ordner wählen»** und den Ordner «Rivals Videos» wählen. Rivals Coach liest die Datei `rivals-video-daten.json`, übernimmt deine bestätigten Markierungen und ordnet sie deinen Matches zu. Genaue Ursachen und «wessen Ult» kommen mit. Bei abgeschlossenen Videos kommen Todesursachen, Ults und die Helden der Ult-Tode ins Match, wo dort noch nichts steht.

## Wenn etwas nicht klappt

- **«Nichts gefunden»:** Darunter zeigt das Programm, was es gemessen hat (höchster Wert und Schwelle). Spul an eine Stelle mit der gelben Zahl und tipp **«Was sieht das Programm hier?»**: Das Bild zeigt die drei Messbereiche. Liegen die Rahmen nicht auf den Anzeigen, schick Claude ein Bildschirmfoto davon.
- Schick Claude einen Screenshot vom schwarzen Fenster. Dort stehen Fehlermeldungen.
- Prüfen, ob das Programm überhaupt läuft: `RivalsVideo.exe --selftest` in der Eingabeaufforderung. Am Ende steht «Selbsttest OK». Der Test prüft auch eine HDR-Aufnahme.

## Für Claude (Technik)

- `rv_core.py`: Messen mit ffmpeg (4 Bilder pro Sekunde, 480 × 270), Merkmale `cnt` / `feed` / `ug` wie `vidFeat` in Rivals Coach, Erkennung `detect`, Lernen `learned`, Daten `Store` (`rivals-video-daten.json` im Ordner, Messreihen im versteckten Ordner `.rivals-video-cache`).
- `rivals_video.py`: Server nur auf 127.0.0.1 mit Zufalls-Token und Host-Prüfung, Video mit Range, Hintergrund-Auswertung, Ordnerwahl (tkinter).
- HDR: `probe` liest den Farbraum (PQ/HLG), `color_mode` wählt `zscale` (ffmpeg, Tonemapping mobius, Weiss = 203 Nits) oder `lut` (eigene PQ-Umrechnung `pq_to_sdr`, falls dem ffmpeg zscale fehlt). Messreihen mit `SER_V` < 2 werden neu gemessen (`upgrade_series`).
- Diagnose: `series_summary` (höchster Wert, Anteil über der Schwelle), `/api/frame/<id>?t=` liefert ein PNG mit Messbereichen (`diag_image`).
- Ursachen und Helden: `rv_data.json`, erzeugt aus Rivals Coach mit `node tools/make_rv_data.js <gebaute App>` (Playwright). Neu erzeugen, wenn sich im Coach Ursachen oder Helden ändern. Wird mit PyInstaller eingepackt (`--add-data`).
- Fights: `fights` (eigene Ereignisse ≤ `FIGHT_GAP_S` auseinander, Farbanteile `fr`/`fb` im Kill-Feed), `fight_answer`, `learned_fights` (ab je 3, Medianabstand ≥ 0,15, Treffer ≥ 70 %).
- `rv_ui.html`: Oberfläche.
- Bau: `.github/workflows/rivals-video.yml` (Selbsttest, PyInstaller, Selbsttest der EXE; Release nur bei Tag `video-v…`).
- Tests (im Scratchpad): `rv3.js` (Programm Ende zu Ende mit Fights, Ursachen, Ult-Held, Diagnose, HDR und Übernahme in Rivals Coach), `t150.js` (Abgleich und Video-Review im Coach). Selbsttest: `python rivals_video.py --selftest`.
