"""
data_generator.py
-----------------
Generates a synthetic bank transactions CSV with 300 rows.
Deliberately plants 4 fraud patterns for the FundTrace demo.
Run this FIRST before starting the Flask app.

Usage:
    python data_generator.py
"""

import pandas as pd
import random
from datetime import datetime, timedelta

# ── Configuration 
random.seed(42)  # Fixed seed for reproducible results

# All 60 account IDs
ACCOUNTS = [f"ACC{str(i).zfill(3)}" for i in range(1, 61)]

CHANNELS = ["mobile", "UPI", "branch", "NEFT", "RTGS"]
BRANCHES = ["Mumbai", "Delhi", "Pune", "Chennai", "Hyderabad"]

# Base reference time — "now" for the simulation
NOW = datetime(2026, 3, 29, 22, 53, 3)  # Matches current local time
START_DATE = NOW - timedelta(days=90)      # 90-day window for transactions


def random_timestamp(start=START_DATE, end=NOW):
    """Return a random datetime between start and end."""
    delta = end - start
    random_seconds = random.randint(0, int(delta.total_seconds()))
    return start + timedelta(seconds=random_seconds)


def make_txn(tx_id, sender, receiver, amount, timestamp=None, channel=None, branch=None):
    """Helper that builds a single transaction dictionary."""
    return {
        "transaction_id": f"TXN{str(tx_id).zfill(5)}",
        "sender_id": sender,
        "receiver_id": receiver,
        "amount": round(amount, 2),
        "timestamp": (timestamp or random_timestamp()).strftime("%Y-%m-%d %H:%M:%S"),
        "channel": channel or random.choice(CHANNELS),
        "branch": branch or random.choice(BRANCHES),
    }


# ── Fraud Pattern Generators 

def generate_circular_pattern(start_id):
    """
    FRAUD PATTERN 1 — Circular Fund Flow
    ACC001 → ACC002 → ACC003 → ACC004 → ACC001
    Money goes in a loop to obscure its origin (classic layering).
    """
    txns = []
    chain = ["ACC001", "ACC002", "ACC003", "ACC004", "ACC001"]
    base_time = random_timestamp()
    for i in range(len(chain) - 1):
        txns.append(make_txn(
            start_id + i,
            sender=chain[i],
            receiver=chain[i + 1],
            amount=random.uniform(44000, 46000),  # ~₹45,000 each hop
            timestamp=base_time + timedelta(hours=i * 2),
            channel="NEFT",
            branch="Mumbai",
        ))
    return txns


def generate_structuring_pattern(start_id):
    """
    FRAUD PATTERN 2 — Structuring (Smurfing)
    ACC010 splits a large sum into multiple transactions just below ₹10,000
    to avoid automatic reporting thresholds.
    """
    txns = []
    receivers = ["ACC011", "ACC012", "ACC013", "ACC014", "ACC015", "ACC016"]
    base_time = random_timestamp()
    for i, recv in enumerate(receivers):
        txns.append(make_txn(
            start_id + i,
            sender="ACC010",
            receiver=recv,
            amount=random.uniform(8500, 9800),  # just below ₹10,000
            timestamp=base_time + timedelta(hours=i * 3),  # within 24 hours
            channel="UPI",
            branch="Delhi",
        ))
    return txns


def generate_dormant_account_pattern(start_id):
    """
    FRAUD PATTERN 3 — Dormant Account Activation
    ACC020 is inactive for 75 days, then receives ₹180,000 and immediately
    forwards ₹175,000 — a sign of a money-mule account.
    """
    # The dormancy break happens near the end of the 90-day window
    activation_time = START_DATE + timedelta(days=76)
    txns = [
        make_txn(start_id,     "ACC021", "ACC020", 180000,
                 activation_time, "RTGS", "Chennai"),
        make_txn(start_id + 1, "ACC020", "ACC022", 175000,
                 activation_time + timedelta(hours=1), "RTGS", "Chennai"),
    ]
    return txns


def generate_hub_pattern(start_id):
    """
    FRAUD PATTERN 4 — Hub Account (Fan-In)
    ACC030 receives money from 12 different accounts within 48 hours.
    High in-degree nodes can indicate money collection hubs.
    """
    txns = []
    senders = [a for a in ACCOUNTS if a not in
               ("ACC001","ACC002","ACC003","ACC004","ACC010",
                "ACC011","ACC012","ACC013","ACC014","ACC015","ACC016",
                "ACC020","ACC021","ACC022","ACC030")][:12]
    base_time = random_timestamp()
    for i, sender in enumerate(senders):
        txns.append(make_txn(
            start_id + i,
            sender=sender,
            receiver="ACC030",
            amount=random.uniform(5000, 50000),
            timestamp=base_time + timedelta(hours=i * 3),  # spread over 36 hrs
            channel=random.choice(CHANNELS),
            branch=random.choice(BRANCHES),
        ))
    return txns


# ── Main Generator 

def generate_transactions():
    """
    Builds the full 300-row transactions list.
    First adds all planted fraud transactions, then fills the rest
    with normal random transactions between random accounts.
    """
    txns = []
    tx_id = 1

    # Plant the 4 fraud patterns
    circular   = generate_circular_pattern(tx_id);        txns.extend(circular);   tx_id += len(circular)
    structured = generate_structuring_pattern(tx_id);     txns.extend(structured); tx_id += len(structured)
    dormant    = generate_dormant_account_pattern(tx_id); txns.extend(dormant);    tx_id += len(dormant)
    hub        = generate_hub_pattern(tx_id);             txns.extend(hub);        tx_id += len(hub)

    # Fill remaining rows with normal transactions (up to 300 total)
    fraud_accounts = {"ACC001","ACC002","ACC003","ACC004",
                      "ACC010","ACC011","ACC012","ACC013","ACC014","ACC015","ACC016",
                      "ACC020","ACC021","ACC022","ACC030"}

    while len(txns) < 300:
        sender   = random.choice(ACCOUNTS)
        receiver = random.choice(ACCOUNTS)
        if sender == receiver:
            continue  # Skip self-transactions
        txns.append(make_txn(
            tx_id,
            sender=sender,
            receiver=receiver,
            amount=random.uniform(1000, 200000),
        ))
        tx_id += 1

    return txns


# ── Entry Point 

if __name__ == "__main__":
    print("Generating synthetic transactions...")
    transactions = generate_transactions()
    df = pd.DataFrame(transactions[:300])  # Trim to exactly 300 rows

    # Sort by timestamp so the CSV reads naturally chronological
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    output_path = "transactions.csv"
    df.to_csv(output_path, index=False)
    print(f"✅ Saved {len(df)} transactions to {output_path}")
    print(f"   Accounts involved: {df['sender_id'].nunique() + df['receiver_id'].nunique()} unique IDs")
    print(f"   Date range: {df['timestamp'].min()} → {df['timestamp'].max()}")
