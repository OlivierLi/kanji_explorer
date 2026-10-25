"""各モジュールの組み込み診断メイン関数（main / self-test）の回帰テスト."""

import ids_parser
import glyph_service
import server


def test_ids_parser_main(capsys):
    ids_parser.main()
    captured = capsys.readouterr()
    assert "すべての検証テストに正常に合格しました。" in captured.out


def test_glyph_service_main(capsys):
    glyph_service.main()
    captured = capsys.readouterr()
    assert "すべての要件検証に100%合格しました。" in captured.out


def test_server_run_internal_self_tests():
    success = server.run_internal_self_tests()
    assert success is True
