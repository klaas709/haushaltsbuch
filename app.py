from flask import Flask, render_template, url_for, request, redirect, flash
from datetime import date

app = Flask(__name__)
app.secret_key = "dev-only-change-me"

entries = []
CATEGORIES = ["Lebensmittel", "Miete", "Transport", "Freizeit", "Haushalt", "Einnahme", "Sonstiges"]

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
    amt_raw = (request.form.get("amount") or "").strip().replace(",", ".")
    note = (request.form.get("note") or "").strip()
    entry_type = request.form.get("type")  # "income" oder "expense"

    errors = []
    if not d:
        errors.append("Bitte ein Datum angeben.")
    if not cat:
        errors.append("Bitte eine Kategorie wählen.")

    try:
        amount = float(amt_raw)
    except ValueError:
        errors.append("Betrag muss eine Zahl sein.")
        amount = None

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

    entries.append({"date": d, "category": cat, "amount": amount, "note": note})
    flash("Eintrag gespeichert.", "success")
    return redirect(url_for("home"))

@app.post("/clear")
def clear_entries():
    entries.clear()
    flash("Alle Einträge gelöscht (nur In-Memory).", "success")
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)
