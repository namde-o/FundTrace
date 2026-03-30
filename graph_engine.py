"""
graph_engine.py
---------------
Core analysis module for FundTrace.
Handles:
  1. Building a directed transaction graph (NetworkX)
  2. Detecting 4 fraud patterns (cycles, structuring, dormancy, hubs)
  3. Calculating risk scores for every account
  4. Rendering the graph as interactive HTML (Pyvis)
"""

import pandas as pd
import networkx as nx
from datetime import timedelta


# ── Graph Construction 
def build_graph(df):
    """
    Build a directed graph where:
      - Each NODE  = an account (sender or receiver)
      - Each EDGE  = a transaction (directed from sender → receiver)
      - Edge attributes store transaction metadata for later lookup

    Args:
        df (pd.DataFrame): The transactions dataframe

    Returns:
        nx.DiGraph: The directed transaction graph
    """
    G = nx.DiGraph()

    for _, row in df.iterrows():
        G.add_edge(
            row["sender_id"],
            row["receiver_id"],
            amount=row["amount"],
            timestamp=str(row["timestamp"]),
            channel=row["channel"],
            branch=row["branch"],
            transaction_id=row["transaction_id"],
        )

    return G


# ── Fraud Detection Functions 

def detect_cycles(graph, max_cycles=100):
    """
    FRAUD TYPE 1 — Circular Money Flow
    Uses NetworkX's simple_cycles() to find circular money flows.

    IMPORTANT: On a dense graph (many edges), simple_cycles() can generate
    millions of cycles and hang indefinitely. We stop early after collecting
    `max_cycles` results — we only need to know WHICH accounts are in cycles,
    not count every possible loop.

    Args:
        graph      (nx.DiGraph): The transaction graph
        max_cycles (int):        Maximum number of cycles to collect (default 100)

    Returns:
        list[list[str]]: Each item is a list of account IDs forming a cycle
    """
    try:
        cycles = []
        for cycle in nx.simple_cycles(graph):
            if len(cycle) >= 3:  # Ignore 2-node back-and-forth
                cycles.append(cycle)
            if len(cycles) >= max_cycles:
                break  # Stop early — we have enough to flag the risky accounts
        return cycles
    except Exception:
        return []


def detect_structuring(df):
    """
    FRAUD TYPE 2 — Structuring (Smurfing)
    Structuring = breaking a large amount into smaller chunks just below
    a reporting threshold (here: ₹10,000) to avoid detection.

    Flags any sender who sent 4+ transactions between ₹8,000–₹9,999
    within any 24-hour rolling window.

    Args:
        df (pd.DataFrame): The transactions dataframe

    Returns:
        list[str]: Account IDs flagged for structuring
    """
    flagged = []

    # Make sure timestamp is a proper datetime for time arithmetic
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    for sender, grp in df.groupby("sender_id"):
        # Only look at transactions in the suspicious amount range
        suspicious = grp[(grp["amount"] >= 8000) & (grp["amount"] < 10000)].copy()
        suspicious = suspicious.sort_values("timestamp")

        if len(suspicious) < 4:
            continue

        # Sliding window: for each transaction, count how many others
        # from the same sender fall within the next 24 hours
        times = suspicious["timestamp"].tolist()
        for i, t in enumerate(times):
            window = [t2 for t2 in times[i:] if t2 - t <= timedelta(hours=24)]
            if len(window) >= 4:
                flagged.append(sender)
                break  # No need to check further for this sender

    return list(set(flagged))


def detect_dormant_accounts(df):
    """
    FRAUD TYPE 3 — Dormant-then-Active Accounts
    A long period of inactivity followed by sudden large transactions
    often indicates a money-mule account being "awakened."

    Flags accounts with a gap of 60+ days between consecutive transactions.

    Args:
        df (pd.DataFrame): The transactions dataframe

    Returns:
        list[str]: Account IDs with suspicious dormancy patterns
    """
    flagged = []
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Get all accounts that appear as either sender or receiver
    all_accounts = set(df["sender_id"].unique()) | set(df["receiver_id"].unique())

    for account in all_accounts:
        # Collect all timestamps where this account was active
        sent     = df[df["sender_id"]   == account]["timestamp"]
        received = df[df["receiver_id"] == account]["timestamp"]
        all_times = pd.concat([sent, received]).sort_values().reset_index(drop=True)

        if len(all_times) < 2:
            continue  # Not enough data to judge

        # Check consecutive gaps
        for i in range(1, len(all_times)):
            gap = all_times[i] - all_times[i - 1]
            if gap.days >= 60:
                flagged.append(account)
                break

    return list(set(flagged))


def detect_hubs(graph):
    """
    FRAUD TYPE 4 — Hub Accounts (Fan-In Aggregators)
    Accounts that receive money from many different sources in a short period
    may be acting as collection points for illicit funds.

    Flags any node whose in-degree (number of incoming edges) is ≥ 8.

    Args:
        graph (nx.DiGraph): The transaction graph

    Returns:
        list[str]: Account IDs identified as hubs
    """
    return [node for node, in_deg in graph.in_degree() if in_deg >= 8]


# ── Risk Scoring 

def calculate_risk_scores(graph, df):
    """
    Aggregates all fraud signals and assigns a numeric risk score to every account.

    Scoring:
      +3 — involved in a circular money flow
      +2 — flagged for structuring
      +2 — flagged as dormant-then-active
      +1 — flagged as a hub account

    Risk levels:
      Low    = score 0–2
      Medium = score 3–4
      High   = score 5+

    Args:
        graph (nx.DiGraph): The transaction graph
        df    (pd.DataFrame): The transactions dataframe

    Returns:
        dict: {account_id: {"score": int, "reasons": [str], "risk_level": str}}
    """
    # Run all 4 detectors
    cycles        = detect_cycles(graph)
    structuring   = detect_structuring(df)
    dormant       = detect_dormant_accounts(df)
    hubs          = detect_hubs(graph)

    # Flatten cycle lists into a set of account IDs involved in any cycle
    cycle_accounts = set(acc for cycle in cycles for acc in cycle)

    # Build a score dict for every node in the graph
    risk_scores = {}
    all_accounts = list(graph.nodes())

    for account in all_accounts:
        score   = 0
        reasons = []

        if account in cycle_accounts:
            score   += 3
            reasons.append("Involved in circular fund flow (cycle detected)")

        if account in structuring:
            score   += 2
            reasons.append("Structuring suspected: multiple sub-threshold transactions in 24h")

        if account in dormant:
            score   += 2
            reasons.append("Dormant account suddenly activated with large transactions")

        if account in hubs:
            score   += 1
            reasons.append("Hub account: receives funds from many different sources")

        # Determine risk level from numeric score
        if score >= 5:
            risk_level = "High"
        elif score >= 3:
            risk_level = "Medium"
        else:
            risk_level = "Low"

        risk_scores[account] = {
            "score":      score,
            "reasons":    reasons,
            "risk_level": risk_level,
        }

    return risk_scores


# ── Interactive Graph Renderer 

def build_pyvis_graph(graph, risk_scores):
    """
    Renders the transaction graph as an interactive HTML visualization using vis.js.

    Instead of using Pyvis (which downloads vis.js from the internet at Python runtime),
    we build the JSON data structures directly and embed them in an HTML template.
    vis.js is loaded by the USER'S BROWSER via CDN — no Python network call is made.

    Visual encoding:
      - Node COLOR  → risk level (green = Low, orange = Medium, red = High)
      - Node SIZE   → risk score (bigger = riskier, min base size 20)
      - Edge TITLE  → transaction amount, channel, branch (shown on hover)

    Args:
        graph       (nx.DiGraph): The transaction graph
        risk_scores (dict):       Output from calculate_risk_scores()

    Returns:
        str: Full self-contained HTML string with the interactive graph
    """
    import json as _json

    COLOR_MAP = {
        "Low":    "#2A9D8F",
        "Medium": "#F4A261",
        "High":   "#E63946",
    }

    # ── Build vis.js node list ──
    vis_nodes = []
    for node in graph.nodes():
        info       = risk_scores.get(node, {"score": 0, "risk_level": "Low", "reasons": []})
        color      = COLOR_MAP[info["risk_level"]]
        size       = max(20, 20 + info["score"] * 10)
        reasons_txt = "&#10;".join(info["reasons"]) if info["reasons"] else "No fraud signals"
        tooltip    = (
            f"Account: {node}&#10;"
            f"Risk Level: {info['risk_level']}&#10;"
            f"Risk Score: {info['score']}&#10;"
            f"Flags:&#10;{reasons_txt}"
        )
        vis_nodes.append({
            "id":         node,
            "label":      node,
            "color":      {"background": color, "border": "#FFFFFF",
                           "highlight": {"background": color, "border": "#FFFFFF"}},
            "size":       size,
            "title":      tooltip,
            "font":       {"color": "#FFFFFF", "size": 12},
            "borderWidth": 1,
        })

    # ── Build vis.js edge list ──
    # Collapse multi-edges between the same pair (keep last)
    seen_pairs = {}
    for u, v, data in graph.edges(data=True):
        seen_pairs[(u, v)] = data

    edge_id = 0
    vis_edges = []
    for (u, v), data in seen_pairs.items():
        amt   = data.get("amount", 0)
        label = f"\u20b9{amt:,.0f}"        # ₹ symbol via unicode
        tip   = f"{label} | {data.get('channel','')} | {data.get('branch','')}"
        vis_edges.append({
            "id":    edge_id,
            "from":  u,
            "to":    v,
            "title": tip,
            "color": {"color": "#4A90D9", "highlight": "#FFFFFF", "opacity": 0.7},
            "arrows": "to",
            "smooth": {"type": "curvedCW", "roundness": 0.15},
            "width": 1.5,
        })
        edge_id += 1

    nodes_json = _json.dumps(vis_nodes)
    edges_json = _json.dumps(vis_edges)

    # ── HTML Template ──
    # vis.js is loaded by the browser from CDN — Python never touches the network.
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  body {{ margin:0; background:#0A1628; overflow:hidden; }}
  #graph {{ width:100%; height:100vh; }}
</style>
<!-- vis.js loaded by the browser; Python does NOT fetch this -->
<script src="https://cdn.jsdelivr.net/npm/vis-network@9.1.9/dist/vis-network.min.js"></script>
</head>
<body>
<div id="graph"></div>
<script>
var nodes = new vis.DataSet({nodes_json});
var edges = new vis.DataSet({edges_json});
var container = document.getElementById("graph");
var options = {{
  physics: {{
    enabled: true,
    barnesHut: {{
      gravitationalConstant: -4000,
      centralGravity: 0.3,
      springLength: 160,
      springConstant: 0.04,
      damping: 0.1
    }}
  }},
  interaction: {{ hover: true, tooltipDelay: 80 }},
  nodes: {{ shape: "dot" }},
  edges: {{ font: {{ size: 0 }}, selectionWidth: 2 }}
}};
new vis.Network(container, {{ nodes: nodes, edges: edges }}, options);
</script>
</body>
</html>"""
    return html
