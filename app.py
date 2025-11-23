import os
import sqlite3
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()
app = Flask(__name__)
# It's highly recommended to set this as an environment variable in production
app.secret_key = os.getenv("SECRET_KEY", "replace_this_secret") 

# ---------------- DATABASE ----------------
DB_FILE = "expenses.db"

def get_db():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    # Set row_factory to sqlite3.Row to allow column access by name
    conn.row_factory = sqlite3.Row 
    return conn

def init_sqlite():
    """Initializes the database tables if they do not exist."""
    conn = get_db()
    cur = conn.cursor()

    # Users Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            joined_date TEXT
        )
    """)

    # Expenses Table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            amount REAL,
            category TEXT,
            date TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Budgets Table (using user_id as PRIMARY KEY ensures only one budget per user)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            user_id INTEGER PRIMARY KEY,
            amount REAL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()

init_sqlite()

# ---------------- HELPERS ----------------
def login_required(f):
    """Decorator to ensure a user is logged in before accessing a route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            # Redirect to login if not logged in
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    """Retrieves the current user's details from the database."""
    uid = session.get("user_id")
    if not uid: return None
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email, joined_date FROM users WHERE id=?", (uid,))
    user = cur.fetchone()
    conn.close()
    if user:
        # Return user details as a dictionary
        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "joined_date": user["joined_date"] or datetime.utcnow().strftime("%Y-%m-%d")
        }
    return None

# ---------------- PAGES ----------------
@app.route("/")
def home():
    """Root route redirects to the login page."""
    return redirect("/login")

@app.route("/login")
def login():
    """Login page. Redirects to dashboard if already logged in."""
    if "user_id" in session:
        return redirect("/dashboard")
    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    """Main dashboard page."""
    return render_template("dashboard.html", page="dashboard", user=get_current_user())

@app.route("/expenses")
@login_required
def expenses_page():
    """Expenses management page."""
    return render_template("expenses.html", page="expenses", user=get_current_user())

@app.route("/analytics")
@login_required
def analytics_page():
    """Analytics and reporting page."""
    return render_template("analytics.html", page="analytics", user=get_current_user())

@app.route("/budget")
@login_required
def budget_page():
    """Budget setting page."""
    return render_template("budget.html", page="budget", user=get_current_user())

@app.route("/profile")
@login_required
def profile_page():
    """User profile page."""
    return render_template("profile.html", page="profile", user=get_current_user())


# ---------------- AUTH API ----------------
@app.route("/api/signup", methods=["POST"])
def api_signup():
    """API endpoint for new user registration."""
    data = request.json or {}
    
    # FIX: Replaced non-existent .trim() with Python's .strip()
    username = data.get("username", "").strip() 
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error":"Username and password required"}), 400

    conn = get_db(); cur = conn.cursor()
    
    # Check for existing username
    cur.execute("SELECT id FROM users WHERE username=?", (username,))
    if cur.fetchone():
        conn.close()
        return jsonify({"error":"Username already exists"}), 400

    # Check for existing email if provided
    if email:
        cur.execute("SELECT id FROM users WHERE email=?", (email,))
        if cur.fetchone():
            conn.close()
            return jsonify({"error":"Email already registered"}), 400

    # Hash password and store user
    pwd_hash = generate_password_hash(password)
    joined = datetime.utcnow().strftime("%Y-%m-%d")
    cur.execute("""
        INSERT INTO users (username, email, password_hash, joined_date)
        VALUES (?,?,?,?)
    """,(username,email,pwd_hash,joined))
    conn.commit()
    
    # Automatically log in the user upon successful signup
    session["user_id"] = cur.lastrowid
    conn.close()
    return jsonify({"message":"Created"})

@app.route("/api/login", methods=["POST"])
def api_login():
    """API endpoint for user login."""
    data = request.json or {}
    # Handles login via username OR email
    login_input = data.get("username","").strip() 
    password = data.get("password","")

    conn = get_db(); cur = conn.cursor()
    # Query by username or email
    cur.execute("SELECT id, password_hash FROM users WHERE username=? OR email=?", (login_input, login_input))
    user = cur.fetchone()
    conn.close()

    # Check credentials
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error":"Invalid credentials"}), 401

    session["user_id"] = user["id"]
    return jsonify({"message":"Success"})

@app.route("/api/logout", methods=["POST"])
def api_logout():
    """API endpoint for user logout."""
    session.clear()
    return jsonify({"message":"Logged out"})


# ---------------- EXPENSES API ----------------
@app.route("/api/expenses", methods=["GET","POST"])
@login_required
def api_expenses():
    """Handles fetching and adding expenses."""
    user = get_current_user()

    if request.method == "GET":
        conn = get_db(); cur = conn.cursor()
        # Fetch all expenses for the current user, ordered by date
        cur.execute("SELECT id, title, amount, category, date FROM expenses WHERE user_id=? ORDER BY date DESC", (user["id"],))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return jsonify(rows)

    # POST method (Add new expense)
    data = request.json or {}
    
    # Basic validation
    try:
        amount = float(data.get("amount",0))
        if amount <= 0:
             return jsonify({"error":"Amount must be positive"}), 400
    except ValueError:
        return jsonify({"error":"Invalid amount"}), 400

    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO expenses (user_id,title,amount,category,date) VALUES (?,?,?,?,?)",
                (user["id"], data.get("title").strip(), amount, data.get("category").strip(), data.get("date")))
    conn.commit(); conn.close()
    return jsonify({"message":"Saved"})

@app.route("/api/expenses/<eid>", methods=["DELETE"])
@login_required
def api_del_exp(eid):
    """API endpoint to delete a specific expense."""
    user = get_current_user()
    conn = get_db(); cur = conn.cursor()
    # Delete the expense only if it belongs to the current user
    cur.execute("DELETE FROM expenses WHERE id=? AND user_id=?", (eid, user["id"]))
    conn.commit(); conn.close()
    return jsonify({"message":"Deleted"})


# ---------------- BUDGET API ----------------
@app.route("/api/budget", methods=["GET","PUT"])
@login_required
def api_budget():
    """Handles fetching and updating the user's budget."""
    user = get_current_user()
    conn = get_db(); cur = conn.cursor()

    if request.method == "GET":
        cur.execute("SELECT amount FROM budgets WHERE user_id=?", (user["id"],))
        r = cur.fetchone(); conn.close()
        # Returns 0 if no budget is set
        return jsonify({"amount": r["amount"] if r else 0.0})

    # PUT method (Update or set budget)
    data = request.json or {}
    try:
        val = float(data.get("amount", 0))
    except ValueError:
        return jsonify({"error":"Invalid budget amount"}), 400

    if val < 0: return jsonify({"error":"Budget cannot be negative"}), 400

    # INSERT OR REPLACE handles both insertion (first time) and update (subsequent times)
    cur.execute("INSERT OR REPLACE INTO budgets (user_id,amount) VALUES (?,?)", (user["id"], val))
    conn.commit(); conn.close()
    return jsonify({"message":"Updated"})


# ---------------- ANALYTICS API ----------------
@app.route("/api/analytics", methods=["GET"])
@login_required
def api_analytics():
    """Calculates and returns expense analytics for the user."""
    user = get_current_user()
    conn = get_db(); cur = conn.cursor()
    cat_tot = {} # Category totals
    monthly = {} # Monthly totals

    # 1. Total spent per category
    cur.execute("SELECT category, SUM(amount) as t FROM expenses WHERE user_id=? GROUP BY category", (user["id"],))
    for r in cur.fetchall(): cat_tot[r["category"]] = r["t"]

    # 2. Total spent per month
    cur.execute("SELECT strftime('%Y-%m', date) as m, SUM(amount) as t FROM expenses WHERE user_id=? GROUP BY m", (user["id"],))
    for r in cur.fetchall(): monthly[r["m"]] = r["t"]

    # 3. Overall total spent
    cur.execute("SELECT SUM(amount) FROM expenses WHERE user_id=?", (user["id"],))
    # Fetchone returns a tuple, access the first element (index 0)
    total = cur.fetchone()[0] or 0.0

    # 4. Current budget
    cur.execute("SELECT amount FROM budgets WHERE user_id=?", (user["id"],))
    b = cur.fetchone(); budget = b["amount"] if b else 0.0

    conn.close()

    # Sort months for consistent charting
    sorted_months = sorted(list(monthly.keys()))

    return jsonify({
        "categories": list(cat_tot.keys()),
        "category_amounts": list(cat_tot.values()),
        "months": sorted_months,
        "monthly_amounts": [monthly[m] for m in sorted_months],
        "total_spent": total,
        "budget": budget
    })


# ---------------- RUN ----------------
if __name__ == "__main__":
    # Ensure debug is off in production environments
    app.run(debug=True)
