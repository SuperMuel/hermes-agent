"""Failed browser teardown remains recoverable and pinned executables are honored."""

import pytest

from tools import browser_tool as bt
from tools import browser_tool_install as install
from tools import browser_tool_lifecycle as lifecycle
from tools import browser_tool_session as session


@pytest.mark.parametrize("force", [False, True])
def test_failed_daemon_kill_retains_tracking_and_socket(tmp_path, monkeypatch, force):
    key = "retained-teardown"
    name = "h_retained"
    socket = tmp_path / f"agent-browser-{name}"
    socket.mkdir()
    (socket / f"{name}.pid").write_text("12345")
    info = {"session_name": name, "bb_session_id": None}
    monkeypatch.setattr(bt, "_active_sessions", {key: info})
    monkeypatch.setattr(bt, "_session_last_activity", {key: 1})
    monkeypatch.setattr(bt, "_session_owner_homes", {key: str(tmp_path)})
    monkeypatch.setattr(bt, "_socket_safe_tmpdir", lambda: str(tmp_path))
    monkeypatch.setattr(lifecycle, "_kill_verified_daemon", lambda *args: False)
    monkeypatch.setattr(lifecycle, "_pid_exists", lambda pid: True)

    with pytest.raises(RuntimeError, match="still alive"):
        if force:
            lifecycle._force_reap_browser_session(key)
        else:
            lifecycle._release_session_resources(key, info)

    assert bt._active_sessions[key] is info
    assert key in bt._session_last_activity
    assert socket.exists()


def test_configured_executable_reaches_scrubbed_command_env(tmp_path, monkeypatch):
    chrome = tmp_path / "chrome"
    chrome.write_text("#!/bin/sh\nexit 0\n")
    chrome.chmod(0o700)
    from hermes_cli import config

    monkeypatch.setattr(
        config,
        "read_raw_config",
        lambda: {"browser": {"executable_path": str(chrome)}},
    )
    monkeypatch.setattr(bt, "_build_browser_env", lambda: {"PATH": "/usr/bin"})
    assert session._agent_browser_command_env(str(tmp_path))["AGENT_BROWSER_EXECUTABLE_PATH"] == str(chrome)
    assert install._chromium_installed()
    chrome.unlink()
    assert not install._chromium_installed(), "a missing explicit executable must not fall back to PM Chromium"


def test_close_never_creates_or_recycles_a_session(monkeypatch):
    monkeypatch.setattr(bt, "_active_sessions", {})
    monkeypatch.setattr(session, "_browser_command_preflight", lambda: {"browser_cmd": "/unused"})

    def unexpected(*args):
        pytest.fail("close must not get or create a session")

    monkeypatch.setattr(session, "_get_session_info", unexpected)
    assert session._run_browser_command("absent", "close")["success"]
