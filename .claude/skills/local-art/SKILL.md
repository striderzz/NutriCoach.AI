---
name: local-art
description: Make or change NutriCoach.AI images locally, never with an LLM or image API. Use when adding exercise/food diagrams, editing the body illustrator, or producing raster art (hero image, GitHub preview banner, icons) with the gimp MCP.
---

# Local art for NutriCoach.AI

The app never generates images with a model. Two pipelines:

## 1. Runtime art: code in `static/js/art.js` (no files, no LLM)

- **Body illustrator** `Art.bodySVG(sex, fatPct, musclePct)`: a 200x400 front-view
  cartoon. Widths come from two normalised values:
  `f = (fat - base_fat) / 30` (base 15% men, 25% women) and
  `m = (muscle - base_muscle) / 12` (base 40% men, 31% women: normal muscle mass,
  the default for every new user). Shoulders/arms follow `m`, waist/hips/thighs
  follow `f`, abs appear only under 15% (men) / 22% (women) body fat.
  The starting and goal numbers come from `planner.body()`.
- **Exercise diagrams** `Art.poseSVG(id)`: a stick figure animated between two
  key poses. Add a move by adding `POSES["ex-<move>"] = [poseA, poseB, props]`.
  Each pose is a flat list of x,y points in a 100x100 box, in the order
  `H S E W P K F` (head, shoulder, elbow, wrist, hip, knee, foot), optionally
  followed by `E2 W2 K2 F2` for the second arm and leg. `props` can contain `db`
  (a dumbbell at the wrist), `bench`, `seat` or `bar`. Ground is y=96.
  Then reference the id from `planner.EX` (4th field).
- **Food icons** `Art.foodEmoji(name)`: keyword → emoji table, first match wins.
- Colours always use theme variables (`var(--accent)`, `var(--accent2)`,
  `var(--muted)`), so art follows all four themes.

## 2. Raster art: GIMP via the gimp MCP (build time only)

GIMP must be open with **Tools > Start MCP Server**. Check with
`mcp__gimp__check_server` first.

| Asset | Size | Path |
|---|---|---|
| Hero illustration | 512x512, transparent | `static/art/hero.png` |
| GitHub preview banner | 1280x640 | `docs/preview.png` |
| App icon | from `make_icon.py` | `static/icon.png`, `static/icon.ico` |

Palette (hacker theme, used for shared art): background `#050b07`, surface
`#0b1610`, accent `#00ff9c`, accent 2 `#00c8ff`, text `#c8ffe0`.
Neon alternative: `#0b0414`, `#ff2bd6`, `#a855f7`.

Recipe for the preview banner:
1. `new_canvas(1280, 640, fill="#050b07")`, then `gradient_fill` from `#0b1610` to `#050b07`.
2. Open the screenshots from `docs/screenshots/` (`open_image`), `scale_to_fit`, and copy them in as layers, with `apply_drop_shadow` in the accent colour.
3. `add_text` with the title "NutriCoach.AI" (Poppins, about 72 px, `#00ff9c`) and the tagline (Carlito, about 30 px, `#c8ffe0`).
4. Export the result to `docs/preview.png` with `export_image`. Keep it under 1 MB.

Rules: keep PNGs at 512 px or smaller unless they are banners, name files in kebab-case, and commit the
exported PNGs (never `.xcf` working files).

## Screenshots without GIMP

Headless Edge renders the running app at any size:

```
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --headless=new --disable-gpu --hide-scrollbars --window-size=1440,900 --screenshot=docs\screenshots\desktop.png http://localhost:5000/
```
