/* Local illustrations — drawn in code, never by an LLM.
   bodySVG(): cartoon body morphed by body-fat % and muscle %.
   poseSVG(): animated stick-figure exercise diagrams (two key poses, looped).
   foodEmoji(): icon for a meal name. */
const Art = (() => {
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  function bodySVG(sex, fat, muscle) {
    const fem = sex === "female";
    const f = clamp((fat - (fem ? 25 : 15)) / 30, -0.35, 1.2);      // 0 = average, 1 = obese
    const m = clamp((muscle - (fem ? 31 : 40)) / 12, -0.8, 1.2);    // 0 = normal muscle
    const sh = (fem ? 31 : 37) + 8 * m + 4 * f, ch = (fem ? 27 : 30) + 5 * m + 7 * f;
    const w = (fem ? 19 : 22) + 18 * f + 2 * m, hp = (fem ? 33 : 28) + 12 * f;
    const th = 14 + 7 * f + 3 * m, cf = 9 + 2.5 * f + 2 * m, ua = 9 + 4 * f + 4 * m, fa = 7 + 1.5 * f + 2.5 * m;
    const nk = 9 + 2 * m + 2 * f, skin = "#d9a066", line = "#3a2414";
    const lx = Math.max(th, hp * .5 + 2), kx = Math.max(16, th * .8);
    const leg = (s) => `<path d="M${100 + s * lx},214 L${100 + s * kx},300" stroke="${line}" stroke-width="${th * 2 + 3}" stroke-linecap="round"/>
      <path d="M${100 + s * kx},300 L${100 + s * (kx - 1)},372" stroke="${line}" stroke-width="${cf * 2 + 3}" stroke-linecap="round"/>
      <path d="M${100 + s * lx},214 L${100 + s * kx},300" stroke="${skin}" stroke-width="${th * 2}" stroke-linecap="round"/>
      <path d="M${100 + s * kx},300 L${100 + s * (kx - 1)},372" stroke="${skin}" stroke-width="${cf * 2}" stroke-linecap="round"/>
      <ellipse cx="${100 + s * (kx + 3)}" cy="381" rx="14" ry="6" fill="${line}" opacity=".85"/>`;
    const ax = sh - ua * .5, ex = Math.max(sh + 2, w + ua + 2);      // elbows clear the waist
    const arm = (s) => `<path d="M${100 + s * ax},98 L${100 + s * ex},166" stroke="${line}" stroke-width="${ua * 2 + 3}" stroke-linecap="round"/>
      <path d="M${100 + s * ex},166 L${100 + s * (ex + 2)},226" stroke="${line}" stroke-width="${fa * 2 + 3}" stroke-linecap="round"/>
      <path d="M${100 + s * ax},98 L${100 + s * ex},166" stroke="${skin}" stroke-width="${ua * 2}" stroke-linecap="round"/>
      <path d="M${100 + s * ex},166 L${100 + s * (ex + 2)},226" stroke="${skin}" stroke-width="${fa * 2}" stroke-linecap="round"/>`;
    const side = (s) => `${100 + s * sh},92 L${100 + s * ch},120 Q${100 + s * (w + 3)},150 ${100 + s * w},178 Q${100 + s * (hp + 2)},196 ${100 + s * hp},214`;
    const torso = `M${100 - nk},74 Q${100 - sh + 6},78 ${side(-1)} L100,232 L${100 + hp},214 Q${100 + hp + 2},196 ${100 + w},178 Q${100 + w + 3},150 ${100 + ch},120 L${100 + sh},92 Q${100 + sh - 6},78 ${100 + nk},74 Z`;
    const abDef = clamp(((fem ? 22 : 15) - fat) / 6, 0, 1);         // visible abs only when lean
    let abs = "";
    if (abDef > 0) for (let i = 0; i < 3; i++)
      abs += `<path d="M90,${142 + i * 15} q10,3 20,0" stroke="${line}" stroke-width="1.6" fill="none" opacity="${abDef}"/>`;
    if (abDef > 0) abs += `<path d="M100,132 V188" stroke="${line}" stroke-width="1.4" opacity="${abDef}"/>`;
    const pecs = m > 0.15 || !fem ? `<path d="M${100 - ch + 6},118 q${ch - 6},${12 + 6 * m} ${ch - 6},0 M${100 + ch - 6},118 q-${ch - 6},${12 + 6 * m} -${ch - 6},0" stroke="${line}" stroke-width="1.5" fill="none" opacity="${fem ? .35 : .5}"/>` : "";
    const belly = f > 0.2 ? `<path d="M${100 - w + 6},${170 - 6 * f} Q100,${196 + 18 * f} ${100 + w - 6},${170 - 6 * f}" stroke="${line}" stroke-width="1.4" fill="none" opacity="${Math.min(.6, f)}"/>` : "";
    const top = fem ? `<path d="M${100 - ch + 2},108 Q100,${128 + 4 * f} ${100 + ch - 2},108 L${100 + ch - 4},134 Q100,${144 + 4 * f} ${100 - ch + 4},134 Z" fill="var(--accent2)"/>` : "";
    const hair = fem ? `<path d="M76,44 Q78,14 100,16 Q124,14 124,44 Q128,78 120,86 L118,50 Q100,36 82,50 L80,86 Q72,78 76,44Z" fill="#1d120b"/>`
                     : `<path d="M79,40 Q80,18 100,18 Q121,18 121,40 Q112,30 100,31 Q88,30 79,40Z" fill="#1d120b"/>`;
    return `<g stroke-linejoin="round">
      ${leg(-1)}${leg(1)}${arm(-1)}${arm(1)}
      <rect x="${100 - nk}" y="60" width="${nk * 2}" height="22" fill="${skin}"/>
      <path d="${torso}" fill="${skin}" stroke="${line}" stroke-width="1.5"/>
      ${belly}${pecs}${abs}${top}
      <path d="M${100 - hp - 1},206 L${100 + hp + 1},206 L${100 + hp + 3},252 L102,252 L100,236 L98,252 L${100 - hp - 3},252 Z" fill="var(--accent)" stroke="${line}" stroke-width="1.2"/>
      <circle cx="100" cy="44" r="23" fill="${skin}" stroke="${line}" stroke-width="1.5"/>
      ${hair}
      <circle cx="92" cy="45" r="2.3" fill="${line}"/><circle cx="108" cy="45" r="2.3" fill="${line}"/>
      <path d="M93,55 q7,5 14,0" stroke="${line}" stroke-width="1.8" fill="none" stroke-linecap="round"/>
    </g>`;
  }

  // Key poses: H S E W P K F [E2 W2 K2 F2] as flat x,y lists in a 100x100 box
  const POSES = {
    "ex-pushup": [[18,58,25,62,25,78,25,95,55,77,73,86,92,95], [18,79,25,82,35,80,25,95,55,88,73,91,92,95]],
    "ex-squat": [[50,12,50,24,58,34,56,26,50,52,52,73,50,95], [47,30,45,42,55,50,54,42,35,68,60,70,50,95], "db"],
    "ex-plank": [[18,72,25,76,25,95,38,95,55,82,73,88,92,95], [18,70,25,75,25,95,38,95,55,79,73,87,92,95]],
    "ex-leg-raise": [[12,86,20,89,32,93,42,94,50,91,70,91,90,91], [12,86,20,89,32,93,42,94,50,91,58,72,62,52]],
    "ex-lunge": [[50,12,50,24,50,40,50,54,50,52,52,73,50,95,50,40,50,54,48,73,50,95],
                 [50,26,50,38,50,52,50,66,50,64,66,72,66,95,50,52,50,66,38,90,26,95], "db"],
    "ex-db-row": [[22,44,30,48,36,62,36,76,66,50,62,72,70,95,28,58,26,68,56,68,76,68],
                  [22,44,30,48,46,44,40,58,66,50,62,72,70,95,28,58,26,68,56,68,76,68], "db bench"],
    "ex-bench-press": [[16,60,24,62,24,48,24,34,56,62,70,60,76,95], [16,60,24,62,14,58,24,50,56,62,70,60,76,95], "db bench"],
    "ex-shoulder-press": [[50,18,50,30,40,32,40,20,50,60,68,60,68,92], [50,18,50,30,44,16,48,2,50,60,68,60,68,92], "db seat"],
    "ex-curl": [[50,12,50,24,52,40,54,56,50,52,50,73,50,95], [50,12,50,24,52,40,46,28,50,52,50,73,50,95], "db"],
    "ex-pullup": [[50,22,50,30,43,18,45,6,50,58,50,75,50,92], [50,6,50,16,38,14,45,6,50,44,50,61,50,78], "bar"],
    "ex-db-rdl": [[50,12,50,24,51,38,52,52,50,52,51,73,50,95], [24,44,32,48,32,62,32,76,56,52,54,73,52,95], "db"],
    "walk-brisk": [[50,12,50,24,58,38,62,50,50,52,58,72,62,95,42,38,38,50,44,74,38,93],
                   [50,12,50,24,42,38,38,50,50,52,44,74,38,93,58,38,62,50,58,72,62,95]],
    "run-easy": [[54,12,53,24,62,34,70,30,50,52,64,64,60,84,42,36,40,48,44,74,30,82],
                 [54,12,53,24,42,36,40,48,50,52,44,74,30,82,62,34,70,30,64,64,60,84]],
  };
  const full = (p) => p.length === 14 ? p.concat(p.slice(4, 8), p.slice(10, 14)) : p;
  const BONES = [[1, 2], [2, 3], [1, 4], [4, 5], [5, 6], [1, 7], [7, 8], [4, 9], [9, 10]];

  function poseSVG(id) {
    const def = POSES[id];
    if (!def) return `<svg viewBox="0 0 100 100"><text x="50" y="55" text-anchor="middle" font-size="30">🏋️</text></svg>`;
    const [a, b] = [full(def[0]), full(def[1])], props = def[2] || "";
    const pt = (arr, i) => [arr[i * 2], arr[i * 2 + 1]];
    const anim = (attr, i, k) => `<animate attributeName="${attr}" values="${pt(a, i)[k]};${pt(b, i)[k]};${pt(a, i)[k]}" dur="2.4s" repeatCount="indefinite" calcMode="spline" keySplines=".45 0 .55 1;.45 0 .55 1"/>`;
    let s = `<svg viewBox="0 0 100 100" role="img" aria-label="${id.replace(/^ex-/, "")} diagram"><line x1="4" y1="96.5" x2="96" y2="96.5" stroke="var(--muted)" stroke-width="1"/>`;
    if (props.includes("bench")) s += `<rect x="14" y="${id === "ex-bench-press" ? 65 : 70}" width="66" height="5" rx="2" fill="var(--muted)"/><rect x="20" y="70" width="3" height="26" fill="var(--muted)"/><rect x="70" y="70" width="3" height="26" fill="var(--muted)"/>`;
    if (props.includes("seat")) s += `<rect x="40" y="62" width="30" height="5" rx="2" fill="var(--muted)"/><rect x="40" y="30" width="5" height="34" rx="2" fill="var(--muted)"/>`;
    if (props.includes("bar")) s += `<line x1="20" y1="6" x2="80" y2="6" stroke="var(--muted)" stroke-width="2.5"/>`;
    for (const [i, j] of BONES) s += `<line stroke="var(--accent)" stroke-width="4" stroke-linecap="round">${anim("x1", i, 0)}${anim("y1", i, 1)}${anim("x2", j, 0)}${anim("y2", j, 1)}</line>`;
    s += `<circle r="6" fill="var(--accent)">${anim("cx", 0, 0)}${anim("cy", 0, 1)}</circle>`;
    if (props.includes("db")) s += `<g><rect x="-6" y="-2" width="12" height="4" rx="1.5" fill="var(--accent2)"/><rect x="-7" y="-4" width="3" height="8" fill="var(--accent2)"/><rect x="4" y="-4" width="3" height="8" fill="var(--accent2)"/>
      <animateTransform attributeName="transform" type="translate" values="${pt(a, 3).join(" ")};${pt(b, 3).join(" ")};${pt(a, 3).join(" ")}" dur="2.4s" repeatCount="indefinite" calcMode="spline" keySplines=".45 0 .55 1;.45 0 .55 1"/></g>`;
    return s + "</svg>";
  }

  const FOOD = [["prawn", "🦐"], ["fish", "🐟"], ["salmon", "🐟"], ["tuna", "🐟"], ["chicken", "🍗"], ["mutton", "🍖"], ["beef", "🥩"],
    ["egg", "🥚"], ["omelette", "🍳"], ["paneer", "🧀"], ["cottage", "🧀"], ["cheese", "🧀"], ["tofu", "🍱"], ["soya", "🌱"],
    ["sprouts", "🌱"], ["chana", "🫘"], ["chole", "🫘"], ["rajma", "🫘"], ["bean", "🫘"], ["dal", "🍲"], ["lentil", "🍲"],
    ["khichdi", "🍲"], ["soup", "🍲"], ["shake", "🥤"], ["milk", "🥛"], ["curd", "🥣"], ["raita", "🥣"], ["oat", "🥣"],
    ["peanut", "🥜"], ["almond", "🥜"], ["banana", "🍌"], ["apple", "🍎"], ["fruit", "🍎"], ["rice", "🍚"], ["pulao", "🍚"],
    ["roti", "🫓"], ["paratha", "🫓"], ["chilla", "🥞"], ["idli", "🍘"], ["poha", "🍚"], ["toast", "🍞"], ["sandwich", "🥪"],
    ["wrap", "🌯"], ["burrito", "🌯"], ["roll", "🌯"], ["quesadilla", "🌮"], ["chili", "🌶️"], ["salad", "🥗"], ["burger", "🍔"],
    ["pizza", "🍕"], ["chikki", "🍬"], ["date", "🌴"]];
  const foodEmoji = (name) => (FOOD.find(([k]) => name.toLowerCase().includes(k)) || [0, "🍽️"])[1];

  return { bodySVG, poseSVG, foodEmoji };
})();
