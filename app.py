"""
NutriCoach.AI — Flask application.

Settings (provider, API keys, models, theme) live in ~/.nutricoach/config.json,
profiles and the daily log in ~/.nutricoach/data.db — never in the repo.
"""
import json
import os
import sys
import traceback
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

import agents as A
import llm as L
import tracker as T

# PyInstaller unpacks bundled files under sys._MEIPASS
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
CONFIG = Path.home() / ".nutricoach" / "config.json"
THEMES = ["hacker", "light", "dark", "neon"]
DEFAULTS = {"provider": "openai", "keys": {}, "model_small": "", "model_large": "",
            "ollama_url": L.OLLAMA_URL, "theme": "hacker"}

app = Flask(__name__, template_folder=str(BASE / "templates"), static_folder=str(BASE / "static"))


def load_settings() -> dict:
    try:
        s = {**DEFAULTS, **json.loads(CONFIG.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        s = dict(DEFAULTS)
    if s.get("api_key"):                         # v1 config: single OpenAI key
        s["keys"] = {**s["keys"], "openai": s.pop("api_key")}
    s.pop("model", None)
    if s["theme"] not in THEMES:
        s["theme"] = "hacker"
    return s


def save_settings(s: dict) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(s, indent=2), encoding="utf-8")


def mask(key: str) -> str:
    return f"{key[:5]}…{key[-4:]}" if len(key) > 12 else ""


@app.route("/")
def index():
    return render_template("index.html", theme=load_settings()["theme"])


@app.get("/settings")
def get_settings():
    s = load_settings()
    return jsonify(provider=s["provider"], theme=s["theme"], themes=THEMES,
                   model_small=L.model_name(s, "small") if s["provider"] in L.PROVIDERS else "",
                   model_large=L.model_name(s, "large") if s["provider"] in L.PROVIDERS else "",
                   ollama_url=s["ollama_url"],
                   keys={p: mask(k) for p, k in s["keys"].items() if k},
                   providers={k: {kk: v[kk] for kk in ("label", "key", "small", "large", "models")}
                              for k, v in L.PROVIDERS.items()})


@app.post("/settings")
def post_settings():
    d = request.json or {}
    s = load_settings()
    if d.get("provider") in L.PROVIDERS:
        s["provider"] = d["provider"]
    for p, k in (d.get("keys") or {}).items():   # empty string clears a key
        if p in L.PROVIDERS:
            s["keys"][p] = k.strip()
    for f in ("model_small", "model_large", "ollama_url"):
        if f in d:
            s[f] = str(d[f]).strip()
    if d.get("theme") in THEMES:
        s["theme"] = d["theme"]
    save_settings(s)
    return get_settings()


@app.get("/local-models")
def local_models():
    s = load_settings()
    return jsonify(installed=L.installed_ollama_models(s["ollama_url"]),
                   suggested=L.LOCAL_MODELS, install_url=L.OLLAMA_INSTALL)


# ── Profiles and tracker ─────────────────────────────────────────────────────
@app.get("/profiles")
def list_profiles():
    return jsonify(profiles=T.profiles(), max=T.MAX_PROFILES)


@app.post("/profiles")
def save_profile():
    d = request.json or {}
    try:
        pid = T.save_profile(d.get("name") or "Me", d.get("data") or {}, d.get("id"))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(id=pid, profiles=T.profiles())


@app.delete("/profiles/<int:pid>")
def delete_profile(pid):
    T.delete_profile(pid)
    return jsonify(profiles=T.profiles())


@app.get("/log/<int:pid>")
def get_log(pid):
    try:
        return jsonify(T.history(pid))
    except ValueError as e:
        return jsonify(error=str(e)), 404


@app.post("/log/<int:pid>")
def post_log(pid):
    d = request.json or {}
    T.log_day(pid, d["day"], d.get("kcal_in", 0), d.get("steps", 0),
              bool(d.get("gym")), bool(d.get("healthy")), d.get("weight") or 0)
    return jsonify(T.history(pid))


@app.get("/quote")
def get_quote():
    return jsonify(quote=T.quote())


# ── Analysis ─────────────────────────────────────────────────────────────────
# What the UI receives when each node finishes (state keys -> event fields)
DONE_FIELDS = {
    "bmi_agent":        {"content": "bmi_report", "trace": "bmi_trace", "plan": "plan"},
    "nutrition_agent":  {"content": "nutrition_plan", "trace": "nutrition_trace"},
    "nutrition_critic": {"content": "nutrition_critique", "trace": "critic_trace",
                         "score": "nutrition_score", "revision": "nutrition_revision_count"},
    "meal_agent":       {"meal_content": "meal_plan", "supp_content": "supplement_advice", "trace": "meal_trace"},
    "activity_agent":   {"content": "activity_plan", "trace": "activity_trace"},
    "plan_critic":      {"content": "plan_critique", "trace": "plan_critic_trace",
                         "score": "plan_score", "checks": "plan_checks"},
    "coach_agent":      {"content": "final_report", "trace": "coach_trace"},
}


@app.post("/analyze")
def analyze():
    d = request.json or {}
    s = load_settings()
    try:
        graph = A.build_graph(s)
    except Exception as e:                      # missing key or SDK
        return jsonify(error=str(e)), 400

    f = lambda k, default, cast=str: cast(d.get(k) or default)
    params = dict(
        age=f("age", 28, int), gender=f("gender", "Male"),
        weight_kg=f("weight_kg", 78, float), height_cm=f("height_cm", 172, float),
        activity_level=f("activity_level", "Moderately Active"), goal=f("goal", "lose"),
        dietary_restrictions=f("dietary_restrictions", "none"),
        health_conditions=f("health_conditions", "none"),
        target_weight_kg=f("target_weight_kg", d.get("weight_kg") or 78, float),
        target_weeks=f("target_weeks", 0, int), region=f("region", "in"),
        diet_type=f("diet_type", "nonveg"), gym=bool(d.get("gym")), gym_days=f("gym_days", 3, int),
        budget=bool(d.get("budget")), waist_cm=f("waist_cm", 0, float),
    )
    pid = d.get("profile_id")

    def emit(**kw):
        return f"data: {json.dumps(kw, default=str)}\n\n"

    def generate():
        state = A.make_initial_state(**params)
        try:
            yield emit(event="preview", provider=L.PROVIDERS[s["provider"]]["label"])
            for mode, chunk in graph.stream(state, stream_mode=["custom", "updates"]):
                if mode == "custom":
                    yield emit(**chunk)
                    continue
                for node, out in chunk.items():
                    state.update(out or {})
                    fields = {k: state.get(v) for k, v in DONE_FIELDS.get(node, {}).items()}
                    yield emit(event="agent_done", node=node, agent=A.NODES[node][0], **fields)
                    if node == "nutrition_critic":
                        yield emit(event="loop_decision", decision=A.should_revise(state),
                                   score=state["nutrition_score"], revision=state["nutrition_revision_count"])
            if pid:
                T.save_plan(int(pid), state["plan"])
            yield emit(event="complete", plan=state["plan"], plan_score=state["plan_score"],
                       nutrition_score=state["nutrition_score"],
                       nutrition_revisions=state["nutrition_revision_count"] - 1, quote=T.quote())
        except Exception as e:
            yield emit(event="error", message=str(e), trace=traceback.format_exc())

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    app.run(debug=os.environ.get("NUTRICOACH_DEBUG") == "1", port=5000, threaded=True)
