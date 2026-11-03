"""HEAD must suppress bodies at the server boundary, including WSGI errors."""
from urllib.parse import urlencode

import pytest

import server


def request(method, path, params):
    responses = []
    body = server.application({'REQUEST_METHOD': method, 'PATH_INFO': path,
                               'QUERY_STRING': urlencode(params)},
                              lambda status, headers: responses.append((status, dict(headers))))
    status, headers = responses[0]
    return status, headers, b''.join(body)


@pytest.mark.parametrize('path,params,status', [
    ('/', {}, '200 OK'), ('/static/styles.css', {}, '200 OK'),
    ('/api/char', {'q': '日'}, '200 OK'), ('/api/glyph', {'c': '日'}, '200 OK'),
    ('/view', {'char': '日'}, '200 OK'), ('/missing', {}, '404 Not Found'),
    ('/api/char', {}, '400 Bad Request'),
])
def test_head_has_get_headers_without_a_response_body(path, params, status):
    get_status, get_headers, body = request('GET', path, params)
    head_status, head_headers, head_body = request('HEAD', path, params)
    assert get_status == head_status == status
    assert body
    assert head_body == b''
    assert head_headers['Content-Type'] == get_headers['Content-Type']
    assert int(head_headers['Content-Length']) == int(get_headers['Content-Length']) == len(body)


def test_head_static_file_is_not_opened_for_streaming(monkeypatch):
    import builtins
    original_open = builtins.open
    target = server.STATIC_DIR / 'styles.css'

    def no_body_read(path, *args, **kwargs):
        if path == target:
            pytest.fail('HEAD should not open the static body for streaming')
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, 'open', no_body_read)
    assert request('HEAD', '/static/styles.css', {})[2] == b''



def test_options_advertises_supported_head_requests():
    status, headers, body = request('OPTIONS', '/', {})
    assert status == '204 No Content'
    assert 'HEAD' in headers['Access-Control-Allow-Methods'].split(', ')
    assert body == b''
