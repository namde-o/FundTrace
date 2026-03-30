"""
app.py
------
Flask backend for FundTrace.
Loads the transactions CSV on startup, runs fraud detection,
and serves the dashboard + data routes.

Run with: python app.py
"""

import os
import json
import pandas as pd
from flask import Flask, render_template, request, jsonify

# Import our custom analysis module
from graph_engine import (
    build_graph,
    calculate_risk_scores,
    build_pyvis_graph,
)

app = Flask(__name__)

# ── Global State 
# We keep the processed data in module-level variables so all routes can
# access them without re-reading the CSV on every request.

_df          = None   # The raw transactions dataframe
_graph       = None   # The NetworkX DiGraph
_risk_scores = None   # {account_id: {score, reasons, risk_level}}
_graph_html  = None   # The Pyvis HTML string for the iframe


def load_and_process(filepath):
    """
    Central function to read a CSV, build the graph, run fraud detection,
    and generate the Pyvis HTML — all in one call.
    Updates the global state variables.

    Args:
        filepath (str): Path to the transactions CSV

    Returns:
        str|None: Error message if something went wrong, else None
    """
    global _df, _graph, _risk_scores, _graph_html

    # ── Read & Validate ──
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        return f"Could not read CSV: {e}"

    required_cols = {"transaction_id","sender_id","receiver_id","amount","timestamp","channel","branch"}
    if not required_cols.issubset(df.columns):
        missing = required_cols - set(df.columns)
        return f"CSV is missing columns: {missing}"

    if df.empty:
        return "The uploaded CSV has no rows."

    # ── Process ──
    _df          = df
    _graph       = build_graph(df)
    _risk_scores = calculate_risk_scores(_graph, df)
    _graph_html  = build_pyvis_graph(_graph, _risk_scores)
    return None  # No error


# ── Load default CSV on startup 
DEFAULT_CSV = os.path.join(os.path.dirname(__file__), "transactions.csv")
_startup_error = None

if os.path.exists(DEFAULT_CSV):
    _startup_error = load_and_process(DEFAULT_CSV)
else:
    _startup_error = (
        "transactions.csv not found. "
        "Please run: python data_generator.py"
    )


# ── Routes 

@app.route("/")
def index():
    """
    GET /
    Serves the main dashboard page.
    Passes the Pyvis graph HTML and summary stats to the Jinja template.
    """
    if _startup_error:
        # Show a friendly error page if data isn't loaded
        return render_template("index.html",
                               error=_startup_error,
                               graph_html="",
                               risk_scores={},
                               stats={})

    # Compute summary stats for the bottom bar
    stats = {
        "total_accounts":    len(_graph.nodes()),
        "total_transactions": len(_df),
        "high_risk_count":   sum(1 for v in _risk_scores.values() if v["risk_level"] == "High"),
        "medium_risk_count": sum(1 for v in _risk_scores.values() if v["risk_level"] == "Medium"),
    }

    return render_template("index.html",
                           error=None,
                           graph_html=_graph_html,
                           risk_scores=_risk_scores,
                           stats=stats)


@app.route("/upload", methods=["POST"])
def upload():
    """
    POST /upload
    Accepts a CSV file upload, processes it, returns JSON with updated
    risk scores and a signal for the frontend to reload.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.endswith(".csv"):
        return jsonify({"error": "Only CSV files are supported"}), 400

    # Save to a temp location and process
    tmp_path = "/tmp/fundtrace_upload.csv"
    file.save(tmp_path)
    err = load_and_process(tmp_path)

    if err:
        return jsonify({"error": err}), 400

    # Return top stats so the frontend can update without a full page reload
    return jsonify({
        "message": "File processed successfully",
        "total_accounts":    len(_graph.nodes()),
        "total_transactions": len(_df),
        "high_risk_count":   sum(1 for v in _risk_scores.values() if v["risk_level"] == "High"),
        "medium_risk_count": sum(1 for v in _risk_scores.values() if v["risk_level"] == "Medium"),
    })


@app.route("/account/<account_id>")
def account_detail(account_id):
    """
    GET /account/<account_id>
    Returns full transaction history + risk profile for one account as JSON.
    Used by the frontend when a user clicks an account card.
    """
    if _df is None:
        return jsonify({"error": "No data loaded"}), 503

    if account_id not in _risk_scores:
        return jsonify({"error": f"Account {account_id} not found"}), 404

    # Pull rows where this account is sender or receiver
    sent     = _df[_df["sender_id"]   == account_id].to_dict(orient="records")
    received = _df[_df["receiver_id"] == account_id].to_dict(orient="records")

    return jsonify({
        "account_id":  account_id,
        "risk":        _risk_scores[account_id],
        "sent":        sent,
        "received":    received,
        "total_sent":      sum(r["amount"] for r in sent),
        "total_received":  sum(r["amount"] for r in received),
    })


@app.route("/api/risk-leaderboard")
def risk_leaderboard():
    """
    GET /api/risk-leaderboard
    Returns the top 15 highest-risk accounts sorted by score (descending).
    Used to populate the left sidebar leaderboard.
    """
    if not _risk_scores:
        return jsonify([])

    # Sort accounts by score descending, then alphabetically for ties
    sorted_accounts = sorted(
        _risk_scores.items(),
        key=lambda x: (-x[1]["score"], x[0])
    )[:15]

    leaderboard = [
        {"account_id": acc_id, **info}
        for acc_id, info in sorted_accounts
    ]
    return jsonify(leaderboard)


@app.route("/api/graph-html")
def graph_html_route():
    """
    GET /api/graph-html
    Returns the Pyvis graph HTML so the frontend can refresh the iframe
    after a CSV upload without a full page reload.
    """
    if _graph_html is None:
        return "No graph data available.", 503
    return _graph_html, 200, {"Content-Type": "text/html"}


# ── Run 
if __name__ == "__main__":
    print("🚀 Starting FundTrace...")
    print(f"   Data loaded: {'✅ Yes' if _df is not None else '❌ No - run data_generator.py first'}")
    print("   Open http://127.0.0.1:5001 in your browser")
    app.run(debug=True, port=5001)
