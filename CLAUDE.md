# NutriCoach.AI — Project Reference

Durable context for this project, so it isn't lost between sessions.

## What it is

A multi-agent clinical nutrition app. Five LangGraph-style ReAct agents (model
bound to tools via `bind_tools()`, tool results fed back as `ToolMessage`s)
turn a patient profile into a nutrition prescription, a 7-day meal plan and a
90-day coaching report. Flask serves a single-page dashboard that streams each
agent's output and reasoning trace live over SSE.

Stack: Python 3.13, Flask, langchain-core, langchain-openai (OpenAI only),
langgraph. Pinned in `requirements.txt`; the working env is `venv/`.
`venv_broken_old/` is a stale leftover, not used.

## Files

- **`agents.py`** — all agents, their `@tool` functions, `NutritionState`,
  `_run_react` (the shared ReAct loop), `build_graph()` and
  `make_initial_state()`.
- **`app.py`** — Flask app. `/analyze` streams SSE events (`preview`,
  `agent_start`, `agent_done`, `loop_decision`, `complete`, `error`).
  `/settings` GET/POST for key, model and theme.
- **`templates/index.html`** — the whole UI (Bootstrap 5, inline CSS/JS),
  with themes switched via `data-theme` (`original`, `dark`, ...).
- **`desktop.py`** — launcher: Flask on a free local port, opened in a
  chromeless Edge/Chrome `--app` window with its own profile under
  `~/.nutricoach/window-profile`; closing the window quits.
- **`visualize_graph.py`** — renders the agent graph diagram.
- **`make_icon.py`** — generates `static/icon.png` / `icon.ico`.

## Agent flow

BMI → Nutrition → Critic → (score < 7: back to Nutrition, max 2 revisions)
→ Meal → Coach.

**`app.py` does not run `build_graph()`.** It drives the nodes itself
(`step()` in `/analyze`) so it can emit an SSE event around every agent, and
re-implements the Critic loop with `A.should_revise(state)`. A change to the
graph's routing in `agents.py` must be mirrored in `app.py`'s loop.

## Secrets and settings

The OpenAI key, model and theme live in `~/.nutricoach/config.json`, never in
the repo. The key is passed to each `ChatOpenAI` client directly and never
written to `os.environ`, so it can't leak between runs. Allowed models are the
`MODELS` list in `app.py`.

## Running and building

```
venv\Scripts\python.exe app.py        # dev server on :5000 (NUTRICOACH_DEBUG=1 for debug)
venv\Scripts\python.exe desktop.py    # desktop app window
build_exe.cmd                          # PyInstaller one-file NutriCoachAI.exe
```

`app.py` resolves templates/static through `sys._MEIPASS` so the frozen exe
finds its bundled files. `build/`, `dist/`, `*.spec`, `NutriCoachAI.exe`,
`venv*/` and `output/` are gitignored.
