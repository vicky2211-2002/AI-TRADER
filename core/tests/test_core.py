"""Offline regression tests for the AI-TRADER core.

Run:  python -m pytest core/tests -q
No network and no MetaTrader5 required. TestClient runs the real lifespan.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CORE))

from aitrader import risk  # noqa: E402
from aitrader.mcp_client import StdioMCPClient  # noqa: E402


def _account(equity=10000):
    return {"balance": equity, "equity": equity, "floating_pnl": 0, "trade_mode": "DEMO"}


def _settings(**over):
    base = {
        "kill_switch": False,
        "allow_live_trading": False,
        "default_symbols": ["EURUSD", "XAUUSD"],
        "max_lot_size": 0.10,
        "max_risk_per_trade_pct": 1.0,
        "max_open_positions": 2,
        "max_daily_loss_pct": 2.0,
        "max_drawdown_pct": 8.0,
    }
    base.update(over)
    return base


def test_risk_blocks_missing_stop():
    async def run():
        order = {"symbol": "EURUSD", "side": "BUY", "volume": 0.01, "sl": 0, "tp": 0}
        verdict = await risk.evaluate_order(order, _account(), [], _settings(), {"price": 1.085, "source": "test"})
        assert verdict["allowed"] is False
        assert "Stop loss required" in verdict["blocked_by"]
    asyncio.run(run())


def test_risk_passes_small_trade():
    async def run():
        order = {"symbol": "EURUSD", "side": "BUY", "volume": 0.01, "sl": 1.080, "tp": 1.095}
        verdict = await risk.evaluate_order(order, _account(), [], _settings(), {"price": 1.085, "source": "test"})
        assert verdict["allowed"] is True, verdict["checks"]
        # 0.01 lots x 50 pips x $10/pip = $5 risk on a $10k account
        assert verdict["risk_usd"] == pytest.approx(5.0, rel=0.01)
        assert verdict["risk_pct"] == pytest.approx(0.05, rel=0.01)
    asyncio.run(run())


def test_risk_blocks_live_and_kill_switch():
    async def run():
        order = {"symbol": "EURUSD", "side": "SELL", "volume": 0.01, "sl": 1.090, "tp": 1.070}
        v1 = await risk.evaluate_order(order, _account(), [], _settings(), {"price": 1.085})
        assert v1["allowed"] is True
        live = {"symbol": "EURUSD", "side": "SELL", "volume": 0.01, "sl": 1.090, "tp": 1.070, "environment": "LIVE"}
        v2 = await risk.evaluate_order(live, _account(), [], _settings(), {"price": 1.085})
        assert v2["allowed"] is False
        assert "Live trading disabled" in v2["blocked_by"]
        v3 = await risk.evaluate_order(order, _account(), [], _settings(kill_switch=True), {"price": 1.085})
        assert v3["allowed"] is False
    asyncio.run(run())


def test_risk_blocks_oversized_volume():
    async def run():
        order = {"symbol": "EURUSD", "side": "BUY", "volume": 5.0, "sl": 1.080, "tp": 1.095}
        verdict = await risk.evaluate_order(order, _account(), [], _settings(), {"price": 1.085})
        assert verdict["allowed"] is False
        assert any("lot" in b.lower() for b in verdict["blocked_by"])
    asyncio.run(run())


def test_stdio_mcp_client_roundtrip():
    server = Path(__file__).parent / "fixtures" / "mcp_echo.py"
    client = StdioMCPClient("echo", sys.executable, [str(server)], {})
    try:
        client.start(timeout=20)
        assert client.alive()
        assert client.server_info.get("serverInfo", {}).get("name") == "echo-test"
        names = [t["name"] for t in client.tools]
        assert "echo" in names
        result = client.call_tool("echo", {"text": "hi"})
        assert "hi" in json.dumps(result)
    finally:
        client.stop()


def test_api_bootstrap_and_crud(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from aitrader.api import app

    with TestClient(app) as c:
        assert c.get("/api/health").json()["ok"] is True
        boot = c.get("/api/bootstrap").json()
        assert len(boot["providers"]) >= 6
        assert len(boot["accounts"]) >= 1
        assert boot["system"]["vault"] in ("fernet", "obfuscated")

        created = c.post("/api/providers", json={
            "name": "Test Provider", "base_url": "https://example.invalid/v1",
            "model": "test-model", "api_key": "sk-secret-value",
        })
        assert created.status_code == 200
        body = created.json()
        assert body["has_key"] is True
        assert "sk-secret-value" not in json.dumps(body)

        patched = c.patch(f"/api/providers/{body['id']}", json={"model": "test-model-2"})
        assert patched.json()["model"] == "test-model-2"

        assert c.delete(f"/api/providers/{body['id']}").json()["ok"] is True

        skills = c.get("/api/skills").json()
        assert len(skills) >= 10, "bundled skills should be discovered"

        live = c.put("/api/settings", json={"trading_mode": "live"})
        assert live.status_code == 400

        blocked = c.post("/api/orders", json={
            "symbol": "EURUSD", "side": "BUY", "volume": 0.01, "sl": 0, "tp": 0,
        }).json()
        assert blocked["status"] == "blocked"
        assert "Stop loss required" in blocked["blocked_by"]

        mcp_catalog = c.get("/api/mcp/catalog").json()
        assert any(item["id"] == "playwright" for item in mcp_catalog)


def test_mcp_edit_keeps_masked_secrets(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from aitrader.api import app

    with TestClient(app) as c:
        created = c.post("/api/mcp", json={
            "name": "Secret server", "transport": "stdio", "command": "npx",
            "args": ["-y", "some-package"], "env": {"API_KEY": "sk-live-123456"},
            "category": "test", "notes": "before",
        }).json()
        masked = created["env"]["API_KEY"]
        assert masked.startswith("*") and masked.endswith("3456")

        # The UI echoes the mask back and leaves new fields blank; neither may
        # overwrite or invent a stored secret.
        patched = c.patch(f"/api/mcp/{created['id']}", json={
            "name": "Renamed server",
            "env": {"API_KEY": masked, "OPTIONAL_TOKEN": ""},
        }).json()
        assert patched["name"] == "Renamed server"
        assert patched["env"]["API_KEY"] == masked
        assert patched["env"]["OPTIONAL_TOKEN"] == ""

        assert c.delete(f"/api/mcp/{created['id']}").json()["ok"] is True


def test_account_edit_keeps_blank_secrets(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from aitrader.api import app

    with TestClient(app) as c:
        account = c.post("/api/accounts", json={
            "name": "Paper test", "broker": "paper", "environment": "paper",
            "config": {}, "secret": {"note": "keep-me"},
        }).json()
        assert account["has_secret"] is True

        patched = c.patch(f"/api/accounts/{account['id']}", json={
            "name": "Paper renamed", "secret": {"note": ""},
        }).json()
        assert patched["name"] == "Paper renamed"
        assert patched["has_secret"] is True, "a blank field must not wipe the vault"

        assert c.delete(f"/api/accounts/{account['id']}").json()["ok"] is True


# ---------------------------------------------------------------------------
# Autopilot: pure helpers (no network, no models)
# ---------------------------------------------------------------------------
def test_autopilot_extract_and_parse_decision():
    from aitrader import autopilot

    fenced = """```json
    {"action": "buy", "confidence": 0.72, "reason": "trend up", "sl_atr": 2.5, "tp_atr": 5}
    ```"""
    parsed = autopilot.parse_decision(fenced)
    assert parsed is not None
    assert parsed["action"] == "BUY"
    assert parsed["confidence"] == pytest.approx(0.72)
    assert parsed["sl_atr"] == pytest.approx(2.5)
    assert parsed["tp_atr"] == pytest.approx(5.0)

    # Percent-style confidence is normalised, out-of-range multipliers clamped.
    loose = autopilot.parse_decision('{"action":"SELL","confidence":85,"sl_atr":0.01,"tp_atr":99}')
    assert loose is not None
    assert loose["confidence"] == pytest.approx(0.85)
    assert loose["sl_atr"] == pytest.approx(0.5)
    assert loose["tp_atr"] == pytest.approx(20.0)

    # Garbage, unknown actions and empty strings never produce an order.
    assert autopilot.parse_decision("no json here") is None
    assert autopilot.parse_decision('{"action":"MOON","confidence":0.9}') is None
    assert autopilot.parse_decision("") is None


def test_autopilot_aggregate_votes():
    from aitrader import autopilot

    buy_majority = autopilot.aggregate_votes(
        [
            {"ok": True, "action": "BUY", "confidence": 0.8, "sl_atr": 2.0, "tp_atr": 4.0, "reason": "a"},
            {"ok": True, "action": "BUY", "confidence": 0.6, "sl_atr": 3.0, "tp_atr": 6.0, "reason": "b"},
            {"ok": True, "action": "SELL", "confidence": 0.5, "sl_atr": 2.0, "tp_atr": 4.0, "reason": "c"},
        ],
        threshold=0.55,
        default_sl=2.0,
        default_tp=4.0,
    )
    assert buy_majority["action"] == "BUY"
    assert buy_majority["winners"] == 2
    assert buy_majority["voters"] == 3
    assert buy_majority["sl_atr"] == pytest.approx(2.5)
    assert buy_majority["tp_atr"] == pytest.approx(5.0)
    assert 0.0 < buy_majority["confidence"] <= 1.0

    all_hold = autopilot.aggregate_votes(
        [{"ok": True, "action": "HOLD", "confidence": 0.4, "reason": "no setup"}],
        threshold=0.55, default_sl=2.0, default_tp=4.0,
    )
    assert all_hold["action"] == "HOLD"
    assert all_hold["winners"] == 0

    split = autopilot.aggregate_votes(
        [
            {"ok": True, "action": "BUY", "confidence": 0.6, "reason": ""},
            {"ok": True, "action": "SELL", "confidence": 0.6, "reason": ""},
        ],
        threshold=0.55, default_sl=2.0, default_tp=4.0,
    )
    assert split["action"] == "HOLD", "equal weight must never pick a side"

    dead = autopilot.aggregate_votes(
        [{"ok": False, "action": "HOLD", "confidence": 0.0, "error": "timeout"}],
        threshold=0.55, default_sl=2.0, default_tp=4.0,
    )
    assert dead["action"] == "HOLD"
    assert dead["voters"] == 0


def test_autopilot_size_order_respects_risk_and_lot_cap():
    from aitrader import autopilot

    settings = {"max_risk_per_trade_pct": 1.0, "max_lot_size": 0.10}
    snapshot = {"symbol": "EURUSD", "price": 1.0850, "atr14": 0.0020}
    sizing = autopilot.size_order(snapshot, "BUY", settings, equity=10000, sl_atr=2.0, tp_atr=4.0)
    assert sizing is not None
    assert sizing["volume"] <= 0.10
    assert sizing["volume"] >= 0.01
    assert sizing["sl"] < snapshot["price"] < sizing["tp"]
    assert sizing["risk_usd"] <= 100.0 + 0.01  # 1% of equity, ignoring rounding

    short = autopilot.size_order(snapshot, "SELL", settings, equity=10000, sl_atr=2.0, tp_atr=4.0)
    assert short is not None and short["sl"] > snapshot["price"] > short["tp"]

    # No ATR means no defensible stop, so no order.
    assert autopilot.size_order({"symbol": "EURUSD", "price": 1.085, "atr14": 0}, "BUY", settings, 10000, 2, 4) is None
    # Risk budget too small for the minimum lot.
    assert autopilot.size_order(snapshot, "BUY", settings, equity=10, sl_atr=2.0, tp_atr=4.0) is None


def test_autopilot_cooldown_helper():
    from aitrader import autopilot

    cooldowns = {"EURUSD": 1000.0}
    assert autopilot.in_cooldown(cooldowns, "EURUSD", ts=999.0) is True
    assert autopilot.in_cooldown(cooldowns, "eurusd", ts=1000.0) is False
    assert autopilot.in_cooldown(cooldowns, "XAUUSD", ts=0.0) is False
    assert autopilot.in_cooldown({}, "EURUSD", ts=0.0) is False


def test_autopilot_provider_readiness_and_failure_reasons():
    from aitrader import autopilot

    assert autopilot.provider_ready({"api_key_enc": "ciphertext"}) is True
    assert autopilot.provider_ready({"base_url": "http://localhost:11434/v1"}) is True
    assert autopilot.provider_ready({"base_url": "http://127.0.0.1:8799/v1"}) is True
    assert autopilot.provider_ready({"base_url": "https://api.example.com/v1"}) is False

    vote = asyncio.run(
        autopilot._ask_one(
            {"id": "prv_x", "name": "NoKey", "model": "m", "base_url": "https://api.example.com/v1"},
            "{}",
        )
    )
    assert vote["ok"] is False
    assert "API key" in vote["error"]

    agg = autopilot.aggregate_votes([vote], 0.55, 2.0, 4.0)
    assert agg["action"] == "HOLD"
    assert agg["voters"] == 0
    assert "First error" in agg["reason"]


def test_dashboard_and_autopilot_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from aitrader.api import app

    with TestClient(app) as c:
        dash = c.get("/api/dashboard")
        assert dash.status_code == 200
        body = dash.json()
        for key in ("autopilot", "control", "account", "positions", "stats", "decisions", "equity", "activity"):
            assert key in body, f"dashboard payload missing {key}"
        assert body["autopilot"]["running"] is False
        assert body["stats"]["closed_trades"] >= 0
        assert isinstance(body["decisions"], list)

        status = c.get("/api/autopilot").json()
        assert status["running"] is False
        assert "stage" in status
        assert c.get("/api/autopilot/decisions?limit=5").status_code == 200

        # A single cycle with no model configured must fail cleanly, not crash
        # (and must not reach the network).
        from aitrader.db import get_db

        db = get_db()
        enabled_ids = [r["id"] for r in db.query("SELECT id FROM providers WHERE enabled=1")]
        db.execute("UPDATE providers SET enabled=0")
        try:
            once = c.post("/api/autopilot/run-once").json()
            assert once["ok"] is False
            assert "provider" in once["error"].lower()
        finally:
            for pid in enabled_ids:
                db.execute("UPDATE providers SET enabled=1 WHERE id=?", (pid,))

        killed = c.post("/api/autopilot/kill").json()
        assert killed["ok"] is True and killed["kill_switch"] is True
        c.put("/api/settings", json={"kill_switch": False})
        assert c.get("/api/autopilot").json()["running"] is False


def test_bundled_tool_dirs_finds_sibling_folders(tmp_path, monkeypatch):
    """The bundled runtimes are siblings of core-runtime, so the search must
    walk up from the executable."""
    from aitrader import tools

    install = tmp_path / "install"
    resources = install / "resources"
    (resources / "core-runtime").mkdir(parents=True)
    (resources / "node").mkdir()
    (resources / "uv").mkdir()

    fake_exe = resources / "core-runtime" / "aitrader-core.exe"
    fake_exe.write_bytes(b"")
    monkeypatch.setattr(tools.sys, "executable", str(fake_exe))

    found = {Path(p).name for p in tools.bundled_tool_dirs()}
    assert "node" in found, found
    assert "uv" in found, found


def test_is_bundled_command_only_matches_real_tool_folders(tmp_path, monkeypatch):
    """A system-wide Node.js must never be reported as bundled.

    The old check ended with "or resolved.parent.parent.exists()", which is
    true for essentially every path on disk, so a system install could be
    announced to the user as "bundled with AI-TRADER".
    """
    from aitrader import tools

    install = tmp_path / "install"
    resources = install / "resources"
    (resources / "core-runtime").mkdir(parents=True)
    (resources / "node").mkdir()
    (resources / "uv").mkdir()

    fake_exe = resources / "core-runtime" / "aitrader-core.exe"
    fake_exe.write_bytes(b"")
    monkeypatch.setattr(tools.sys, "executable", str(fake_exe))

    bundled_npx = resources / "node" / ("npx.cmd" if sys.platform == "win32" else "npx")
    bundled_npx.write_text("", encoding="utf-8")
    assert tools.is_bundled_command(bundled_npx) is True

    # A system install: same file name, but in a folder the bundle does not ship.
    system_node = tmp_path / "hostedtoolcache" / "nodejs" / "20.x" / "x64"
    system_node.mkdir(parents=True)
    system_npx = system_node / ("npx.cmd" if sys.platform == "win32" else "npx")
    system_npx.write_text("", encoding="utf-8")
    assert tools.is_bundled_command(system_npx) is False


def test_system_endpoint_reports_bundled_flags():
    """The flags the UI uses to say "bundled with AI-TRADER" must be present
    and honest -- they are what CI asserts on."""
    from fastapi.testclient import TestClient
    from aitrader.api import app

    with TestClient(app) as c:
        sysinfo = c.get("/api/system").json()
    for key in ("node", "uv", "node_bundled", "uv_bundled", "mt5_available"):
        assert key in sysinfo, f"/api/system missing {key}"
    assert isinstance(sysinfo["node_bundled"], bool)
    assert isinstance(sysinfo["uv_bundled"], bool)

