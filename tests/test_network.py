from unittest.mock import patch

import requests

from paperman.utils.network import HTTPClient, _load_proxy


def test_http_client_default_headers():
    client = HTTPClient()
    ua = client.sess.headers.get("User-Agent", "")
    assert "Paperman" in ua
    assert client.sess.headers.get("Accept", "") != ""


def test_http_client_no_proxy_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", tmp_path / "nonexistent.ini")
    client = HTTPClient()
    assert client.sess.proxies == {}


def test_http_client_reload_proxy(tmp_path, monkeypatch):
    cfg = tmp_path / "config.ini"
    cfg.write_text("[settings]\nproxy = socks5://127.0.0.1:1080\n")
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", cfg)
    client = HTTPClient()
    assert "socks5://127.0.0.1:1080" in str(client.sess.proxies)


def test_http_client_reload_clears_proxy(tmp_path, monkeypatch):
    cfg = tmp_path / "config.ini"
    cfg.write_text("[settings]\n")
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", cfg)
    client = HTTPClient()
    client.reload_proxy()
    assert client.sess.proxies == {}


def test_load_proxy_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", tmp_path / "nonexistent.ini")
    assert _load_proxy() == ""


def test_load_proxy_with_value(tmp_path, monkeypatch):
    cfg = tmp_path / "config.ini"
    cfg.write_text("[settings]\nproxy = http://proxy:8080\n")
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", cfg)
    assert _load_proxy() == "http://proxy:8080"


def test_load_proxy_corrupted_file(tmp_path, monkeypatch):
    cfg = tmp_path / "config.ini"
    cfg.write_text("not valid ini \x00 content")
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", cfg)
    assert _load_proxy() == ""


def test_http_get_returns_none_on_error(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", tmp_path / "nonexistent.ini")
    client = HTTPClient()
    with patch.object(client.sess, "get", side_effect=requests.RequestException("fail")):
        assert client.get("https://example.com") is None


def test_http_head_returns_none_on_error(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", tmp_path / "nonexistent.ini")
    client = HTTPClient()
    with patch.object(client.sess, "head", side_effect=requests.RequestException("fail")):
        assert client.head("https://example.com") is None


def test_http_post_returns_none_on_error(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", tmp_path / "nonexistent.ini")
    client = HTTPClient()
    with patch.object(client.sess, "post", side_effect=requests.RequestException("fail")):
        assert client.post("https://example.com") is None


def test_http_get_raises_on_4xx(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", tmp_path / "nonexistent.ini")
    client = HTTPClient()
    resp = requests.Response()
    resp.status_code = 404
    resp.url = "https://example.com/404"
    with patch.object(client.sess, "get", return_value=resp):
        result = client.get("https://example.com/404")
        assert result is None


def test_http_head_allows_4xx(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", tmp_path / "nonexistent.ini")
    client = HTTPClient()
    resp = requests.Response()
    resp.status_code = 404
    resp.url = "https://example.com/404"
    with patch.object(client.sess, "head", return_value=resp):
        result = client.head("https://example.com/404")
        assert result is not None
        assert result.status_code == 404


def test_get_passes_kwargs(tmp_path, monkeypatch):
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", tmp_path / "nonexistent.ini")
    client = HTTPClient()
    resp = requests.Response()
    resp.status_code = 200
    resp._content = b"ok"
    with patch.object(client.sess, "get", return_value=resp) as mock:
        client.get("https://example.com", headers={"X-Custom": "value"})
        call_kwargs = mock.call_args[1]
        assert call_kwargs["headers"]["X-Custom"] == "value"


def test_direct_mode_ignores_environment_proxy_and_keeps_ca(tmp_path, monkeypatch):
    cfg = tmp_path / "config.ini"
    cfg.write_text("[settings]\nproxy_mode = direct\nproxy = http://configured:8080\n")
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", cfg)
    monkeypatch.setenv("HTTPS_PROXY", "http://environment:8080")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/tmp/test-ca.pem")
    client = HTTPClient()
    settings = client.sess.merge_environment_settings("https://example.com", {}, False, None, None)
    assert client.sess.trust_env is False
    assert client.sess.proxies == {}
    assert settings["proxies"] == {}
    assert settings["verify"] == "/tmp/test-ca.pem"


def test_reload_can_switch_between_direct_and_auto(tmp_path, monkeypatch):
    cfg = tmp_path / "config.ini"
    cfg.write_text("[settings]\nproxy_mode = direct\n")
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", cfg)
    client = HTTPClient()
    assert client.sess.trust_env is False
    cfg.write_text("[settings]\nproxy_mode = auto\nproxy = http://configured:8080\n")
    client.reload_proxy()
    assert client.sess.trust_env is False
    assert client.sess.proxies["https"] == "http://configured:8080"

def test_explicit_proxy_wins_over_environment(tmp_path, monkeypatch):
    cfg = tmp_path / "config.ini"
    cfg.write_text("[settings]\nproxy_mode=auto\nproxy=http://configured:8080\n")
    monkeypatch.setattr("paperman.utils.network.CONFIG_PATH", cfg)
    monkeypatch.setenv("HTTPS_PROXY", "http://environment:9999")
    client = HTTPClient()
    settings = client.sess.merge_environment_settings("https://example.org", {}, False, None, None)
    assert settings["proxies"]["https"] == "http://configured:8080"
