# Rivals Video

Ein Programm für deinen Windows-PC. Es wertet deine Marvel-Rivals-Aufnahmen aus, lernt aus deinen Antworten und gibt die Ergebnisse an Rivals Coach weiter. Alles bleibt auf deinem PC.

## Einmal einrichten

1. Lade **RivalsVideo.exe** herunter (Seite «Releases» im Repository, Datei unter «Assets»).
2. Leg die Datei an einen festen Ort, zum Beispiel in deinen Ordner «Claude».
3. Doppelklick. Beim ersten Start warnt Windows, weil das Programm nicht signiert ist: **«Weitere Informationen» → «Trotzdem ausführen»**.
4. Es öffnet sich ein schwarzes Fenster und dein Browser mit der Oberfläche. **Das schwarze Fenster offen lassen**, solange du das Programm nutzt.
5. Das Programm legt den Ordner **Videos\Rivals Videos** an, darin **Neu** und **Ausgewertet**. Einen anderen Ordner wählst du links mit «Anderen Ordner wählen».

## So nutzt du es

1. Kopier deine Aufnahmen vom USB-Stick in **Neu**. Auf der PS5 am besten: MP4, 1080p, HDR aus.
2. Das Programm wertet jedes neue Video von selbst aus (Tode, deine Kills, deine Ults).
3. Wähl links ein Video. Bei jedem Fund: **Stimmt** oder **Stimmt nicht**. Bei einem Tod wählst du die Ursache. Liegt die Zeit daneben, spulst du genau an deinen Tod und tippst **«Tod ist hier»**.
4. **Kurz-Review** spielt nur die wichtigen Stellen: jeden Tod mit den 10 Sekunden davor, jede Ult, jeden Kill.
5. **Auswertung abschliessen** verschiebt das Video nach «Ausgewertet» und nennt es «Ausgewertet JJJJ-MM-TT HH-MM-SS».

Tasten wie in Rivals Coach: T Tod, K Kill, U Ult, G Gegner-Ult, W und V Fight gewonnen oder verloren, B gut gemacht, N Notiz, Leertaste Pause, Pfeiltasten 5 Sekunden.

## Lernen

Jede Antwort speichert das Programm mit den Messwerten. Daraus stellt es nach:

- wie stark ein Merkmal sein muss, damit es als Tod, Kill oder Ult zählt,
- wie viele Sekunden der Tod vor dem Auftauchen der gelben Zahl liegt (aus deinen «Tod ist hier»).

Mit «Alle Videos mit neuem Wissen neu auswerten» wendet es das Gelernte auf alle Videos an. Deine Antworten bleiben.

## Verbindung zu Rivals Coach

In Rivals Coach: **Review → Video-Review → «Ganzen Ordner wählen»** und den Ordner «Rivals Videos» wählen. Rivals Coach liest die Datei `rivals-video-daten.json`, übernimmt deine bestätigten Markierungen und ordnet sie deinen Matches zu. Bei abgeschlossenen Videos kommen Todesursachen und Ults ins Match, wo dort noch nichts steht.

## Wenn etwas nicht klappt

- Schick Claude einen Screenshot vom schwarzen Fenster. Dort stehen Fehlermeldungen.
- Prüfen, ob das Programm überhaupt läuft: `RivalsVideo.exe --selftest` in der Eingabeaufforderung. Am Ende steht «Selbsttest OK».

## Für Claude (Technik)

- `rv_core.py`: Messen mit ffmpeg (4 Bilder pro Sekunde, 480 × 270), Merkmale `cnt` / `feed` / `ug` wie `vidFeat` in Rivals Coach, Erkennung `detect`, Lernen `learned`, Daten `Store` (`rivals-video-daten.json` im Ordner, Messreihen im versteckten Ordner `.rivals-video-cache`).
- `rivals_video.py`: Server nur auf 127.0.0.1 mit Zufalls-Token und Host-Prüfung, Video mit Range, Hintergrund-Auswertung, Ordnerwahl (tkinter).
- `rv_ui.html`: Oberfläche.
- Bau: `.github/workflows/rivals-video.yml` (Selbsttest, PyInstaller, Selbsttest der EXE; Release nur bei Tag `video-v…`).
- Tests (im Scratchpad): `rv1.js` (Programm Ende zu Ende), `t139.js` (Übernahme in Rivals Coach).
