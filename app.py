from flask import Flask, render_template, url_for

app = Flask(__name__)

@app.get("/")
def home():
    # rendert die Datei templates/index.html
    return render_template("index.html", app_name="Haushaltsbuch")

if __name__ == "__main__":
    # debug=True: Auto-Reload bei Codeänderungen
    app.run(debug=True)
