/* NutriCoach.AI front end: form, live metrics, SSE agent stream, today plan, tracker, body, settings. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const api = async (url, opts = {}) => {
  const r = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts,
    body: opts.body && JSON.stringify(opts.body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
};
const store = {                                        // per-viewer conveniences only
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};
const toast = (msg) => {
  const t = document.createElement("div"); t.className = "toast"; t.textContent = msg;
  document.body.append(t); setTimeout(() => t.remove(), 2600);
};
const today = () => new Date().toLocaleDateString("en-CA");

let S = {}, profiles = [], pid = store.get("pid", null), plan = null;

/* ── Tabs ─────────────────────────────────────────────────────────────── */
function show(page) {
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.page === page));
  $$("section.page").forEach((p) => p.classList.toggle("hidden", p.id !== "page-" + page));
  if (page === "tracker") loadLog();
  window.scrollTo({ top: 0, behavior: "smooth" });
}
$$(".tab").forEach((t) => (t.onclick = () => show(t.dataset.page)));

/* ── Form ─────────────────────────────────────────────────────────────── */
const form = $("#form");
$$(".seg", form).forEach((seg) => seg.addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  $$("button", seg).forEach((x) => x.classList.toggle("on", x === b)); live();
}));
form.gym.onchange = () => $("#gymDays").classList.toggle("hidden", !form.gym.checked);
form.gym_days.oninput = () => ($("#gymDaysV").textContent = form.gym_days.value);
form.addEventListener("input", live);

function collect() {
  const d = Object.fromEntries(new FormData(form));
  $$(".seg", form).forEach((s) => (d[s.dataset.name] = $("button.on", s).dataset.v));
  d.gym = form.gym.checked; d.budget = form.budget.checked;
  return d;
}
function fill(d) {
  for (const [k, v] of Object.entries(d || {})) {
    const el = form.elements[k];
    if (el && el.type === "checkbox") el.checked = !!v;
    else if (el) el.value = v;
    const seg = $(`.seg[data-name="${k}"]`, form);
    if (seg) $$("button", seg).forEach((b) => b.classList.toggle("on", b.dataset.v === v));
  }
  form.gym.onchange(); form.gym_days.oninput(); live();
}

/* ── Live metrics + BMI gauge ─────────────────────────────────────────── */
function live() {
  const d = collect(), h = d.height_cm / 100, w = +d.weight_kg;
  if (!h || !w) return;
  const asian = d.region === "in", bmi = w / (h * h), male = d.gender !== "Female";
  const [over, obese] = asian ? [23, 25] : [25, 30];
  const cat = bmi < 18.5 ? "Underweight" : bmi < over ? "Normal" : bmi < obese ? "Overweight" : "Obese";
  const bf = Math.max(4, 1.2 * bmi + 0.23 * d.age - 10.8 * male - 5.4);
  const whtr = d.waist_cm ? d.waist_cm / d.height_cm : null;
  const lo = 18.5 * h * h, hi = (asian ? 22.9 : 24.9) * h * h;
  gauge(bmi, asian);
  const cls = cat === "Normal" ? "ok" : cat === "Obese" ? "bad" : "warn";
  $("#liveStats").innerHTML = [
    ["BMI", bmi.toFixed(1), `<span class="pill ${cls}">${cat}</span>`],
    ["Body fat (est.)", bf.toFixed(1) + "%", male ? "healthy 10-20%" : "healthy 18-28%"],
    ["Healthy weight", `${lo.toFixed(0)}-${hi.toFixed(0)} kg`, `${Math.max(0, w - hi).toFixed(1)} kg above range`],
    ["Waist / height", whtr ? whtr.toFixed(2) : "–", whtr ? (whtr < .5 ? '<span class="ok">low risk</span>' : '<span class="bad">aim under 0.5</span>') : "add waist"],
  ].map(([k, v, s]) => `<div class="stat"><small>${k}</small><b>${v}</b><small>${s}</small></div>`).join("");
  $("#cutoffNote").textContent = asian
    ? "Using Asian BMI cut-offs (overweight from 23, obese from 25): South Asians carry more risk at lower BMI."
    : "Using WHO BMI cut-offs (overweight from 25, obese from 30).";
}
function gauge(bmi, asian) {
  const segs = asian ? [[15, 18.5, "#4cc9f0"], [18.5, 23, "var(--ok)"], [23, 25, "var(--warn)"], [25, 30, "#ff8c42"], [30, 40, "var(--bad)"]]
                     : [[15, 18.5, "#4cc9f0"], [18.5, 25, "var(--ok)"], [25, 30, "var(--warn)"], [30, 35, "#ff8c42"], [35, 40, "var(--bad)"]];
  const ang = (v) => Math.PI * (1 - (Math.min(40, Math.max(15, v)) - 15) / 25);
  const p = (v, r) => [110 + r * Math.cos(ang(v)), 115 - r * Math.sin(ang(v))];
  let s = segs.map(([a, b, c]) => { const [x1, y1] = p(a, 90), [x2, y2] = p(b, 90);
    return `<path d="M${x1},${y1} A90,90 0 0 1 ${x2},${y2}" stroke="${c}" stroke-width="18" fill="none"/>`; }).join("");
  const [nx, ny] = p(bmi, 72);
  s += `<line x1="110" y1="115" x2="${nx}" y2="${ny}" stroke="var(--text)" stroke-width="4" stroke-linecap="round" style="transition:all .6s"/>
        <circle cx="110" cy="115" r="7" fill="var(--text)"/>
        <text x="110" y="146" text-anchor="middle" font-family="Poppins" font-weight="700" font-size="20" fill="var(--text)">${bmi.toFixed(1)}</text>`;
  $("#gauge").innerHTML = s;
}

/* ── Run the agents (SSE over fetch) ──────────────────────────────────── */
form.onsubmit = async (e) => {
  e.preventDefault();
  const btn = $("#runBtn"); btn.disabled = true; btn.textContent = "⏳ Agents working…";
  $("#agents").innerHTML = ""; $("#dash").innerHTML = ""; show("results");
  try {
    const r = await fetch("/analyze", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...collect(), profile_id: pid }) });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
    const rd = r.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await rd.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n"); buf = parts.pop();
      for (const p of parts) if (p.startsWith("data: ")) onEvent(JSON.parse(p.slice(6)));
    }
  } catch (err) { $("#agents").insertAdjacentHTML("beforeend", `<div class="card bad">⚠ ${esc(err.message)}</div>`); }
  btn.disabled = false; btn.textContent = "▶ Build my plan";
};

function onEvent(ev) {
  const box = $("#agents");
  if (ev.event === "preview") $("#provLabel").textContent = "· " + ev.provider;
  if (ev.event === "agent_start") {
    $$(".agent.run", box).forEach((a) => a.classList.remove("run"));
    box.insertAdjacentHTML("beforeend", `<details class="agent run scan" data-node="${ev.node}"><summary><span class="dot"></span>
      <div><b>${esc(ev.agent)}</b><br><small class="muted">${esc(ev.description)}</small></div></summary><div class="body muted">Thinking…</div></details>`);
  }
  if (ev.event === "agent_done") {
    const el = $$(`.agent[data-node="${ev.node}"]`, box).pop(); if (!el) return;
    el.className = "agent done";
    const text = ev.content ?? [ev.meal_content, ev.supp_content && "SUPPLEMENTS\n" + ev.supp_content].filter(Boolean).join("\n\n");
    const extra = ev.score != null ? ` <span class="pill ${ev.score >= 7 ? "ok" : "warn"}">${ev.score}/10</span>` : "";
    $("summary b", el).insertAdjacentHTML("afterend", extra);
    $(".body", el).className = "body";
    $(".body", el).innerHTML = esc(text) + (ev.trace?.length ? `<div class="trace">${ev.trace.map((t) =>
      `<div>[${t.type}${t.tool ? " · " + esc(t.tool) : ""}] ${esc(t.content).slice(0, 600)}</div>`).join("")}</div>` : "");
    if (ev.plan) { plan = ev.plan; renderDash(); }
  }
  if (ev.event === "loop_decision" && ev.decision === "nutrition_agent")
    box.insertAdjacentHTML("beforeend", `<p class="warn" style="margin:0">↺ Critic scored ${ev.score}/10 — sending back for revision</p>`);
  if (ev.event === "complete") {
    plan = ev.plan; store.set("plan:" + (pid || 0), plan);
    renderDash(ev); renderToday(); setBody(plan.body);
    $(".agent:last-child", box)?.setAttribute("open", "");
    toast("✅ Plan ready! Open Today for your checklist.");
    if (ev.quote) $("#heroQuote").textContent = "“" + ev.quote + "”";
  }
  if (ev.event === "error") box.insertAdjacentHTML("beforeend", `<div class="card"><b class="bad">⚠ ${esc(ev.message)}</b></div>`);
}

/* ── Dashboard (results page) ─────────────────────────────────────────── */
function rec() { return plan.paths.tiers.find((t) => t.name === plan.paths.recommended); }
function renderDash(done) {
  const t = plan.targets, r = rec(), p = plan.paths;
  const icons = { Easy: "🚶", Medium: "🏃", High: "🔥" };
  let h = `<div class="card"><h2>3 ways to your goal <small class="muted">${p.goal} ${Math.abs(p.delta_kg)} kg</small></h2>
    ${p.target_feasible ? "" : `<p class="warn">Your deadline needs ${p.needed_kg_per_week} kg/week, which isn't safe. Here are realistic dates.</p>`}
    <div class="grid g3">${p.tiers.map((x) => `<div class="path ${x.name === p.recommended ? "rec" : ""}">
      <h3>${icons[x.name]} ${x.name} effort</h3>
      <div class="mono">${x.kcal} kcal · ${x.steps.toLocaleString()} steps${x.gym_days ? ` · gym ${x.gym_days}×/wk` : ""}${x.run ? " · 2 easy runs" : ""}</div>
      <div style="margin-top:6px"><b class="ok">${x.kg_per_week} kg/week</b> · ${x.kg_per_month} kg/month</div>
      <div class="muted">Goal in ${x.weeks} weeks → <b>${new Date(x.deadline).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</b></div></div>`).join("")}</div></div>
    <div class="card"><h2>Daily targets</h2><div class="grid g4">${[
      ["🔥 Calories", t.kcal + " kcal"], ["🥚 Protein", t.protein_g + " g"], ["🍚 Carbs", t.carbs_g + " g"], ["🥜 Fat", t.fat_g + " g"],
      ["🥗 Fibre", t.fibre_g + " g"], ["💧 Water", t.water_l + " L"], ["👟 Steps", r.steps.toLocaleString()], ["📉 TDEE", plan.metrics.tdee + " kcal"],
    ].map(([k, v]) => `<div class="stat"><small>${k}</small><b>${v}</b></div>`).join("")}</div>
    <p class="muted" style="font-size:.85rem;margin:.6rem 0 0">Protein ${t.protein_per_kg} g per kg, only from real food: no whey, no protein bars.</p></div>`;
  if (done) h += `<div class="card"><h2>Quality checks <span class="pill ${done.plan_score >= 8 ? "ok" : "warn"}">${done.plan_score}/10</span></h2>
      <div id="checks" class="muted">See the Plan Critic card for each rule.</div></div>
    <div class="card"><h2>Supplements <small class="muted">bone health + recovery</small></h2>${plan.supplements.map((s) =>
      `<div class="check" style="cursor:default"><span>💊</span><div><b>${esc(s.name)}</b> — ${esc(s.dose)}<br><small class="muted">${esc(s.why)}</small></div></div>`).join("")}
      <p class="muted" style="font-size:.8rem">Check with your doctor before starting supplements.</p></div>
    <button class="btn" onclick="show('today')">✅ Open today's plan</button>`;
  $("#dash").innerHTML = h;
  const pc = $$('.agent[data-node="plan_critic"] .body').pop();
  if (done && pc) $("#checks").innerHTML = esc(pc.firstChild?.textContent || "").split("\n").filter((l) => /^(PASS|FAIL)/.test(l))
    .map((l) => `<div>${l.startsWith("PASS") ? "✅" : "❌"} ${esc(l.replace(/^(PASS|FAIL)\s+/, ""))}</div>`).join("");
}

/* ── Today: checklist, meals, activity ────────────────────────────────── */
function renderToday() {
  if (!plan) return;
  const key = "check:" + (pid || 0) + ":" + today(), done = store.get(key, []);
  const dayIdx = (new Date().getDay() + 6) % 7, a = plan.activity;
  const meals = (i) => plan.meals[i].meals.map((m) => `<div class="meal"><div class="emo">${Art.foodEmoji(m.name)}</div>
      <div><div class="slot">${esc(m.slot)}</div><b>${esc(m.name)}</b>${m.portion && m.portion !== 1 ? ` <small class="muted">×${m.portion} portion</small>` : ""}
      <br><small class="muted">${m.kcal} kcal · ${m.protein} g protein</small></div></div>`).join("") +
      `<p class="mono muted">Day total: ${plan.meals[i].kcal} kcal · ${plan.meals[i].protein} g protein</p>`;
  const ex = (e) => `<div class="ex">${Art.poseSVG(e.diagram || e[3])}<div><b>${esc(e.name || e[0])}</b> <span class="pill ok">${esc(e.sets || e[2])}</span><br>
      <small class="muted">${esc(e.equipment || e[1])} · ${esc(e.focus || e[4])}</small></div></div>`;
  const w = a.walking, maxR = Math.max(...w.ramp_weeks);
  let gym = "";
  if (a.gym) gym = `<div class="card"><h2>🏋️ Gym plan <small class="muted">${a.gym.days_per_week}×/week · ${a.gym.minutes} min</small></h2>
      <p class="muted">${esc(a.gym.equipment)} — no machines needed.</p>
      <div class="daytabs" id="sessTabs">${a.gym.sessions.map((s, i) => `<button class="tab ${i ? "" : "active"}" data-i="${i}">${i + 1}. ${esc(s.name)}</button>`).join("")}</div>
      <div id="sess">${a.gym.sessions[0].exercises.map(ex).join("")}</div>
      <p class="muted" style="font-size:.9rem">${esc(a.gym.progression)}<br>${esc(a.gym.abs_note)}</p></div>`;
  else gym = `<div class="card"><h2>🏠 Home circuit <small class="muted">3 rounds, no equipment</small></h2>${a.home_circuit.map(ex).join("")}</div>`;
  const extras = plan.gain
    ? `<div class="card"><h2>💪 High-protein gainers</h2>${plan.gain.extras.map((x) => `<div class="meal"><div class="emo">${Art.foodEmoji(x)}</div><b>${esc(x)}</b></div>`).join("")}
       <h3>Treats allowed</h3><ul>${plan.gain.treats.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
       <h3>Gain muscle, not fat</h3><ul>${plan.gain.tips.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`
    : `<div class="card"><h2>🥒 Eat before meals to avoid overeating</h2><ul>${plan.pre_meal.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
  $("#today").innerHTML = `
    <div class="card"><h2>Today's checklist <small class="muted">${new Date().toDateString()}</small></h2>
      <div class="meter" style="margin-bottom:8px"><div id="chkBar"></div></div>
      ${plan.checklist.map((c, i) => `<label class="check ${done.includes(i) ? "done" : ""}"><input type="checkbox" data-i="${i}" ${done.includes(i) ? "checked" : ""}><span>${esc(c)}</span></label>`).join("")}
      <button class="btn ghost sm" style="margin-top:10px" onclick="show('tracker')">🔥 Log today in the tracker</button></div>
    <div class="card"><h2>🍽️ Meals</h2><div class="daytabs" id="dayTabs">${plan.meals.map((d, i) => `<button class="tab ${i === dayIdx ? "active" : ""}" data-i="${i}">Day ${d.day}</button>`).join("")}</div>
      <div id="dayMeals">${meals(dayIdx)}</div></div>
    ${extras}
    <div class="card"><h2>🚶 Walking <small class="muted">${w.daily_steps.toLocaleString()} steps · ~${w.walk_minutes} min</small></h2>
      <div class="ex">${Art.poseSVG(w.diagram)}<div>${esc(w.how)}${w.run ? `<br><b>Running:</b> ${w.run.sessions}×/week — ${esc(w.run.plan)}` : ""}</div></div>
      ${w.run ? `<div class="ex">${Art.poseSVG(w.run.diagram)}<div><b>Easy run intervals</b><br><small class="muted">${esc(w.run.plan)}</small></div></div>` : ""}
      <h3>6-week ramp-up</h3><div class="bars">${w.ramp_weeks.map((s) => `<div style="height:${(s / maxR) * 100}%" title="${s} steps"></div>`).join("")}</div>
      <div class="row mono muted" style="justify-content:space-between;font-size:.75rem">${w.ramp_weeks.map((s, i) => `<span>W${i + 1}<br>${(s / 1000).toFixed(1)}k</span>`).join("")}</div></div>
    ${gym}
    <div class="card"><h2>🛡️ Don't relapse</h2><ul>${plan.relapse_tips.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`;
  const bar = () => ($("#chkBar").style.width = (store.get(key, []).length / plan.checklist.length) * 100 + "%");
  bar();
  $$("#today .check input").forEach((cb) => (cb.onchange = () => {
    const s = new Set(store.get(key, [])); cb.checked ? s.add(+cb.dataset.i) : s.delete(+cb.dataset.i);
    store.set(key, [...s]); cb.parentElement.classList.toggle("done", cb.checked); bar();
    if (s.size === plan.checklist.length) toast("🏆 Perfect day! Log it in the tracker.");
  }));
  const tabs = (sel, render) => $$(sel + " .tab").forEach((b) => (b.onclick = () => {
    $$(sel + " .tab").forEach((x) => x.classList.toggle("active", x === b)); render(+b.dataset.i); }));
  tabs("#dayTabs", (i) => ($("#dayMeals").innerHTML = meals(i)));
  if (a.gym) tabs("#sessTabs", (i) => ($("#sess").innerHTML = a.gym.sessions[i].exercises.map(ex).join("")));
}

/* ── Body illustrator ─────────────────────────────────────────────────── */
let bodySex = "male";
function drawBody() {
  for (const k of ["now", "goal"]) {
    const fat = +$(`#${k}Fat`).value, mus = +$(`#${k}Mus`).value;
    $(`#body${k === "now" ? "Now" : "Goal"}`).innerHTML = Art.bodySVG(bodySex, fat, mus);
    $(`[data-out="${k}Fat"]`).textContent = fat; $(`[data-out="${k}Mus"]`).textContent = mus;
  }
}
function setBody(b) {
  if (!b) {                                             // before any plan: estimate from the form
    const d = collect(), h = d.height_cm / 100, bmi = d.weight_kg / (h * h), male = d.gender !== "Female";
    const bf = Math.max(4, 1.2 * bmi + 0.23 * d.age - 10.8 * male - 5.4);
    b = { sex: male ? "male" : "female", current: { body_fat_pct: bf.toFixed(1), muscle_pct: male ? 40 : 31 },
          goal: { body_fat_pct: male ? 15 : 23, muscle_pct: male ? 42 : 33 } };
  }
  bodySex = b.sex;
  $("#nowFat").value = b.current.body_fat_pct; $("#nowMus").value = b.current.muscle_pct;
  $("#goalFat").value = b.goal.body_fat_pct; $("#goalMus").value = b.goal.muscle_pct;
  drawBody();
}
$$("#page-body input[type=range]").forEach((r) => (r.oninput = drawBody));

/* ── Tracker ──────────────────────────────────────────────────────────── */
const logForm = $("#logForm");
logForm.day.value = today();
logForm.onsubmit = async (e) => {
  e.preventDefault();
  if (!pid) return toast("Save a profile first (Plan → Save profile).");
  const d = Object.fromEntries(new FormData(logForm));
  d.gym = logForm.gym.checked; d.healthy = logForm.healthy.checked;
  renderLog(await api(`/log/${pid}`, { method: "POST", body: d }), d.day);
  toast("Saved ✔");
};
async function loadLog() {
  if (!pid) { $("#streaks").innerHTML = '<p class="muted">Save a profile to start tracking.</p>'; return; }
  try { renderLog(await api(`/log/${pid}`)); } catch (e) { toast(e.message); }
}
function renderLog(h, day) {
  const s = h.streaks;
  $("#streaks").innerHTML = [["🚶", s.walking, "walking days"], ["🥗", s.healthy, "healthy days"],
    ["🎯", s.budget, "in calorie budget"], ["🏋️", s.gym_weeks, "gym weeks (2+/wk)"]]
    .map(([i, n, l]) => `<div class="badge"><div style="font-size:1.6rem">${i}</div><div class="n">${n}</div><small class="muted">${l}</small></div>`).join("");
  $("#lvl").textContent = `Level ${s.level} · ${s.title}`;
  $("#xp").textContent = `${s.xp} / ${s.next_at} XP`;
  $("#xpBar").style.width = Math.min(100, (s.xp % 150) / 1.5) + "%";
  const last = h.log.slice(-21), max = Math.max(300, ...last.map((r) => Math.abs(r.balance)));
  $("#bars").innerHTML = last.map((r) => `<div class="${r.balance < -150 ? "neg" : r.balance > 150 ? "pos" : ""}"
     style="height:${(Math.abs(r.balance) / max) * 100}%" title="${r.day}: ${r.result} (${r.balance} kcal)"></div>`).join("") || '<p class="muted">No days logged yet.</p>';
  $("#trackQuote").textContent = "“" + h.quote + "”";
  const r = h.log.find((x) => x.day === (day || today()));
  $("#dayResult").innerHTML = r ? `<div class="stat"><small>${r.day}</small><b class="${r.balance < -150 ? "ok" : r.balance > 150 ? "bad" : "warn"}">${r.result}</b>
     <small>Ate ${r.kcal_in} · burned ~${r.burned} kcal · ${r.balance > 0 ? "+" : ""}${r.balance} kcal ≈ ${r.fat_g > 0 ? "+" : ""}${r.fat_g} g fat</small></div>` : "";
}

/* ── Profiles ─────────────────────────────────────────────────────────── */
async function loadProfiles(select) {
  profiles = (await api("/profiles")).profiles;
  if (select !== undefined) pid = select;
  if (pid && !profiles.some((p) => p.id === pid)) pid = null;
  store.set("pid", pid);
  $("#profileSel").innerHTML = `<option value="">👤 Guest</option>` +
    profiles.map((p) => `<option value="${p.id}" ${p.id === pid ? "selected" : ""}>👤 ${esc(p.name)}</option>`).join("") +
    (profiles.length < 3 ? `<option value="new">➕ New profile</option>` : "") + (pid ? `<option value="del">🗑 Delete this profile</option>` : "");
}
$("#profileSel").onchange = async (e) => {
  const v = e.target.value;
  if (v === "del") {
    if (confirm("Delete this profile and its tracker history?")) { await api(`/profiles/${pid}`, { method: "DELETE" }); await loadProfiles(null); }
    else e.target.value = pid;
  } else if (v === "new") { form.reset(); form.name.value = "Profile " + (profiles.length + 1); await loadProfiles(null); show("plan"); live(); }
  else { await loadProfiles(v ? +v : null); usePlan(); }
};
function usePlan() {
  const p = profiles.find((x) => x.id === pid);
  if (p) fill(p.data);
  plan = store.get("plan:" + (pid || 0), null);
  if (plan) { renderToday(); setBody(plan.body); } else { $("#today").innerHTML = '<div class="card"><p class="muted">Build a plan to see today\'s checklist.</p></div>'; setBody(); }
}
$("#saveProfile").onclick = async () => {
  const d = collect();
  try { const r = await api("/profiles", { method: "POST", body: { id: pid, name: d.name, data: d } });
        await loadProfiles(r.id); toast("Profile saved ✔"); }
  catch (e) { toast(e.message); }
};

/* ── Settings ─────────────────────────────────────────────────────────── */
const dlg = $("#settings");
async function loadSettings() {
  S = await api("/settings");
  document.documentElement.dataset.theme = S.theme; $("#themeSel").value = S.theme;
}
$("#themeSel").onchange = async (e) => {
  document.documentElement.dataset.theme = e.target.value;
  S = await api("/settings", { method: "POST", body: { theme: e.target.value } });
};
$("#openSettings").onclick = () => {
  $("#provider").innerHTML = Object.entries(S.providers).map(([k, v]) => `<option value="${k}" ${k === S.provider ? "selected" : ""}>${esc(v.label)}</option>`).join("");
  provChanged(true); dlg.showModal();
};
$("#provider").onchange = () => provChanged(false);
async function provChanged(initial) {
  const p = $("#provider").value, info = S.providers[p];
  $("#keyBox").classList.toggle("hidden", !info.key);
  $("#keyHint").textContent = S.keys[p] ? `(saved: ${S.keys[p]})` : "(not set)";
  $("#apiKey").value = "";
  $("#mSmall").value = initial && p === S.provider ? S.model_small : info.small;
  $("#mLarge").value = initial && p === S.provider ? S.model_large : info.large;
  $("#modelList").innerHTML = info.models.map((m) => `<option value="${m}">`).join("");
  $("#localBox").classList.toggle("hidden", p !== "ollama");
  if (p !== "ollama") return;
  $("#localList").innerHTML = '<p class="muted">Checking Ollama…</p>';
  const L = await api("/local-models");
  $("#modelList").innerHTML = (L.installed || []).map((m) => `<option value="${m}">`).join("");
  $("#localList").innerHTML = (L.installed ? `<p class="ok">✔ Ollama running · installed: ${L.installed.map(esc).join(", ") || "none yet"}</p>`
      : `<p class="warn">Ollama isn't running. Install it free from <a href="${L.install_url}" target="_blank" rel="noopener">ollama.com</a>, then pull a model:</p>`) +
    `<p class="muted" style="font-size:.85rem">Suggested models, smallest first:</p>` +
    L.suggested.map((m) => `<div style="margin-bottom:6px"><b>${m.name}</b> <small class="muted">${m.gb} GB · needs ${m.ram_gb} GB RAM · ${esc(m.note)}</small>
      <pre class="cmd">ollama pull ${m.name}</pre></div>`).join("");
}
$("#saveSettings").onclick = async () => {
  const p = $("#provider").value, body = { provider: p, model_small: $("#mSmall").value, model_large: $("#mLarge").value };
  if ($("#apiKey").value.trim()) body.keys = { [p]: $("#apiKey").value.trim() };
  S = await api("/settings", { method: "POST", body }); dlg.close(); toast("Settings saved ✔");
};

/* ── Boot ─────────────────────────────────────────────────────────────── */
(async () => {
  live();
  api("/quote").then((q) => ($("#heroQuote").textContent = "“" + q.quote + "”"));
  await loadSettings();
  await loadProfiles();
  usePlan();
  // #page opens a tab; #demo-<page>-<theme> builds a sample plan first (used for README screenshots)
  const [a, page, theme] = location.hash.slice(1).split("-");
  if (a === "demo") {
    document.documentElement.classList.add("still");
    form.gym.checked = true; form.gym.onchange();
    if (theme) document.documentElement.dataset.theme = $("#themeSel").value = theme;
    await form.onsubmit(new Event("submit"));
    show(page || "results");
  } else if (a && $("#page-" + a)) show(a);
})();
