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
from typing import Any

import requests


class ExchangeBalanceFetchError(RuntimeError):
    """Raised when exchange balance fetch fails."""


def _browser_ws_endpoint(cdp_http: str = "http://172.30.0.1:9222") -> str:
    r = requests.get(f"{cdp_http}/json/version", timeout=10)
    r.raise_for_status()
    obj = r.json()
    ws = obj.get("webSocketDebuggerUrl")
    if not ws:
        raise ExchangeBalanceFetchError("webSocketDebuggerUrl missing from CDP /json/version")
    return str(ws)


def fetch_exchange_balance_snapshot() -> dict[str, Any]:
    ws = _browser_ws_endpoint()

    node_script = r"""
const mod = require('/workspace/openbb-decision-pipeline/browser/fetch_exchange_balance.js');
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
        env={**os.environ, **{"WS_ENDPOINT": ws}},
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
