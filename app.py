from flask import Flask, render_template, url_for, request, redirect, flash, jsonify
from datetime import date
from pathlib import Path
import sqlite3

# Auth
from flask_login import (
    LoginManager, login_user, login_required, logout_user, current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash

# =========================
# Konfiguration
# =========================
app = Flask(__name__)
app.secret_key = "dev-only-change-me"  # TODO: für Produktion per ENV setzen
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

DB_PATH = Path(__file__).with_name("haushaltsbuch.db")

# Diese E-Mail (falls vorhanden) wird automatisch zum Admin gesetzt,
# sobald der Benutzer existiert.
ADMIN_EMAIL = "jonas.klaas@t-online.de"

CATEGORIES = [
    "Lebensmittel", "Miete", "Transport", "Freizeit",
    "Haushalt", "Einnahme", "Sonstiges"
]

# =========================
# Login-Manager
# =========================
login_manager = LoginManager()
login_manager.login_view = "login"  # unautorisierte Zugriffe -> Login-Seite
login_manager.login_message = "Bitte melde dich an, um diese Seite zu sehen."
login_manager.login_message_category = "error"  # nutzt unser Flash-Design
login_manager.init_app(app)

class DBUser(UserMixin):
    def __init__(self, id, email, name, is_admin: int = 0):
        self.id = str(id)
        self.email = email
        self.name = name
        self.is_admin = bool(is_admin)

@login_manager.user_loader
def load_user(user_id: str):
    u = get_user_by_id(user_id)
    if not u:
        return None
    return DBUser(u["id"], u["email"], u["name"], u.get("is_admin", 0))

# =========================
# DB-Helfer
# =========================
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Tabellen anlegen + Migrationen in richtiger Reihenfolge + optionaler Admin-Bootstrap.
    """
    with get_conn() as conn:
        # ---- users: Basis-Tabelle ohne is_admin (wird ggf. migriert) ----
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT UNIQUE NOT NULL,
              name TEXT NOT NULL,
              password_hash TEXT NOT NULL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # MIGRATION: users.is_admin nachrüsten, falls fehlt
        cols_users = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        if "is_admin" not in cols_users:
            conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")

        # ---- entries: Basis-Tabelle (user_id wird ggf. migriert) ----
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                note TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # MIGRATION: entries.user_id nachrüsten, falls fehlt
        cols_entries = {r["name"] for r in conn.execute("PRAGMA table_info(entries)")}
        if "user_id" not in cols_entries:
            conn.execute("ALTER TABLE entries ADD COLUMN user_id INTEGER REFERENCES users(id)")

        # Indizes (idempotent)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_user ON entries(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(date)")

    # WICHTIG: Bootstrap NACH allen Migrationen ausführen
    bootstrap_admin_if_configured()

def bootstrap_admin_if_configured():
    """Setzt is_admin=1 für ADMIN_EMAIL, wenn dieser User existiert."""
    if not ADMIN_EMAIL:
        return
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (ADMIN_EMAIL.lower().strip(),)
        ).fetchone()
        if row:
            conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (row["id"],))

# =========================
# User-Queries
# =========================
def create_user(name: str, email: str, password: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users(name, email, password_hash) VALUES (?, ?, ?)",
            (name.strip(), email.lower().strip(), generate_password_hash(password)),
        )

def get_user_by_email(email: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email.lower().strip(),)
        ).fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

# =========================
# Entries-Queries (mit user_id)
# =========================
def insert_entry(d: str, category: str, amount: float, note: str, user_id: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO entries (date, category, amount, note, user_id) VALUES (?, ?, ?, ?, ?)",
            (d, category, amount, note, user_id),
        )

def fetch_entries(where_sql: str = "", params: list | None = None):
    params = params or []
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT id, date, category, amount, note
            FROM entries
            WHERE user_id = ?{(' AND ' + where_sql[7:]) if where_sql.startswith(' WHERE') else ''}
            ORDER BY id DESC
            """,
            [current_user.id] + params,
        ).fetchall()
        return [dict(r) for r in rows]

def get_entry(entry_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, date, category, amount, note FROM entries WHERE id = ? AND user_id = ?",
            (entry_id, current_user.id),
        ).fetchone()
        return dict(row) if row else None

def update_entry(entry_id: int, d: str, category: str, amount: float, note: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE entries SET date = ?, category = ?, amount = ?, note = ? WHERE id = ? AND user_id = ?",
            (d, category, amount, note, entry_id, current_user.id),
        )

def delete_entry(entry_id: int):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM entries WHERE id = ? AND user_id = ?",
            (entry_id, current_user.id)
        )

def clear_all():
    with get_conn() as conn:
        conn.execute("DELETE FROM entries WHERE user_id = ?", (current_user.id,))

def compute_totals(where_sql: str = "", params: list | None = None):
    params = params or []
    with get_conn() as conn:
        row = conn.execute(
            f"""
            SELECT
              COALESCE(SUM(CASE WHEN amount > 0 THEN amount END), 0) AS income,
              COALESCE(SUM(CASE WHEN amount < 0 THEN amount END), 0) AS expense
            FROM entries
            WHERE user_id = ?{(' AND ' + where_sql[7:]) if where_sql.startswith(' WHERE') else ''}
            """,
            [current_user.id] + params,
        ).fetchone()
        income = float(row["income"])
        expense = float(row["expense"])  # negativ
        balance = income + expense
        return income, expense, balance

# =========================
# Filter-Helfer
# =========================
def build_filter_from_args(args):
    category = (args.get("category") or "").strip()
    q = (args.get("q") or "").strip()
    date_from = (args.get("date_from") or "").strip()
    date_to = (args.get("date_to") or "").strip()
    etype = (args.get("type") or "").strip()  # "", "income", "expense"

    where, params = [], []
    if category:
        where.append("category = ?"); params.append(category)
    if q:
        where.append("note LIKE ?"); params.append(f"%{q}%")
    if date_from:
        where.append("date >= ?"); params.append(date_from)
    if date_to:
        where.append("date <= ?"); params.append(date_to)
    if etype == "income":
        where.append("amount > 0")
    elif etype == "expense":
        where.append("amount < 0")

    where_sql = f" WHERE {' AND '.join(where)}" if where else ""
    return where_sql, params, {
        "category": category, "q": q, "date_from": date_from, "date_to": date_to, "type": etype
    }

# =========================
# Format & Betrag
# =========================
def parse_de_amount(text: str) -> float:
    t = (text or "").strip().replace(" ", "")
    if not t:
        raise ValueError("leer")
    sign = 1
    if t and t[0] == "+":
        t = t[1:]
    elif t and t[0] == "-":
        sign = -1
        t = t[1:]
    t = t.replace(".", "").replace(",", ".")
    return sign * float(t)

@app.template_filter("euro")
def format_euro(value) -> str:
    try:
        v = float(value)
    except Exception:
        return str(value)
    sign = "-" if v < 0 else ""
    v = abs(v)
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}{s}"

# =========================
# Public: Register/Login/Logout
# =========================
@app.get("/register")
def register():
    init_db()
    return render_template("register.html", app_name="Haushaltsbuch")

@app.post("/register")
def register_post():
    init_db()
    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    confirm = request.form.get("confirm") or ""

    errors = []
    if not name:
        errors.append("Bitte Namen angeben.")
    if not email:
        errors.append("Bitte E-Mail angeben.")
    if not password or len(password) < 8:
        errors.append("Passwort muss mind. 8 Zeichen haben.")
    if password != confirm:
        errors.append("Passwörter stimmen nicht überein.")
    if get_user_by_email(email):
        errors.append("E-Mail ist bereits registriert.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("register"))

    create_user(name, email, password)
    flash("Registrierung erfolgreich. Bitte melde dich an.", "success")

    # Nach Registrierung: Admin-Flag ggf. setzen (falls ADMIN_EMAIL == email)
    bootstrap_admin_if_configured()
    return redirect(url_for("login"))

@app.get("/login")
def login():
    init_db()
    return render_template("login.html", app_name="Haushaltsbuch")

@app.post("/login")
def login_post():
    init_db()
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""

    u = get_user_by_email(email)
    if not u or not check_password_hash(u["password_hash"], password):
        flash("E-Mail oder Passwort ist falsch.", "error")
        return redirect(url_for("login"))

    login_user(DBUser(u["id"], u["email"], u["name"], u.get("is_admin", 0)))
    flash(f"Willkommen, {u['name']}!", "success")
    return redirect(url_for("home"))

@app.get("/logout")
@login_required
def logout():
    logout_user()
    flash("Abgemeldet.", "success")
    return redirect(url_for("login"))

# =========================
# Admin: Benutzerübersicht & Verwaltung
# =========================
@app.get("/admin/users")
@login_required
def admin_users():
    if not getattr(current_user, "is_admin", False):
        flash("Keine Berechtigung, um diese Seite zu sehen.", "error")
        return redirect(url_for("home"))
    with get_conn() as conn:
        users = conn.execute(
            "SELECT id, name, email, is_admin, created_at FROM users ORDER BY id"
        ).fetchall()
    return render_template("admin_users.html", users=users)

@app.get("/admin/users.json")
@login_required
def admin_users_json():
    if not getattr(current_user, "is_admin", False):
        return jsonify({"error": "forbidden"}), 403
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, email, is_admin, created_at FROM users ORDER BY id"
        ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.post("/admin/users/<int:user_id>/promote")
@login_required
def admin_promote(user_id: int):
    if not getattr(current_user, "is_admin", False):
        flash("Keine Berechtigung.", "error")
        return redirect(url_for("home"))
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
    flash("Benutzer ist jetzt Admin.", "success")
    return redirect(url_for("admin_users"))

@app.post("/admin/users/<int:user_id>/demote")
@login_required
def admin_demote(user_id: int):
    if not getattr(current_user, "is_admin", False):
        flash("Keine Berechtigung.", "error")
        return redirect(url_for("home"))
    if str(user_id) == str(current_user.id):
        flash("Du kannst dir selbst die Admin-Rechte nicht entziehen.", "error")
        return redirect(url_for("admin_users"))
    with get_conn() as conn:
        conn.execute("UPDATE users SET is_admin = 0 WHERE id = ?", (user_id,))
    flash("Admin-Rechte entzogen.", "success")
    return redirect(url_for("admin_users"))

# =========================
# App-Routen (geschützt)
# =========================
@app.get("/")
@login_required
def home():
    init_db()
    where_sql, params, filters = build_filter_from_args(request.args)
    entries = fetch_entries(where_sql, params)
    total_income, total_expense, balance = compute_totals(where_sql, params)
    return render_template(
        "index.html",
        app_name="Haushaltsbuch",
        entries=entries,
        categories=CATEGORIES,
        today=date.today().isoformat(),
        total_income=total_income,
        total_expense=total_expense,
        balance=balance,
        filters=filters,
        result_count=len(entries),
        user=current_user,
    )

@app.post("/add")
@login_required
def add_entry_route():
    init_db()
    d = (request.form.get("date") or "").strip()
    cat = (request.form.get("category") or "").strip()
    amt_raw = (request.form.get("amount") or "").strip()
    note = (request.form.get("note") or "").strip()
    entry_type = request.form.get("type")

    errors = []
    if not d:
        errors.append("Bitte ein Datum angeben.")
    if not cat:
        errors.append("Bitte eine Kategorie wählen.")
    try:
        amount = parse_de_amount(amt_raw)
    except ValueError:
        errors.append("Betrag muss eine Zahl sein (deutsches Format, z. B. 2.100 oder 12,34).")
        amount = None
    if amount is not None and amount <= 0:
        errors.append("Betrag muss größer als 0 sein.")
    if not entry_type:
        errors.append("Bitte Einnahme oder Ausgabe auswählen.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("home"))

    amount = -abs(amount) if entry_type == "expense" else abs(amount)
    insert_entry(d, cat, amount, note, int(current_user.id))
    flash("Eintrag gespeichert.", "success")
    return redirect(url_for("home"))

@app.get("/edit/<int:entry_id>")
@login_required
def edit_entry(entry_id: int):
    init_db()
    entry = get_entry(entry_id)
    if not entry:
        flash("Eintrag nicht gefunden.", "error")
        return redirect(url_for("home"))
    abs_amount = abs(entry["amount"])
    entry_type = "expense" if entry["amount"] < 0 else "income"
    return render_template(
        "edit.html",
        app_name="Haushaltsbuch",
        entry=entry,
        abs_amount=abs_amount,
        entry_type=entry_type,
        categories=CATEGORIES,
        user=current_user,
    )

@app.post("/edit/<int:entry_id>")
@login_required
def save_edit_entry(entry_id: int):
    init_db()
    entry = get_entry(entry_id)
    if not entry:
        flash("Eintrag nicht gefunden.", "error")
        return redirect(url_for("home"))

    d = (request.form.get("date") or "").strip()
    cat = (request.form.get("category") or "").strip()
    amt_raw = (request.form.get("amount") or "").strip()
    note = (request.form.get("note") or "").strip()
    entry_type = request.form.get("type")

    errors = []
    if not d:
        errors.append("Bitte ein Datum angeben.")
    if not cat:
        errors.append("Bitte eine Kategorie wählen.")
    try:
        amount = parse_de_amount(amt_raw)
    except ValueError:
        errors.append("Betrag muss eine Zahl sein (deutsches Format).")
        amount = None
    if amount is not None and amount <= 0:
        errors.append("Betrag muss größer als 0 sein.")
    if not entry_type:
        errors.append("Bitte Einnahme oder Ausgabe auswählen.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("edit_entry", entry_id=entry_id))

    amount = -abs(amount) if entry_type == "expense" else abs(amount)
    update_entry(entry_id, d, cat, amount, note)
    flash("Eintrag aktualisiert.", "success")
    return redirect(url_for("home"))

@app.post("/delete/<int:entry_id>")
@login_required
def delete_entry_route(entry_id: int):
    init_db()
    if not get_entry(entry_id):
        flash("Eintrag nicht gefunden.", "error")
        return redirect(url_for("home"))
    delete_entry(entry_id)
    flash("Eintrag gelöscht.", "success")
    return redirect(url_for("home"))

@app.post("/clear")
@login_required
def clear_entries():
    init_db()
    clear_all()
    flash("Alle Einträge gelöscht (nur dein Account).", "success")
    return redirect(url_for("home"))

# =========================
# Main
# =========================
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
