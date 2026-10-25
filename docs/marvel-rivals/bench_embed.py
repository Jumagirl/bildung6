#!/usr/bin/env python3
"""Bettet die Vergleichswerte in die App ein (zwischen /*TOPB_START*/ und /*TOPB_END*/ in app/index.html): Rangbänder und Rangverteilung,
die Werte der Besten und, falls angegeben, die Werte pro Rang über die ganze Rangleiter (``rank_bench_aggregate.py``).

Benutzung:
    python bench_embed.py rank_data.json top_bench.json [rank_bench.json] [app/index.html]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(rank_path: str, bench_path: str, *rest: str) -> int:
    ladder_path = next((a for a in rest if a.endswith(".json")), None)
    html_path = next((a for a in rest if a.endswith(".html")), "app/index.html")
    rank = json.loads(Path(rank_path).read_text(encoding="utf-8"))
    bench = json.loads(Path(bench_path).read_text(encoding="utf-8"))
    data = {"stand": min(rank["stand"], bench["stand"]) if rank.get("stand") and bench.get("stand") else rank.get("stand"),
            "source": rank.get("source"), "bands": rank["bands"], "mu": rank["matchups"], "ranks": rank["ranks"], "rankTotal": rank.get("rankTotal"),
            "bench": bench}
    if ladder_path:
        data["ladder"] = json.loads(Path(ladder_path).read_text(encoding="utf-8"))
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    p = Path(html_path)
    s = p.read_text(encoding="utf-8")
    a, b = s.index("/*TOPB_START*/") + len("/*TOPB_START*/"), s.index("/*TOPB_END*/")
    p.write_text(s[:a] + payload + s[b:], encoding="utf-8")
    print(f"{len(payload) // 1024} KB eingebettet in {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
