from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
from datetime import datetime
from algosdk.v2client import algod
from algosdk import transaction, account, mnemonic

# ----------------- Algorand Setup -----------------
ALGOD_ADDRESS = "https://testnet-algorand.api.purestake.io/ps2"
ALGOD_TOKEN = "YOUR_PURESTAKE_API_KEY"  # Replace with your PureStake API key
HEADERS = {"X-API-Key": ALGOD_TOKEN}
algod_client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS, HEADERS)

# Alice's test account (for sending tokens)
ALICE_MNEMONIC = "PASTE_ALICE_MNEMONIC_HERE"  # Replace with test account mnemonic
ALICE_PRIVATE_KEY = mnemonic.to_private_key(ALICE_MNEMONIC)
ALICE_ADDRESS = account.address_from_private_key(ALICE_PRIVATE_KEY)

# ----------------- Flask Setup -----------------
app = Flask(__name__)
CORS(app)  # Allow frontend connection

# ----------------- DB Setup -----------------
conn = sqlite3.connect('payroll.db', check_same_thread=False)
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS wallet (
    employee TEXT PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    salary INTEGER DEFAULT 0,
    monthly_salary INTEGER DEFAULT 3000,
    connected INTEGER DEFAULT 0
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT,
    amount INTEGER,
    recipient TEXT,
    email TEXT,
    date TEXT
)
''')

c.execute("INSERT OR IGNORE INTO wallet (employee) VALUES ('Alice')")
conn.commit()

# ----------------- Helper Functions -----------------
def send_algo(receiver: str, amount: int):
    """Send ALGOs from Alice account to receiver (amount in microAlgos)."""
    try:
        params = algod_client.suggested_params()
        amount_micro = amount * 1_000_000
        txn = transaction.PaymentTxn(ALICE_ADDRESS, params, receiver, amount_micro)
        stxn = txn.sign(ALICE_PRIVATE_KEY)
        txid = algod_client.send_transaction(stxn)
        transaction.wait_for_confirmation(algod_client, txid, 4)
        return True, txid
    except Exception as e:
        return False, str(e)

# ----------------- Routes -----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/wallet/connect", methods=["POST"])
def connect_wallet():
    c.execute("SELECT connected FROM wallet WHERE employee='Alice'")
    status = c.fetchone()[0]
    new_status = 0 if status else 1
    c.execute("UPDATE wallet SET connected=? WHERE employee='Alice'", (new_status,))
    conn.commit()
    c.execute("SELECT * FROM wallet WHERE employee='Alice'")
    wallet = c.fetchone()
    return jsonify({
        "employee": wallet[0],
        "balance": wallet[1],
        "salary": wallet[2],
        "monthly_salary": wallet[3],
        "connected": bool(wallet[4])
    })

@app.route("/wallet", methods=["GET"])
def get_wallet():
    c.execute("SELECT * FROM wallet WHERE employee='Alice'")
    wallet = c.fetchone()
    return jsonify({
        "employee": wallet[0],
        "balance": wallet[1],
        "salary": wallet[2],
        "monthly_salary": wallet[3],
        "connected": bool(wallet[4])
    })

@app.route("/withdraw", methods=["POST"])
def withdraw():
    data = request.get_json()
    amount = data.get("amount", 0)
    c.execute("SELECT balance, salary FROM wallet WHERE employee='Alice'")
    balance, salary = c.fetchone()
    if amount <= 0 or amount > salary:
        return jsonify({"message": "Invalid or insufficient balance"}), 400
    salary -= amount
    balance += amount
    c.execute("UPDATE wallet SET salary=?, balance=? WHERE employee='Alice'", (salary, balance))
    c.execute("INSERT INTO transactions (type, amount, date) VALUES ('Withdraw', ?, ?)", (amount, datetime.now().isoformat()))
    conn.commit()
    return jsonify({"message": f"Withdrawn {amount} Tokens", "wallet": {"balance": balance, "salary": salary}})

@app.route("/milestone", methods=["POST"])
def milestone():
    data = request.get_json()
    milestone = data.get("milestone")
    amount = data.get("amount", 0)
    c.execute("SELECT salary FROM wallet WHERE employee='Alice'")
    salary = c.fetchone()[0] + amount
    c.execute("UPDATE wallet SET salary=? WHERE employee='Alice'", (salary,))
    c.execute("INSERT INTO transactions (type, amount, date) VALUES (?, ?, ?)", (f"Milestone {milestone}", amount, datetime.now().isoformat()))
    conn.commit()
    return jsonify({"message": f"Milestone {milestone} Released", "wallet": {"salary": salary}})

@app.route("/payment", methods=["POST"])
def payment():
    data = request.get_json()
    recipient = data.get("recipient")
    amount = data.get("amount", 0)
    c.execute("SELECT balance FROM wallet WHERE employee='Alice'")
    balance = c.fetchone()[0]
    if amount <= 0 or amount > balance:
        return jsonify({"message": "Invalid or insufficient wallet balance"}), 400

    success, tx_info = send_algo(recipient, amount)
    if not success:
        return jsonify({"message": f"Blockchain transaction failed: {tx_info}"}), 500

    balance -= amount
    c.execute("UPDATE wallet SET balance=? WHERE employee='Alice'", (balance,))
    c.execute("INSERT INTO transactions (type, amount, recipient, date) VALUES ('Payment', ?, ?, ?)", (amount, recipient, datetime.now().isoformat()))
    conn.commit()
    return jsonify({"message": f"Sent {amount} Tokens to {recipient} on Algorand ✅", "txid": tx_info, "wallet": {"balance": balance}})

@app.route("/settings", methods=["POST"])
def settings():
    data = request.get_json()
    email = data.get("email")
    c.execute("INSERT INTO transactions (type, email, date) VALUES ('Settings', ?, ?)", (email, datetime.now().isoformat()))
    conn.commit()
    return jsonify({"message": f"Delegate access granted to {email}"})

@app.route("/history", methods=["GET"])
def history():
    c.execute("SELECT type, amount, recipient, email, date FROM transactions ORDER BY date DESC")
    txs = [{"type": t[0], "amount": t[1], "recipient": t[2], "email": t[3], "date": t[4]} for t in c.fetchall()]
    return jsonify(txs)

# ----------------- Run Server -----------------
if __name__ == "__main__":
    app.run(debug=True)s
