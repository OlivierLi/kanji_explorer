"""Tests for view_renderer and /view endpoint supporting 2D Sumi-Ink Calligraphy canvas."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import urllib.request
import pytest

import server
import view_renderer


@pytest.fixture(scope="module")
def live_server():
    """テスト用の一時的ThreadingHTTPServerインスタンスをエフェメラルポートで起動."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.KanjiExplorerHandler)
    host, port = httpd.server_address
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://{host}:{port}"
    yield base_url

    httpd.shutdown()
    httpd.server_close()


class TestViewRendererSumiCanvas:
    """view_renderer.py の 2D <canvas> 墨絵書道エンジン連携テスト."""

    def test_tile0_and_tile_components_contain_sumi_canvas(self):
        """KanjiVG モード時に Tile 0 および各部品タイルに calligraphy-sumi-canvas が含まれること."""
        meta = {
            "codepoint": "U+540D",
            "stroke_count": 6,
            "radical": "口",
            "grade": 1,
        }
        html_out = view_renderer.render_side_by_side_html("名", meta, {"mode": ["kvg"]})

        # Tile 0: data-tile-mode="all"
        assert '<canvas class="calligraphy-sumi-canvas audit-sumi-canvas" width="792" height="792" data-tile-mode="all"></canvas>' in html_out
        assert '<svg viewBox="0 0 109 109" class="kvg-svg has-sumi-canvas">' in html_out
        # Tile 0 SVG 内の既存要素が維持されていること
        assert '<g class="kvg-root">' in html_out
        assert 'class="kvg-stroke calligraphic-stroke"' in html_out

        # 部品タイル: data-tile-mode="highlight" と data-active-ids
        assert '<canvas class="calligraphy-sumi-canvas audit-sumi-canvas" width="792" height="792" data-tile-mode="highlight"' in html_out
        assert 'data-active-ids=' in html_out
        assert '<g class="kvg-bg-strokes"' in html_out
        assert '<g class="kvg-active-strokes"' in html_out

    def test_audit_strokes_serialization_and_script(self):
        """window.AUDIT_KVG_STROKES に KanjiVG ストローク情報がシリアライズされ app.js が読み込まれること."""
        meta = {"codepoint": "U+6728", "stroke_count": 4}
        html_out = view_renderer.render_side_by_side_html("木", meta, {"mode": ["kvg"]})

        assert "window.AUDIT_KVG_STROKES = [" in html_out
        assert '<script src="/static/app.js"></script>' in html_out
        assert "if (window.renderAllAuditCanvases) window.renderAllAuditCanvases();" in html_out

        # JSONシリアライズの中身検証
        match = re.search(r"window\.AUDIT_KVG_STROKES\s*=\s*(\[[\s\S]*?\]);", html_out)
        assert match is not None
        strokes_data = json.loads(match.group(1))
        assert len(strokes_data) > 0
        for s in strokes_data:
            assert "id" in s
            assert "d" in s
            assert "adjusted_d" in s
            assert "role_hint" in s
            assert "type" in s
            assert "component" in s

    def test_style_positioning_rules(self):
        """view_renderer 内のスタイルで position: relative / z-index が正しく設定されていること."""
        meta = {"codepoint": "U+6728"}
        html_out = view_renderer.render_side_by_side_html("木", meta, {})

        assert ".audit-card-stage .canvas-svg-container" in html_out
        assert "position: relative;" in html_out
        assert ".audit-card-stage .kvg-svg" in html_out
        assert "z-index: 2;" in html_out

    def test_mincho_mode_retains_print_vectors(self):
        """明朝体モード時は canvas を挿入せずベクター分解SVGが正しく出力されること."""
        meta = {"codepoint": "U+6728"}
        html_out = view_renderer.render_side_by_side_html("木", meta, {"mode": ["mincho"]})
        assert "print-style-svg" in html_out
        assert "print-base-glyph" in html_out


class TestStylesCssSumiCanvas:
    """static/styles.css の 2D <canvas> 墨絵書道エンジン対応CSS定義テスト."""

    def test_css_classes_defined(self):
        css_path = Path(__file__).resolve().parent.parent / "static" / "styles.css"
        css_text = css_path.read_text(encoding="utf-8")

        # .canvas-svg-container position: relative
        assert ".canvas-svg-container" in css_text
        assert "position: relative;" in css_text

        # .calligraphy-sumi-canvas
        assert ".calligraphy-sumi-canvas" in css_text
        assert "position: absolute;" in css_text
        assert "pointer-events: none;" in css_text
        assert "z-index: 1;" in css_text

        # .canvas-svg-container svg position: relative; z-index: 2;
        assert ".canvas-svg-container svg" in css_text

        # .has-sumi-canvas 透過ルール
        assert ".has-sumi-canvas .kvg-stroke.calligraphic-stroke" in css_text
        assert "fill-opacity: 0 !important;" in css_text
        assert "filter: none !important;" in css_text


class TestViewLiveEndpoint:
    """/view エンドポイントの統合レスポンステスト."""

    def test_view_endpoint_kvg_mode(self, live_server):
        url = f"{live_server}/view?char=%E5%90%8D&mode=kvg"
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "text/html" in content_type
            body = resp.read().decode("utf-8")
            assert "audit-sumi-canvas" in body
            assert "window.AUDIT_KVG_STROKES" in body
            assert '<script src="/static/app.js"></script>' in body
