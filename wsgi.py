"""WSGI エントリーポイント (PythonAnywhere, Gunicorn, uWSGI 互換).

PythonAnywhere の Web アプリ設定から直接読み込むためのエントリーポイントです。
WSGI サーバーは `from wsgi import application` をインポートしてリクエストをディスパッチします。
"""

import sys
from pathlib import Path

# プロジェクトルートディレクトリを sys.path に追加
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from server import application

__all__ = ["application"]
