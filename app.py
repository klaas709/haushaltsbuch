from flask import Flask, render_template, url_for, request, redirect, flash
from datetime import date
from pathlib import Path
import sqlite3

app = Flask(__name__)
app.secret_key = "dev-only-change-me"

DB_PATH = Path(__file__).with_name("haushaltsbuch.db")

CATEGORIES = ["Lebensmittel", "Miete", "Transport", "Freizeit", "Haushalt", "Einnahme", "Sonstiges"]

# ---------- DB-Helfer ----------

def get_conn():
    # row_factory ermöglicht Zugriff per Spaltennamen (e["amount"])
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
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

def insert_entry(d: str, category: str, amount: float, note: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO entries (date, category, amount, note) VALUES (?, ?, ?, ?)",
            (d, category, amount, note),
        )

def fetch_entries():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, date, category, amount, note FROM entries ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]

def clear_all():
    with get_conn() as conn:
        conn.execute("DELETE FROM entries")

def compute_totals():
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN amount > 0 THEN amount END), 0) AS income,
              COALESCE(SUM(CASE WHEN amount < 0 THEN amount END), 0) AS expense
            FROM entries
            """
        ).fetchone()
        income = float(row["income"])
        expense = float(row["expense"])  # negativ
        balance = income + expense
        return income, expense, balance

# ---------- Betrags-Parsing & Format ----------

def parse_de_amount(text: str) -> float:
    """
    Deutsche Zahleneingaben -> float
    Erlaubt: '2.100', '1.234,56', '+12,3', '1200'
    (Vorzeichen aus Umschalter; hier > 0 erzwingen)
    """
    t = (text or "").strip().replace(" ", "")
    if not t:
        raise ValueError("leer")

    # Vorzeichen separat behandeln (wir erwarten positive Eingabe)
    sign = 1
    if t[0] == "+":
        t = t[1:]
    elif t[0] == "-":
        sign = -1
        t = t[1:]

    # Tausenderpunkte entfernen, Dezimalkomma in Punkt
    t = t.replace(".", "").replace(",", ".")
    val = float(t)

    return sign * val

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

# ---------- Routen ----------

@app.get("/")
def home():
    init_db()  # sicherstellen, dass Tabelle existiert
    entries = fetch_entries()
    total_income, total_expense, balance = compute_totals()
    return render_template(
        "index.html",
        app_name="Haushaltsbuch",
        entries=entries,
        categories=CATEGORIES,
        today=date.today().isoformat(),
        total_income=total_income,
        total_expense=total_expense,
        balance=balance,
    )

@app.post("/add")
def add_entry():
    init_db()

    d = (request.form.get("date") or "").strip()
    cat = (request.form.get("category") or "").strip()
    amt_raw = (request.form.get("amount") or "").strip()
    note = (request.form.get("note") or "").strip()
    entry_type = request.form.get("type")  # "income" oder "expense"

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

    # Vorzeichen per Typ
    amount = -abs(amount) if entry_type == "expense" else abs(amount)

    # In DB speichern
    insert_entry(d, cat, amount, note)
    flash("Eintrag gespeichert.", "success")
    return redirect(url_for("home"))

@app.post("/clear")
def clear_entries():
    init_db()
    clear_all()
    flash("Alle Einträge gelöscht (persistente DB).", "success")
    return redirect(url_for("home"))

# ---------- Main ----------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
