import os
import sqlite3
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "replace_this_secret")

# Database Config
DB_FILE = "expenses.db"
USE_CLOUDANT = False # Set to True if using IBM Cloudant

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_sqlite():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            email TEXT,
            password_hash TEXT,
            joined_date TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            amount REAL,
            category TEXT,
            date TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            user_id INTEGER PRIMARY KEY,
            amount REAL
        )
    """)
    conn.commit()
    conn.close()

# Initialize DB on start
init_sqlite()

# --- HELPERS ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    uid = session.get("user_id")
    if not uid: return None
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email, joined_date FROM users WHERE id=?", (uid,))
    user = cur.fetchone()
    conn.close()
    if user:
        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "joined_date": user["joined_date"] or datetime.utcnow().strftime("%Y-%m-%d")
        }
    return None

# --- ROUTES ---
@app.route('/')
def home():
    user = get_current_user()
    if not user:
        return redirect("/login")
    return render_template("dashboard.html", page="dashboard", user=user)

@app.route("/expenses")
@login_required
def expenses_page():
    return render_template("expenses.html", page="expenses", user=get_current_user())

@app.route("/analytics")
@login_required
def analytics_page():
    return render_template("analytics.html", page="analytics", user=get_current_user())

@app.route("/budget")
@login_required
def budget_page():
    return render_template("budget.html", page="budget", user=get_current_user())

@app.route("/profile")
@login_required
def profile_page():
    return render_template("profile.html", page="profile", user=get_current_user())

@app.route("/login")
def login():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    return render_template("login.html")

# --- API ---
@app.route("/api/signup", methods=["POST"])
def api_signup():
    data = request.json or {}
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    conn = get_db()
    cur = conn.cursor()
    
    # Check existing
    cur.execute("SELECT id FROM users WHERE username=?", (username,))
    if cur.fetchone():
        conn.close()
        return jsonify({"error": "Username already exists"}), 400
    
    if email:
        cur.execute("SELECT id FROM users WHERE email=?", (email,))
        if cur.fetchone():
            conn.close()
            return jsonify({"error": "Email already registered"}), 400

    # Create
    pwd_hash = generate_password_hash(password)
    joined = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        cur.execute("INSERT INTO users (username, email, password_hash, joined_date) VALUES (?, ?, ?, ?)",
                    (username, email, pwd_hash, joined))
        conn.commit()
        session["user_id"] = cur.lastrowid
        conn.close()
        return jsonify({"message": "Created"})
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 400

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    login_input = data.get("username", "").strip()
    password = data.get("password", "")
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE username=? OR email=?", (login_input, login_input))
    user = cur.fetchone()
    conn.close()
    
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401
    
    session["user_id"] = user["id"]
    return jsonify({"message": "Success"})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"message": "Logged out"})

@app.route("/api/delete_account", methods=["DELETE"])
@login_required
def api_delete_account():
    user = get_current_user()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM expenses WHERE user_id=?", (user["id"],))
    cur.execute("DELETE FROM budgets WHERE user_id=?", (user["id"],))
    cur.execute("DELETE FROM users WHERE id=?", (user["id"],))
    conn.commit()
    conn.close()
    session.clear()
    return jsonify({"message": "Deleted"})

@app.route("/api/expenses", methods=["GET", "POST"])
@login_required
def api_expenses():
    user = get_current_user()
    if request.method == "GET":
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT id, title, amount, category, date FROM expenses WHERE user_id=? ORDER BY date DESC", (user["id"],))
        rows = [dict(r) for r in cur.fetchall()]; conn.close()
        return jsonify(rows)
    
    data = request.json or {}
    try:
        if float(data.get("amount", 0)) < 0: return jsonify({"error": "Amount cannot be negative"}), 400
    except: return jsonify({"error": "Invalid amount"}), 400

    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO expenses (user_id, title, amount, category, date) VALUES (?,?,?,?,?)",
                (user["id"], data.get("title"), float(data.get("amount")), data.get("category"), data.get("date")))
    conn.commit(); conn.close()
    return jsonify({"message": "Saved"})

@app.route("/api/expenses/<eid>", methods=["DELETE"])
@login_required
def api_del_exp(eid):
    user = get_current_user()
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM expenses WHERE id=? AND user_id=?", (eid, user["id"]))
    conn.commit(); conn.close()
    return jsonify({"message": "Deleted"})

@app.route("/api/budget", methods=["GET", "PUT"])
@login_required
def api_budget():
    user = get_current_user()
    conn = get_db(); cur = conn.cursor()
    if request.method == "GET":
        cur.execute("SELECT amount FROM budgets WHERE user_id=?", (user["id"],))
        r = cur.fetchone(); conn.close()
        return jsonify({"amount": r["amount"] if r else 0})
    
    val = float(request.json.get("amount", 0))
    if val < 0: return jsonify({"error": "Budget cannot be negative"}), 400
    cur.execute("INSERT OR REPLACE INTO budgets (user_id, amount) VALUES (?,?)", (user["id"], val))
    conn.commit(); conn.close()
    return jsonify({"message": "Updated"})

@app.route("/api/analytics", methods=["GET"])
@login_required
def api_analytics():
    user = get_current_user()
    conn = get_db(); cur = conn.cursor()
    cat_tot={}; monthly={}; total=0; budget=0
    
    cur.execute("SELECT category, SUM(amount) as t FROM expenses WHERE user_id=? GROUP BY category", (user["id"],))
    for r in cur.fetchall(): cat_tot[r["category"]] = r["t"]
    
    cur.execute("SELECT strftime('%Y-%m', date) as m, SUM(amount) as t FROM expenses WHERE user_id=? GROUP BY m", (user["id"],))
    for r in cur.fetchall(): monthly[r["m"]] = r["t"]
    
    cur.execute("SELECT SUM(amount) FROM expenses WHERE user_id=?", (user["id"],)); total = cur.fetchone()[0] or 0
    cur.execute("SELECT amount FROM budgets WHERE user_id=?", (user["id"],)); b = cur.fetchone()
    budget = b["amount"] if b else 0
    conn.close()
    
    return jsonify({
        "categories": list(cat_tot.keys()), "category_amounts": list(cat_tot.values()),
        "months": sorted(list(monthly.keys())), "monthly_amounts": [monthly[k] for k in sorted(monthly.keys())],
        "total_spent": total, "budget": budget
    })

@app.route("/api/profile", methods=["PUT"])
@login_required
def api_profile():
    user = get_current_user(); data = request.json
    conn = get_db(); cur = conn.cursor()
    if data.get("email"): cur.execute("UPDATE users SET email=? WHERE id=?", (data["email"], user["id"]))
    if data.get("password"): cur.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(data["password"]), user["id"]))
    conn.commit(); conn.close()
    return jsonify({"message":"Updated"})

if __name__ == "__main__":

    app.run(debug=True)
