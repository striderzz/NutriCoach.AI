"""
NutriCoach ReAct — Reasoning + Acting Nutrition Agent System
=============================================================

Architecture: ReAct Pattern with LangGraph
-------------------------------------------

Each agent follows the ReAct loop:
    THINK → ACT (call tool) → OBSERVE (read result) → THINK → ...

The system has 5 specialist agents, each with their own tools, connected
through a LangGraph StateGraph with conditional routing and a Critic-Revise
feedback loop.

Graph:
                    ┌──────────────────┐
                    │   BMI AGENT      │  Tools: calculate_bmi, classify_risk
                    │  (ReAct loop)    │  Reasons about health profile
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  NUTRITION AGENT  │  Tools: compute_tdee, build_macro_targets
                    │  (ReAct loop)    │  conditional: standard vs intervention
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐ ◄──────────────┐
                    │  CRITIC AGENT    │  Tool: score_plan  LOOP (max 2)
                    │  (ReAct loop)    │  Scores 0-10, decides revise/proceed
                    └────────┬─────────┘ ────────────────┘
                             │ score ≥ 7
                    ┌────────▼─────────┐
                    │  MEAL AGENT      │  Tools: build_meal_plan, get_supplement_stack
                    │  (ReAct loop)    │  Builds 7-day plan + supplements
                    └────────▼─────────┘
                    ┌────────▼─────────┐
                    │  COACH AGENT     │  Tools: safety_check, synthesise_report
                    │  (ReAct loop)    │  Audits safety, writes final coaching report
                    └────────┬─────────┘
                             │
                            END

ReAct Pattern:
  Each agent has a system prompt that instructs it to reason step-by-step,
  call tools explicitly, read observations, and iterate until confident.
  Every agent's reasoning trace is captured and streamed to the UI.
"""

import json
import math
from typing import TypedDict, Annotated, Sequence, Literal, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.config import get_stream_writer

import llm as L
import planner as P


# ═══════════════════════════════════════════════════════════════════════════════
# STATE
# ═══════════════════════════════════════════════════════════════════════════════

class NutritionState(TypedDict):
    # User inputs
    age: int
    gender: str
    weight_kg: float
    height_cm: float
    activity_level: str
    goal: str
    dietary_restrictions: str
    health_conditions: str
    target_weight_kg: float
    target_weeks: int
    region: str               # "in" (Indian, default) or "us"
    diet_type: str            # veg | egg | nonveg
    gym: bool
    gym_days: int
    budget: bool
    waist_cm: float

    # Rule-based plan from planner.build(): every number the agents narrate
    plan: dict
    plan_checks: list
    plan_score: int
    plan_revision_count: int
    activity_plan: str
    activity_trace: list
    plan_critic_trace: list
    plan_critique: str

    # Computed
    bmi: float
    bmi_category: str
    risk_level: str
    tdee: int

    # Loop control
    nutrition_revision_count: int
    nutrition_score: int

    # Message history (full ReAct traces per agent)
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # Agent ReAct traces (list of step dicts for UI rendering)
    bmi_trace: list
    nutrition_trace: list
    critic_trace: list
    meal_trace: list
    coach_trace: list

    # Final outputs
    bmi_report: str
    nutrition_plan: str
    nutrition_critique: str
    meal_plan: str
    supplement_advice: str
    final_report: str


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _make_model(cfg: dict, tier: str = "small"):
    """Chat model for the provider in settings; None means rule-based (no LLM)."""
    return L.make_model(cfg, tier)

def _bind(model, tools):
    """Bind tools, or return the bare model if it can't call tools (weak/local models)."""
    if model is None:
        return None
    try:
        return model.bind_tools(tools)
    except Exception:
        return model

def _bmi(weight_kg: float, height_cm: float) -> float:
    h = height_cm / 100
    return round(weight_kg / (h * h), 1)

def _bmi_category(bmi: float) -> str:
    if bmi < 18.5:   return "Underweight"
    elif bmi < 25.0: return "Normal weight"
    elif bmi < 30.0: return "Overweight"
    else:            return "Obese"

def _tdee(weight_kg, height_cm, age, gender, activity_level) -> int:
    if gender.lower() == "female":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age - 161
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5
    mults = {"Sedentary": 1.2, "Lightly Active": 1.375,
             "Moderately Active": 1.55, "Very Active": 1.725, "Extremely Active": 1.9}
    return int(bmr * mults.get(activity_level, 1.55))

# Profile of the current run, read by tools whose args are only a few numbers
# (simple args keep tool calling reliable on small local models)
_CTX: dict = {}

FMT = ("Write in plain text only. No markdown, no asterisks, no hashes. "
       "Section headings in ALL CAPS. All numbers must be specific to this patient.")

def _profile(s: NutritionState) -> str:
    return (f"Age {s['age']} | {s['gender']} | {s['weight_kg']}kg | {s['height_cm']}cm | "
            f"BMI {s['bmi']} ({s['bmi_category']}) | TDEE {s['tdee']} kcal | "
            f"Goal: {s['goal']} | Activity: {s['activity_level']} | "
            f"Diet: {s['dietary_restrictions']} | Conditions: {s['health_conditions']}"
            + (f"\nCOMPUTED NUMBERS (use exactly): {P.summary(s['plan'])}" if s.get("plan") else ""))

def _run_react(model_with_tools, system_prompt: str, user_message: str,
               tools_by_name: dict) -> tuple[str, list]:
    """
    Run a ReAct loop: Think → Act → Observe → repeat until no more tool calls.
    Returns (final_text_response, trace_steps).
    trace_steps is a list of dicts:
        {"type": "thought"|"action"|"observation", "content": str, "tool": str|None}
    """
    if model_with_tools is None:
        return "", [{"type": "thought", "content": "No AI model selected: writing this section from the rule engine.", "tool": None}]
    try:
        return _react_loop(model_with_tools, system_prompt, user_message, tools_by_name)
    except Exception as e:
        # Caller falls back to planner text, so a flaky or weak model never breaks the run
        return "", [{"type": "thought", "content": f"Model error ({type(e).__name__}: {e}). Using the rule engine's text.", "tool": None}]

def _text(response) -> str:
    """Message text; Anthropic/Gemini may return a list of content blocks."""
    c = response.content
    if isinstance(c, list):
        c = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in c)
    return (c or "").strip()

def _react_loop(model_with_tools, system_prompt, user_message, tools_by_name):
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    trace = []
    max_iters = 6

    for _ in range(max_iters):
        response = model_with_tools.invoke(messages)
        messages.append(response)

        if response.tool_calls:
            # Extract thought from text content before tool call
            thought_text = _text(response) or "Determining which tool to use..."
            if thought_text:
                trace.append({"type": "thought", "content": thought_text, "tool": None})

            # Execute each tool call
            for tc in response.tool_calls:
                action_text = f"Calling {tc['name']} with: {json.dumps(tc['args'], indent=2)}"
                trace.append({"type": "action", "content": action_text, "tool": tc["name"]})

                if tc["name"] in tools_by_name:
                    try:
                        result = tools_by_name[tc["name"]].invoke(tc["args"])
                        obs_text = str(result)
                    except Exception as e:
                        obs_text = f"Tool error: {str(e)}"
                else:
                    obs_text = f"Tool '{tc['name']}' not found."

                trace.append({"type": "observation", "content": obs_text, "tool": tc["name"]})
                messages.append(ToolMessage(
                    content=obs_text,
                    name=tc["name"],
                    tool_call_id=tc["id"]
                ))
        else:
            # No tool calls — final answer
            final_text = _text(response)
            trace.append({"type": "thought", "content": "I have all the information needed. Composing final response.", "tool": None})
            return final_text, trace

    # Max iterations reached
    final = messages[-1].content if hasattr(messages[-1], 'content') else "Analysis complete."
    return final, trace


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 1 — BMI AGENT
# Tools: calculate_bmi, classify_risk
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def calculate_bmi(weight_kg: float, height_cm: float) -> dict:
    """Calculate BMI and derive healthy weight range from height."""
    bmi = _bmi(weight_kg, height_cm)
    category = _bmi_category(bmi)
    h = height_cm / 100
    target_lo = round(18.5 * h * h, 1)
    target_hi = round(24.9 * h * h, 1)
    delta = round(abs(weight_kg - (target_hi if bmi > 25 else target_lo)), 1)
    weeks = max(4, int(delta / 0.5))
    return {
        "bmi": bmi,
        "category": category,
        "healthy_range_kg": f"{target_lo}–{target_hi}",
        "weight_change_needed_kg": delta,
        "estimated_weeks_at_safe_rate": weeks,
    }

@tool
def classify_risk(bmi: float, age: int, health_conditions: str) -> dict:
    """Classify cardiovascular and metabolic risk based on BMI, age, and conditions."""
    high_risk_conditions = ["diabetes", "hypertension", "heart", "kidney", "liver"]
    has_condition = any(c in health_conditions.lower() for c in high_risk_conditions)
    intervention = bmi < 17.5 or bmi >= 27.5 or age > 60 or has_condition

    cv_risk = "High" if (bmi >= 30 or has_condition) else "Moderate" if bmi >= 25 else "Low"
    metabolic_risk = "Elevated" if (bmi >= 27.5 or has_condition) else "Normal"

    return {
        "protocol": "intervention" if intervention else "standard",
        "cardiovascular_risk": cv_risk,
        "metabolic_risk": metabolic_risk,
        "intervention_triggered_by": (
            "BMI out of range" if (bmi < 17.5 or bmi >= 27.5) else
            "Age > 60" if age > 60 else
            f"Health condition: {health_conditions}" if has_condition else
            "None — standard protocol"
        ),
    }

BMI_TOOLS = [calculate_bmi, classify_risk]
BMI_TOOLS_BY_NAME = {t.name: t for t in BMI_TOOLS}

def bmi_agent_node(state: NutritionState, model: ChatOpenAI) -> dict:
    model_with_tools = _bind(model, BMI_TOOLS)

    system = f"""You are a clinical physiologist using the ReAct (Reasoning + Acting) framework.
You have access to tools: calculate_bmi, classify_risk.

{FMT}

REACT INSTRUCTIONS:
- First THINK about what you need to know
- Then ACT by calling the appropriate tool
- OBSERVE the result and reason about it
- Repeat until you have a complete clinical picture
- Finally write your assessment

Your goal: Produce a formal BMI and risk assessment for this patient."""

    user = f"""Patient profile:
Age: {state['age']} | Gender: {state['gender']}
Weight: {state['weight_kg']} kg | Height: {state['height_cm']} cm
Goal: {state['goal']} | Activity: {state['activity_level']}
Health conditions: {state['health_conditions']}

Use your tools to calculate BMI, classify risk, then write a formal clinical assessment with headings:
CLINICAL STATUS, TARGET ANALYSIS, RISK PROFILE, CLINICAL PRIORITIES."""

    final_text, trace = _run_react(model_with_tools, system, user, BMI_TOOLS_BY_NAME)

    # The rule engine computes the whole plan once; later agents narrate and check it
    plan = P.build(state)
    final_text = final_text or P.bmi_text(plan)
    bmi = plan["metrics"]["bmi"]
    cat = plan["metrics"]["category"]
    tdee = plan["metrics"]["tdee"]

    risk_result = classify_risk.invoke({
        "bmi": bmi, "age": state["age"],
        "health_conditions": state["health_conditions"]
    })

    return {
        "bmi": bmi, "bmi_category": cat, "tdee": tdee,
        "risk_level": risk_result["protocol"],
        "plan": plan,
        "bmi_report": final_text,
        "bmi_trace": trace,
        "nutrition_revision_count": 0,
        "nutrition_score": 0,
        "messages": [AIMessage(content=f"[BMI Agent] BMI {bmi} ({cat}). Protocol: {risk_result['protocol'].upper()}.")],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 2 — NUTRITION AGENT
# Tools: compute_tdee, build_macro_targets
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def compute_tdee(weight_kg: float, height_cm: float, age: int,
                 gender: str, activity_level: str, goal: str) -> dict:
    """Compute TDEE (Mifflin-St Jeor) and the Easy/Medium/High calorie paths with realistic deadlines."""
    s = {**_CTX, "weight_kg": weight_kg, "height_cm": height_cm, "age": age,
         "gender": gender, "activity_level": activity_level}
    p = P.paths(s)
    return {"tdee_kcal": P.tdee(s), "goal": p["goal"], "recommended": p["recommended"],
            "paths": [{k: x[k] for k in ("name", "kcal", "kg_per_week", "weeks", "deadline", "steps")}
                      for x in p["tiers"]],
            "target_feasible": p["target_feasible"]}

@tool
def build_macro_targets(weight_kg: float, daily_kcal: int,
                        goal: str, risk_level: str) -> dict:
    """Protein (1.3 g/kg, natural foods only), carbohydrate, fat, fibre and water targets."""
    return P.targets({**_CTX, "weight_kg": weight_kg}, daily_kcal)

NUTRITION_TOOLS = [compute_tdee, build_macro_targets]
NUTRITION_TOOLS_BY_NAME = {t.name: t for t in NUTRITION_TOOLS}

def nutrition_agent_node(state: NutritionState, model: ChatOpenAI) -> dict:
    model_with_tools = _bind(model, NUTRITION_TOOLS)
    is_intervention = state["risk_level"] == "intervention"

    revision_context = ""
    if state["nutrition_revision_count"] > 0:
        revision_context = f"\n\nPREVIOUS CRITIQUE TO ADDRESS:\n{state['nutrition_critique']}\nRevise your plan to fix every issue."

    system = f"""You are a Registered Dietitian using the ReAct framework.
You have tools: compute_tdee, build_macro_targets.
Protocol: {'INTERVENTION (therapeutic — 750 kcal max deficit/surplus, elevated protein)' if is_intervention else 'STANDARD (maintenance optimisation)'}

{FMT}
{revision_context}

REACT INSTRUCTIONS:
- THINK about what calculations you need
- ACT by calling tools in the right order (compute_tdee first, then build_macro_targets)
- OBSERVE each result carefully
- Build your complete nutrition prescription from the tool outputs"""

    user = f"""Patient: {_profile(state)}
BMI assessment: {state['bmi_report'][:400]}

Use your tools, then write a detailed nutrition plan with these ALL CAPS sections:
CALORIE PRESCRIPTION, MACRONUTRIENT TARGETS, MICRONUTRIENT PRIORITIES (4 nutrients),
HYDRATION, FOODS TO PRIORITISE (6 items), FOODS TO LIMIT (4 items), MEAL TIMING.
State the exact kcal and protein grams from COMPUTED NUMBERS. Protein comes only from natural
{'Indian' if state.get('region', 'in') == 'in' else 'American'} foods (eggs, chicken, fish, paneer,
tofu, dal, curd, milk, nuts). Never suggest whey, protein powder, protein bars or Greek yogurt."""

    _CTX.update(state)
    final_text, trace = _run_react(model_with_tools, system, user, NUTRITION_TOOLS_BY_NAME)
    final_text = final_text or P.nutrition_text(state["plan"])

    return {
        "nutrition_plan": final_text,
        "nutrition_trace": trace,
        "messages": [AIMessage(content=f"[Nutrition Agent] Plan complete. Revision {state['nutrition_revision_count'] + 1}.")],
    }

def route_nutrition(state: NutritionState) -> Literal["nutrition_critic", "nutrition_critic"]:
    return "nutrition_critic"


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 3 — CRITIC AGENT (ReAct Feedback Loop)
# Tool: score_plan
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def score_plan(
    calorie_accuracy: int,
    macro_balance: int,
    clinical_safety: int,
    specificity: int,
    completeness: int,
) -> dict:
    """Score the nutrition plan on 5 dimensions (1-10 each) and compute overall."""
    scores = [calorie_accuracy, macro_balance, clinical_safety, specificity, completeness]
    overall = round(sum(scores) / len(scores))
    passed = overall >= 7
    weakest = min(zip(scores, ["calorie_accuracy","macro_balance","clinical_safety","specificity","completeness"]))
    return {
        "dimension_scores": {
            "calorie_accuracy": calorie_accuracy,
            "macro_balance": macro_balance,
            "clinical_safety": clinical_safety,
            "specificity": specificity,
            "completeness": completeness,
        },
        "overall_score": overall,
        "passed": passed,
        "weakest_dimension": weakest[1],
        "verdict": "PROCEED to meal planning" if passed else "REVISE — score below threshold of 7",
    }

CRITIC_TOOLS = [score_plan]
CRITIC_TOOLS_BY_NAME = {t.name: t for t in CRITIC_TOOLS}

def critic_agent_node(state: NutritionState, model: ChatOpenAI) -> dict:
    model_with_tools = _bind(model, CRITIC_TOOLS)

    system = f"""You are a senior clinical nutrition reviewer using the ReAct framework.
You have one tool: score_plan.

{FMT}

REACT INSTRUCTIONS:
- THINK: read the nutrition plan carefully and evaluate each dimension
- ACT: call score_plan with your scores (1-10 each)
- OBSERVE: read the verdict
- Write your detailed critique explaining every score and listing specific revision instructions"""

    user = f"""Patient: {_profile(state)}

NUTRITION PLAN TO REVIEW:
{state['nutrition_plan']}

Score these 5 dimensions honestly:
1. calorie_accuracy (1-10): Is TDEE calculated correctly and goal adjustment appropriate?
2. macro_balance (1-10): Are protein/carbs/fat targets correct for this patient?
3. clinical_safety (1-10): Is it safe for conditions: {state['health_conditions']}?
4. specificity (1-10): Are all numbers patient-specific (not generic ranges)?
5. completeness (1-10): Are all sections present and detailed?

After scoring, write your full critique with:
DIMENSION SCORES, OVERALL VERDICT, ISSUES FOUND, REVISION INSTRUCTIONS (or NONE if passed)."""

    final_text, trace = _run_react(model_with_tools, system, user, CRITIC_TOOLS_BY_NAME)

    # Parse score from tool observation in trace
    score = 7  # safe default
    for step in trace:
        if step["type"] == "observation" and "overall_score" in step["content"]:
            try:
                obs = json.loads(step["content"].replace("'", '"'))
                score = obs.get("overall_score", 7)
            except Exception:
                import re
                m = re.search(r"overall_score['\": ]+(\d+)", step["content"])
                if m:
                    score = int(m.group(1))

    # Code checks the text too, so a weak model can't pass a plan with wrong numbers or whey
    t = state["plan"]["targets"]
    plan_text = state["nutrition_plan"].replace(",", "")
    issues = [f"mentions banned item: {b}" for b in P.banned_in(plan_text)]
    if str(t["kcal"]) not in plan_text:
        issues.append(f"must state the daily calorie target {t['kcal']} kcal")
    if str(t["protein_g"]) not in plan_text:
        issues.append(f"must state the protein target {t['protein_g']} g")
    if issues:
        score = min(score, 10 - 2 * len(issues))
        final_text = (final_text or "") + "\nRULE CHECKS FAILED: " + "; ".join(issues)
    elif not final_text:
        final_text = f"RULE CHECKS PASSED: calories {t['kcal']} kcal and protein {t['protein_g']} g stated, no banned foods."
        score = max(score, 8)

    count = state["nutrition_revision_count"] + 1
    return {
        "nutrition_critique": final_text,
        "nutrition_score": score,
        "nutrition_revision_count": count,
        "critic_trace": trace,
        "messages": [AIMessage(content=f"[Critic Agent] Score: {score}/10. Revision count: {count}.")],
    }

def should_revise(state: NutritionState) -> Literal["nutrition_agent", "meal_agent"]:
    if state["nutrition_score"] < 7 and state["nutrition_revision_count"] < 2:
        return "nutrition_agent"
    return "meal_agent"


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 4 — MEAL AGENT
# Tools: build_meal_plan, get_supplement_stack
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def build_meal_plan(
    daily_kcal: int,
    protein_g: int,
    carb_g: int,
    fat_g: int,
    dietary_restrictions: str,
    goal: str,
) -> dict:
    """Build a 7-day plan of real Indian/American meals scaled to the calorie target and
    topped up with natural protein; no food repeats more than twice a week."""
    t = P.targets(_CTX, daily_kcal)
    week = P.meal_week(_CTX, {**t, "protein_g": protein_g}, goal)
    return {"days": [{"day": d["day"], "kcal": d["kcal"], "protein_g": d["protein"],
                      "meals": [f"{i['slot']}: {i['name']} (x{i['portion']})" for i in d["meals"]]}
                     for d in week],
            "pre_meal_fillers": P.PRE_MEAL if goal != "gain" else [],
            "gain_extras": [g[0] for g in P.GAIN_EXTRAS] if goal == "gain" else []}

@tool
def get_supplement_stack(
    bmi: float,
    age: int,
    gender: str,
    goal: str,
    health_conditions: str,
    dietary_restrictions: str,
) -> dict:
    """Supplements for bone health and gym recovery only (no protein powders)."""
    return {"supplements": P.supplements(_CTX)}

MEAL_TOOLS = [build_meal_plan, get_supplement_stack]
MEAL_TOOLS_BY_NAME = {t.name: t for t in MEAL_TOOLS}

def meal_agent_node(state: NutritionState, model: ChatOpenAI) -> dict:
    model_with_tools = _bind(model, MEAL_TOOLS)

    t = state["plan"]["targets"]
    daily_kcal, protein_g, carb_g, fat_g = t["kcal"], t["protein_g"], t["carbs_g"], t["fat_g"]
    _CTX.update(state)
    feedback = (f"\nPLAN CRITIC FEEDBACK TO FIX:\n{state['plan_critique']}"
                if state.get("plan_revision_count") else "")

    system = f"""You are a culinary nutritionist and supplementation specialist using the ReAct framework.
You have tools: build_meal_plan, get_supplement_stack.

{FMT}

REACT INSTRUCTIONS:
- THINK about what you need to build
- ACT by calling build_meal_plan first (to get the framework), then get_supplement_stack
- OBSERVE each result — use the framework numbers to write specific meals
- Write out all 7 days with actual dish names, ingredients, and macros"""

    user = f"""Patient: {_profile(state)}
Nutrition prescription: {state['nutrition_plan'][:500]}

Computed targets: {daily_kcal} kcal/day | Protein {protein_g}g | Carbs {carb_g}g | Fat {fat_g}g

Call build_meal_plan with these targets, then get_supplement_stack.

After observing the results, write:

SECTION 1: 7-DAY MEAL PLAN
For each day use:
DAY N — [Cuisine Theme]
BREAKFAST: [dish] | Ingredients: [list] | Macros: P Xg / C Xg / F Xg / ~X kcal
LUNCH: [dish] | Ingredients: [list] | Macros: P Xg / C Xg / F Xg / ~X kcal
DINNER: [dish] | Ingredients: [list] | Macros: P Xg / C Xg / F Xg / ~X kcal
SNACK: [item] | Macros: P Xg / C Xg / F Xg / ~X kcal
DAILY TOTAL: X kcal

Use the tool's meals (modern breakfasts like egg or tofu scramble are welcome), keep each
food to at most twice a week, and cover fibre, calcium, iron and B12 sources.
{'Add EAT BEFORE MEALS: fillers from pre_meal_fillers to prevent overeating.' if state['plan']['paths']['goal'] != 'gain'
 else 'Add HIGH-PROTEIN GAINERS from gain_extras (homemade shakes are fine, treats allowed twice a week).'}
Never suggest whey, protein powder, protein bars or Greek yogurt.{feedback}

SECTION 2: SUPPLEMENT PROTOCOL
List each supplement from the tool result with dose, timing, and rationale."""

    final_text, trace = _run_react(model_with_tools, system, user, MEAL_TOOLS_BY_NAME)
    final_text = final_text or (P.meal_text(state["plan"]) + "\nSECTION 2:\n" + P.supplement_text(state["plan"]))

    # Split sections
    meal_part = final_text
    supp_part = ""
    if "SECTION 2:" in final_text:
        parts = final_text.split("SECTION 2:", 1)
        meal_part = parts[0].replace("SECTION 1:", "").strip()
        supp_part = parts[1].strip()

    return {
        "meal_plan": meal_part,
        "supplement_advice": supp_part,
        "meal_trace": trace,
        "messages": [AIMessage(content="[Meal Agent] 7-day plan + supplements complete.")],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 5 — ACTIVITY AGENT (walking for everyone, minimal-equipment gym if opted in)
# Tools: walking_plan, gym_plan
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def walking_plan(daily_steps: int) -> dict:
    """Daily step target, walking minutes, a 6-week ramp-up and optional easy running."""
    p = P.paths(_CTX)
    return P.activity(_CTX, {**P.tier(p), "steps": daily_steps, "gym_days": 0})["walking"]

@tool
def gym_plan(days_per_week: int) -> dict:
    """Push/pull/legs plan using only dumbbells, a bench, a pull-up bar and bodyweight."""
    days = max(2, min(6, days_per_week))
    return P.activity(_CTX, {**P.tier(P.paths(_CTX)), "gym_days": days})["gym"]

ACTIVITY_TOOLS = [walking_plan, gym_plan]
ACTIVITY_TOOLS_BY_NAME = {t.name: t for t in ACTIVITY_TOOLS}

def activity_agent_node(state: NutritionState, model) -> dict:
    tr = P.tier(state["plan"]["paths"])
    _CTX.update(state)
    tools = ACTIVITY_TOOLS if tr["gym_days"] else [walking_plan]
    system = f"""You are a fitness coach for beginners using the ReAct framework.
You have tools: {', '.join(t.name for t in tools)}.
{FMT}
Call walking_plan{' and gym_plan' if tr['gym_days'] else ''} first, then explain the plan simply."""
    user = f"""Patient: {_profile(state)}
Steps target {tr['steps']} a day{f", gym {tr['gym_days']} days a week" if tr['gym_days'] else ''}.
Write: WALKING PLAN (steps, minutes, how to walk, weekly ramp){', RUNNING' if tr.get('run') else ''},
{'GYM PLAN (each session with sets and reps, form cues, progression), ' if tr['gym_days'] else 'HOME BODYWEIGHT CIRCUIT, '}
CORE AND ABS, SAFETY. Only dumbbells, a flat bench, a pull-up bar and bodyweight moves; no machines."""
    final_text, trace = _run_react(_bind(model, tools), system, user, {t.name: t for t in tools})
    return {"activity_plan": final_text or P.activity_text(state["plan"]),
            "activity_trace": trace,
            "messages": [AIMessage(content="[Activity Agent] Walking and training plan complete.")]}


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 6 — PLAN CRITIC (rule checks in code, LLM explains; loops back to Meal once)
# ═══════════════════════════════════════════════════════════════════════════════

def plan_critic_node(state: NutritionState, model) -> dict:
    checks = P.plan_checks(state, state["plan"], state["meal_plan"] + state["supplement_advice"])
    score = P.score(checks)
    lines = [f"{'PASS' if c['ok'] else 'FAIL'}  {c['check']}: {c['detail']}" for c in checks]
    trace = [{"type": "action", "content": "Running rule checks on meals, protein, rate of change and activity",
              "tool": "plan_checks"},
             {"type": "observation", "content": "\n".join(lines), "tool": "plan_checks"}]
    text = ""
    if model is not None and score < 10:
        try:
            text = _text(model.invoke([SystemMessage(content=f"You are a strict nutrition plan reviewer. {FMT}"),
                                       HumanMessage(content="Explain these failed checks and exactly how to fix each:\n"
                                                            + "\n".join(l for l in lines if l.startswith("FAIL")))]))
        except Exception:
            pass
    return {"plan_checks": checks, "plan_score": score,
            "plan_critique": "\n".join(lines) + ("\n\n" + text if text else ""),
            "plan_revision_count": state.get("plan_revision_count", 0) + 1,
            "plan_critic_trace": trace,
            "messages": [AIMessage(content=f"[Plan Critic] {score}/10 on {len(checks)} rule checks.")]}

def should_revise_plan(state: NutritionState) -> Literal["meal_agent", "coach_agent"]:
    if state["plan_score"] < 8 and state["plan_revision_count"] < 2:
        return "meal_agent"
    return "coach_agent"


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT 5 — COACH AGENT
# Tools: safety_check, synthesise_report
# ═══════════════════════════════════════════════════════════════════════════════

@tool
def safety_check(
    daily_kcal: int,
    protein_g: int,
    weight_kg: float,
    gender: str,
    health_conditions: str,
) -> dict:
    """Audit the nutrition plan for clinical safety violations."""
    violations = []
    min_floor = 1200 if gender.lower() == "female" else 1500
    max_protein = round(2.5 * weight_kg)

    if daily_kcal < min_floor:
        violations.append(f"Calories {daily_kcal} kcal below safe floor of {min_floor} kcal — increase immediately.")
    if protein_g > max_protein:
        violations.append(f"Protein {protein_g}g exceeds safe ceiling of {max_protein}g for {weight_kg}kg patient.")
    if "kidney" in health_conditions.lower() and protein_g > round(1.2 * weight_kg):
        violations.append(f"High protein contraindicated for kidney disease. Reduce to max {round(1.2 * weight_kg)}g.")

    return {
        "status": "CLEARED" if not violations else "FLAGS RAISED",
        "violations": violations,
        "violations_count": len(violations),
        "safe_calorie_floor": min_floor,
        "safe_protein_ceiling": max_protein,
    }

@tool
def synthesise_report(
    nutrition_score: int,
    nutrition_revisions: int,
    safety_status: str,
    risk_level: str,
    goal: str,
) -> dict:
    """Generate a quality and process summary for the coaching report."""
    quality_label = "Excellent" if nutrition_score >= 9 else "Good" if nutrition_score >= 7 else "Acceptable"
    return {
        "quality_summary": f"Nutrition plan scored {nutrition_score}/10 ({quality_label}) after {nutrition_revisions} revision(s).",
        "safety_summary": f"Safety audit: {safety_status}.",
        "protocol": risk_level.upper(),
        "goal": goal,
        "process_note": (
            f"This plan was generated by 5 specialist ReAct agents, each reasoning "
            f"step-by-step with tools before producing their outputs."
        ),
    }

COACH_TOOLS = [safety_check, synthesise_report]
COACH_TOOLS_BY_NAME = {t.name: t for t in COACH_TOOLS}

def coach_agent_node(state: NutritionState, model: ChatOpenAI) -> dict:
    model_with_tools = _bind(model, COACH_TOOLS)

    daily_kcal = state["plan"]["targets"]["kcal"]
    protein_g = state["plan"]["targets"]["protein_g"]
    paths = "\n".join(f"{x['name']}: {x['kcal']} kcal, {x['steps']} steps, gym {x['gym_days']}/wk -> "
                      f"{x['kg_per_week']} kg/wk, {x['kg_per_month']} kg/month, {x['weeks']} weeks ({x['deadline']})"
                      for x in state["plan"]["paths"]["tiers"])

    system = f"""You are a senior wellness coach and clinical safety officer using the ReAct framework.
You have tools: safety_check, synthesise_report.

{FMT}

REACT INSTRUCTIONS:
- THINK about what to verify before writing the final report
- ACT: call safety_check first, then synthesise_report
- OBSERVE results and incorporate safety status into your coaching
- Write the final integrated coaching report"""

    user = f"""Patient: {_profile(state)}
Nutrition plan score: {state['nutrition_score']}/10 after {state['nutrition_revision_count']} revision(s)

Run safety_check with: daily_kcal={daily_kcal}, protein_g={protein_g},
weight_kg={state['weight_kg']}, gender={state['gender']}, health_conditions={state['health_conditions']}

Then run synthesise_report with the process metadata.

After observing both results, write the final coaching report:

EXECUTIVE SUMMARY (3 sentences: current status, what this plan achieves, realistic timeline)
3 WAYS TO REACH YOUR GOAL (copy these numbers exactly, recommend {state['plan']['paths']['recommended']}):
{paths}
{'' if state['plan']['paths']['target_feasible'] else 'Say plainly that the requested deadline is unsafe and give the High path deadline instead.'}
YOUR FINAL DAILY PLAN (food, water, walking or gym, sleep)
SAFETY AUDIT RESULT (what was checked and the outcome; plan checks scored {state.get('plan_score', 10)}/10)
YOUR THREE PRIORITIES THIS WEEK (specific and actionable)
YOUR 90-DAY MILESTONES (Week 2, Month 1, Month 3, with expected weights)
TIPS TO PREVENT RELAPSE (5 practical tips for Indian family meals, festivals and travel)
COACHING NOTE (warm closing)"""

    final_text, trace = _run_react(model_with_tools, system, user, COACH_TOOLS_BY_NAME)
    final_text = final_text or P.coach_text(state["plan"])

    return {
        "final_report": final_text,
        "coach_trace": trace,
        "messages": [AIMessage(content="[Coach Agent] Final report complete.")],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH
# ═══════════════════════════════════════════════════════════════════════════════

# node -> (UI name, description, function, model tier). Small models narrate, large ones judge.
NODES = {
    "bmi_agent":        ("BMI Agent", "Body metrics, Asian/WHO BMI cut-offs, risk", bmi_agent_node, "small"),
    "nutrition_agent":  ("Nutrition Agent", "TDEE, 3 effort paths, 1.3 g/kg natural protein", nutrition_agent_node, "small"),
    "nutrition_critic": ("Critic Agent", "Scores the prescription; rule checks on numbers and banned foods", critic_agent_node, "large"),
    "meal_agent":       ("Meal Agent", "7-day meals, anti-overeating snacks, supplements", meal_agent_node, "small"),
    "activity_agent":   ("Activity Agent", "Steps, walking/running and dumbbell gym plan", activity_agent_node, "small"),
    "plan_critic":      ("Plan Critic", "Rule checks: calories, protein, food repeats, safe rate", plan_critic_node, "large"),
    "coach_agent":      ("Coach Agent", "3 paths, realistic deadlines, final plan, relapse tips", coach_agent_node, "large"),
}

def _node(key, models):
    name, desc, fn, tier = NODES[key]
    def run(state):
        try:   # tell the UI an agent started (only inside graph.stream)
            get_stream_writer()({"event": "agent_start", "agent": name, "node": key, "description": desc})
        except Exception:
            pass
        return fn(state, models[tier])
    return run

def build_graph(cfg: dict):
    """cfg is the settings dict (provider, keys, model_small, model_large)."""
    models = {"small": _make_model(cfg, "small"), "large": _make_model(cfg, "large")}

    g = StateGraph(NutritionState)
    for key in NODES:
        g.add_node(key, _node(key, models))

    g.set_entry_point("bmi_agent")
    g.add_edge("bmi_agent",        "nutrition_agent")
    g.add_edge("nutrition_agent",  "nutrition_critic")

    # Critic feedback loop
    g.add_conditional_edges(
        "nutrition_critic",
        should_revise,
        {"nutrition_agent": "nutrition_agent", "meal_agent": "meal_agent"},
    )

    g.add_edge("meal_agent",     "activity_agent")
    g.add_edge("activity_agent", "plan_critic")
    g.add_conditional_edges("plan_critic", should_revise_plan,
                            {"meal_agent": "meal_agent", "coach_agent": "coach_agent"})
    g.add_edge("coach_agent", END)

    return g.compile()


def make_initial_state(**kw) -> NutritionState:
    return NutritionState(
        age=kw["age"], gender=kw["gender"],
        weight_kg=kw["weight_kg"], height_cm=kw["height_cm"],
        activity_level=kw["activity_level"], goal=kw["goal"],
        dietary_restrictions=kw.get("dietary_restrictions", "none"),
        health_conditions=kw.get("health_conditions", "none"),
        target_weight_kg=float(kw.get("target_weight_kg") or kw["weight_kg"]),
        target_weeks=int(kw.get("target_weeks") or 0),
        region=kw.get("region", "in"), diet_type=kw.get("diet_type", "nonveg"),
        gym=bool(kw.get("gym")), gym_days=int(kw.get("gym_days") or 3),
        budget=bool(kw.get("budget")), waist_cm=float(kw.get("waist_cm") or 0),
        plan={}, plan_checks=[], plan_score=0, plan_revision_count=0,
        activity_plan="", activity_trace=[], plan_critic_trace=[], plan_critique="",
        bmi=0.0, bmi_category="", risk_level="standard", tdee=0,
        nutrition_revision_count=0, nutrition_score=0,
        messages=[],
        bmi_trace=[], nutrition_trace=[], critic_trace=[],
        meal_trace=[], coach_trace=[],
        bmi_report="", nutrition_plan="", nutrition_critique="",
        meal_plan="", supplement_advice="", final_report="",
    )
