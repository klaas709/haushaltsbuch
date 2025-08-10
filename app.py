from flask import Flask, render_template, url_for, request, redirect, flash
from datetime import date

app = Flask(__name__)
app.secret_key = "dev-only-change-me"  # nötig für flash()-Nachrichten

# In-Memory-Speicher
entries = []  # jedes Element: {"date": "...", "category": "...", "amount": 12.34, "note": "..."}
CATEGORIES = ["Lebensmittel", "Miete", "Transport", "Freizeit", "Haushalt", "Einnahme", "Sonstiges"]

# ---------- Hilfsfunktionen ----------

def parse_de_amount(text: str) -> float:
    """
    Konvertiert deutsche Zahleneingaben in float.
    Erlaubt z. B.: '2.100', '1.234,56', '+12,3', '-45', '1200'
    """
    t = (text or "").strip().replace(" ", "")
    if not t:
        raise ValueError("leer")

    # Vorzeichen extrahieren
    sign = 1
    if t[0] == "+":
        t = t[1:]
    elif t[0] == "-":
        sign = -1
        t = t[1:]

    # Tausenderpunkte entfernen, Dezimalkomma in Punkt wandeln
    t = t.replace(".", "").replace(",", ".")

    return sign * float(t)

# Jinja-Filter für €-Format
@app.template_filter("euro")
def format_euro(value) -> str:
    try:
        v = float(value)
    except Exception:
        return str(value)

    sign = "-" if v < 0 else ""
    v = abs(v)
    # Erst US-Format (z. B. 12,345.67), dann Zeichen tauschen
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{sign}{s}"

# ---------- Routen ----------

@app.get("/")
def home():
    total_expense = sum(e["amount"] for e in entries if e["amount"] < 0)
    total_income = sum(e["amount"] for e in entries if e["amount"] > 0)
    balance = total_income + total_expense
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

    # Betrag parsen (deutsches Format)
    try:
        amount = parse_de_amount(amt_raw)
    except ValueError:
        errors.append("Betrag muss eine Zahl sein (deutsches Format, z. B. 2.100 oder 12,34).")
        amount = None

    # Betrag > 0 erzwingen, Vorzeichen kommt vom Typ
    if amount is not None and amount <= 0:
        errors.append("Betrag muss größer als 0 sein.")

    if not entry_type:
        errors.append("Bitte Einnahme oder Ausgabe auswählen.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("home"))

    # Vorzeichen setzen
    if entry_type == "expense":
        amount = -abs(amount)
    else:
        amount = abs(amount)

    # Speichern
    entries.append({"date": d, "category": cat, "amount": amount, "note": note})
    flash("Eintrag gespeichert.", "success")
    return redirect(url_for("home"))

@app.post("/clear")
def clear_entries():
    entries.clear()
    flash("Alle Einträge gelöscht (nur In-Memory).", "success")
    return redirect(url_for("home"))

# ---------- Main ----------
if __name__ == "__main__":
    app.run(debug=True)
