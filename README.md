# FundTrace 🔍

FundTrace is a Flask-based fraud analytics dashboard for bank transaction monitoring.  
It combines graph analysis and ML-based scoring to identify risky accounts and suspicious fund movement patterns.

## Highlights

- Directed transaction graph using **NetworkX**
- Rule-based fraud pattern detection
- ML-assisted scoring using **Isolation Forest** and **Random Forest**
- Interactive graph exploration (filter, search, zoom, snapshot)
- Risk leaderboard with account-level drilldown
- Analytics dashboard with charts and feature insights
- CSV upload flow for running analysis on new datasets

## Fraud Patterns Detected

| Pattern | Rule |
|---|---|
| Circular flow | Account is part of a directed cycle involving at least 3 accounts (example: A → B → C → A) |
| Structuring | 4+ outgoing transactions just below ₹10,000 (₹8,000–₹9,999) within 24 hours |
| Dormant activation | 60+ day inactivity gap before activity |
| Hub account | In-degree (incoming sources) ≥ 8 |

## Risk Scoring

Each account gets a **0–100** score from:

- **40%** rule-based score
- **35%** Isolation Forest anomaly score
- **25%** Random Forest probability

Risk levels:

- **High**: 67–100
- **Medium**: 34–66
- **Low**: 0–33

## Quick Start

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

### 2) Generate sample data

```bash
python data_generator.py
```

This creates `transactions.csv` (1000 synthetic transactions across 80 account IDs), including planted fraud patterns and extra fields such as `transaction_type`, `location`, and `device_id`.

### 3) Run the app

```bash
python app.py
```

### 4) Open in browser

`http://127.0.0.1:5001`

## Input CSV Requirements

The backend requires these columns:

- `transaction_id`
- `sender_id`
- `receiver_id`
- `amount`
- `timestamp`
- `channel`
- `branch`

## Main Routes

- `/` — Main dashboard (leaderboard + graph + account drilldown)
- `/graph` — Graph workspace with controls
- `/analytics` — Data science analytics view
- `/upload` — Upload page for new CSV data
- `/api/risk-leaderboard` — Top risky accounts (JSON)
- `/api/graph-html` — Rendered graph HTML
- `/account/<account_id>` — Account detail + transaction history (JSON)

## Project Structure

```text
FundTrace/
├── app.py
├── graph_engine.py
├── data_generator.py
├── transactions.csv
├── requirements.txt
├── templates/
│   ├── layout.html
│   ├── index.html
│   ├── graph.html
│   ├── analytics.html
│   └── upload.html
└── static/
    └── style.css
```
