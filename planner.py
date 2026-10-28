"""
Rule-based planning engine — every number NutriCoach shows comes from here.

Agents call these functions as tools and narrate the results; if the model is
weak, offline or fails, the *_text() renderers write the section instead, so
the plan is always complete and numerically correct.

Rules: protein 1.3 g/kg from natural foods only (no whey, protein bars or
Greek yogurt), Indian food by default with an American option, walking for
everyone and a dumbbell + bench + pull-up bar gym plan for those who opt in.
"""
import math
from collections import Counter
from datetime import date, timedelta

KCAL_PER_KG = 7700
BANNED = ["whey", "protein powder", "protein bar", "greek yog", "isolate", "mass gainer",
          "protein shake mix", "casein powder", "meal replacement"]
ACTIVITY_MULT = {"Sedentary": 1.2, "Lightly Active": 1.375, "Moderately Active": 1.55,
                 "Very Active": 1.725, "Extremely Active": 1.9}
BASELINE_STEPS = {"Sedentary": 3000, "Lightly Active": 5000, "Moderately Active": 7000,
                  "Very Active": 9000, "Extremely Active": 11000}
DIET_LEVEL = {"veg": 0, "egg": 1, "nonveg": 2}
# Servings a week per key food (others 6); daily staples like milk, curd and dal may repeat
CAP = {"egg": 10, "paneer": 4, "milk": 14, "curd": 14, "dal": 14}

# ── Food data ──────────────────────────────────────────────────────────────────
# (name, slot b/l/d/s, region in/us, diet veg/egg/nonveg, kcal, protein g, key food, cost 1 cheap/2 pricier)
MEALS = [
    ("Masala egg bhurji (3 eggs) + 2 multigrain roti", "b", "in", "egg", 480, 26, "egg", 1),
    ("Tofu bhurji + 2 roti", "b", "in", "veg", 430, 24, "tofu", 1),
    ("Paneer bhurji (100 g) + 2 roti", "b", "in", "veg", 520, 27, "paneer", 2),
    ("Moong dal chilla (2) + curd", "b", "in", "veg", 400, 22, "dal", 1),
    ("Besan chilla (2) + mint curd", "b", "in", "veg", 380, 20, "besan", 1),
    ("Veg poha + roasted peanuts + glass of milk", "b", "in", "veg", 450, 17, "milk", 1),
    ("Idli (4) + sambar + 2 boiled eggs", "b", "in", "egg", 450, 22, "egg", 1),
    ("Brown rice + dal + chicken curry (150 g) + salad", "l", "in", "nonveg", 650, 45, "chicken", 1),
    ("2 roti + rajma + curd + salad", "l", "in", "veg", 600, 25, "rajma", 1),
    ("Brown rice + chole + cucumber raita", "l", "in", "veg", 620, 24, "chole", 1),
    ("Fish curry (150 g) + rice + sabzi", "l", "in", "nonveg", 600, 38, "fish", 2),
    ("2 roti + paneer tikka (100 g) + dal", "l", "in", "veg", 640, 35, "paneer", 2),
    ("Egg curry (3 eggs) + 2 roti + salad", "l", "in", "egg", 560, 28, "egg", 1),
    ("Soya chunk pulao + raita", "l", "in", "veg", 560, 34, "soya", 1),
    ("Mutton curry (120 g) + 2 roti + salad", "l", "in", "nonveg", 650, 36, "goat", 2),
    ("Grilled chicken (150 g) + sauteed veg + 1 roti", "d", "in", "nonveg", 450, 45, "chicken", 1),
    ("Tofu stir-fry + 1 roti + dal", "d", "in", "veg", 430, 28, "tofu", 1),
    ("Palak paneer (80 g) + 2 roti", "d", "in", "veg", 500, 24, "paneer", 2),
    ("Moong dal khichdi + curd", "d", "in", "veg", 450, 20, "dal", 1),
    ("Tandoori fish (150 g) + salad + 1 roti", "d", "in", "nonveg", 400, 38, "fish", 2),
    ("Egg bhurji (3 eggs) + mixed veg + 1 roti", "d", "in", "egg", 420, 24, "egg", 1),
    ("Prawn masala (150 g) + small bowl rice", "d", "in", "nonveg", 450, 34, "seafood", 2),
    ("Dal tadka + mixed veg + 2 roti", "d", "in", "veg", 480, 20, "dal", 1),
    ("Roasted chana (40 g) + buttermilk", "s", "in", "veg", 200, 11, "chana", 1),
    ("2 boiled eggs + a fruit", "s", "in", "egg", 220, 13, "egg", 1),
    ("Sprouts chaat", "s", "in", "veg", 180, 12, "sprouts", 1),
    ("Curd (200 g) + fruit + seeds", "s", "in", "veg", 230, 11, "curd", 1),
    ("Glass of milk + handful of almonds", "s", "in", "veg", 260, 12, "milk", 1),
    ("Paneer cubes (60 g) + cucumber", "s", "in", "veg", 200, 11, "paneer", 2),
    ("Scrambled eggs (3) + whole-grain toast + fruit", "b", "us", "egg", 450, 24, "egg", 1),
    ("Tofu scramble + toast + avocado", "b", "us", "veg", 430, 22, "tofu", 2),
    ("Oatmeal with milk, peanut butter and banana", "b", "us", "veg", 480, 18, "milk", 1),
    ("Cottage cheese bowl with berries + toast", "b", "us", "veg", 380, 26, "cottage", 2),
    ("Grilled chicken + brown rice + veggies", "l", "us", "nonveg", 600, 45, "chicken", 1),
    ("Black bean burrito bowl with cheese", "l", "us", "veg", 600, 24, "beans", 1),
    ("Tuna salad whole-grain wrap", "l", "us", "nonveg", 480, 35, "fish", 1),
    ("Lentil soup + grilled cheese sandwich", "l", "us", "veg", 550, 26, "lentil", 1),
    ("Egg salad sandwich + side salad", "l", "us", "egg", 500, 24, "egg", 1),
    ("Baked salmon + potatoes + greens", "d", "us", "nonveg", 550, 38, "fish", 2),
    ("Chicken stir-fry + rice", "d", "us", "nonveg", 520, 40, "chicken", 1),
    ("Tofu stir-fry + rice", "d", "us", "veg", 480, 26, "tofu", 1),
    ("Veggie omelette (3 eggs) + salad + toast", "d", "us", "egg", 420, 26, "egg", 1),
    ("Lean beef chili", "d", "us", "nonveg", 500, 36, "beef", 2),
    ("Bean and cheese quesadilla + salsa", "d", "us", "veg", 520, 24, "beans", 1),
    ("2 hard-boiled eggs + apple", "s", "us", "egg", 220, 13, "egg", 1),
    ("Milk + almonds", "s", "us", "veg", 260, 12, "milk", 1),
    ("Apple + peanut butter", "s", "us", "veg", 250, 7, "peanut", 1),
    ("Cottage cheese + fruit", "s", "us", "veg", 200, 14, "cottage", 2),
]
# Natural protein top-ups used when a day falls short of the protein target
TOPUPS = [("30 g soya chunks", "veg", 105, 15), ("100 g chicken breast", "nonveg", 165, 31),
          ("2 boiled eggs", "egg", 140, 12), ("100 g firm tofu", "veg", 90, 10),
          ("200 g curd", "veg", 120, 8), ("250 ml milk", "veg", 150, 8)]
PRE_MEAL = ["500 ml water + a bowl of cucumber/carrot salad 15 min before lunch and dinner",
            "A cup of clear vegetable or chicken soup before dinner",
            "A glass of buttermilk (chaas) before lunch",
            "An apple or guava 30 min before a big meal",
            "A small handful of roasted chana when hungry between meals"]
GAIN_EXTRAS = [("Banana + peanut butter milkshake (homemade)", 500, 20),
               ("Dates, almonds and milk shake", 450, 15),
               ("Paneer paratha (2) + curd", 650, 25),
               ("Chicken or egg kathi roll", 550, 30),
               ("Peanut chikki + glass of milk", 400, 14)]
GAIN_TREATS = ["Burger or pizza slice (max 2 times a week, after training)",
               "Samosa or vada pav with a glass of milk (once a week)",
               "Ice cream or kulfi (once a week)"]
LEAN_GAIN_TIPS = ["Keep the surplus small (200-450 kcal) so the gain is mostly muscle",
                  "Train every major muscle at least twice a week",
                  "Hit the protein target daily from eggs, paneer, chicken, dal and milk",
                  "Check your waist weekly: if it grows faster than 1 cm a month, cut 150 kcal"]

# ── Exercise data ──────────────────────────────────────────────────────────────
# (name, equipment, sets x reps, diagram id, focus)
EX = {
    "db_bench":   ("Dumbbell bench press", "dumbbells + bench", "3 x 8-12", "ex-bench-press", "chest, triceps"),
    "db_ohp":     ("Seated dumbbell shoulder press", "dumbbells + bench", "3 x 8-12", "ex-shoulder-press", "shoulders"),
    "pushup":     ("Push-ups", "bodyweight", "3 x max", "ex-pushup", "chest, triceps, core"),
    "bench_dip":  ("Bench dips", "bench", "3 x 10-15", "ex-bench-press", "triceps"),
    "pullup":     ("Pull-ups (or slow negatives)", "pull-up bar", "3 x max", "ex-pullup", "back, biceps"),
    "db_row":     ("One-arm dumbbell row", "dumbbell + bench", "3 x 10 each side", "ex-db-row", "back"),
    "db_curl":    ("Dumbbell curl", "dumbbells", "3 x 10-12", "ex-curl", "biceps"),
    "hang_raise": ("Hanging knee/leg raise", "pull-up bar", "3 x 10-12", "ex-leg-raise", "lower abs"),
    "goblet":     ("Goblet squat", "dumbbell", "4 x 10", "ex-squat", "quads, glutes"),
    "db_rdl":     ("Dumbbell Romanian deadlift", "dumbbells", "3 x 10", "ex-db-rdl", "hamstrings, glutes"),
    "split_sq":   ("Bulgarian split squat", "dumbbells + bench", "3 x 10 each leg", "ex-lunge", "legs, balance"),
    "lunge":      ("Walking lunges", "bodyweight / dumbbells", "3 x 12 each leg", "ex-lunge", "legs"),
    "plank":      ("Plank", "bodyweight", "3 x 30-60 s", "ex-plank", "core"),
    "leg_raise":  ("Lying leg raises", "bodyweight", "3 x 12-15", "ex-leg-raise", "lower abs"),
    "squat":      ("Bodyweight squats", "bodyweight", "3 x 20", "ex-squat", "legs"),
}
DAYS = {
    "Push":      ["db_bench", "db_ohp", "pushup", "bench_dip", "plank"],
    "Pull":      ["pullup", "db_row", "db_curl", "hang_raise", "leg_raise"],
    "Legs":      ["goblet", "db_rdl", "split_sq", "lunge", "plank"],
    "Full body": ["goblet", "db_bench", "db_row", "db_rdl", "pushup", "plank", "leg_raise"],
}
SPLITS = {2: ["Full body", "Full body"], 3: ["Push", "Pull", "Legs"],
          4: ["Push", "Pull", "Legs", "Full body"], 5: ["Push", "Pull", "Legs", "Push", "Pull"],
          6: ["Push", "Pull", "Legs", "Push", "Pull", "Legs"]}
HOME_CIRCUIT = ["pushup", "squat", "lunge", "plank", "leg_raise"]

RELAPSE_TIPS = [
    "Plan for bad days: one off-plan meal is a blip, two in a row is a pattern; get back on the next meal.",
    "Never skip the walk twice in a row; even 10 minutes keeps the streak and the habit alive.",
    "Keep ready protein at home (boiled eggs, curd, roasted chana) so hunger never decides for you.",
    "Weigh yourself on the same morning each week and track the 4-week trend, not daily swings.",
    "At weddings and parties, fill half the plate with salad and protein first, then enjoy the rest.",
    "Sleep 7-8 hours; short sleep raises hunger hormones and cravings the next day.",
    "When the scale stalls for 3 weeks, cut 100-150 kcal or add 2000 steps; don't crash diet.",
]


# ── Metrics ────────────────────────────────────────────────────────────────────
def _male(s) -> bool:
    return str(s.get("gender", "Male")).lower() != "female"

def bmr(s) -> int:
    w, h, a = s["weight_kg"], s["height_cm"], s["age"]
    return int(10 * w + 6.25 * h - 5 * a + (5 if _male(s) else -161))

def tdee(s) -> int:
    return int(bmr(s) * ACTIVITY_MULT.get(s.get("activity_level"), 1.55))

def bmi_category(bmi: float, asian: bool) -> str:
    over, obese = (23, 25) if asian else (25, 30)
    if bmi < 18.5:  return "Underweight"
    if bmi < over:  return "Normal weight"
    if bmi < obese: return "Overweight"
    return "Obese"

def obesity_class(bmi: float, asian: bool) -> str:
    cuts = [(25, "Class I"), (30, "Class II"), (35, "Class III")] if asian else \
           [(30, "Class I"), (35, "Class II"), (40, "Class III")]
    cls = "None"
    for c, label in cuts:
        if bmi >= c:
            cls = label
    return cls

def body_fat(bmi: float, age: int, male: bool) -> float:
    """Deurenberg estimate from BMI, age and sex."""
    return round(max(4.0, 1.2 * bmi + 0.23 * age - 10.8 * male - 5.4), 1)

def metrics(s) -> dict:
    h = s["height_cm"] / 100
    bmi = round(s["weight_kg"] / (h * h), 1)
    asian = s.get("region", "in") == "in"
    male = _male(s)
    waist = float(s.get("waist_cm") or 0)
    return {
        "bmi": bmi, "category": bmi_category(bmi, asian), "obesity_class": obesity_class(bmi, asian),
        "asian_cutoffs": asian, "body_fat_pct": body_fat(bmi, s["age"], male),
        "muscle_pct": 40.0 if male else 31.0,          # normal skeletal muscle share to start from
        "whtr": round(waist / s["height_cm"], 2) if waist else None,
        "healthy_weight_range": [round(18.5 * h * h, 1), round((22.9 if asian else 24.9) * h * h, 1)],
        "bmr": bmr(s), "tdee": tdee(s),
    }

def targets(s, kcal: int) -> dict:
    """Macros for a calorie level: 1.3 g/kg protein, 25% fat, carbs fill the rest."""
    w = s["weight_kg"]
    h = s["height_cm"] / 100
    basis = min(w, 27 * h * h)                         # obese: dose protein on a BMI-27 weight
    per_kg = 0.8 if "kidney" in str(s.get("health_conditions", "")).lower() else 1.3
    protein = round(basis * per_kg)
    fat = round(kcal * 0.25 / 9)
    carbs = max(0, round((kcal - protein * 4 - fat * 9) / 4))
    gym_days = int(s.get("gym_days") or 0) if s.get("gym") else 0
    return {"kcal": kcal, "protein_g": protein, "protein_per_kg": per_kg, "carbs_g": carbs,
            "fat_g": fat, "fibre_g": 25 if kcal < 2000 else 30,
            "water_l": round(w * 0.035 + (0.5 if gym_days else 0), 1)}


# ── Effort paths and realistic timeline ───────────────────────────────────────
def paths(s) -> dict:
    w = s["weight_kg"]
    tw = float(s.get("target_weight_kg") or w)
    delta = tw - w
    goal = "maintain" if abs(delta) < 0.5 else ("gain" if delta > 0 else "lose")
    t, b = tdee(s), bmr(s)
    floor = max(1500 if _male(s) else 1200, b)
    gym = bool(s.get("gym"))
    base_steps = BASELINE_STEPS.get(s.get("activity_level"), 7000)
    tiers = []
    for i, name in enumerate(["Easy", "Medium", "High"]):
        rate = {"lose": [0.25, 0.5, 0.75], "gain": [0.1, 0.25, 0.4], "maintain": [0, 0, 0]}[goal][i]
        if goal == "lose":
            rate = min(rate, round(0.01 * w, 2))                    # never above 1% body weight a week
            steps = ([6000, 8000, 10000] if gym else [7000, 9000, 12000])[i]
        else:
            steps = [6000, 7000, 8000][i]
        gym_days = ([2, 3, 4] if goal != "gain" else [3, 4, 5])[i] if gym else 0
        burn = max(0, steps - base_steps) * 0.00057 * w + gym_days * 250 / 7
        if goal == "lose":
            kcal = max(floor, round(t + burn - rate * KCAL_PER_KG / 7))
            rate = round(min(0.01 * w, (t + burn - kcal) * 7 / KCAL_PER_KG), 2)
        else:
            kcal = round(t + burn + rate * KCAL_PER_KG / 7)
        weeks = math.ceil(abs(delta) / rate) if rate else 0
        tiers.append({
            "name": name, "kcal": int(kcal), "kg_per_week": rate, "kg_per_month": round(rate * 4.35, 1),
            "weeks": weeks, "deadline": (date.today() + timedelta(weeks=weeks)).isoformat(),
            "steps": steps, "walk_min": round(steps / 100), "gym_days": gym_days,
            "run": goal == "lose" and name == "High" and not gym,
        })
    want = float(s.get("target_weeks") or 0)
    needed = abs(delta) / want if want else 0
    rec = next((x["name"] for x in tiers if x["kg_per_week"] >= needed), "High") if goal != "maintain" else "Easy"
    feasible = not needed or any(x["kg_per_week"] >= needed for x in tiers)
    return {"goal": goal, "delta_kg": round(delta, 1), "tiers": tiers, "recommended": rec,
            "target_feasible": feasible,
            "needed_kg_per_week": round(needed, 2)}

def tier(p: dict, name: str | None = None) -> dict:
    name = name or p["recommended"]
    return next(x for x in p["tiers"] if x["name"] == name)


# ── Meals ──────────────────────────────────────────────────────────────────────
def _pool(s, slot):
    lvl = DIET_LEVEL.get(s.get("diet_type", "nonveg"), 2)
    region = s.get("region", "in")
    rows = [m for m in MEALS if m[1] == slot and m[2] == region and DIET_LEVEL[m[3]] <= lvl]
    if s.get("budget"):
        rows = [m for m in rows if m[7] == 1] or rows
    return rows

def meal_week(s, t: dict, goal: str) -> list[dict]:
    """7 days of real meals scaled to the calorie target, topped up to the protein target."""
    lvl = DIET_LEVEL.get(s.get("diet_type", "nonveg"), 2)
    tops = [x for x in TOPUPS if DIET_LEVEL[x[1]] <= lvl]
    pools = {k: _pool(s, k) for k in "blds"}
    used, keys, week = Counter(), Counter(), []
    for d in range(7):
        picks = []
        for off, slot in enumerate("bld"):
            pool = pools[slot]
            for j in range(len(pool)):                # rotate; skip a meal or key food used too often
                m = pool[(d + off + j) % len(pool)]
                if used[m[0]] < 2 and keys[m[6]] < CAP.get(m[6], 6) - 1:
                    break
            used[m[0]] += 1; keys[m[6]] += 1
            picks.append(m)
        sp = pools["s"]
        snacks = [m for m in (sp[(d + j) % len(sp)] for j in range(len(sp)))
                  if keys[m[6]] < CAP.get(m[6], 6)][:2]
        keys.update(m[6] for m in snacks)
        items = [{"slot": "Breakfast Lunch Dinner".split()[i], "name": m[0], "kcal": m[4], "protein": m[5]}
                 for i, m in enumerate(picks)]
        items += [{"slot": "Snack", "name": m[0], "kcal": m[4], "protein": m[5]} for m in snacks]
        if goal == "gain":
            g = GAIN_EXTRAS[d % len(GAIN_EXTRAS)]
            items.append({"slot": "Gain snack", "name": g[0], "kcal": g[1], "protein": g[2]})
        base_k = sum(i["kcal"] for i in items)
        base_p = sum(i["protein"] for i in items)
        f = min(1.6, max(0.6, t["kcal"] / base_k))
        added_k = added_p = 0
        for name, _, k, p in tops * 2:                 # protein top-ups until the day hits target
            if base_p * f + added_p >= t["protein_g"]:
                break
            items.append({"slot": "Protein top-up", "name": name, "kcal": k, "protein": p, "fixed": True})
            added_k += k; added_p += p
            f = min(1.6, max(0.6, (t["kcal"] - added_k) / base_k))
        f = round(f * 20) / 20
        for i in items:
            if not i.get("fixed"):
                i["kcal"], i["protein"], i["portion"] = round(i["kcal"] * f), round(i["protein"] * f), f
            else:
                i["portion"] = 1.0
                i.pop("fixed")
        week.append({"day": d + 1, "meals": items,
                     "kcal": sum(i["kcal"] for i in items), "protein": sum(i["protein"] for i in items)})
    return week

def supplements(s) -> list[dict]:
    """Bone health and gym recovery only; food first, no protein powders."""
    lvl = DIET_LEVEL.get(s.get("diet_type", "nonveg"), 2)
    out = [{"name": "Vitamin D3", "dose": "1000-2000 IU/day with a meal", "why": "Bone health; most Indians are deficient"},
           {"name": "Calcium (if under 2 dairy servings/day)", "dose": "500 mg/day", "why": "Bone density"},
           {"name": "Magnesium glycinate", "dose": "200-300 mg at night", "why": "Sleep, muscle recovery, bone health"}]
    if lvl < 2:
        out.append({"name": "Vitamin B12", "dose": "500-1000 mcg/day", "why": "Low in vegetarian diets"})
        out.append({"name": "Omega-3 (algal or fish oil)", "dose": "1 g/day", "why": "Joints and recovery; low without fish"})
    if s.get("gym"):
        out.append({"name": "Creatine monohydrate (optional)", "dose": "3-5 g/day", "why": "Strength and recovery; best-studied gym supplement"})
    return out


# ── Activity ───────────────────────────────────────────────────────────────────
def activity(s, tr: dict) -> dict:
    steps = tr["steps"]
    start = max(3000, BASELINE_STEPS.get(s.get("activity_level"), 7000) - 1000)
    ramp = [int(round(start + (steps - start) * wk / 5, -2)) for wk in range(6)]
    walk = {"daily_steps": steps, "walk_minutes": tr["walk_min"], "ramp_weeks": ramp,
            "how": "Brisk pace (you can talk but not sing); split into 2-3 walks, one after a meal",
            "diagram": "walk-brisk"}
    if tr.get("run"):
        walk["run"] = {"sessions": 2, "plan": "20 min: alternate 2 min jog / 1 min walk", "diagram": "run-easy"}
    out = {"walking": walk, "gym": None, "home_circuit": [EX[k] for k in HOME_CIRCUIT]}
    if tr["gym_days"]:
        split = SPLITS[min(6, max(2, tr["gym_days"]))]
        out["gym"] = {"days_per_week": tr["gym_days"], "minutes": 45,
                      "equipment": "dumbbells, flat bench, pull-up bar",
                      "sessions": [{"name": n, "exercises": [dict(zip(
                          ["name", "equipment", "sets", "diagram", "focus"], EX[k])) for k in DAYS[n]]}
                          for n in split],
                      "progression": "Add 1-2 reps each week; when you hit the top of the range on all sets, use heavier dumbbells.",
                      "abs_note": "A visible six-pack needs roughly 10-12% body fat (men) or 18-20% (women): the diet and walking get you there, the core work shapes it."}
    return out


# ── Checks ─────────────────────────────────────────────────────────────────────
def banned_in(text: str) -> list[str]:
    low = (text or "").lower()
    return [b for b in BANNED if b in low]

def plan_checks(s, plan: dict, text: str = "") -> list[dict]:
    t, tr, week = plan["targets"], tier(plan["paths"]), plan["meals"]
    avg = sum(d["kcal"] for d in week) / 7
    keys = Counter(m[6] for d in week for i in d["meals"] for m in MEALS if m[0] == i["name"])
    over = [(k, n) for k, n in keys.items() if n > CAP.get(k, 6)]
    worst = over[0] if over else (keys.most_common(1)[0] if keys else ("-", 0))
    floor = 1500 if _male(s) else 1200
    c = [
        ("Calories on target", abs(avg - t["kcal"]) <= 0.1 * t["kcal"], f"avg {round(avg)} vs {t['kcal']} kcal"),
        ("Protein >= target every day", min(d["protein"] for d in week) >= 0.95 * t["protein_g"],
         f"lowest day {min(d['protein'] for d in week)} g vs {t['protein_g']} g"),
        ("No whey / bars / artificial protein", not banned_in(text + str(week) + str(plan["supplements"])),
         ", ".join(banned_in(text)) or "clean"),
        ("No food over-used", not over, f"most used: {worst[0]} x{worst[1]}/week"),
        ("Safe rate of change", tr["kg_per_week"] <= 0.01 * s["weight_kg"] + 0.001, f"{tr['kg_per_week']} kg/week"),
        ("Above calorie floor", tr["kcal"] >= floor, f"{tr['kcal']} kcal (floor {floor})"),
        ("Enough movement", tr["steps"] >= 6000, f"{tr['steps']} steps/day"),
    ]
    if s.get("gym"):
        c.append(("Gym at least 2x/week", tr["gym_days"] >= 2, f"{tr['gym_days']} days"))
    return [{"check": n, "ok": bool(ok), "detail": d} for n, ok, d in c]

def score(checks: list[dict]) -> int:
    return max(0, 10 - 2 * sum(not c["ok"] for c in checks))


# ── Body composition for the illustrator ─────────────────────────────────────
def body(s, m: dict, p: dict) -> dict:
    w, tw = s["weight_kg"], float(s.get("target_weight_kg") or s["weight_kg"])
    fat = w * m["body_fat_pct"] / 100
    musc = w * m["muscle_pct"] / 100
    d = tw - w
    gym = bool(s.get("gym"))
    if d < 0:
        fat_share = 0.85 if gym else 0.75
        fat2, musc2 = fat + d * fat_share, musc + d * (1 - fat_share) * (0.2 if gym else 0.5)
    else:
        lean_share = 0.5 if gym else 0.3
        fat2, musc2 = fat + d * (1 - lean_share), musc + d * lean_share * 0.6
    return {"sex": "male" if _male(s) else "female", "height_cm": s["height_cm"],
            "current": {"weight": w, "body_fat_pct": m["body_fat_pct"], "muscle_pct": m["muscle_pct"]},
            "goal": {"weight": tw, "body_fat_pct": round(max(5, fat2 / tw * 100), 1),
                     "muscle_pct": round(min(55, musc2 / tw * 100), 1)}}


# ── One call builds everything ────────────────────────────────────────────────
def build(s) -> dict:
    m = metrics(s)
    p = paths(s)
    tr = tier(p)
    t = targets(s, tr["kcal"])
    plan = {"metrics": m, "paths": p, "targets": t,
            "meals": meal_week(s, t, p["goal"]), "supplements": supplements(s),
            "activity": activity(s, tr), "body": body(s, m, p),
            "pre_meal": PRE_MEAL if p["goal"] != "gain" else [],
            "gain": {"extras": [g[0] for g in GAIN_EXTRAS], "treats": GAIN_TREATS, "tips": LEAN_GAIN_TIPS}
                    if p["goal"] == "gain" else None,
            "relapse_tips": RELAPSE_TIPS}
    plan["checklist"] = daily_checklist(plan)
    return plan

def daily_checklist(plan: dict) -> list[str]:
    t, tr = plan["targets"], tier(plan["paths"])
    out = [f"Eat within {t['kcal']} kcal", f"Hit {t['protein_g']} g protein from real food",
           f"Drink {t['water_l']} L water", f"Walk {tr['steps']} steps (~{tr['walk_min']} min)",
           "Vegetables or salad with lunch and dinner", "Sleep 7-8 hours"]
    if tr["gym_days"]:
        out.insert(4, f"Gym session ({tr['gym_days']}x this week)")
    return out


# ── Fallback text (used when the LLM is offline, weak or fails) ──────────────
def _join(lines):
    return "\n".join(lines)

def summary(plan: dict) -> str:
    """Exact numbers handed to every agent prompt so even small models stay correct."""
    m, t, p = plan["metrics"], plan["targets"], plan["paths"]
    tr = tier(p)
    return (f"BMI {m['bmi']} ({m['category']}, {'Asian' if m['asian_cutoffs'] else 'WHO'} cut-offs), "
            f"est. body fat {m['body_fat_pct']}%, BMR {m['bmr']}, TDEE {m['tdee']} kcal. "
            f"Goal {p['goal']} {abs(p['delta_kg'])} kg, recommended {tr['name']} path: {t['kcal']} kcal/day, "
            f"protein {t['protein_g']} g, carbs {t['carbs_g']} g, fat {t['fat_g']} g, fibre {t['fibre_g']} g, "
            f"water {t['water_l']} L, {tr['steps']} steps/day, gym {tr['gym_days']} days/week, "
            f"{tr['kg_per_week']} kg/week, {tr['weeks']} weeks (by {tr['deadline']}). "
            f"Protein only from natural foods; never whey, protein bars or Greek yogurt.")

def bmi_text(plan):
    m = plan["metrics"]
    lo, hi = m["healthy_weight_range"]
    return _join([
        "CLINICAL STATUS", f"BMI {m['bmi']} — {m['category']} (obesity class: {m['obesity_class']}).",
        f"Estimated body fat {m['body_fat_pct']}%. " + (f"Waist-to-height ratio {m['whtr']} (aim under 0.5)." if m["whtr"] else ""),
        "TARGET ANALYSIS", f"Healthy weight range for your height: {lo}-{hi} kg.",
        "ENERGY", f"BMR {m['bmr']} kcal, TDEE {m['tdee']} kcal a day.",
    ])

def nutrition_text(plan):
    t, p = plan["targets"], plan["paths"]
    return _join([
        "CALORIE PRESCRIPTION", f"{t['kcal']} kcal a day ({tier(p)['name']} path).",
        "MACRONUTRIENT TARGETS",
        f"Protein {t['protein_g']} g ({t['protein_per_kg']} g/kg), carbs {t['carbs_g']} g, fat {t['fat_g']} g, fibre {t['fibre_g']} g.",
        "HYDRATION", f"{t['water_l']} litres of water a day.",
        "FOODS TO PRIORITISE", "Eggs, chicken, fish, paneer, tofu, dal, curd, milk, soya chunks, nuts, brown rice.",
        "FOODS TO LIMIT", "Sugary drinks, deep-fried snacks, refined flour, sweets.",
        "MEAL TIMING", "3 meals and 1-2 snacks; protein in every meal; last meal 2-3 h before bed.",
    ])

def meal_text(plan):
    out = ["7-DAY MEAL PLAN"]
    for d in plan["meals"]:
        out.append(f"DAY {d['day']} — {d['kcal']} kcal, {d['protein']} g protein")
        out += [f"{i['slot'].upper()}: {i['name']} (~{i['kcal']} kcal, {i['protein']} g protein)" for i in d["meals"]]
    if plan["pre_meal"]:
        out += ["EAT BEFORE MEALS TO AVOID OVEREATING"] + plan["pre_meal"]
    if plan["gain"]:
        out += ["HIGH-PROTEIN GAINERS"] + plan["gain"]["extras"] + ["TREATS ALLOWED"] + plan["gain"]["treats"]
    return _join(out)

def supplement_text(plan):
    return _join([f"{x['name']}: {x['dose']} — {x['why']}" for x in plan["supplements"]])

def activity_text(plan):
    a = plan["activity"]
    w = a["walking"]
    out = ["WALKING PLAN", f"{w['daily_steps']} steps a day (~{w['walk_minutes']} min). {w['how']}.",
           "Weekly ramp: " + ", ".join(f"wk{i + 1} {x}" for i, x in enumerate(w["ramp_weeks"]))]
    if w.get("run"):
        out.append(f"RUNNING: {w['run']['sessions']}x a week — {w['run']['plan']}.")
    if a["gym"]:
        g = a["gym"]
        out.append(f"GYM PLAN — {g['days_per_week']} days a week, {g['minutes']} min, {g['equipment']}")
        for sess in g["sessions"]:
            out.append(f"{sess['name'].upper()}: " + "; ".join(f"{e['name']} {e['sets']}" for e in sess["exercises"]))
        out += [g["progression"], g["abs_note"]]
    else:
        out.append("HOME CIRCUIT (3 rounds): " + "; ".join(f"{e[0]} {e[2]}" for e in a["home_circuit"]))
    return _join(out)

def coach_text(plan):
    p = plan["paths"]
    out = ["EXECUTIVE SUMMARY", summary(plan), "3 WAYS TO REACH YOUR GOAL"]
    for x in p["tiers"]:
        out.append(f"{x['name'].upper()}: {x['kcal']} kcal, {x['steps']} steps, gym {x['gym_days']}/wk -> "
                   f"{x['kg_per_week']} kg/week, {x['kg_per_month']} kg/month, done in {x['weeks']} weeks ({x['deadline']})")
    if not p["target_feasible"]:
        out.append(f"Your target date needs {p['needed_kg_per_week']} kg/week, which is not safe; use the High path deadline instead.")
    out += ["DAILY CHECKLIST"] + plan["checklist"] + ["TIPS TO PREVENT RELAPSE"] + plan["relapse_tips"]
    return _join(out)
