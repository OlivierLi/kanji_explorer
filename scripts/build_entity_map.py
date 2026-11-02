#!/usr/bin/env python3
"""CHISE entity to Unicode mapping generator via multi-source IDS alignment.

This script infers mappings from unmapped CHISE XML entity references
(e.g., &AJ1-01904;) to single Unicode characters by aligning IDS representations
across multiple data sources (CHISE IDS datasets in data/chise-ids/ and
data/cjkvi-ids.txt).

When to rerun:
    Rerun this script whenever data/chise-ids/ or data/cjkvi-ids.txt are updated,
    or when rule-based normalization rules change. After generating the updated
    mapping files (data/entity_unicode_map.tsv and data/entity_unicode_review.tsv),
    rebuild the database with scripts/build_db.py (or build_db.py).
"""

from __future__ import annotations

import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ids_parser

IDC = set(ids_parser.IDC_INFO.keys())
CIRCLED = re.compile(r"[\u2460-\u2473]")


def tokenize(ids_str: str) -> list[str]:
    """Tokenize an IDS string using rule-based normalization only (ignoring maps)."""
    return [
        ids_parser.normalize_entity(t, use_maps=False)
        for t in re.findall(r"&[^;]+;|.", ids_str)
        if not t.isspace()
    ]


def collect_sources(
    chise_dir: Path, cjkvi_path: Path
) -> dict[str, list[list[str]]]:
    """Collect tokenized IDS variants per character across CHISE and CJKVI sources."""
    sources: dict[str, list[list[str]]] = defaultdict(list)

    # 1. CHISE IDS files (sorted for determinism)
    for path in sorted(chise_dir.glob("IDS-*.txt")):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith(";;") or not line.strip():
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                # Normalize headword via rule-based normalization only
                ch = ids_parser.normalize_entity(parts[1].strip(), use_maps=False)
                if ch.startswith("&") or len(ch) != 1:
                    continue
                for ids in parts[2:]:
                    ids = re.sub(r"\[.*?\]", "", ids).strip()
                    if ids:
                        sources[ch].append(tokenize(ids))

    # 2. CJKVI IDS file
    if cjkvi_path.is_file():
        with open(cjkvi_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                ch = parts[1].strip()
                if ch.startswith("&") or len(ch) != 1:
                    continue
                for ids in parts[2:]:
                    ids = re.sub(r"\[.*?\]", "", ids).strip()
                    if ids and not CIRCLED.search(ids):
                        sources[ch].append(tokenize(ids))

    return sources


def align_and_vote(
    sources: dict[str, list[list[str]]]
) -> dict[str, Counter[str]]:
    """Align IDS variants for each character and vote on entity -> Unicode mappings."""
    votes: dict[str, Counter[str]] = defaultdict(Counter)

    for ch in sorted(sources.keys()):
        variants = sources[ch]
        for a in variants:
            if not any(t.startswith("&") for t in a):
                continue
            for b in variants:
                if b is a or len(a) != len(b):
                    continue
                pairs: list[tuple[str, str]] | None = []
                for x, y in zip(a, b):
                    if x.startswith("&"):
                        if (
                            len(y) != 1
                            or y.startswith("&")
                            or y in IDC
                            or (0x2460 <= ord(y) <= 0x2473)
                        ):
                            pairs = None
                            break
                        pairs.append((x, y))
                    elif x != y and ids_parser.normalize_component(x) != ids_parser.normalize_component(y):
                        pairs = None
                        break
                if pairs:
                    for x, y in pairs:
                        votes[x][y] += 1

    return votes


def build_entity_map() -> tuple[dict[str, tuple[str, int, float]], dict[str, Counter[str]]]:
    """Run full inference and partition into accepted map and review candidates."""
    chise_dir = ROOT / "data" / "chise-ids"
    cjkvi_path = ROOT / "data" / "cjkvi-ids.txt"

    sources = collect_sources(chise_dir, cjkvi_path)
    votes = align_and_vote(sources)

    accepted: dict[str, tuple[str, int, float]] = {}
    review: dict[str, Counter[str]] = {}

    for ent in sorted(votes.keys()):
        c = votes[ent]
        top, top_cnt = sorted(c.items(), key=lambda item: (-item[1], item[0]))[0]
        total = sum(c.values())
        share = top_cnt / total
        if top_cnt >= 2 and share >= 0.8:
            accepted[ent] = (top, top_cnt, share)
        else:
            review[ent] = c

    return accepted, review


def main() -> None:
    t0 = time.time()
    out_map = ROOT / "data" / "entity_unicode_map.tsv"
    out_review = ROOT / "data" / "entity_unicode_review.tsv"

    accepted, review = build_entity_map()

    # Deterministic, sorted output for accepted mappings
    with open(out_map, "w", encoding="utf-8") as f:
        f.write("entity\tunicode\tvotes\tshare\n")
        for ent in sorted(accepted.keys()):
            char, count, share = accepted[ent]
            f.write(f"{ent}\t{char}\t{count}\t{share:.4f}\n")

    # Deterministic, sorted output for review candidates
    with open(out_review, "w", encoding="utf-8") as f:
        f.write("entity\tcandidates\n")
        for ent in sorted(review.keys()):
            c = review[ent]
            cands_str = ", ".join(
                f"{char}:{cnt}"
                for char, cnt in sorted(c.items(), key=lambda item: (-item[1], item[0]))
            )
            f.write(f"{ent}\t{cands_str}\n")

    elapsed = time.time() - t0
    total_candidates = len(accepted) + len(review)
    print(f"Build completed in {elapsed:.2f}s")
    print(f"Entities with candidates: {total_candidates}")
    print(f"Accepted (votes >= 2, share >= 0.8): {len(accepted)} -> {out_map}")
    print(f"Review candidates: {len(review)} -> {out_review}")


if __name__ == "__main__":
    main()
