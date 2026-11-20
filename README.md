Automatisch erzeugt vom Workflow «sync» (Rivals Coach). Nicht von Hand ändern, ausser players.txt.
- players.txt: ein Spielername pro Zeile (genau wie bei Rivals Data), Zeilen mit # sind Kommentare
- data/<name>-<prüfwert>.json: die letzten Matches dieses Spielers (öffentliche Daten von Rivals Data)
- data/<name>-<prüfwert>.error.json: nur wenn der letzte Abruf scheiterte
Der Branch hat immer nur einen Commit; jeder Lauf ersetzt ihn.
