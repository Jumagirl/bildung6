# CompiTek – neue Internetseite

Neue Version von [compitek.de](https://compitek.de): modern, schnell und auf dem Handy gut bedienbar.
Die Seite besteht aus reinem HTML und CSS. Sie braucht kein WordPress, keine Datenbank und keine Plugin-Updates.

> **Vor dem Livegang:** Bitte die [CHECKLISTE.md](CHECKLISTE.md) durchgehen. Ein paar Angaben (z. B. USt-IdNr., Webhoster, AGB-Text) muss Karl noch bestätigen oder ergänzen.

## Ansehen

`index.html` per Doppelklick im Browser öffnen. Das funktioniert auch ohne Internet.

## Aufbau

| Datei | Inhalt |
| --- | --- |
| `index.html` | Startseite: Windows-11-Angebot, Leistungen, Preise, Ablauf, Über mich, Kontakt & Öffnungszeiten |
| `windows-11.html` | Alles zum Upgrade von Windows 10 auf Windows 11 |
| `kontakt.html` | Kontaktseite mit Anfrage-Formular (Häkchen), Öffnungszeiten und Anfahrt mit Google-Maps-Karte |
| `kontakt.php` | Verschickt das Anfrage-Formular als E-Mail (braucht PHP beim Webhoster) |
| `danke.html` | Bestätigung nach dem Absenden des Formulars |
| `tipps.html` | Tipps & Links: empfohlene Programme und IT-Sicherheit (BSI) |
| `impressum.html`, `datenschutz.html`, `agb.html` | Rechtliches (siehe Checkliste) |
| `404.html` | Fehlerseite für nicht vorhandene Adressen |
| `assets/css/style.css` | Gestaltung (Farben, Schrift, Layout) |
| `assets/js/main.js` | Handy-Menü, Anzeige „Jetzt geöffnet“, Anruf-Leiste, Formular-Prüfung, Karte nach Klick |
| `assets/fonts/` | Schrift „Figtree“ (lokal, Lizenz: SIL OFL) |
| `favicon.svg`, `apple-touch-icon.png`, `assets/img/logo.svg` | Logo und App-Symbol |
| `.htaccess` | Weiterleitungen alter Adressen, Fehlerseite, Caching (nur Apache-Webserver) |
| `robots.txt`, `sitemap.xml` | Hinweise für Suchmaschinen |

## Häufige Änderungen

Alle Dateien lassen sich mit einem einfachen Texteditor bearbeiten (z. B. Notepad++ oder VS Code).

- **Texte:** direkt in der jeweiligen HTML-Datei ändern.
- **Öffnungszeiten:** stehen in `index.html` (Abschnitt „Kontakt“) und in `kontakt.html`. Jeweils den sichtbaren Text *und* das Attribut `data-hours` anpassen (leer = geschlossen). Daraus berechnet die Seite automatisch „Jetzt geöffnet“ oder „Geschlossen – öffnet …“. Zusätzlich die Angaben im Block `application/ld+json` oben in `index.html` anpassen (die liest Google).
- **Formular-Empfänger:** ganz oben in `kontakt.php` (`EMPFAENGER`). Die E-Mail-Adresse wird bewusst nirgends öffentlich verlinkt, Anfragen laufen über das Formular. Nur im Impressum muss sie stehen (gesetzliche Pflicht), dort kodiert in `impressum.html`. `ABSENDER` muss eine Adresse der eigenen Domain sein, sonst landen die Mails leicht im Spam.
- **Formular-Auswahl** (Häkchen): Wer Punkte ändert, muss sie in `kontakt.html` *und* in den Listen oben in `kontakt.php` anpassen (gleicher `value`).
- **Preise:** in `index.html` (Abschnitte „Windows 11“ und „Preise“) und in `windows-11.html` (Angebotskarte).
- **Hinweis-Leiste** (z. B. „Urlaub bis …“): in `index.html` beim Element `<div class="notice" … hidden>` das Wort `hidden` entfernen und den Text anpassen.
- **Google-Bewertungen:** in `index.html` im Abschnitt „Bewertungen“. Dort steht eine Vorlage im Kommentar: je Bewertung ein Listeneintrag, nur Vorname und Initial, den Hinweistext darunter stehen lassen.
- **Foto für „Über mich“:** Bild als `assets/img/karl-stockenhofen.jpg` speichern (Hochformat, ca. 800 × 1000 px) und in `index.html` die vorbereitete Zeile im Abschnitt „Über mich“ einkommentieren.
- **Kopf- und Fußbereich** stehen in jeder HTML-Datei. Bei Änderungen dort bitte alle Dateien anpassen.

## Veröffentlichen

### Variante A: beim bisherigen Webhoster (empfohlen)

1. Die bisherige Seite komplett sichern (Backup beim Hoster oder per FTP herunterladen).
2. Die alten Dateien aus dem Webverzeichnis entfernen bzw. in einen Unterordner verschieben, insbesondere eine alte `index.php`.
3. Alle Dateien aus diesem Ordner per FTP oder Dateimanager hochladen, auch `.htaccess` (versteckte Datei!). `README.md` und `CHECKLISTE.md` müssen nicht mit hoch.
4. Testen: Startseite, Unterseiten, Handy-Ansicht, eine alte Adresse wie `compitek.de/service.html` (muss weiterleiten) und **das Formular einmal selbst abschicken** (die Mail muss bei `info@compitek.de` ankommen).
5. Im Kundenmenü des Hosters „SSL/HTTPS erzwingen“ einschalten, falls noch nicht aktiv.

### Schritt für Schritt bei all-inkl

CompiTek liegt bei **all-inkl**. So geht der Umzug von der alten Seite (WordPress) auf die neue:

1. **Zugangsdaten holen:** Im KAS von all-inkl (`kas.all-inkl.com`) unter **„FTP“** stehen FTP-Benutzer und Server. Das Passwort lässt sich dort bei Bedarf neu setzen.
2. **Ordner der Domain finden:** Im KAS unter **„Domain“** steht bei `compitek.de`, auf welchen Ordner die Domain zeigt, zum Beispiel `/` oder `/compitek.de/`. Genau in diesen Ordner kommt die neue Seite.
3. **Verbinden:** Mit **FileZilla** (kostenlos) oder dem **WebFTP** von all-inkl im Browser. In FileZilla unter *Server → Anzeige versteckter Dateien erzwingen* einschalten, damit die Datei `.htaccess` sichtbar ist.
4. **Alte Seite sichern:**
   - Zuerst den kompletten Ordner der Domain einmal auf den eigenen PC herunterladen (Sicherheitskopie).
   - Dann auf dem Server im Ordner der Domain einen neuen Ordner `alte-seite` anlegen und **alle bisherigen Dateien und Ordner hineinschieben**. Bei WordPress sind das unter anderem `wp-admin`, `wp-content`, `wp-includes`, `index.php`, `wp-config.php` und `.htaccess`.
   - Nichts löschen. So ist die alte Seite jederzeit wiederherstellbar. Die WordPress-Datenbank bleibt unverändert beim Hoster.
5. **Neue Seite hochladen:** Die ZIP am PC entpacken, den Ordner `compitek-website` öffnen und **dessen Inhalt** (alle Dateien, den Ordner `assets` und `.htaccess`) in den Ordner der Domain hochladen. `README.md` und `CHECKLISTE.md` müssen nicht mit.
6. **Testen:**
   - `compitek.de` im Browser öffnen, bei Bedarf mit *Strg + F5* neu laden.
   - Alle Seiten durchklicken, am PC und am Handy.
   - `compitek.de/service.html` aufrufen: Die Seite muss zu den Leistungen springen.
   - Das **Formular einmal selbst abschicken**: Die Mail muss bei `info@compitek.de` ankommen.
7. **Falls Formular-Mails nicht ankommen:** Oben in `kontakt.php` bei `ABSENDER` eine echte Adresse der Domain eintragen (zum Beispiel `info@compitek.de`) und die Datei erneut hochladen. Hilft das nicht, weiß der all-inkl-Support weiter.
8. **HTTPS prüfen:** Im KAS unter *Domain → compitek.de bearbeiten* sollte der SSL-Schutz (Let’s Encrypt) aktiv sein.
9. **Nach etwa zwei Wochen:** Läuft alles, den Ordner `alte-seite` auf dem Server löschen. Ein altes, nicht mehr gepflegtes WordPress auf dem Server ist ein Sicherheitsrisiko. Die Kopie auf dem PC bleibt als Sicherung.

Zurück zur alten Seite (falls nötig): die neuen Dateien entfernen und den Inhalt von `alte-seite` wieder in den Ordner der Domain schieben.

### Variante B: kostenlos über GitHub Pages

1. Repository auf „Public“ stellen (GitHub Pages ist für private Repositories kostenpflichtig).
2. *Settings → Pages → Deploy from a branch → `main` / `(root)`*.
3. Beim Domain-Anbieter die DNS-Einträge für `compitek.de` auf GitHub Pages umstellen und die Domain in den Pages-Einstellungen eintragen.

Hinweis: GitHub Pages wertet weder `.htaccess` noch PHP aus. Weiterleitungen und **das Anfrage-Formular funktionieren dort nicht**. Für die CompiTek-Seite ist deshalb Variante A die richtige.

## Technik und Datenschutz

- **Keine Cookies, kein Tracking, keine externen Dienste.** Die Schrift liegt auf dem eigenen Server (kein Google Fonts). Deshalb ist **kein Cookie-Banner** nötig.
- **Google-Maps-Karte** (Kontaktseite) wird erst nach einem Klick auf „Karte laden“ geladen (2-Klick-Lösung). Vorher fließen keine Daten zu Google.
- **Anfrage-Formular:** Prüfung direkt im Browser und noch einmal auf dem Server, Schutz vor Spam (unsichtbares Fallen-Feld und das „Spam-Roboter“-Häkchen), keine Speicherung auf dem Server, nur Versand per E-Mail.
- **Suchmaschinen:** aussagekräftige Seitentitel und Beschreibungen, strukturierte Daten für Google (Adresse, Öffnungszeiten, Einzugsgebiet), `sitemap.xml`.
- **Barrierearm:** große Schrift, hohe Kontraste, mit Tastatur bedienbar, Sprunglink zum Inhalt, reduzierte Animationen, wenn im System eingestellt.
- **Handy:** Telefonnummern sind antippbar, unten erscheint beim Scrollen eine „Jetzt anrufen“-Leiste.

## Herkunft der Inhalte

Die Texte stammen von der bisherigen Seite compitek.de (Startseite, Windows 11, Service, Preise, Kontakt mit Formular, Anfahrt, Sicherheit, Tipps & Tricks, Impressum, Datenschutz, AGB). Werbetexte wurden sprachlich überarbeitet und neu gegliedert, Rechtstexte (AGB, Haftungsausschluss) wörtlich übernommen. Was noch zu prüfen ist, steht in der [CHECKLISTE.md](CHECKLISTE.md).
