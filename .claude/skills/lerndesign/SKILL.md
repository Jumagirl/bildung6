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

## Fallstricke
- Abrufen ohne Antwortkontrolle; Abstände zu gross; nur Leichtes üben; Wissens-Check nur zu den Themen von heute.
- Neues Wissen nur dann einbauen, wenn es belegt ist. Keine erfundenen Spielfakten, keine Zahlen ausser aus den Patch-Notes von Season 10 und 10.5.

## Wo es in der App steckt
`docs/marvel-rivals/app/index.html`: Abschnitt «Wiederholungs-System, Zwischenstopps in den Blöcken, Rückblick» (`leitner`, `nugQuestion`, `recallNugHtml`, `tipNugHtml`, `whyNugHtml`, `reflectionHtml`), `startKnow` (gemischter Tages-Check), `renderKnow` (Sicherheit). Beschreibung für Nutzer: `docs/marvel-rivals/index.md`, Abschnitt «Lernmethoden hinter der App».

## Schreibregeln
Deutsch, Schweizer Schreibung (immer «ss», nie «ß»), Du-Form, kurze Sätze, Fachwörter beim ersten Mal erklären, Namen von Helden, Fähigkeiten und Karten englisch wie im Spiel.
