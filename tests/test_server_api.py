"""server.py のHTTP APIエンドポイント網羅的テストスイート."""

import json
import threading
from typing import Any
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer

import pytest

import server


@pytest.fixture(scope="module")
def live_server():
    """テスト用の一時的ThreadingHTTPServerインスタンスをエフェメラルポートで起動."""
    # port 0 でOSに空きポートを自動割り当てさせる
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.KanjiExplorerHandler)
    host, port = httpd.server_address
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://{host}:{port}"
    yield base_url

    httpd.shutdown()
    httpd.server_close()


class TestStaticEndpoints:
    """静的アセット配信エンドポイント."""

    def test_root_html(self, live_server):
        with urllib.request.urlopen(f"{live_server}/") as resp:
            assert resp.status == 200
            assert "text/html" in resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8")
            assert "<!DOCTYPE html>" in body
            assert "canvasSvgContainer" in body

    def test_styles_css(self, live_server):
        with urllib.request.urlopen(f"{live_server}/static/styles.css") as resp:
            assert resp.status == 200
            assert "text/css" in resp.headers.get("Content-Type", "")

    def test_app_js(self, live_server):
        with urllib.request.urlopen(f"{live_server}/static/app.js") as resp:
            assert resp.status == 200
            assert "javascript" in resp.headers.get("Content-Type", "")

    def test_jigmo_font(self, live_server):
        with urllib.request.urlopen(f"{live_server}/static/fonts/Jigmo.ttf") as resp:
            assert resp.status == 200
            assert "font" in resp.headers.get("Content-Type", "").lower() or resp.status == 200


class TestApiGlyph:
    """/api/glyph エンドポイント."""

    def test_api_glyph_single_char(self, live_server):
        url = f"{live_server}/api/glyph?c=%E8%9B%8D"  # 蛍
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            assert "image/svg+xml" in resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8")
            assert body.startswith("<svg")

    def test_api_glyph_entity(self, live_server):
        url = f"{live_server}/api/glyph?c=%26CDP-8BD9%3B"
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert body.startswith("<svg")

    def test_api_glyph_missing_param_returns_400(self, live_server):
        url = f"{live_server}/api/glyph"
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(url)
        assert exc_info.value.code == 400


class TestApiCharAndCharacter:
    """/api/char および /api/character エンドポイント."""

    def test_api_char_query(self, live_server):
        url = f"{live_server}/api/char?q=%E8%9B%8D"  # 蛍
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("meta", {}).get("char") == "蛍"
            assert "tree" in data
            assert "visual" in data
            assert "interactive_svg" in data["visual"]

    def test_api_character_alias(self, live_server):
        url = f"{live_server}/api/character?c=%E6%9C%A8"  # 木
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("meta", {}).get("char") == "木"

    def test_api_char_missing_query_returns_400(self, live_server):
        url = f"{live_server}/api/char"
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(url)
        assert exc_info.value.code == 400


class TestApiIdsFind:
    """/api/ids-find エンドポイント."""

    def test_find_by_components(self, live_server):
        # 𭕄 (U+2D544) と 虫 を含む漢字（蛍）の検索
        url = f"{live_server}/api/ids-find?components=%F0%AD%95%84&components=%E8%99%AB&hierarchy=indirect"
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "results" in data
            chars = [r.get("char") for r in data["results"]]
            assert "蛍" in chars

    def test_find_by_reading(self, live_server):
        url = f"{live_server}/api/ids-find?q=%E3%81%BB%E3%81%9F%E3%82%8B"  # ほたる
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "results" in data
            chars = [r.get("char") for r in data["results"]]
            assert "蛍" in chars


class TestHttpMethodsAndErrors:
    """CORS、OPTIONS、HEAD、404ハンドリング."""

    def test_options_cors(self, live_server):
        req = urllib.request.Request(f"{live_server}/api/char?q=%E6%9C%A8", method="OPTIONS")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 204
            assert resp.headers.get("Access-Control-Allow-Origin") == "*"

    def test_head_request(self, live_server):
        req = urllib.request.Request(f"{live_server}/", method="HEAD")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            body = resp.read()
            assert len(body) == 0

    def test_not_found_404(self, live_server):
        url = f"{live_server}/nonexistent/path/xyz"
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(url)
        assert exc_info.value.code == 404

    def test_side_by_side_view_endpoint(self, live_server):
        url = f"{live_server}/view?char=%E5%90%8D"
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            assert "text/html" in resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8")
            assert "名" in body
            assert "audit-card" in body
            assert ("kvg-svg" in body or "print-style-svg" in body)

        url_mincho = f"{live_server}/view?char=%E5%90%8D&mode=mincho"
        with urllib.request.urlopen(url_mincho) as resp:
            assert resp.status == 200
            body_mincho = resp.read().decode("utf-8")
            assert "print-style-svg" in body_mincho
            assert "component-vector-layer" in body_mincho

    def test_side_by_side_view_path_param(self, live_server):
        url = f"{live_server}/view/%E5%90%8D?theme=light"
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            body = resp.read().decode("utf-8")
            assert 'data-theme="light"' in body
            assert 'mode=kvg&theme=light' in body
            assert 'mode=mincho&theme=light' in body
            assert '<input type="hidden" name="theme" value="light">' in body


class TestApiWords:
    """/api/words 熟語・語彙検索エンドポイント."""

    def test_api_words_query_success(self, live_server):
        url = f"{live_server}/api/words?kanji=%E8%9B%8D"  # 蛍
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            assert "application/json" in resp.headers.get("Content-Type", "")
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("kanji") == "蛍"
            assert data.get("total", 0) >= 10
            assert "summary" in data
            assert "results" in data

            results = data["results"]
            lemmas = [r["lemma"] for r in results]
            assert "蛍" in lemmas
            assert "蛍光灯" in lemmas

            # 頻度降順（BCCWJ順位昇順）の検証
            ranks = [r["frequency_rank"] for r in results if r.get("frequency_rank") is not None]
            assert ranks == sorted(ranks)
            assert ranks[0] < ranks[-1]

            # 語釈および日本語メタデータの検証
            top_item = results[0]
            assert top_item["lemma"] in ("蛍", "蛍光灯")
            assert top_item["pos"] in ("名詞", "字義")
            assert len(top_item["definition"]) > 0

    def test_api_words_missing_kanji_returns_400(self, live_server):
        url = f"{live_server}/api/words"
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(url)
        assert exc_info.value.code == 400

    def test_api_words_position_filter(self, live_server):
        url = f"{live_server}/api/words?kanji=%E8%9B%8D&position=tail"
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            for r in data.get("results", []):
                assert r["position_type"] == "tail"
            lemmas = [r["lemma"] for r in data.get("results", [])]
            assert "海蛍" in lemmas

    def test_api_words_tier_filter(self, live_server):
        url = f"{live_server}/api/words?kanji=%E8%9B%8D&tier=high"
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            for r in data.get("results", []):
                assert r["frequency_tier"] in ("最頻出", "頻出")

    def test_api_words_keyword_filter(self, live_server):
        url = f"{live_server}/api/words?kanji=%E8%9B%8D&keyword=%E3%83%9A%E3%83%B3"  # ペン
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            lemmas = [r["lemma"] for r in data.get("results", [])]
            assert "蛍光ペン" in lemmas

    def test_api_words_fallback_structure(self):
        fallback = server.query_words_fallback("蛍")
        assert fallback["kanji"] == "蛍"
        assert fallback["total"] == 0
        assert fallback["results"] == []
        assert "summary" in fallback


class TestWSGIApplication:
    """WSGI エントリーポイント (wsgi.py / server.application) の適合性テスト."""

    def _make_environ(self, path: str = "/", query: str = "", method: str = "GET") -> dict[str, Any]:
        import io
        return {
            "REQUEST_METHOD": method,
            "SCRIPT_NAME": "",
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": "http",
            "wsgi.input": io.BytesIO(),
            "wsgi.errors": io.StringIO(),
            "wsgi.multithread": True,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
            "SERVER_NAME": "localhost",
            "SERVER_PORT": "80",
        }

    def test_wsgi_module_export(self):
        import wsgi
        assert hasattr(wsgi, "application")
        assert callable(wsgi.application)

    def test_wsgi_root_get(self):
        status_box = []
        headers_box = []

        def start_response(status, headers, exc_info=None):
            status_box.append(status)
            headers_box.extend(headers)

        environ = self._make_environ(path="/")
        body_chunks = server.application(environ, start_response)
        body = b"".join(body_chunks).decode("utf-8")

        assert status_box[0].startswith("200")
        assert "<!DOCTYPE html>" in body
        assert any(k.lower() == "content-type" and "text/html" in v for k, v in headers_box)

    def test_wsgi_api_char_get(self):
        status_box = []
        headers_box = []

        def start_response(status, headers, exc_info=None):
            status_box.append(status)
            headers_box.extend(headers)

        environ = self._make_environ(path="/api/char", query="q=%E8%9B%8D")
        body_chunks = server.application(environ, start_response)
        data = json.loads(b"".join(body_chunks).decode("utf-8"))

        assert status_box[0].startswith("200")
        assert data.get("meta", {}).get("char") == "蛍"

    def test_wsgi_api_words_get(self):
        status_box = []
        headers_box = []

        def start_response(status, headers, exc_info=None):
            status_box.append(status)
            headers_box.extend(headers)

        environ = self._make_environ(path="/api/words", query="kanji=%E8%9B%8D")
        body_chunks = server.application(environ, start_response)
        data = json.loads(b"".join(body_chunks).decode("utf-8"))

        assert status_box[0].startswith("200")
        assert data.get("kanji") == "蛍"
        assert len(data.get("results", [])) > 0

    def test_wsgi_not_found(self):
        status_box = []

        def start_response(status, headers, exc_info=None):
            status_box.append(status)

        environ = self._make_environ(path="/api/nonexistent")
        body_chunks = server.application(environ, start_response)
        data = json.loads(b"".join(body_chunks).decode("utf-8"))

        assert status_box[0].startswith("404")
        assert "error" in data

    def test_wsgi_method_not_allowed(self):
        status_box = []

        def start_response(status, headers, exc_info=None):
            status_box.append(status)

        environ = self._make_environ(path="/api/char", method="POST")
        body_chunks = server.application(environ, start_response)
        data = json.loads(b"".join(body_chunks).decode("utf-8"))

        assert status_box[0].startswith("405")
        assert "error" in data



