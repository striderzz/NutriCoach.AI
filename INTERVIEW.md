# NutriCoach.AI: interview prep

Answers below are drawn from the code in this repo. For diagrams and the full design, see
[INFO.md](INFO.md). No performance, accuracy or user numbers were measured; where a number
would go, this file uses "—".

## Contents

- [30-second pitch](#30-second-pitch)
- [2-minute walkthrough](#2-minute-walkthrough)
- [Questions and answers](#questions-and-answers)
- [Resume bullet templates](#resume-bullet-templates)

## 30-second pitch

NutriCoach.AI is a nutrition and fitness coach built as a 7-agent LangGraph pipeline. Six of
the agents are ReAct agents that call 11 tools, and two critic agents send work back for
revision when it scores too low. The key design choice is that a rule engine computes every
number and the LLM only writes the explanation, so the plan stays correct on any of 5 LLM
providers, including small local models through Ollama, or with no model at all. Each agent's
think, act and observe steps stream to the browser over server-sent events from Flask.

## 2-minute walkthrough

1. **Problem.** Diet apps give generic plans, push protein powders and ignore Indian food.
   An LLM-only coach can invent calorie and protein numbers, and small local models do it more.
2. **Shape.** A Flask app serves a single-page UI. `POST /analyze` builds a LangGraph
   `StateGraph` with 7 nodes: BMI, Nutrition, Critic, Meal, Activity, Plan Critic, Coach.
3. **Rule engine first.** The BMI node calls `planner.build()` once. It computes BMI with
   Asian cut-offs for India, TDEE with Mifflin-St Jeor, three effort paths with deadlines and a
   1% body weight a week loss cap, macros at 1.3 g/kg protein, a 7-day meal plan, supplements
   and an activity plan. The result sits in `state["plan"]`, and every later prompt carries the
   exact numbers.
4. **Agents.** Six nodes run a ReAct loop: the model is bound to that node's tools, tool calls
   run and come back as `ToolMessage`s, up to 6 model calls. The tools are thin wrappers over
   planner functions, so even tool output is computed, not guessed.
5. **Loops.** The Critic scores the nutrition plan with `score_plan`, then code checks that
   the exact kcal and protein figures appear and that no banned item (whey, protein bars, Greek
   yogurt and similar) is mentioned. Below 7 it goes back to Nutrition. The Plan Critic runs
   7 or 8 rule checks in code; below 8 it goes back to Meal. Each loop allows one revision.
6. **Providers.** `llm.py` maps settings to OpenAI, Anthropic, Gemini, DeepSeek or Ollama
   with a small tier for narrating nodes and a large tier for judging nodes. An offline mode
   runs the same graph with no model, using the planner's own text.
7. **Streaming.** `graph.stream` with `custom` and `updates` modes feeds a Flask generator.
   The browser gets `agent_start`, `agent_done` (text, trace, score), `loop_decision` and
   `complete` events and renders a card per agent.
8. **Around it.** A SQLite tracker logs daily calories and steps, labels each day as fat
   loss, fat gain or maintenance, and keeps streaks and XP levels. It also ships as a desktop
   window and a one-file exe.

## Questions and answers

### Project overview

**1. What is NutriCoach.AI in one sentence?**
A local-first multi-agent coach that turns a profile into calorie targets, three effort paths
with realistic deadlines, a natural-protein 7-day meal plan, a walking or dumbbell gym plan and
a final coaching report.

**2. Why multiple agents instead of one big prompt?**
Each section has its own job, tools and prompt, so each model call is small and focused. The
graph makes the order and the review loops explicit, and the UI can show one card per agent
with its own trace. Small local models also do better with 2 tools than with 11.

**3. What is the single most important design rule?**
Code computes, the model narrates. `planner.py` computes every number; agents get those
numbers in their prompt through `_profile()` and `P.summary()`. If a model is missing, fails
or writes nothing, the node uses `P.<section>_text(plan)` instead.

**4. Who is it for?**
Indian users at home or abroad (American food is an option), and anyone who wants an AI coach
that runs free and offline with Ollama. Data stays in `~/.nutricoach/` on the user's machine.

### Agent design

**5. Walk me through the 7 nodes.**

| Node | Tools | Tier |
|---|---|---|
| BMI Agent | `calculate_bmi`, `classify_risk` | small |
| Nutrition Agent | `compute_tdee`, `build_macro_targets` | small |
| Critic Agent | `score_plan` | large |
| Meal Agent | `build_meal_plan`, `get_supplement_stack` | small |
| Activity Agent | `walking_plan`, `gym_plan` | small |
| Plan Critic | none, code checks | large |
| Coach Agent | `safety_check`, `synthesise_report` | large |

That is 7 nodes, 6 ReAct agents and 11 tools.

**6. Why is the Plan Critic not a ReAct agent?**
Its checks are deterministic: average calories within 10%, protein at least 95% every day, no
banned items, food repeat caps, safe rate, calorie floor, steps, gym days. Code runs them and
scores `10 - 2 x failures`. The large model is called once, without tools, only to explain the
failures in plain words, and only when the score is below 10.

**7. Some tools take only one or two arguments. How do they know the profile?**
Nodes copy the state into a module-level dict, `_CTX`, before running, and tools like
`walking_plan(daily_steps)` read the rest from it. The code comment says simple arguments keep
tool calling reliable on small local models. The cost is that `_CTX` is shared across threads
(see question 31).

**8. Why are tools thin wrappers over planner functions?**
So that a tool result is a computed number, never a model guess. `compute_tdee` calls
`P.paths` and `P.tdee`, `build_macro_targets` calls `P.targets`, `build_meal_plan` calls
`P.meal_week`. The model chooses when to call them and how to explain the result.

### LangGraph

**9. How is the graph built?**
`build_graph(cfg)` creates a `StateGraph(NutritionState)`, adds each node from `NODES`, sets
`bmi_agent` as the entry point, adds fixed edges (BMI to Nutrition, Nutrition to Critic, Meal
to Activity, Activity to Plan Critic, Coach to `END`) and two `add_conditional_edges` calls
using `should_revise` and `should_revise_plan`, then compiles it.

**10. How is state shared and merged?**
`NutritionState` is a `TypedDict` with the profile, the planner output, scores and counters,
section text and per-agent traces. Each node returns a partial dict. Only `messages` has a
reducer (`add_messages`, which appends); every other key is overwritten by the latest writer.

**11. How does the UI know an agent has started?**
`_node()` wraps every node function. Before it runs, the wrapper calls
`get_stream_writer()({"event": "agent_start", ...})`. That shows up as a `custom` chunk in
`graph.stream`. The call is in a `try` so the node still works outside a stream.

**12. Why build the graph on every request?**
The models come from the saved settings (provider, key, model ids), so a settings change takes
effect on the next run. The cost is rebuilding clients each time; at scale you would cache
compiled graphs per settings.

### ReAct and tool calling

**13. Explain your ReAct loop.**
`_react_loop` starts with a system and a human message. Each iteration calls the model. If the
response has `tool_calls`, it records a thought (the model's text or a default line), then for
each call records an action, runs the tool, records the observation and appends a
`ToolMessage` with the matching `tool_call_id`. If there are no tool calls, the response text
is the final answer.

**14. Why cap it at 6, and what happens at the cap?**
`max_iters = 6` bounds cost and stops a model that keeps calling tools. Each iteration is one
model call, which can request several tools. At the cap the loop returns the content of the
last message. If the model was still calling tools, that is a `ToolMessage`, so the node's
text becomes the raw tool output.

**15. What if a model cannot call tools?**
`_bind` tries `model.bind_tools(tools)` and returns the bare model if that raises. The bare
model never emits tool calls, so the loop ends after one call with plain text, and the prompt
already holds the numbers.

**16. What if a tool fails or the model calls a tool that does not exist?**
A tool exception becomes the observation `Tool error: ...`; an unknown name becomes
`Tool '<name>' not found.` Both go back to the model as a `ToolMessage`, so it can correct
itself instead of the run crashing. Any other exception in the loop is caught in `_run_react`,
which returns empty text so the node uses planner text.

### Critic loops

**17. Describe the two critic-revise loops.**
The Critic routes back to Nutrition when `nutrition_score < 7` and
`nutrition_revision_count < 2`; otherwise on to Meal. The Plan Critic routes back to Meal
when `plan_score < 8` and `plan_revision_count < 2`; otherwise on to Coach. On a revision the
critique is added to the agent's prompt.

**18. How many revisions can happen?**
One per loop. Each critic adds 1 to its counter before routing. After the first pass the
counter is 1, so a low score sends it back; after the second pass it is 2, so the graph moves
on whatever the score. Nutrition and Meal each run at most twice. Going back to Meal also
re-runs Activity, because the Meal to Activity edge is fixed.

**19. How is the Critic's score computed, and why not trust the model's score?**
The model calls `score_plan` with 5 dimension scores; the code reads `overall_score` from the
observation (JSON parse, then regex), defaulting to 7. Then code checks the text: banned items,
the exact kcal target and the exact protein grams. Each failed check caps the score at
`10 - 2 x issues`. A weak model could score its own wrong plan 9; the rule checks stop that.

**20. What is a weakness of the Plan Critic loop?**
The plan numbers come from `planner.build()` once, in the BMI node. When the loop goes back to
Meal, only the text changes, so checks on calories, protein, repeats, rate, floor and steps
return the same result. The loop can really only fix the banned-item check on the text. A
fix would be to feed failed checks back into planner parameters.

### Provider layer and small models

**21. How do you support 5 providers behind one interface?**
`llm.PROVIDERS` lists each provider's label, whether it needs a key, and small and large
defaults. `make_model(cfg, tier)` returns `ChatOpenAI` (OpenAI, and DeepSeek through its
`base_url`), `ChatAnthropic`, `ChatGoogleGenerativeAI` or `ChatOllama`, or `None` for the
offline mode. SDKs are imported inside the function, so a missing package only breaks that
provider.

**22. What are the small and large tiers for?**
Small models narrate (BMI, Nutrition, Meal, Activity); large models judge (Critic, Plan
Critic, Coach). Defaults are, for example, `gpt-4.1-mini` and `gpt-4.1`, or `llama3.2:3b` and
`qwen2.5:7b` on Ollama. Users can type any model id for either tier.

**23. How can a small local model produce a correct plan?**
It never has to produce a number. The numbers are in the prompt as "COMPUTED NUMBERS (use
exactly)", tools return planner output, the critic checks the text for the exact kcal and
protein, and if the model fails or writes nothing, planner text fills the section.

**24. How are API keys handled?**
They are saved in `~/.nutricoach/config.json`, outside the repo, passed straight to each
client and never written to `os.environ`. `GET /settings` returns them masked. A missing key
raises in `build_graph`, and `/analyze` returns HTTP 400 before streaming.

### Streaming

**25. What events does the browser receive?**
`preview` (provider label), `agent_start` (name, node, description), `agent_done` (section
text, trace and, for critics, score, revision or checks), `loop_decision` after the Critic,
`complete` (plan, scores, revision count, quote) and `error` (message and traceback).
`DONE_FIELDS` in `app.py` maps each node's state keys to its `agent_done` fields.

**26. Why SSE, and why read it with `fetch` instead of `EventSource`?**
The data only flows server to browser during one request, so a Flask generator returning
`text/event-stream` is enough; no socket server is needed. `EventSource` only supports GET,
and `/analyze` is a POST with a JSON body, so `app.js` reads `response.body` with a reader and
splits frames on blank lines.

**27. Do you stream tokens or each ReAct step live?**
No. A node's whole trace arrives in its `agent_done` event when it finishes; the card shows
"Thinking..." until then. Emitting each step through `get_stream_writer` would make it live.

### Testing and reliability

**28. How do you test it?**
There is no automated test suite in the repo yet. The `offline` provider runs the whole graph
with no model, which exercises routing, the planner and the fallback text end to end. The
project notes describe pointing `USERPROFILE` at a scratch folder so tests do not touch the
real config, and `#demo-<page>-<theme>` URLs that build a sample plan for screenshots. Next I
would add unit tests for `planner.py` (BMR, paths, caps, checks) and graph tests with a fake
chat model that returns scripted tool calls to drive both loops.

**29. How does a run avoid breaking when the model misbehaves?**
Layers of fallback: no model gives planner text; `bind_tools` failure gives the bare model;
any exception in the loop gives planner text; empty output gives planner text; tool errors are
fed back as observations. Clients also set `max_retries=2` and, for OpenAI, DeepSeek and
Anthropic, a 90-second timeout.

**30. How do you know the numbers are right?**
They come from fixed formulas in one file: Mifflin-St Jeor BMR, activity multipliers, 7700
kcal per kg, protein dosed on actual weight capped at a BMI-27 weight, fat at 25% of calories,
loss capped at 1% of body weight a week, calorie floors of 1500 and 1200. Both critics then
check the output against those numbers.

### Scaling and failure modes

**31. What breaks with two users at once?**
`_CTX` is a module-level dict and Flask runs with `threaded=True`. Two concurrent `/analyze`
runs can overwrite each other's context, so a tool can compute with the wrong profile. The fix
is to pass context through state or bind it per run.

**32. How would you scale this to many users?**
Remove `_CTX`, cache compiled graphs, move to async clients or a worker queue so streams do not
hold a thread each, put auth in front, store keys in a secret store, replace SQLite with
Postgres, send short error messages instead of tracebacks, and add tracing per run.

**33. What happens if the provider goes down mid-run?**
The client retries twice. If the call still fails, `_run_react` catches the exception, adds an
error thought to the trace and returns empty text, so that node uses planner text and the run
continues to `complete`.

**34. What security issues would you fix first?**
Tracebacks are sent to the client in the `error` event; keys are plain JSON in the home folder;
there is no auth. For a local single-user app these are acceptable; for a hosted version they
are the first three changes.

### Debugging scenarios

**35. The Critic always reports 7/10. Where do you look?**
7 is the default when no `score_plan` observation is found. Either the model never called the
tool (check the trace for an action step), or the observation did not parse. The code tries
JSON after swapping single quotes, then a regex on `overall_score`.

**36. The BMI Agent's trace says "Normal weight" but the dashboard says "Overweight".**
`calculate_bmi` in `agents.py` uses WHO cut-offs (25 and 30), while `planner.metrics` uses
Asian cut-offs (23 and 25) for region `in`. The state and dashboard use the planner value. The
fix is to have the tool call `P.bmi_category` with the region.

**37. An agent's final text is a raw dict instead of prose.**
The ReAct loop hit its 6-iteration cap while the model was still calling tools, so the last
message was a `ToolMessage` and its content became the final text. Check the trace length;
fixes are a final no-tools call at the cap or using planner text when the last message is a
tool result.

**38. The Plan Critic gives the same failing score twice.**
Expected for number checks: the revision re-runs Meal, which only changes text, while the
checks read `state["plan"]`, built once. Only the banned-item check can change between passes.

### Behavioral STAR outlines

**39. Tell me about making a system work under tight constraints.**
- Situation: the coach had to work on cheap and local models, including 1-4 GB Ollama models
  that often get numbers or tool calls wrong.
- Task: keep every plan numerically correct whatever the model.
- Action: moved every calculation into a rule engine (`planner.py`), passed exact numbers into
  each prompt, made tools thin wrappers over it, added fallback text per section and rule checks
  in both critics, plus an offline mode. The git history shows the rule-based planner, provider
  layer and the Activity and Plan Critic agents landing in one commit.
- Result: the full graph runs end to end with no model at all. Measured quality on each
  provider: —.

**40. Tell me about a flaw you found in your own design.**
- Situation: reviewing the Plan Critic loop.
- Task: check that a revision can actually fix what the critic flags.
- Action: traced the data flow and saw the checks read `state["plan"]`, which is built once,
  while the revision only rewrites Meal text. Outline the fix: feed failed checks back into the
  planner, or route number failures to a planner step.
- Result: —. Use this only for work you have actually done; say "I would" for changes not yet
  made.

## Resume bullet templates

Facts below match the code. Fill "—" only with numbers from a real run.

- Built NutriCoach.AI, a 7-agent LangGraph pipeline with 6 ReAct tool-calling agents, 11 tools
  and 2 Critic-Revise feedback loops that turns a user profile into calorie targets, 3 effort
  paths with safe deadlines and a natural-protein meal plan.
- Streamed per-agent Think-Act-Observe traces via Flask SSE, generating 7-day meal plans on 5
  swappable LLM providers (OpenAI, Anthropic, Gemini, DeepSeek, Ollama) plus a no-LLM mode.
- Designed a rule-engine-first architecture where code computes every number and the LLM only
  narrates, with a per-agent fallback chain and code-level critic checks, so small local models
  (Ollama) still produce correct plans; — runs evaluated.
- Added a SQLite tracker with daily fat-loss or fat-gain labels, streaks and XP levels, and
  shipped the Flask app as a desktop window and a one-file PyInstaller exe.
