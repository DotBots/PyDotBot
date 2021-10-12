from flask import Flask, render_template, redirect, url_for
import toml

app = Flask(__name__, template_folder="views")

config = toml.load("default_config.toml")

@app.route("/", methods=["GET"])
def index():
    return redirect((url_for('joy_demo')))

@app.route("/joy", methods=["GET"])
def joy_demo():
    return render_template("index.html", ORCH_URL=config["demo"]["orch_url"])

app.run("localhost", 5001, debug=False, threaded=True)