"""Reproduce review glyph findings; run from repository root."""
import json
from pathlib import Path
import sys
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from scripts.fuzz import raster


def character(char):
    status = []
    body = server.application({
        "REQUEST_METHOD": "GET", "PATH_INFO": "/api/char",
        "QUERY_STRING": urlencode({"q": char}),
    }, lambda s, h: status.append(s))
    assert status == ["200 OK"], status
    return json.loads(b"".join(body))


for char in ["日", "目"]:
    data = character(char)
    visual = data["visual"]["interactive_svg"]
    _, masks = raster.compute_all_layer_masks(char, visual)
    print("ENCLOSURE", char, "shared_pixels", int((masks["0.0"] & masks["0.1"]).sum()),
          "inner_pixels", int(masks["0.1"].sum()))

mapping = character("麟")["visual"]["layer_strokes"]
for path in ["0.0.1", "0.0.1.0", "0.0.1.1"]:
    print("KVG", path, mapping[path])
