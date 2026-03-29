# FundTrace 🔍

**Interactive fraud detection dashboard for tracking fund flows within a bank.**  
Built for the bank hackathon on the theme: *"Tracking of Funds within the Bank for Fraud Detection."*

---

## What It Does

FundTrace reads a synthetic bank transactions CSV, builds a **directed graph** of money flows using NetworkX, detects 4 fraud patterns using rule-based logic, assigns risk scores to each account, and displays everything on an **interactive visual dashboard** powered by Pyvis.

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
cd fundtrace
pip install -r requirements.txt
```

### 2. Generate sample data
```bash
python data_generator.py
```
This creates `transactions.csv` with 300 rows and 4 planted fraud patterns.

### 3. Start the server
```bash
python app.py
```

### 4. Open in browser
Navigate to: **http://127.0.0.1:5001**

---

## Features
- **Interactive graph** — drag nodes, zoom, hover for details
- **Risk leaderboard** — top 10 risky accounts in the sidebar
- **Account drilldown** — click any account card to see its full transaction history
- **CSV upload** — load your own transactions file via the Upload button
- **Offline** — no external API calls; works fully without internet

---

## Project Structure
```
fundtrace/
├── app.py               Flask backend (4 routes)
├── graph_engine.py      Fraud detection + graph rendering
├── data_generator.py    Synthetic CSV generator
├── transactions.csv     Auto-generated sample data
├── templates/
│   └── index.html       Dashboard UI
├── static/
│   └── style.css        Dark navy stylesheet
└── requirements.txt     Python dependencies
```
