from flask import Flask, render_template, url_for, request, redirect, flash
from datetime import date

app = Flask(__name__)
app.secret_key = "dev-only-change-me"  # nötig für flash()-Nachrichten im Dev

# In-Memory-Speicher (wird beim Neustart zurückgesetzt)
entries = []  # jedes Element ist ein dict: {"date": "...", "category": "...", "amount": 12.34, "note": "..."}

CATEGORIES = ["Lebensmittel", "Miete", "Transport", "Freizeit", "Haushalt", "Einnahme", "Sonstiges"]

@app.get("/")
def home():
    # Startseite: Formular + Tabelle
    # Summe(n) vorbereiten
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
    # Formulardaten auslesen
    d = (request.form.get("date") or "").strip()
    cat = (request.form.get("category") or "").strip()
    amt_raw = (request.form.get("amount") or "").strip().replace(",", ".")
    note = (request.form.get("note") or "").strip()

    # Validierung
    errors = []
    if not d:
        errors.append("Bitte ein Datum angeben.")
    if not cat:
        errors.append("Bitte eine Kategorie wählen.")
    try:
        amount = float(amt_raw)
    except ValueError:
        errors.append("Betrag muss eine Zahl sein (z. B. 12.34 oder -45,67).")
        amount = None

    if amount is not None and amount == 0:
        errors.append("Betrag darf nicht 0 sein.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("home"))

    # Speichern
    entry = {"date": d, "category": cat, "amount": amount, "note": note}
    entries.append(entry)
    flash("Eintrag gespeichert.", "success")
    return redirect(url_for("home"))

@app.post("/clear")
def clear_entries():
    # Nur für die Lernphase, um die Liste zu leeren
    entries.clear()
    flash("Alle Einträge gelöscht (nur In-Memory).", "success")
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)

print(app.url_map)