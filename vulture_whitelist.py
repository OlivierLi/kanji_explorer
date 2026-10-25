# vulture whitelist: フレームワークや標準ライブラリによって動的呼出されるシンボル一覧
# HTTPサーバープロトコルおよびsqlite3接続で使用されます。

import sqlite3
import server
from server import KanjiExplorerHandler

# server.KanjiExplorerHandler (BaseHTTPRequestHandler プロトコルオーバーライド)
KanjiExplorerHandler.server_version
KanjiExplorerHandler.do_OPTIONS
KanjiExplorerHandler.do_HEAD

# WSGI エントリーポイント (PythonAnywhere, uWSGI, Gunicorn 等)
server.application
server.WSGIHandlerAdapter

# sqlite3.Connection 属性プロトコル
_conn = sqlite3.connect(":memory:")
_conn.row_factory = sqlite3.Row
_conn.row_factory
