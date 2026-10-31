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
            assert "探索例:" not in body
            assert "U+4E2D" in body

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
            assert "font/ttf" in resp.headers.get("Content-Type", "")
            cache_control = resp.headers.get("Cache-Control", "")
            assert "max-age=31536000" in cache_control
            assert "immutable" in cache_control
            assert resp.headers.get("ETag") is not None
            assert resp.headers.get("Last-Modified") is not None

    def test_font_caching_and_conditional_request(self, live_server):
        url = f"{live_server}/static/fonts/Jigmo.ttf"
        with urllib.request.urlopen(url) as resp:
            etag = resp.headers.get("ETag")
            assert etag is not None

        # If-None-Match による 304 Not Modified 検証
        req = urllib.request.Request(url, headers={"If-None-Match": etag})
        try:
            with urllib.request.urlopen(req) as resp:
                assert resp.status == 304
        except urllib.error.HTTPError as e:
            assert e.code == 304
            assert e.headers.get("ETag") == etag
            assert "max-age=31536000" in e.headers.get("Cache-Control", "")

    def test_root_contains_credits_modal(self, live_server):
        with urllib.request.urlopen(f"{live_server}/") as resp:
            assert resp.status == 200
            html_text = resp.read().decode("utf-8")
            assert "creditsModal" in html_text
            assert "btnCreditsModal" in html_text
            assert "出典・ライセンス" in html_text


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

    def test_api_words_component_exploration_for_radical_symbol(self, live_server):
        """非漢字構成要素（部首「𭕄」など）選択時に包含漢字の熟語（学校 等）が自動返却されること."""
        url = f"{live_server}/api/words?kanji=%F0%AD%95%84"  # 𭕄 (U+2D544)
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("kanji") == "𭕄"
            assert data.get("is_component_search") is True
            assert data.get("scope") == "all"
            assert data.get("total", 0) > 1000

            results = data.get("results", [])
            assert len(results) > 0
            lemmas = [r["lemma"] for r in results]

            # 𭕄 を含む「学」「単」「覚」等の熟語が含まれること
            assert "学校" in lemmas
            assert "簡単" in lemmas
            assert "大学" in lemmas
            assert "覚える" in lemmas

            # 「学校」の matched_kanji が「学」として記録されていること
            gakko_item = next(r for r in results if r["lemma"] == "学校")
            assert "学" in gakko_item["matched_kanji"]
            assert "学" in gakko_item["matched_kanjis"]
            assert gakko_item["position_type"] == "head"
            assert gakko_item["has_direct_kanji"] is False
            assert "学" in gakko_item["carrier_kanjis"]

    def test_api_words_both_direct_kanji_and_subparts_for_kanji(self, live_server):
        """「缶」選択時に、漢字直接熟語（缶、空き缶 等）と部品として含む熟語（鬱病 等）の双方が返却されること."""
        url = f"{live_server}/api/words?kanji=%E7%BC%B6"  # 缶 (U+7F36)
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("kanji") == "缶"
            assert data.get("scope") == "all"
            assert data.get("is_component_search") is True
            assert data.get("summary", {}).get("direct", 0) > 0
            assert data.get("summary", {}).get("carrier", 0) > 0

            results = data.get("results", [])
            lemmas = [r["lemma"] for r in results]

            # 漢字直接熟語および下位部品熟語（鬱病）が共存すること
            assert "缶" in lemmas
            assert "鬱病" in lemmas

            kan_item = next(r for r in results if r["lemma"] == "缶")
            assert kan_item["has_direct_kanji"] is True
            assert kan_item["carrier_kanjis"] == []

            utsu_item = next(r for r in results if r["lemma"] == "鬱病")
            assert utsu_item["has_direct_kanji"] is False
            assert "鬱" in utsu_item["carrier_kanjis"]

    def test_api_words_component_position_filters(self, live_server):
        """部首探索時の出現位置フィルタ（語頭・語尾）の適合性検証."""
        # 語頭(head)
        url_head = f"{live_server}/api/words?kanji=%F0%AD%95%84&position=head"
        with urllib.request.urlopen(url_head) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            lemmas = [r["lemma"] for r in data.get("results", [])]
            assert "学校" in lemmas
            for r in data.get("results", []):
                assert r["position_type"] == "head"

        # 語尾(tail)
        url_tail = f"{live_server}/api/words?kanji=%F0%AD%95%84&position=tail"
        with urllib.request.urlopen(url_tail) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            lemmas = [r["lemma"] for r in data.get("results", [])]
            assert "大学" in lemmas or "簡単" in lemmas
            for r in data.get("results", []):
                assert r["position_type"] == "tail"

    def test_api_words_explicit_scope_modes(self, live_server):
        """明示的スコープ指定（component / direct）の動作切り替え検証."""
        # 「木」を部首として含む熟語探索（校、森、林 などを含む学校、森林等）
        url_comp = f"{live_server}/api/words?kanji=%E6%9C%A8&scope=component"
        with urllib.request.urlopen(url_comp) as resp:
            data_comp = json.loads(resp.read().decode("utf-8"))
            assert data_comp["scope"] == "component"
            assert data_comp["is_component_search"] is True
            lemmas_comp = [r["lemma"] for r in data_comp.get("results", [])]
            assert "学校" in lemmas_comp  # 「校」が木を含む

        # 「木」の直接熟語探索（木材、樹木等）
        url_direct = f"{live_server}/api/words?kanji=%E6%9C%A8&scope=direct"
        with urllib.request.urlopen(url_direct) as resp:
            data_direct = json.loads(resp.read().decode("utf-8"))
            assert data_direct["scope"] == "direct"
            assert data_direct["is_component_search"] is False
            lemmas_direct = [r["lemma"] for r in data_direct.get("results", [])]
            assert "学校" not in lemmas_direct
            assert "木材" in lemmas_direct or "樹木" in lemmas_direct

        # 「木」の scope=all（直接＋部品包含の全結合）
        url_all = f"{live_server}/api/words?kanji=%E6%9C%A8&scope=all"
        with urllib.request.urlopen(url_all) as resp:
            data_all = json.loads(resp.read().decode("utf-8"))
            assert data_all["scope"] == "all"
            assert data_all["is_component_search"] is True
            assert data_all["total"] > data_direct["total"]

    def test_api_words_sanzui_radical_exploration(self, live_server):
        """さんずい部首（氵）による熟語探索で包含漢字熟語が返却されること."""
        url = f"{live_server}/api/words?kanji=%E6%B0%B5"  # 氵
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["is_component_search"] is True
            assert data["scope"] == "all"
            assert data["total"] > 1000


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



