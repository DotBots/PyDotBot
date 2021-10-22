from flask import Flask, render_template, redirect, url_for
from dotbot.demo import DemoConfig

app = Flask(__name__, template_folder="views")
config = DemoConfig().demo

@app.route("/", methods=["GET"])
def index():
    return redirect((url_for('joy_demo')))

@app.route("/joy", methods=["GET"])
def joy_demo():
    return render_template("index.html", ORCH_URL=config.orch_url)

app.run(config.host, config.port, debug=False, threaded=True)