---
name: lerndesign
description: Lerndesign-Regeln für den Rivals Coach (docs/marvel-rivals). Vor jeder Änderung an Lektionen, Quiz, Trainingsplan, Zwischenstopps oder Rückblick lesen: Methoden mit Evidenz, Checkliste, Fallstricke, Schreibregeln.
---

# Lerndesign für den Rivals Coach

Grundlage: Dunlosky et al. (2013), Cepeda et al. (2006), Roediger & Karpicke (2006), Rohrer & Taylor (2007), Gollwitzer & Sheeran (2006), Butterfield & Metcalfe (2001), Zimmerman (2002), Ericsson et al. (1993). Die Studien stammen aus Schule, Studium und Labor, nicht aus Videospielen: Übertragung ist plausibel, nicht bewiesen. Das immer so sagen.

## Rangfolge der Methoden
1. **Hoher Nutzen:** Abrufen (Practice Testing) und Wiederholen mit Abstand.
2. **Mittlerer Nutzen:** Mischen (Interleaving), Warum-Fragen, Selbsterklären.
3. **Geringer Nutzen, nicht als Hauptmittel bauen:** Nachlesen, Markieren, Zusammenfassen.

## Checkliste für jede neue Lernübung
- Muss die Person zuerst etwas aus dem Kopf holen (Antwort aufschreiben), bevor die Lösung erscheint?
- Wird die richtige Antwort danach gezeigt, mit Begründung? (Ohne Prüfen verstärkt Abrufen Fehler.)
- Kommt der Stoff später wieder, mit wachsendem Abstand (App: 1, 2, 4, 8, 16, 32 Tage; nicht gewusst: morgen)?
- Werden alte und neue Themen gemischt, statt nur das Thema von heute?
- Gibt es einen Wenn-dann-Satz oder ein klares Mini-Ziel für das nächste Match?
- Kann die Person ihre Sicherheit einschätzen (Kalibrierung)?
- Ist es kurz (höchstens etwa 1 Minute pro Zwischenstopp) und überspringbar? Nicht überladen.
- Zählt die Übung für das automatische Abhaken (`autoEval`)?

## Was für Spiele belegt ist (Stand Oktober 2026, selbst recherchiert, Quellen im Abschnitt «Was die Forschung speziell zu Videospielen sagt» in `docs/marvel-rivals/index.md`)
- Belegt, aber beobachtend: verteiltes Üben ohne lange Pausen (Stafford & Dewar 2014; Stafford & Haasnoot 2017; Huang et al. 2017). Kein Zusatznutzen von Schlaf in den Pausen gefunden.
- **Nicht bestätigt:** Gezielte Übung (Ericsson) in Esport. Martončik et al. (2024, Collabra, vorab registriert) fanden keinen Zusammenhang mit Leistung bei CS:GO und LoL. Deshalb Mini-Ziele und Rückmeldung als Hilfe formulieren, nie als Garantie.
- Zusätzliche Rückmeldung hilft beim Üben, der Vorteil schwindet nach dem Wegfall (Jiménez-Díaz et al. 2020, Bewegungsfertigkeiten): Hilfen ausblenden, ohne Hilfe üben lassen.
- Tilt, Coaching, Vorstellungstraining: Forschung dünn. Nicht als Fakt in die App, höchstens als offene Frage.
- Neue Belege nur nach Prüfung der Originalquelle übernehmen. Eine Webrecherche allein reicht nicht für Zahlen.

## Fallstricke
- Abrufen ohne Antwortkontrolle; Abstände zu gross; nur Leichtes üben; Wissens-Check nur zu den Themen von heute.
- Neues Wissen nur dann einbauen, wenn es belegt ist. Keine erfundenen Spielfakten, keine Zahlen ausser aus den Patch-Notes von Season 10 und 10.5.

## Wo es in der App steckt
`docs/marvel-rivals/app/index.html`: Abschnitt «Wiederholungs-System, Zwischenstopps in den Blöcken, Rückblick» (`leitner`, `nugQuestion`, `recallNugHtml`, `tipNugHtml`, `whyNugHtml`, `reflectionHtml`), `startKnow` (gemischter Tages-Check), `renderKnow` (Sicherheit). Beschreibung für Nutzer: `docs/marvel-rivals/index.md`, Abschnitt «Lernmethoden hinter der App».

## Heldenwissen-Fragen
Sie entstehen aus den eingebetteten, geprüften Daten (`PROF`, `MAPINFO`, `TU`) durch `hqGen`/`hqIds` in `index.html`, nie von Hand. Neue Fragetypen nur aus Daten mit Quelle und Stand bauen, immer vier verschiedene Optionen, Erklärung mit Quelle. Falsche Optionen dürfen keine wahren Antworten sein (bei Konter-Fragen steht «laut den Quellen» in der Frage). Test: `t68.js`.

## Schreibregeln
Deutsch, Schweizer Schreibung (immer «ss», nie «ß»), Du-Form, kurze Sätze, Fachwörter beim ersten Mal erklären, Namen von Helden, Fähigkeiten und Karten englisch wie im Spiel.

## Helden-Bootcamp
Tab «Helden-Bootcamp» (Bereich Lernen), Code im Abschnitt «Helden-Bootcamp: ein Kurs pro Held» in `index.html` (`BOOT_STATIONS`, `bootPick`, `bootStart`, `bootFinish`, `bootReadHtml`). Pro Held sieben Stationen; in Station 1 bis 5 gilt immer: erst eine eigene Antwort aufschreiben (Textfeld, leer lassen erlaubt), dann Quellen aufdecken, dann abfragen, wobei die Texte beim Abfragen verdeckt sind. Station 6: Steckbrief und Wenn-dann-Mini-Ziel aus dem Kopf. Station 7: Test (bestanden ab 80 %) und Praxis-Auftrag, der sich aus den Matches selbst abhakt. Alle Antworten laufen über `knowRecord` (Wiederholungs-Fächer, Sicherheit, `actInc("know")`). Fortschritt liegt in `state.boot[held]`.
Regeln: Inhalte und Fragen nur aus `PROF`/`TU`, keine erfundenen Spielfakten. Neue Fragetypen (`inn`: Fähigkeit aus der Beschreibung erkennen, `staerke`) liefern immer vier verschiedene Optionen, Erklärung mit Quelle; bei `inn` kommt der Name der Fähigkeit nicht im Fragetext vor und keine falsche Option steht in der Beschreibung. Tests: `t68.js` (alle Fragen gültig), `t70.js` (Bootcamp).

### Rollen-Bootcamp und Match-Aufgaben
Gleicher Abschnitt in `index.html`. Ein Kurs gilt für einen Helden (`state.boot["Mantis"]`) oder eine Rolle (`state.boot["R:Strategist"]`; Helfer `bootIsRole`, `bootRole`, `bootDefs`, `bootGen`). Rollen-Kurs: `ROLE_STATIONS` (sieben Stationen), `ROLE_WISSEN` (welche Lexikon-Lektionen die Rolle trägt), Pool = Lektionsfragen `W|<id>` plus die Heldenfragen aller Helden der Rolle (Tank und DPS haben nur je drei Lektionsfragen). Empfehlung: `rolePlayed(r)` (irgendein Match mit einem Helden der Rolle), `roleNeed(r)`, Ausblenden in `state.app.roleSkip[r]`.
Match-Aufgaben: `heroTasks(h)` (bis 8 aus `PROF[h].tipps`, `ue` «Wann» und «Wo/Wie», erstem eigenen Team-Up, `ue` «Typischer Fehler») und `roleTasks(r)` (aus `ROLE_TIPS`). Antworten stehen im Match als `m.tasks["<Held oder R:Rolle>|<aufgabenId>"] = ja|teils|nein`; `taskMastered`: letzte drei Antworten, mindestens zwei, davon mindestens zwei «ja». Aktuell ist die erste nicht gemeisterte Aufgabe (`taskCurrent`); das Match-Log zeigt sie über `renderTaskBox` für den gewählten Helden und dessen Rolle, sobald der Kurs begonnen oder die Aufgaben freigeschaltet sind. `bootMastered`: Test bestanden und alle Aufgaben gemeistert. Regeln: Aufgaben nur aus geprüften Profildaten ableiten, nichts erfinden; die Antwort ist Selbstauskunft. Tests: `t76.js`.

## Grundregeln und «läuft von allein»
Code: Abschnitt «Grundregeln» in `index.html` (`activeRules`, `ruleEvidence`, `renderRuleBox`, `rulesCardHtml`, `fadeLevel`, `stepBodyHtml`). Idee: Themen aus dem Plan laufen als höchstens vier Grundregeln im Hintergrund mit; nach jedem Match die Rückwärts-Frage «ohne es dir vorzunehmen?» (`m.rules[themaId]` = auto|bewusst|nein). `topicAuto` bevorzugt ab 3 Antworten die letzten 5 vor der Selbsteinschätzung am Tagesende (so gibt es einen Rückfall, wenn es doch nicht sitzt). Hilfen werden ab Tag 43 gekürzt, ab Tag 50 eingeklappt (abschaltbar). Das ist eine Selbstauskunft, keine Messung; Wirkung auf Marvel Rivals nicht belegt. Test: `t72.js`.
Plantag pro Datum: `guessPlanDay(date)` (rät aus den `done`-Daten der Plantage, überspringt abgehakte, aber nicht erledigte Tage, wenn danach ein Tag erledigt wurde), `state.plan.dayByDate[date]` (selbst festgelegt, 0 = freies Spiel), `planDayOf`, `rulesForDay(n)` (Thema des Tages zuerst, dann Wiederholung, dann Grundregeln, höchstens `RULE_MAX + 1`), Auswahl `#matchDay` im Match-Log. Das ist eine Schätzung: Sie ist nur so gut wie die als erledigt markierten Tage, deshalb ist sie immer sichtbar und änderbar. Über das Dokument `sync-inbox` kann Claude Plantage setzen: `{planDays: {"2026-10-17": 6}}` (0 = freies Spiel), ungültige Einträge werden ignoriert. Test: `t79.js`, `t78.js`.

## Verlauf (Tage, Wochen, Phasen vergleichen)
Code: Abschnitt «Verlauf» in `index.html` (`progSegments`, `progStats`, `PROG_METRICS`, `progDelta`, `progBase`/`progNow`, `progCompareTable`, `progLine`, `renderProgress`), Seite `progress` im Bereich «Spielen». Die Einteilung (Tag, Woche, Phase) kommt aus `planDayOf`; Matches ohne Plantag (freies Spiel) bilden einen eigenen Abschnitt. Alle Zahlen kommen aus `summary()` und den Match-Feldern, es gibt kein neues Spielwissen. Ehrlichkeit vor Schönheit: Unter `PROG_MIN_N` (5) Matches oder unter 3 Antworten gibt es kein Urteil («unsicher», hohler Punkt im Diagramm), kleine Unterschiede zählen als gleich (Toleranzen pro Kennzahl in `PROG_METRICS`). «Auf einen Blick» vergleicht die Baseline (Tag 1, sonst die ersten 10 Matches) mit den letzten 10 Matches, die nicht zur Baseline gehören. Test: `t80.js`.

## Die App selbst lernen (Einführung)
Code: Abschnitt «Die App langsam kennenlernen» in `index.html` (`PAGE_HELP`, `renderPageHelp`, `APP_TOUR`, `tourCardHtml`, `TEAM_STEPS`, `applyTeamView`). Prinzipien: immer nur ein bis zwei Schritte zeigen (Überforderung vermeiden), Erledigtes selbst erkennen (`state.app.seen`), Hilfen von selbst zurücknehmen (Seitenhilfe klappt nach zwei Besuchen zu), Experten dürfen alles sehen («Alles zeigen»). Neue Seiten mit vielen Karten bekommen `data-tstep` oder einen Eintrag in `PAGE_HELP`. Texte erklären nur die App, keine Spielfakten. Test: `t75.js`.

