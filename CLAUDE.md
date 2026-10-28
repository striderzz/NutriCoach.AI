# NutriCoach.AI — Project Reference

Durable context for this project, so it isn't lost between sessions.

## What it is

A multi-agent nutrition and fitness coach aimed at Indian users (American diet as an
option). Seven LangGraph ReAct agents (model bound to tools via `bind_tools()`, tool
results fed back as `ToolMessage`s) turn a profile into calorie targets, 3 effort paths
with realistic deadlines, a natural-protein meal week, a walking/gym plan and a final
coaching report. Flask serves a single-page dashboard that streams each agent live over SSE,
plus a daily tracker, up to 3 profiles and a local body illustrator.

Stack: Python 3.13, Flask, langchain-core, langgraph, langchain-openai /
-anthropic / -google-genai / -ollama. Pinned in `requirements.txt`; the working env is
`venv/`. `venv_broken_old/` is a stale leftover, not used.

## Core rule: code computes, the LLM narrates

`planner.py` computes every number (BMI with Asian cut-offs when region is `in`, TDEE,
1.3 g/kg protein, Easy/Medium/High paths, meals, activity, checks). `planner.build()` runs
once in the BMI node and is stored in `state["plan"]`. Agents get the exact numbers in their
prompt (`_profile()` → `P.summary()`), and each node falls back to `P.<x>_text(plan)` when
the model is missing, can't call tools or fails. Keep this split: never let a model invent a
number, so weak and local models still give correct plans.

Product rules, enforced in code: no whey, protein powder, protein bars or Greek yogurt
(`P.BANNED`, checked by both critics); food repeats are capped (`P.CAP`); weight loss is
capped at 1% of body weight a week; the gym plan uses only dumbbells, a bench, a pull-up
bar and bodyweight; the gym streak needs 2+ sessions a week.

## Files

- **`agents.py`**: the agents, their `@tool` functions, `NutritionState`, `_run_react`
  (the ReAct loop, which returns `""` on failure so nodes use planner text), `NODES` (UI name,
  description, function, model tier), `build_graph(cfg)` and `make_initial_state()`.
  Tools with few args read the profile from the module-level `_CTX`.
- **`planner.py`**: the rule engine, food and exercise data, and the fallback text renderers.
- **`llm.py`**: `PROVIDERS` (openai, anthropic, google, deepseek, ollama, offline), small
  and large tiers, `LOCAL_MODELS` suggestions, `make_model(cfg, tier)` with lazy SDK imports.
- **`tracker.py`**: SQLite at `~/.nutricoach/data.db`; profiles (max 3), daily log,
  fat-loss/gain day result, streaks, XP levels, quotes.
- **`app.py`**: Flask. `/analyze` streams `graph.stream(stream_mode=["custom","updates"])`:
  nodes emit `agent_start` through `get_stream_writer()`, and `DONE_FIELDS` maps each node's
  state to its `agent_done` event. Also `/settings`, `/local-models`, `/profiles`, `/log/<id>`,
  `/quote`.
- **`templates/index.html`** + **`static/css/app.css`** + **`static/js/app.js`**: the UI.
  Themes via `data-theme` (`hacker` default, `light`, `dark`, `neon`). `#demo-<page>-<theme>`
  builds a sample plan on load with animations frozen (used for screenshots).
- **`static/js/art.js`**: body illustrator, animated exercise diagrams and food icons, all
  drawn in code. See the `local-art` skill.
- **`desktop.py`**: launcher. Runs Flask on a free local port, opened in a chromeless
  Edge/Chrome `--app` window with its own profile under `~/.nutricoach/window-profile`;
  closing the window quits.
- **`visualize_graph.py`**, **`make_icon.py`**: graph diagram, app icon.
- **`docs/`**: README screenshots and `preview.png`.

## Agent flow

BMI → Nutrition ⇄ Critic (score < 7, ≤ 2 revisions) → Meal → Activity → Plan Critic
(score < 8 → back to Meal once) → Coach. `app.py` runs `build_graph()` directly, so
routing lives only in `agents.py`.

## Secrets and settings

Provider, per-provider keys, `model_small`/`model_large`, `ollama_url` and theme live in
`~/.nutricoach/config.json`, never in the repo (`load_settings()` migrates the old single
`api_key`). Keys are passed to each client directly and never written to `os.environ`.

## Running, testing and building

```
venv\Scripts\python.exe app.py        # dev server on :5000 (NUTRICOACH_DEBUG=1 for debug)
venv\Scripts\python.exe desktop.py    # desktop app window
build_exe.cmd                          # PyInstaller one-file NutriCoachAI.exe
```

To test without touching the real config, point `USERPROFILE` at a scratch folder before
importing `app` (see `.claude/launch.json`). The `offline` provider runs the whole graph with
no LLM. Templates are cached when debug is off, so restart the server after editing them.
Headless Edge can't go narrower than ~500 px, so take mobile screenshots by embedding the app
in 390 px iframes.

`app.py` resolves templates/static through `sys._MEIPASS` so the frozen exe finds its
bundled files. `build/`, `dist/`, `*.spec`, `NutriCoachAI.exe`, `venv*/` and `output/` are
gitignored.
