"""Session 9 replay viewer — renders one persisted run as a single
self-contained replay.html covering the 8 assignment trace items:

  1 user goal · 2 planner DAG · 3 browser cascade layer · 4 exact actions
  5 evidence (screenshots + a11y legends) · 6 raw extracted data
  7 final comparison table · 8 turn count + token/cost summary

Standalone: reads state/sessions/<sid>/ (via persistence.SessionStore),
the browser artifact folders, and the V9 gateway cost ledger. Zero engine
changes; no CDN scripts; screenshots are base64-embedded.

Usage:  uv run python replay_viewer.py <session_id> [gateway_url]

Cost row shape (from llm_gatewayV9/db.py by_agent + main.py /v1/cost/by_agent):
  each entry dict has keys: agent, provider, calls, in_tok, out_tok,
  total_latency_ms, total_retries, ok, errors, dollars
"""
from __future__ import annotations

import base64
import html as html_mod
import json
import sys
from pathlib import Path

import httpx

import persistence as _persistence_module
from persistence import SessionStore

# Module-level SESSIONS_ROOT so tests can monkeypatch replay_viewer.SESSIONS_ROOT.
# SessionStore.__init__ reads persistence.SESSIONS_ROOT at call time (not import
# time), so patching persistence.SESSIONS_ROOT is sufficient for the store path;
# this alias is used only in write_report and __main__ for listing sessions.
SESSIONS_ROOT = _persistence_module.SESSIONS_ROOT

DEFAULT_GATEWAY = "http://localhost:8109"

_CSS = """
body{font-family:Segoe UI,system-ui,sans-serif;margin:24px;background:#fafafa;color:#222}
h1{font-size:1.4em} h2{border-bottom:2px solid #ddd;padding-bottom:4px;margin-top:32px}
.badge{display:inline-block;padding:2px 10px;border-radius:10px;font-size:.85em;color:#fff}
.badge.extract{background:#2e7d32}.badge.deterministic{background:#1565c0}
.badge.a11y{background:#ef6c00}.badge.vision{background:#8e24aa}.badge.blocked{background:#c62828}
.node{background:#fff;border:1px solid #ddd;border-radius:8px;padding:10px;margin:6px;display:inline-block;vertical-align:top;min-width:160px}
.level{margin:4px 0} .edge{color:#888;font-size:.9em}
table{border-collapse:collapse;background:#fff}td,th{border:1px solid #ccc;padding:4px 10px}
img.shot{max-width:480px;border:1px solid #bbb;margin:4px}
pre{background:#272822;color:#f8f8f2;padding:10px;border-radius:6px;overflow-x:auto;max-height:320px}
details>summary{cursor:pointer;font-weight:600;margin:6px 0}
"""


def _esc(s) -> str:
    return html_mod.escape(str(s if s is not None else ""))


# ── data loading ─────────────────────────────────────────────────────────────

def _load_edges(store: SessionStore) -> list[tuple[str, str]]:
    if not store.graph_path.exists():
        return []
    payload = json.loads(store.graph_path.read_text(encoding="utf-8"))
    return [(e["source"], e["target"]) for e in payload.get("edges", [])]


def _dag_levels(node_ids: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """Longest-path layering — good enough for a small DAG, no deps needed."""
    preds: dict[str, set[str]] = {n: set() for n in node_ids}
    for u, v in edges:
        preds.setdefault(v, set()).add(u)
        preds.setdefault(u, set())
    level: dict[str, int] = {}

    def depth(n: str, seen=()) -> int:
        if n in level:
            return level[n]
        if n in seen:                       # cycle guard; DAGs shouldn't have any
            return 0
        d = 0 if not preds[n] else 1 + max(depth(p, seen + (n,)) for p in preds[n])
        level[n] = d
        return d

    for n in preds:
        depth(n)
    out: list[list[str]] = [[] for _ in range(max(level.values(), default=0) + 1)]
    for n, d in sorted(level.items()):
        out[d].append(n)
    return out


def _evidence_files(session_dir: Path) -> list[Path]:
    root = session_dir / "browser"
    return sorted(root.rglob("turn_*")) if root.exists() else []


def _fetch_costs(session_id: str, gateway_url: str):
    try:
        r = httpx.get(f"{gateway_url}/v1/cost/by_agent",
                      params={"session": session_id}, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ── rendering ────────────────────────────────────────────────────────────────

def _browser_path(node) -> str:
    r = node.result
    if r is None:
        return "?"
    if r.error_code == "gateway_blocked":
        return "blocked"
    return (r.output or {}).get("path", "?")


def _render_dag(states, edges) -> str:
    by_id = {s.node_id: s for s in states}
    ids = sorted(set(by_id) | {n for e in edges for n in e})
    rows = []
    for lvl in _dag_levels(ids, edges):
        cells = []
        for n in lvl:
            st = by_id.get(n)
            label = f"<b>{_esc(n)}</b><br>{_esc(st.skill) if st else '?'}"
            if st and st.skill == "browser":
                p = _browser_path(st)
                label += f'<br><span class="badge {p}">{_esc(p)}</span>'
            status = _esc(st.status) if st else "?"
            cells.append(f'<span class="node">{label}<br><small>{status}</small></span>')
        rows.append(f'<div class="level">{"".join(cells)}</div>')
    edge_txt = " &nbsp; ".join(f'<span class="edge">{_esc(u)} &rarr; {_esc(v)}</span>'
                               for u, v in edges)
    return "".join(rows) + f"<p>{edge_txt}</p>"


def _render_browser_nodes(states) -> tuple[str, str, int]:
    """Returns (actions_html, raw_data_html, total_browser_turns)."""
    actions, raw, turns = [], [], 0
    for st in states:
        if st.skill != "browser" or st.result is None:
            continue
        out = st.result.output or {}
        turns += int(out.get("turns") or 0)
        path = _browser_path(st)
        actions.append(
            f"<h3>{_esc(st.node_id)} — <span class='badge {path}'>{_esc(path)}</span> "
            f"&nbsp;<small>{_esc(out.get('url'))} → {_esc(out.get('final_url'))}</small></h3>"
            f"<p><i>goal:</i> {_esc(out.get('goal'))}</p>"
            f"<pre>{_esc(json.dumps(out.get('actions') or [], indent=2))}</pre>"
        )
        if st.result.error:
            actions.append(f"<p><b>error:</b> {_esc(st.result.error)}</p>")
        content = out.get("content")
        if content:
            raw.append(f"<details><summary>{_esc(st.node_id)} raw extract "
                       f"({len(content)} chars)</summary><pre>{_esc(content)}</pre></details>")
    return "".join(actions) or "<p>(no browser nodes)</p>", \
           "".join(raw) or "<p>(no extracted content)</p>", turns


def _render_evidence(files: list[Path]) -> str:
    parts = []
    for f in files:
        rel = _esc("/".join(f.parts[-3:]))
        if f.suffix == ".png":
            b64 = base64.b64encode(f.read_bytes()).decode()
            parts.append(f'<figure><img class="shot" src="data:image/png;base64,{b64}">'
                         f"<figcaption>{rel}</figcaption></figure>")
        elif f.suffix == ".txt":
            parts.append(f"<details><summary>{rel}</summary>"
                         f"<pre>{_esc(f.read_text(encoding='utf-8', errors='replace'))}</pre></details>")
    return "".join(parts) or "<p>(no browser artifacts captured)</p>"


def _render_costs(costs, states, browser_turns: int) -> str:
    """Render the cost/token summary table.

    Live cost row shape (from llm_gatewayV9/db.py by_agent, decorated in
    main.py /v1/cost/by_agent with a 'dollars' key):
        agent, provider, calls, in_tok, out_tok,
        total_latency_ms, total_retries, ok, errors, dollars
    """
    n_nodes = len(states)
    head = (f"<p><b>Graph nodes run:</b> {n_nodes} &nbsp; "
            f"<b>Browser turns (LLM-driven steps):</b> {browser_turns}</p>")
    if costs is None:
        return head + "<p><i>Cost ledger unavailable (gateway offline when this report was generated).</i></p>"
    rows, t_in, t_out, t_usd = [], 0, 0, 0.0
    for agent, entries in sorted(costs.items()):
        for e in entries if isinstance(entries, list) else [entries]:
            # Keys from db.by_agent: in_tok, out_tok (not input_tokens/output_tokens)
            i = int(e.get("in_tok", 0) or 0)
            o = int(e.get("out_tok", 0) or 0)
            d = float(e.get("dollars", 0) or 0)
            prov = _esc(e.get("provider", ""))
            t_in, t_out, t_usd = t_in + i, t_out + o, t_usd + d
            rows.append(f"<tr><td>{_esc(agent)}</td><td>{prov}</td>"
                        f"<td>{i}</td><td>{o}</td><td>${d:.6f}</td></tr>")
    return (head + "<table><tr><th>agent</th><th>provider</th><th>in tokens</th>"
            "<th>out tokens</th><th>$ est.</th></tr>" + "".join(rows) +
            f"<tr><th>total</th><th></th><th>{t_in}</th><th>{t_out}</th>"
            f"<th>${t_usd:.6f}</th></tr></table>")


def render_session(session_id: str, gateway_url: str = DEFAULT_GATEWAY) -> str:
    # Guard before SessionStore(): its __init__ mkdirs the session dir, so a
    # typo'd id would otherwise yield a junk directory and a silent empty report.
    if not (_persistence_module.SESSIONS_ROOT / session_id).exists():
        raise FileNotFoundError(f"session not found: {session_id}")
    store = SessionStore(session_id)
    states = store.read_all_nodes()
    query = store.read_query()
    edges = _load_edges(store)
    actions_html, raw_html, browser_turns = _render_browser_nodes(states)
    final = next((s.result.output.get("final_answer")
                  for s in reversed(states)
                  if s.skill == "formatter" and s.result and s.result.output
                  and s.result.output.get("final_answer")), None)
    costs = _fetch_costs(session_id, gateway_url)
    paths = sorted({_browser_path(s) for s in states if s.skill == "browser"})
    sections = [
        f"<h1>Replay — session {_esc(session_id)}</h1>",
        f"<h2>1 · User goal</h2><blockquote>{_esc(query)}</blockquote>",
        f"<h2>2 · Planner DAG</h2>{_render_dag(states, edges)}",
        f"<h2>3 · Browser cascade path</h2><p>Layers used: "
        + " ".join(f'<span class="badge {p}">{_esc(p)}</span>' for p in paths or ["?"]) + "</p>",
        f"<h2>4 · Exact browser actions</h2>{actions_html}",
        f"<h2>5 · Evidence (per-turn screenshots &amp; a11y legends)</h2>"
        + _render_evidence(_evidence_files(store.dir)),
        f"<h2>6 · Raw extracted data</h2>{raw_html}",
        f"<h2>7 · Final comparison table</h2><pre>{_esc(final or '(no formatter output)')}</pre>",
        f"<h2>8 · Turns &amp; cost summary</h2>{_render_costs(costs, states, browser_turns)}",
    ]
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>replay {_esc(session_id)}</title><style>{_CSS}</style></head>"
            f"<body>{''.join(sections)}</body></html>")


def write_report(session_id: str, gateway_url: str = DEFAULT_GATEWAY) -> Path:
    store = SessionStore(session_id)
    out = store.dir / "replay.html"
    out.write_text(render_session(session_id, gateway_url), encoding="utf-8")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sessions_root = _persistence_module.SESSIONS_ROOT
        sessions = sorted(p.name for p in sessions_root.iterdir()) if sessions_root.exists() else []
        print("usage: python replay_viewer.py <session_id> [gateway_url]")
        print("sessions:", *sessions[-10:], sep="\n  ")
        raise SystemExit(2)
    gw = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_GATEWAY
    path = write_report(sys.argv[1], gw)
    print(f"wrote {path}")
