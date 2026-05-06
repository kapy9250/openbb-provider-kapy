"""Exchange-balance snapshot helper (provider-native).

Data source:
- Coinglass Balance page via Puppeteer
- Browser script: /workspace/openbb-decision-pipeline/browser/fetch_exchange_balance.js

No legacy raw bridge fallback.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import requests


class ExchangeBalanceFetchError(RuntimeError):
    """Raised when exchange balance fetch fails."""


def _browser_ws_endpoint(cdp_http: str | None = None) -> str:
    cdp_http = cdp_http or os.getenv("COINGLASS_CDP_HTTP") or os.getenv("CDP_HTTP") or "http://localhost:19222"
    r = requests.get(f"{cdp_http}/json/version", timeout=10)
    r.raise_for_status()
    obj = r.json()
    ws = obj.get("webSocketDebuggerUrl")
    if not ws:
        raise ExchangeBalanceFetchError("webSocketDebuggerUrl missing from CDP /json/version")
    return str(ws)


def _fetch_script_path() -> Path:
    candidates = []
    env_path = os.getenv("COINGLASS_EXCHANGE_BALANCE_FETCH_JS")
    if env_path:
        candidates.append(Path(env_path))

    here = Path(__file__).resolve()
    candidates.extend(
        [
            Path("/workspace/openbb-decision-pipeline/browser/fetch_exchange_balance.js"),
            here.parents[3] / "openbb-decision-pipeline/browser/fetch_exchange_balance.js",
        ]
    )
    for path in candidates:
        if path.exists():
            return path
    raise ExchangeBalanceFetchError(
        "fetch_exchange_balance.js not found; set COINGLASS_EXCHANGE_BALANCE_FETCH_JS"
    )


def fetch_exchange_balance_snapshot() -> dict[str, Any]:
    ws = _browser_ws_endpoint()
    fetch_script = _fetch_script_path()

    node_script = r"""
const mod = require(process.env.FETCH_SCRIPT);
(async()=>{
  try {
    const data = await mod.fetchAllBalances(process.env.WS_ENDPOINT);
    console.log('__JSON__' + JSON.stringify(data));
  } catch (e) {
    console.log('__JSON__' + JSON.stringify({error: String(e?.message || e)}));
    process.exit(2);
  }
})();
"""

    p = subprocess.run(
        ["node", "-e", node_script],
        capture_output=True,
        text=True,
        timeout=420,
        env={**os.environ, **{"WS_ENDPOINT": ws, "FETCH_SCRIPT": str(fetch_script)}},
    )

    out = (p.stdout or "")
    err = (p.stderr or "")

    marker = "__JSON__"
    payload_line = None
    for line in out.splitlines()[::-1]:
        if line.startswith(marker):
            payload_line = line[len(marker) :]
            break

    if not payload_line:
        raise ExchangeBalanceFetchError(f"no JSON payload from fetch script; rc={p.returncode}; stderr={err[:300]}")

    payload = json.loads(payload_line)
    if payload.get("error"):
        raise ExchangeBalanceFetchError(f"fetch script error: {payload.get('error')}")

    btc_err = (payload.get("btc") or {}).get("error")
    eth_err = (payload.get("eth") or {}).get("error")
    if btc_err or eth_err:
        raise ExchangeBalanceFetchError(f"coinglass fetch errors: btc={btc_err}, eth={eth_err}")

    payload["_source"] = "kapy-provider:coinglass-puppeteer"
    return payload
