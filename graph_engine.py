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
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import MinMaxScaler
import io
import base64



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



# ── ML and Feature Engineering

def extract_features(graph, df):
    """
    Extracts node-level features for ML models.
    """
    features = []

    # Pre-compute metrics
    pr = nx.pagerank(graph, alpha=0.85, max_iter=100)
    try:
        bc = nx.betweenness_centrality(graph)
    except:
        bc = {node: 0.0 for node in graph.nodes()}

    undirected = graph.to_undirected()
    cc = nx.clustering(undirected)

    df['timestamp'] = pd.to_datetime(df['timestamp'])

    for node in graph.nodes():
        in_deg = graph.in_degree(node)
        out_deg = graph.out_degree(node)
        degree_ratio = in_deg / (out_deg + 1e-5)

        # Transactions involving this node
        node_txns = df[(df['sender_id'] == node) | (df['receiver_id'] == node)]

        if len(node_txns) > 0:
            avg_tx_amount = node_txns['amount'].mean()
            total_volume = node_txns['amount'].sum()

            # Velocity and gap
            times = node_txns['timestamp'].sort_values()
            active_days = (times.max() - times.min()).days + 1
            transaction_velocity = len(node_txns) / max(1, active_days)

            if len(times) > 1:
                gaps = times.diff().dt.days.dropna()
                max_gap_days = gaps.max() if len(gaps) > 0 else 0
            else:
                max_gap_days = 0
        else:
            avg_tx_amount = 0
            total_volume = 0
            transaction_velocity = 0
            max_gap_days = 0

        features.append({
            'account_id': node,
            'in_degree': in_deg,
            'out_degree': out_deg,
            'degree_ratio': degree_ratio,
            'pagerank_score': pr.get(node, 0),
            'betweenness_centrality': bc.get(node, 0),
            'clustering_coefficient': cc.get(node, 0),
            'avg_transaction_amount': avg_tx_amount,
            'transaction_velocity': transaction_velocity,
            'max_gap_days': max_gap_days,
            'total_volume': total_volume
        })

    return pd.DataFrame(features).set_index('account_id')

def train_ml_models(features_df, rule_flags_dict):
    """
    Trains Isolation Forest and Random Forest.
    Returns dictionaries of scores.
    """
    if features_df.empty:
        return {}, {}, {}

    # 1. Isolation Forest
    iso_forest = IsolationForest(contamination=0.1, random_state=42)
    iso_scores_raw = iso_forest.fit_predict(features_df)
    # Convert anomaly (-1) and normal (1) to anomaly probability (0 to 1)
    # Using decision_function: lower is more anomalous
    decision_scores = iso_forest.decision_function(features_df)

    # Scale to 0-100 where 100 is most anomalous
    scaler = MinMaxScaler(feature_range=(0, 100))
    iso_scores_scaled = 100 - scaler.fit_transform(decision_scores.reshape(-1, 1)).flatten()

    iso_dict = {acc: score for acc, score in zip(features_df.index, iso_scores_scaled)}

    # 2. Random Forest
    # Labels based on rule flags
    labels = [1 if rule_flags_dict.get(acc, False) else 0 for acc in features_df.index]

    rf_dict = {}
    feature_importances = {}

    if sum(labels) > 0 and sum(labels) < len(labels):
        rf = RandomForestClassifier(n_estimators=100, random_state=42)
        rf.fit(features_df, labels)
        rf_probs = rf.predict_proba(features_df)[:, 1] * 100
        rf_dict = {acc: prob for acc, prob in zip(features_df.index, rf_probs)}

        feature_importances = dict(zip(features_df.columns, rf.feature_importances_))
    else:
        # If all 0 or all 1, fallback
        rf_dict = {acc: 0.0 for acc in features_df.index}
        feature_importances = {col: 1.0/len(features_df.columns) for col in features_df.columns}

    return iso_dict, rf_dict, feature_importances

# ── Risk Scoring

def calculate_risk_scores(graph, df):
    # Run all 4 detectors
    cycles        = detect_cycles(graph)
    structuring   = detect_structuring(df)
    dormant       = detect_dormant_accounts(df)
    hubs          = detect_hubs(graph)

    cycle_accounts = set(acc for cycle in cycles for acc in cycle)
    all_accounts = list(graph.nodes())

    # Step 1: Rule-based base scores and flags
    rule_flags_dict = {}
    base_scores = {}
    reasons_dict = {}

    for account in all_accounts:
        score = 0
        reasons = []
        if account in cycle_accounts:
            score += 3
            reasons.append("Involved in circular fund flow (cycle detected)")
        if account in structuring:
            score += 2
            reasons.append("Structuring suspected: multiple sub-threshold transactions in 24h")
        if account in dormant:
            score += 2
            reasons.append("Dormant account suddenly activated with large transactions")
        if account in hubs:
            score += 1
            reasons.append("Hub account: receives funds from many different sources")

        base_scores[account] = score
        reasons_dict[account] = reasons
        rule_flags_dict[account] = score > 0

    # Step 2: Extract features and run ML models
    features_df = extract_features(graph, df)
    iso_scores, rf_scores, feature_importances = train_ml_models(features_df, rule_flags_dict)

    # Normalize rule score to 0-100 (assuming max realistic score is ~8)
    max_rule = max(base_scores.values()) if base_scores.values() else 1
    if max_rule == 0: max_rule = 1

    risk_scores = {}

    for account in all_accounts:
        rule_score_normalized = min(100, (base_scores[account] / max_rule) * 100)
        iso_s = iso_scores.get(account, 0)
        rf_s = rf_scores.get(account, 0)

        # Combined Risk Score
        final_score = (0.40 * rule_score_normalized) + (0.35 * iso_s) + (0.25 * rf_s)
        final_score = int(round(final_score))

        if final_score >= 67:
            risk_level = "High"
        elif final_score >= 34:
            risk_level = "Medium"
        else:
            risk_level = "Low"

        # Get feature dict for this account
        f_dict = features_df.loc[account].to_dict() if account in features_df.index else {}

        risk_scores[account] = {
            "score":      final_score,
            "rule_score": int(round(rule_score_normalized)),
            "iso_score":  int(round(iso_s)),
            "rf_score":   int(round(rf_s)),
            "reasons":    reasons_dict[account],
            "risk_level": risk_level,
            "features":   f_dict
        }

    # Attach feature importances to the risk_scores dict (hacky but passes data along)
    risk_scores["_metadata"] = {
        "feature_importances": feature_importances
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
        # Size scaling for 0-100 score: min 20, max 60
        size       = 20 + (info["score"] / 100) * 40
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
var network = new vis.Network(container, {{ nodes: nodes, edges: edges }}, options);

// Listen for messages from parent window
window.addEventListener('message', function(event) {{
    var data = event.data;
    if (data.action === 'filter') {{
        var filteredNodes = nodes.get().filter(function(node) {{
            if (data.type === 'All') return true;
            if (data.type === 'High' && node.title.includes('Risk Level: High')) return true;
            if (data.type === 'Medium' && node.title.includes('Risk Level: Medium')) return true;
            if (data.type === 'Cycles' && node.title.includes('cycle detected')) return true;
            if (data.type === 'Hubs' && node.title.includes('Hub account')) return true;
            return false;
        }});

        var filteredNodeIds = filteredNodes.map(function(n) {{ return n.id; }});
        var filteredEdges = edges.get().filter(function(edge) {{
            return filteredNodeIds.includes(edge.from) && filteredNodeIds.includes(edge.to);
        }});

        network.setData({{
            nodes: filteredNodes,
            edges: filteredEdges
        }});
    }}
    else if (data.action === 'search') {{
        var searchId = data.value.trim().toUpperCase();
        var node = nodes.get(searchId);
        if (node) {{
            network.selectNodes([searchId]);
            network.focus(searchId, {{
                scale: 1.5,
                animation: {{ duration: 1000, easingFunction: 'easeInOutQuad' }}
            }});
        }} else {{
            network.unselectAll();
            network.fit({{ animation: {{ duration: 1000 }} }});
        }}
    }}
    else if (data.action === 'snapshot') {{
        var canvas = document.querySelector('canvas');
        var url = canvas.toDataURL();
        var a = document.createElement('a');
        a.href = url;
        a.download = 'graph_snapshot.png';
        a.click();
    }}
    else if (data.action === 'resetZoom') {{
        network.fit({{ animation: {{ duration: 1000, easingFunction: 'easeInOutQuad' }} }});
    }}
    else if (data.action === 'zoomIn') {{
        var scale = network.getScale() * 1.5;
        network.moveTo({{ scale: scale, animation: {{ duration: 500 }} }});
    }}
    else if (data.action === 'zoomOut') {{
        var scale = network.getScale() / 1.5;
        network.moveTo({{ scale: scale, animation: {{ duration: 500 }} }});
    }}
}});

</script>
</body>
</html>"""
    return html


# ── Analytics Chart Generation

def generate_analytics_charts(df, risk_scores):
    charts = {}

    # 1. Transaction amount distribution (histogram)
    plt.figure(figsize=(8, 4))
    sns.histplot(df['amount'], bins=50, color='#4A90D9', log_scale=True)
    plt.title('Transaction Amount Distribution (Log Scale)')
    plt.xlabel('Amount (₹)')
    plt.ylabel('Count')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    charts['amount_dist'] = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()

    # 2. Fraud pattern breakdown
    patterns = {'Circular': 0, 'Structuring': 0, 'Dormant': 0, 'Hub': 0}
    for acc, info in risk_scores.items():
        if acc == "_metadata": continue
        for r in info.get('reasons', []):
            if 'circular' in r.lower(): patterns['Circular'] += 1
            if 'structuring' in r.lower(): patterns['Structuring'] += 1
            if 'dormant' in r.lower(): patterns['Dormant'] += 1
            if 'hub' in r.lower(): patterns['Hub'] += 1

    plt.figure(figsize=(8, 4))
    sns.barplot(x=list(patterns.keys()), y=list(patterns.values()), palette='rocket')
    plt.title('Fraud Patterns Detected (Accounts Triggered)')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    charts['fraud_patterns'] = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()

    # 3. Transaction volume over time
    df['date'] = pd.to_datetime(df['timestamp']).dt.date
    daily_vol = df.groupby('date')['amount'].sum().reset_index()
    plt.figure(figsize=(10, 4))
    sns.lineplot(data=daily_vol, x='date', y='amount', color='#2A9D8F', linewidth=2)
    plt.title('Transaction Volume Over Time')
    plt.xlabel('Date')
    plt.ylabel('Total Volume (₹)')
    plt.xticks(rotation=45)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    charts['volume_time'] = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()

    # 4. Correlation heatmap
    features_list = [v['features'] for k, v in risk_scores.items() if k != "_metadata" and 'features' in v and v['features']]
    if features_list:
        fdf = pd.DataFrame(features_list)
        plt.figure(figsize=(8, 6))
        sns.heatmap(fdf.corr(), annot=False, cmap='coolwarm', center=0)
        plt.title('Graph Features Correlation Heatmap')
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        charts['correlation'] = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
    else:
        charts['correlation'] = ""

    # 5. Top 10 riskiest accounts
    sorted_accs = sorted([(k, v['score']) for k, v in risk_scores.items() if k != "_metadata"], key=lambda x: x[1], reverse=True)[:10]
    plt.figure(figsize=(8, 4))
    sns.barplot(x=[x[1] for x in sorted_accs], y=[x[0] for x in sorted_accs], palette='Reds_r')
    plt.title('Top 10 Riskiest Accounts')
    plt.xlabel('Risk Score')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    charts['top_risky'] = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()

    # 6. Feature importances
    metadata = risk_scores.get("_metadata", {})
    importances = metadata.get("feature_importances", {})
    if importances:
        s_imp = sorted(importances.items(), key=lambda x: x[1], reverse=True)
        plt.figure(figsize=(8, 4))
        sns.barplot(x=[x[1] for x in s_imp], y=[x[0] for x in s_imp], palette='viridis')
        plt.title('Which signals matter most for fraud detection?')
        plt.xlabel('Importance')
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        charts['feature_importance'] = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()
    else:
        charts['feature_importance'] = ""

    # ML Stats
    high_risk = sum(1 for k, v in risk_scores.items() if k != "_metadata" and v['risk_level'] == 'High')
    med_risk = sum(1 for k, v in risk_scores.items() if k != "_metadata" and v['risk_level'] == 'Medium')
    total = len([k for k in risk_scores.keys() if k != "_metadata"])

    most_common_pattern = max(patterns, key=patterns.get) if any(patterns.values()) else "None"

    stats = {
        'total_analysed': total,
        'high_count': high_risk,
        'high_pct': round(high_risk / total * 100, 1) if total > 0 else 0,
        'med_count': med_risk,
        'med_pct': round(med_risk / total * 100, 1) if total > 0 else 0,
        'most_common_pattern': most_common_pattern
    }

    return charts, stats
