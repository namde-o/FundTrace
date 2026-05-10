# FundTrace 🔍

**Enterprise-Grade Fraud Detection & Fund Flow Intelligence Dashboard**  
Built for the bank hackathon on the theme: *"Tracking of Funds within the Bank for Fraud Detection."*

FundTrace is a sophisticated, offline-first intelligence platform that combines **Graph Network Analysis** with **Machine Learning** to uncover hidden money laundering and fraudulent fund flows within banking systems.

---

## What It Does

FundTrace processes bank transaction datasets to build a **directed graph** of money flows using NetworkX. It extracts advanced graph metrics (PageRank, Betweenness Centrality, Degree Ratios) and employs both rule-based heuristics and unsupervised/supervised Machine Learning models (Isolation Forest & Random Forest) to assign comprehensive risk scores (0–100) to every account. 

Insights are visualized through an **interactive Pyvis graph** and a dedicated **Data Science Analytics Dashboard**.

### Fraud Patterns Detected
| Pattern | How It Works |
|---|---|
| 🔄 Circular Flow | Money loops back to origin (classic layering) |
| 💸 Structuring | Multiple sub-₹10,000 transactions within 24 hrs |
| 💤 Dormant Account | 60+ day gap then sudden large activity |
| 🕸 Hub Account | Receives funds from 8+ different sources |

---

## Setup & Run

### 1. Install dependencies
```bash
pip install -r requirements.txt
2. Generate sample data
python data_generator.py
This generates a rich synthetic transactions.csv dataset featuring 1000 transactions, 80 accounts, localized channels, device IDs, seasonal transaction spikes, and complex planted fraud patterns.

3. Start the server
python app.py
4. Open in browser
Navigate to: http://127.0.0.1:5001

Key Features
Advanced ML Scoring — Risk scores are a weighted ensemble of Rule-Based flags (40%), Isolation Forest anomaly detection (35%), and Random Forest probabilities (25%).
Interactive Graph Analysis — Fully interactive NetworkX-powered graph (via vis.js) with real-time controls: search by account, filter by risk level or fraud pattern, zoom, and take snapshots.
Data Science Analytics — A dedicated dashboard rendering transaction distributions, fraud pattern breakdowns, correlation heatmaps, and ML feature importances.
Risk Leaderboard & Drilldown — View top risky accounts with 0-100 progress bars, and drill down to inspect an account's complete transaction history and detailed ML breakdown.
Offline & Secure — No external API calls are made (libraries loaded via CDN); all data processing and chart generation happens locally.
Client-Side Validation — Upload your own datasets with robust client-side preview and column validation.
Project Structure
fundtrace/
├── app.py               Flask backend application and REST routes
├── graph_engine.py      Graph construction, ML modeling, Risk scoring, Chart rendering
├── data_generator.py    Advanced synthetic CSV generator
├── transactions.csv     Auto-generated sample data
├── templates/
│   ├── layout.html      Base template (Navbar & Theme Toggle)
│   ├── index.html       Main Dashboard (Leaderboard & Account Modal)
│   ├── graph.html       Interactive Graph Workspace
│   ├── analytics.html   Data Science & ML Analytics View
│   └── upload.html      CSV Upload & Validation View
├── static/
│   └── style.css        Application styling with Dark/Light mode support
└── requirements.txt     Python dependencies (Flask, NetworkX, Pandas, Scikit-learn, Seaborn...)
