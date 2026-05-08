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
ACCOUNTS = [f"ACC{str(i).zfill(3)}" for i in range(1, 81)]

CHANNELS = ["mobile", "UPI", "branch", "NEFT", "RTGS"]
BRANCHES = ["Mumbai", "Delhi", "Pune", "Chennai", "Hyderabad"]

# Base reference time — "now" for the simulation
NOW = datetime(2026, 3, 29, 22, 53, 3)  # Matches current local time
START_DATE = NOW - timedelta(days=90)      # 90-day window for transactions


def random_timestamp(start=START_DATE, end=NOW):
    """Return a random datetime between start and end. More likely to be on a weekend."""
    delta = end - start
    while True:
        random_seconds = random.randint(0, int(delta.total_seconds()))
        ts = start + timedelta(seconds=random_seconds)
        # 60% chance to accept if weekend, 20% if weekday
        if ts.weekday() >= 5:
            if random.random() < 0.6: return ts
        else:
            if random.random() < 0.2: return ts


def make_txn(tx_id, sender, receiver, amount, timestamp=None, channel=None, branch=None, transaction_type=None, location=None, device_id=None):
    """Helper that builds a single transaction dictionary."""
    return {
        "transaction_id": f"TXN{str(tx_id).zfill(5)}",
        "sender_id": sender,
        "receiver_id": receiver,
        "amount": round(amount, 2),
        "timestamp": (timestamp or random_timestamp()).strftime("%Y-%m-%d %H:%M:%S"),
        "channel": channel or random.choice(CHANNELS),
        "branch": branch or random.choice(BRANCHES),
        "transaction_type": transaction_type or random.choice(["NEFT", "IMPS", "UPI", "RTGS"]),
        "location": location or random.choice(["Mumbai", "Delhi", "Pune", "Chennai", "Hyderabad", "Bangalore", "Kolkata"]),
        "device_id": device_id or f"DEV{random.randint(1000, 9999)}",
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
    Builds the full 1000-row transactions list.
    First adds all planted fraud transactions, then fills the rest
    with normal random transactions between random accounts.
    """
    txns = []
    tx_id = 1

    # Plant multiple instances of the 4 fraud patterns
    # Pattern 1
    for offset in range(0, 5):
        circular   = generate_circular_pattern(tx_id); txns.extend(circular); tx_id += len(circular)
        # slightly hacky but works for the demo: rename accounts in the new pattern
        if offset > 0:
            for t in circular:
                t['sender_id'] = f"ACC{int(t['sender_id'][3:]) + offset*10:03d}"
                t['receiver_id'] = f"ACC{int(t['receiver_id'][3:]) + offset*10:03d}"

    # Pattern 2
    for offset in range(0, 4):
        structured = generate_structuring_pattern(tx_id); txns.extend(structured); tx_id += len(structured)
        if offset > 0:
             for t in structured:
                 t['sender_id'] = f"ACC{int(t['sender_id'][3:]) + offset*20:03d}"
                 t['receiver_id'] = f"ACC{int(t['receiver_id'][3:]) + offset*20:03d}"

    # Pattern 3
    for offset in range(0, 3):
        dormant    = generate_dormant_account_pattern(tx_id); txns.extend(dormant); tx_id += len(dormant)
        if offset > 0:
            for t in dormant:
                 t['sender_id'] = f"ACC{int(t['sender_id'][3:]) + offset*10:03d}"
                 t['receiver_id'] = f"ACC{int(t['receiver_id'][3:]) + offset*10:03d}"

    # Pattern 4
    for offset in range(0, 4):
        hub        = generate_hub_pattern(tx_id); txns.extend(hub); tx_id += len(hub)
        if offset > 0:
            for t in hub:
                 t['sender_id'] = f"ACC{int(t['sender_id'][3:]) + offset*5:03d}"
                 if t['receiver_id'] == 'ACC030':
                     t['receiver_id'] = f"ACC{30 + offset*5:03d}"

    # Fill remaining rows with normal transactions (up to 1000 total)
    while len(txns) < 1000:
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
    df = pd.DataFrame(transactions[:1000])  # Trim to exactly 300 rows

    # Sort by timestamp so the CSV reads naturally chronological
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    output_path = "transactions.csv"
    df.to_csv(output_path, index=False)
    print(f"✅ Saved {len(df)} transactions to {output_path}")
    print(f"   Accounts involved: {df['sender_id'].nunique() + df['receiver_id'].nunique()} unique IDs")
    print(f"   Date range: {df['timestamp'].min()} → {df['timestamp'].max()}")
