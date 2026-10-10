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
| `impressum.html`, `datenschutz.html`, `agb.html` | Rechtliches (Entwürfe, siehe Checkliste) |
| `404.html` | Fehlerseite für nicht vorhandene Adressen |
| `assets/css/style.css` | Gestaltung (Farben, Schrift, Layout) |
| `assets/js/main.js` | Handy-Menü, Anzeige „Jetzt geöffnet“, Anruf-Leiste |
| `assets/fonts/` | Schrift „Figtree“ (lokal, Lizenz: SIL OFL) |
| `favicon.svg`, `apple-touch-icon.png`, `assets/img/logo.svg` | Logo und App-Symbol |
| `.htaccess` | Weiterleitungen alter Adressen, Fehlerseite, Caching (nur Apache-Webserver) |
| `robots.txt`, `sitemap.xml` | Hinweise für Suchmaschinen |

## Häufige Änderungen

Alle Dateien lassen sich mit einem einfachen Texteditor bearbeiten (z. B. Notepad++ oder VS Code).

- **Texte:** direkt in der jeweiligen HTML-Datei ändern.
- **Öffnungszeiten:** in `index.html` die Tabelle im Abschnitt „Kontakt“ anpassen, und zwar den sichtbaren Text *und* das Attribut `data-hours` (leer = geschlossen). Daraus berechnet die Seite automatisch „Jetzt geöffnet“ oder „Geschlossen – öffnet …“. Zusätzlich die Angaben im Block `application/ld+json` oben in `index.html` anpassen (die liest Google).
- **Preise:** in `index.html` (Abschnitte „Windows 11“ und „Preise“) und in `windows-11.html` (Angebotskarte).
- **Hinweis-Leiste** (z. B. „Urlaub bis …“): in `index.html` beim Element `<div class="notice" … hidden>` das Wort `hidden` entfernen und den Text anpassen.
- **Foto für „Über mich“:** Bild als `assets/img/karl-stockenhofen.jpg` speichern (Hochformat, ca. 800 × 1000 px) und in `index.html` die vorbereitete Zeile im Abschnitt „Über mich“ einkommentieren.
- **Kopf- und Fußbereich** stehen in jeder HTML-Datei. Bei Änderungen dort bitte alle Dateien anpassen.

## Veröffentlichen

### Variante A: beim bisherigen Webhoster (empfohlen)

1. Die bisherige Seite komplett sichern (Backup beim Hoster oder per FTP herunterladen).
2. Die alten Dateien aus dem Webverzeichnis entfernen bzw. in einen Unterordner verschieben, insbesondere eine alte `index.php`.
3. Alle Dateien aus diesem Ordner per FTP oder Dateimanager hochladen, auch `.htaccess` (versteckte Datei!). `README.md` und `CHECKLISTE.md` müssen nicht mit hoch.
4. Testen: Startseite, Unterseiten, Handy-Ansicht, eine alte Adresse wie `compitek.de/service.html` (muss weiterleiten).
5. Im Kundenmenü des Hosters „SSL/HTTPS erzwingen“ einschalten, falls noch nicht aktiv.

### Variante B: kostenlos über GitHub Pages

1. Repository auf „Public“ stellen (GitHub Pages ist für private Repositories kostenpflichtig).
2. *Settings → Pages → Deploy from a branch → `main` / `(root)`*.
3. Beim Domain-Anbieter die DNS-Einträge für `compitek.de` auf GitHub Pages umstellen und die Domain in den Pages-Einstellungen eintragen.

Hinweis: GitHub Pages wertet `.htaccess` nicht aus. Die Weiterleitungen alter Adressen funktionieren dort nicht.

## Technik und Datenschutz

- **Keine Cookies, kein Tracking, keine externen Dienste.** Die Schrift liegt auf dem eigenen Server (kein Google Fonts). Deshalb ist **kein Cookie-Banner** nötig.
- **Karten** werden nicht eingebettet, sondern nur verlinkt (Google Maps, OpenStreetMap).
- **Suchmaschinen:** aussagekräftige Seitentitel und Beschreibungen, strukturierte Daten für Google (Adresse, Öffnungszeiten, Einzugsgebiet), `sitemap.xml`.
- **Barrierearm:** große Schrift, hohe Kontraste, mit Tastatur bedienbar, Sprunglink zum Inhalt, reduzierte Animationen, wenn im System eingestellt.
- **Handy:** Telefonnummern sind antippbar, unten erscheint beim Scrollen eine „Jetzt anrufen“-Leiste.

## Herkunft der Inhalte

Die Texte stammen von der bisherigen Seite compitek.de (Startseite, Windows 11, Service, Preise, Öffnungszeiten, AGB-Angaben) und wurden sprachlich überarbeitet und neu gegliedert. Was noch zu prüfen ist, steht in der [CHECKLISTE.md](CHECKLISTE.md).
