from flask import Flask

app = Flask(__name__)

@app.get("/")
def home():
    return "Hallo Haushaltsbuch 👋 – v0.1 läuft!"

if __name__ == "__main__":
    app.run(debug=True)
