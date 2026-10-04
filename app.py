from flask import Flask, redirect, render_template, request, url_for

import pipeline
import store
from apply import apply_proposal
from crm import CRM

app = Flask(__name__)

TYPE_LABELS = {
    "reparent": "Re-parent",
    "chow": "CHOW",
    "create": "New account",
    "duplicate": "Duplicate",
    "update": "Fix fields",
    "not_on_site": "Not on website",
}


@app.get("/")
def index():
    status = request.args.get("status", "pending")
    conn = store.connect()
    return render_template(
        "index.html",
        proposals=store.list_proposals(conn, status),
        counts=store.counts(conn),
        status=status,
        last_run=store.last_run(conn),
        labels=TYPE_LABELS,
        message=request.args.get("message", ""),
    )


@app.post("/proposals/<key>/approve")
def approve(key):
    conn = store.connect()
    proposal = store.get_proposal(conn, key)
    if not proposal or proposal["status"] not in ("pending", "failed"):
        return redirect(url_for("index", message="Proposal is no longer pending"))
    try:
        log = apply_proposal(CRM(), proposal)
        store.set_status(conn, key, "applied", {"log": log})
        message = f"Applied: {proposal['title']}"
    except Exception as error:
        store.set_status(conn, key, "failed", {"error": str(error)})
        message = f"Failed: {proposal['title']} ({error})"
    return redirect(url_for("index", message=message))


@app.post("/proposals/<key>/reject")
def reject(key):
    conn = store.connect()
    proposal = store.get_proposal(conn, key)
    if proposal and proposal["status"] == "pending":
        store.set_status(conn, key, "rejected", {"reason": request.form.get("reason", "")})
    return redirect(url_for("index", message=f"Rejected: {proposal['title'] if proposal else key}"))


@app.post("/run")
def run_pipeline():
    new = pipeline.run()
    return redirect(url_for("index", message=f"Pipeline finished: {new} new proposals"))


if __name__ == "__main__":
    app.run(port=5050)
