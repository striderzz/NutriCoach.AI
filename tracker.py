"""
Profiles (up to 3), daily food + steps log, streaks, levels and quotes.

Stored in ~/.nutricoach/data.db (SQLite), next to config.json and outside the repo.
"""
import json
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import planner as P

DB = Path.home() / ".nutricoach" / "data.db"
MAX_PROFILES = 3
LEVELS = ["Rookie", "Walker", "Grinder", "Athlete", "Beast", "Legend"]
QUOTES = [
    "Small steps every day beat big steps once a month.",
    "You don't have to be extreme, just consistent.",
    "Discipline is choosing what you want most over what you want now.",
    "The walk you take today is the weight you don't carry tomorrow.",
    "Progress, not perfection.",
    "Eat like you love your body, train like you respect it.",
    "A missed day is a pause, not a stop.",
    "Strong is built one rep, one meal, one step at a time.",
    "Your future self is watching. Make them proud.",
    "Dal, roti, a walk and sleep: simple things, done daily, change everything.",
]


def _db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE IF NOT EXISTS profiles (id INTEGER PRIMARY KEY, name TEXT, data TEXT, plan TEXT);
        CREATE TABLE IF NOT EXISTS logs (profile_id INTEGER, day TEXT, kcal_in INTEGER, steps INTEGER,
            gym INTEGER, healthy INTEGER, weight REAL, PRIMARY KEY (profile_id, day));
    """)
    return con


def quote() -> str:
    return random.choice(QUOTES)


# ── Profiles ──────────────────────────────────────────────────────────────────
def profiles() -> list[dict]:
    with _db() as con:
        return [{"id": r["id"], "name": r["name"], "data": json.loads(r["data"]),
                 "plan": json.loads(r["plan"] or "null")} for r in con.execute("SELECT * FROM profiles")]


def save_profile(name: str, data: dict, pid: int | None = None) -> int:
    with _db() as con:
        if pid:
            con.execute("UPDATE profiles SET name=?, data=? WHERE id=?", (name, json.dumps(data), pid))
            return pid
        if con.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] >= MAX_PROFILES:
            raise ValueError(f"Up to {MAX_PROFILES} profiles; delete one first.")
        return con.execute("INSERT INTO profiles (name, data) VALUES (?, ?)",
                           (name, json.dumps(data))).lastrowid


def save_plan(pid: int, plan: dict) -> None:
    """Keep only what the tracker needs from a finished analysis."""
    tr = P.tier(plan["paths"])
    keep = {"targets": plan["targets"], "tier": tr, "metrics": plan["metrics"],
            "checklist": plan["checklist"], "body": plan["body"]}
    with _db() as con:
        con.execute("UPDATE profiles SET plan=? WHERE id=?", (json.dumps(keep), pid))


def delete_profile(pid: int) -> None:
    with _db() as con:
        con.execute("DELETE FROM profiles WHERE id=?", (pid,))
        con.execute("DELETE FROM logs WHERE profile_id=?", (pid,))


# ── Daily log ─────────────────────────────────────────────────────────────────
def log_day(pid: int, day: str, kcal_in: int, steps: int, gym: bool, healthy: bool, weight: float = 0) -> None:
    with _db() as con:
        con.execute("INSERT OR REPLACE INTO logs VALUES (?,?,?,?,?,?,?)",
                    (pid, day, int(kcal_in), int(steps), int(gym), int(healthy), float(weight or 0)))


def day_result(profile: dict, row: dict) -> dict:
    """Food in vs energy out for one day: fat loss, fat gain or maintenance."""
    d = profile["data"]
    w = float(row.get("weight") or d["weight_kg"])
    out = P.bmr({**d, "weight_kg": w}) * 1.2 + row["steps"] * 0.00057 * w + (250 if row["gym"] else 0)
    bal = round(row["kcal_in"] - out)
    label = "Fat loss day" if bal < -150 else "Fat gain day" if bal > 150 else "Maintenance day"
    return {**row, "burned": round(out), "balance": bal, "result": label, "fat_g": round(bal / 7.7)}


def history(pid: int, days: int = 60) -> dict:
    prof = next((p for p in profiles() if p["id"] == pid), None)
    if not prof:
        raise ValueError("Profile not found.")
    since = (date.today() - timedelta(days=days)).isoformat()
    with _db() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT day, kcal_in, steps, gym, healthy, weight FROM logs WHERE profile_id=? AND day>=? ORDER BY day",
            (pid, since))]
    log = [day_result(prof, r) for r in rows]
    return {"log": log, "streaks": streaks(prof, log), "quote": quote()}


def streaks(prof: dict, log: list[dict]) -> dict:
    plan = prof.get("plan") or {}
    kcal = (plan.get("targets") or {}).get("kcal") or 99999
    steps = (plan.get("tier") or {}).get("steps") or 8000
    by_day = {r["day"]: r for r in log}

    def run(ok) -> int:
        n, d = 0, date.today()
        if d.isoformat() not in by_day:          # today not logged yet doesn't break a streak
            d -= timedelta(days=1)
        while d.isoformat() in by_day and ok(by_day[d.isoformat()]):
            n += 1
            d -= timedelta(days=1)
        return n

    # Gym streak counts weeks with at least 2 sessions
    weeks, wk = 0, date.today() - timedelta(days=date.today().weekday())
    while True:
        days = [(wk + timedelta(days=i)).isoformat() for i in range(7)]
        sessions = sum(by_day.get(x, {}).get("gym", 0) for x in days)
        if sessions >= 2:
            weeks += 1
        elif wk != date.today() - timedelta(days=date.today().weekday()):
            break                                  # the current week may still be in progress
        wk -= timedelta(days=7)
        if wk < date.today() - timedelta(days=400):
            break

    s = {"walking": run(lambda r: r["steps"] >= steps), "healthy": run(lambda r: r["healthy"]),
         "budget": run(lambda r: r["kcal_in"] <= kcal), "gym_weeks": weeks}
    xp = 10 * len(log) + 5 * (s["walking"] + s["healthy"] + s["budget"]) + 20 * weeks
    lvl = min(len(LEVELS) - 1, xp // 150)
    return {**s, "xp": xp, "level": lvl + 1, "title": LEVELS[lvl], "next_at": (lvl + 1) * 150}
