"""Lazy FontTools state must never be accessed concurrently by request threads."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import glyph_service


def test_cold_font_load_and_draws_are_serialized(tmp_path, monkeypatch):
    (tmp_path / 'Jigmo.ttf').touch()
    chars = list('日月木火金土水山')
    gate = threading.Barrier(len(chars))
    state_lock = threading.Lock()
    state = {'opens': 0, 'active': 0, 'maximum': 0}

    class Glyph:
        def draw(self, pen):
            pen.moveTo((0, 0))
            pen.lineTo((1, 0))
            pen.lineTo((1, 1))
            pen.closePath()

    class Font:
        def __init__(self, *args, **kwargs):
            with state_lock:
                state['opens'] += 1

        def getBestCmap(self):
            return {ord(char): char for char in chars}

        def getGlyphSet(self):
            with state_lock:
                state['active'] += 1
                state['maximum'] = max(state['maximum'], state['active'])
            # Model a lazy table read releasing the GIL while seeking/reading.
            time.sleep(0.005)
            with state_lock:
                state['active'] -= 1
            return {char: Glyph() for char in chars}

    monkeypatch.setattr(glyph_service, 'TTFont', Font)
    manager = glyph_service._JigmoFontManager(tmp_path)

    def draw(char):
        gate.wait(timeout=5)
        return manager.get_path(char)

    with ThreadPoolExecutor(max_workers=len(chars)) as pool:
        paths = list(pool.map(draw, chars))
    assert all(path == paths[0] and path for path in paths)
    assert state['opens'] == 1
    assert state['maximum'] == 1


def test_failed_load_closes_partial_fonts_and_can_retry(tmp_path, monkeypatch):
    (tmp_path / 'Jigmo.ttf').touch()
    (tmp_path / 'Jigmo2.ttf').touch()
    failure = [True]
    closed = []

    class Font:
        def __init__(self, path, **kwargs):
            self.path = path

        def getBestCmap(self):
            if failure[0] and self.path.endswith('Jigmo2.ttf'):
                raise OSError('incomplete font')
            return {}

        def close(self):
            closed.append(self.path)

    monkeypatch.setattr(glyph_service, 'TTFont', Font)
    manager = glyph_service._JigmoFontManager(tmp_path)
    import pytest
    with pytest.raises(OSError):
        manager.get_path('日')
    assert len(closed) == 2
    failure[0] = False
    assert manager.get_path('日') is None
