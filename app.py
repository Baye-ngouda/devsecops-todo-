"""Application web Todo (Flask) - cible de la chaîne DevSecOps."""
import os
import sqlite3
import subprocess
from itertools import count

from flask import Flask, jsonify, redirect, render_template, request, url_for

app = Flask(__name__)

APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")

_ids = count(1)
TODOS = []  # stockage en mémoire (suffisant pour la démonstration)


def _find(todo_id):
    return next((t for t in TODOS if t["id"] == todo_id), None)


@app.route("/")
def index():
    return render_template("index.html", todos=TODOS, version=APP_VERSION)


@app.route("/add", methods=["POST"])
def add():
    title = request.form.get("title", "").strip()[:200]
    if title:
        TODOS.append({"id": next(_ids), "title": title, "done": False})
    return redirect(url_for("index"))


@app.route("/toggle/<int:todo_id>", methods=["POST"])
def toggle(todo_id):
    todo = _find(todo_id)
    if todo:
        todo["done"] = not todo["done"]
    return redirect(url_for("index"))


@app.route("/delete/<int:todo_id>", methods=["POST"])
def delete(todo_id):
    todo = _find(todo_id)
    if todo:
        TODOS.remove(todo)
    return redirect(url_for("index"))


@app.route("/api/todos")
def api_todos():
    return jsonify(TODOS)


@app.route("/health")
def health():
    return jsonify(status="ok", version=APP_VERSION)


@app.route("/user")
def user():
    # Injection SQL : requête construite par concaténation
    name = request.args.get("name", "")
    conn = sqlite3.connect(":memory:")
    return jsonify(result=conn.execute("SELECT '" + name + "'").fetchall())


@app.route("/ping")
def ping():
    # Injection de commande : entrée utilisateur passée au shell
    host = request.args.get("host", "127.0.0.1")
    return subprocess.check_output("ping -c 1 " + host, shell=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
