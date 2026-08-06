from http import HTTPStatus
from pathlib import Path

from flask import Flask, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
app = Flask(__name__, static_folder=str(ROOT), static_url_path="")


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "dashboard.html")


@app.get("/dashboard.html")
def dashboard():
    return send_from_directory(app.static_folder, "dashboard.html")


@app.get("/data.js")
def data():
    return send_from_directory(app.static_folder, "data.js")


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.ico", conditional=True)


@app.errorhandler(404)
def not_found(_):
    return "Not Found", HTTPStatus.NOT_FOUND
