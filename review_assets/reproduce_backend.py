"""Print confirmed review failures against the current local data (read-only).

Run from repository root: python3 review_assets/reproduce_backend.py
These are defect reproductions, not assertions that the behavior is correct.
"""
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from scripts.build_words_db import map_pos_title


def get(path, **params):
    statuses = []
    body = server.application({
        "REQUEST_METHOD": "GET", "PATH_INFO": path,
        "QUERY_STRING": urlencode(params),
    }, lambda status, headers: statuses.append(status))
    assert statuses == ["200 OK"], statuses
    raw = b"".join(body).decode()
    return json.loads(raw) if path.startswith("/api/") else raw


for reading, expected in [("たべる", "食"), ("よむ", "読"), ("しこめ", "嫫")]:
    result = get("/api/ids-find", components=reading, limit=500)
    chars = [r["char"] for r in result["results"]]
    print("READING", reading, "total", result["total"], "expected", expected,
          "present", expected in chars, "results", chars)

result = get("/api/ids-find", components="食", mode="indirect", limit=500)
print("INDIRECT_COUNT", "advertised", result["total"], "returned", len(result["results"]))
print("POS_MAP", [(p, map_pos_title(p)) for p in ["形容動詞", "感動詞"]])
words = get("/api/words", kanji="大", keyword="大切", scope="direct")
print("WORD_POS", [(w["lemma"], w["pos"]) for w in words["results"] if w["lemma"] == "大切"])
meta = get("/api/char", q="嫫")["meta"]
print("ROMANIZED", meta["on_readings"], meta["kun_readings"])
for char in ["蛍", "凜"]:
    print("GRADE", char, re.findall(r"小学[0-9]+年", get("/view", char=char, mode="mincho")))
