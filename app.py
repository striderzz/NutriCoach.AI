"""
NutriCoach.AI — Flask application.

Settings (OpenAI key, model) live in ~/.nutricoach/config.json, never in the repo.
"""
import json
import os
import sys
import traceback
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

import agents as A

# PyInstaller unpacks bundled files under sys._MEIPASS
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
CONFIG = Path.home() / ".nutricoach" / "config.json"
MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"]
DEFAULTS = {"api_key": "", "model": "gpt-4o-mini", "theme": "original"}

app = Flask(__name__, template_folder=str(BASE / "templates"), static_folder=str(BASE / "static"))


def load_settings() -> dict:
    try:
        return {**DEFAULTS, **json.loads(CONFIG.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(s: dict) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(s, indent=2), encoding="utf-8")


def mask(key: str) -> str:
    return f"{key[:7]}…{key[-4:]}" if len(key) > 12 else ""


@app.route("/")
def index():
    return render_template("index.html", theme=load_settings()["theme"])


@app.get("/settings")
def get_settings():
    s = load_settings()
    return jsonify(has_key=bool(s["api_key"]), key_hint=mask(s["api_key"]),
                   model=s["model"], models=MODELS, theme=s["theme"])


@app.post("/settings")
def post_settings():
    d = request.json or {}
    s = load_settings()
    if "api_key" in d:                       # empty string clears the key
        s["api_key"] = d["api_key"].strip()
    if d.get("model") in MODELS:
        s["model"] = d["model"]
    if d.get("theme"):
        s["theme"] = d["theme"]
    save_settings(s)
    return get_settings()


@app.post("/analyze")
def analyze():
    d = request.json or {}
    s = load_settings()
    api_key = (d.get("api_key") or s["api_key"]).strip()
    if not api_key:
        return jsonify(error="Add your OpenAI API key in Settings first."), 400

    params = dict(
        age=int(d.get("age", 28)),
        gender=d.get("gender", "Male"),
        weight_kg=float(d.get("weight_kg", 78)),
        height_cm=float(d.get("height_cm", 172)),
        activity_level=d.get("activity_level", "Moderately Active"),
        goal=d.get("goal", "lose"),
        dietary_restrictions=d.get("dietary_restrictions", "none"),
        health_conditions=d.get("health_conditions", "none"),
    )

    def emit(**kw):
        return f"data: {json.dumps(kw)}\n\n"

    def generate():
        try:
            bmi = A._bmi(params["weight_kg"], params["height_cm"])
            tdee = A._tdee(params["weight_kg"], params["height_cm"],
                           params["age"], params["gender"], params["activity_level"])
            yield emit(event="preview", bmi=bmi, category=A._bmi_category(bmi), tdee=tdee)

            model = A._make_model(api_key, s["model"])
            state = A.make_initial_state(**params)

            def step(node, agent, description, revision=None):
                """Announce an agent, run its node and merge the output into state."""
                yield emit(event="agent_start", agent=agent, description=description,
                           **({} if revision is None else {"revision": revision}))
                out = node(state, model)
                state.update({k: v for k, v in out.items() if k != "messages"})
                state["messages"] = list(state["messages"]) + list(out.get("messages", []))

            yield from step(A.bmi_agent_node, "BMI Agent",
                       "Calculates BMI, classifies risk, assigns protocol")
            yield emit(event="agent_done", agent="BMI Agent", content=state["bmi_report"],
                       trace=state["bmi_trace"], bmi=state["bmi"], category=state["bmi_category"],
                       risk_level=state["risk_level"], tdee=state["tdee"])

            # Critic-Revise loop: the critic sends the plan back while its score is below 7
            while True:
                kind = "Intervention" if state["risk_level"] == "intervention" else "Standard"
                yield from step(A.nutrition_agent_node, "Nutrition Agent",
                           f"{kind} nutrition prescription", state["nutrition_revision_count"])
                yield emit(event="agent_done", agent="Nutrition Agent", content=state["nutrition_plan"],
                           trace=state["nutrition_trace"], variant=state["risk_level"])

                yield from step(A.critic_agent_node, "Critic Agent",
                           "Scores plan 0-10 using score_plan tool · triggers revision if score < 7",
                           state["nutrition_revision_count"])
                yield emit(event="agent_done", agent="Critic Agent", content=state["nutrition_critique"],
                           trace=state["critic_trace"], score=state["nutrition_score"],
                           revision=state["nutrition_revision_count"])

                decision = A.should_revise(state)
                yield emit(event="loop_decision", decision=decision, score=state["nutrition_score"],
                           revision=state["nutrition_revision_count"])
                if decision == "meal_agent":
                    break

            yield from step(A.meal_agent_node, "Meal Agent",
                       "Builds 7-day meal plan + supplement stack using tools")
            yield emit(event="agent_done", agent="Meal Agent", meal_content=state["meal_plan"],
                       supp_content=state["supplement_advice"], trace=state["meal_trace"])

            yield from step(A.coach_agent_node, "Coach Agent",
                       "Runs safety_check + synthesise_report tools · writes final coaching report")
            yield emit(event="agent_done", agent="Coach Agent", content=state["final_report"],
                       trace=state["coach_trace"])

            yield emit(event="complete", nutrition_revisions=state["nutrition_revision_count"] - 1,
                       nutrition_score=state["nutrition_score"])
        except Exception as e:
            yield emit(event="error", message=str(e), trace=traceback.format_exc())

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    app.run(debug=os.environ.get("NUTRICOACH_DEBUG") == "1", port=5000, threaded=True)
