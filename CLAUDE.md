# Rivals Coach: Hinweise für Claude

## Zuerst: das zweite Gehirn lesen
Zu diesem Projekt gibt es ein privates Notiz-Repo `Jumagirl/Rivals-Brain`. Die Nutzerin liest es in Obsidian auf dem Handy. Darin stehen Regeln, Entscheidungen, Versionen, Lernstand und offene Punkte.

1. Zu Beginn jeder Sitzung das Repo mit `add_repo` anhängen (owner `Jumagirl`, repo `Rivals-Brain`, access `push`). Dann nach `/home/user/rivals-brain` klonen und `register_repo_root` aufrufen.
2. Lesen: `00 Start.md`, `Projekt/Regeln und Wünsche.md`, `Projekt/Entscheidungen.md`, `Projekt/Versionen.md`, `Lernstand/Mein Stand.md`, `Offen/Ideen und offene Punkte.md`.
3. Neue Notizen der Nutzerin finden: Commits von `Jumagirl` seit dem letzten Commit von Claude (`git log`). Was sie dort schreibt, sind ihre Wünsche an Claude. Kurz bestätigen, was davon angekommen ist.
4. Klappt das Anhängen nicht, der Nutzerin den Grund sagen und mit den Regeln unten weiterarbeiten.

## Nach jeder Arbeitssitzung: Gehirn nachführen
- `Projekt/Entscheidungen.md` (neueste oben, immer mit Grund), `Projekt/Versionen.md` (Version, Freundesversion, Datum, was neu ist), `Lernstand/Mein Stand.md`, `Offen/Ideen und offene Punkte.md`.
- Direkt auf `main` von `Rivals-Brain` committen und pushen. Den Ordner `.obsidian` nicht anfassen, er gehört der Obsidian-App.
- Nie hineinschreiben: Tokens, Spielernamen aus Ranglisten, Namen von Teammates.

## Regeln (Kurzfassung, falls das Gehirn nicht erreichbar ist)
- Deutsch, Du-Form, Schweizer Schreibung (immer «ss»), kurze Sätze. Helden, Fähigkeiten und Karten englisch wie im Spiel.
- Keine erfundenen Spielfakten und keine Zahlen ohne Quelle. Schätzungen als Schätzung kennzeichnen.
- Vor jedem Veröffentlichen fragen: «Soll ich das als Version N veröffentlichen?» Erst nach «Ja» veröffentlichen, immer auch die Freundesversion.
- Pull Request und Merge nach `main` nur auf ausdrücklichen Wunsch («Website aktualisieren»).
- Spielernamen aus Ranglisten nie speichern oder zeigen. Teammates nur als Kürzel, ihre Ränge nur als Zahl. `private.json` kommt nie ins Repo.
- «Zuschauen» bleibt ohne Aufschreiben.
- Die Nutzerin nie einen Token in den Chat schreiben lassen.

## Code
- App: `docs/marvel-rivals/app/index.html` (eine Datei). Beschreibung für Nutzer: `docs/marvel-rivals/index.md`.
- Vor Änderungen an Lektionen, Quiz, Trainingsplan oder Rückblick den Skill `lerndesign` lesen (`.claude/skills/lerndesign/SKILL.md`).
