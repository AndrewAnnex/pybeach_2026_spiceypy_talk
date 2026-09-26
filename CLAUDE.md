# pybeach 2026 SpiceyPy talk

Single-file reveal.js slide deck (`index.html`) with live,
runnable SpiceyPy demos via PyScript/pyodide. Slides are authored as pure
markdown inside the one `data-markdown` textarea; ```python fences are
auto-promoted to interactive PyScript editors at load time by a custom inline
reveal plugin (`PyScriptPromote`). This mirrors the setup in the SpiceyPy docs
(`../SpiceyPy/docs/pyodide.rst`, `exampleone.rst`, and the `pyscript_editor.py`
Sphinx extension) — consult those when adding examples.

## Running it

- Must be served over HTTP, never opened as `file://`: `python3 -m http.server`
  in this folder. `mini-coi.js` is a service-worker shim that fakes the
  cross-origin-isolation headers PyScript's worker needs; expect one automatic
  page reload on first visit while it installs.
- First click of Run in each env downloads pyodide + packages (the `cass` env
  also fetches matplotlib and 8 subset SPICE kernels) — on the order of a
  minute. When presenting, start the Cassini "Setup" cell early; navigation
  isn't blocked while a cell runs.
- Editors sharing an env share one interpreter, so state (imports, `times`,
  `positions`) carries across slides — cells must be run in slide order.

## Deployment

`.github/workflows/deploy.yml` publishes the whole folder to GitHub Pages on
every push to `main` (official actions/deploy-pages flow, no build step). The
repo's Pages settings must have "GitHub Actions" selected as the source once;
the live URL is then shown in the workflow run's deploy step. The deck is
`index.html`, so the repo's root Pages URL serves it directly. Pages must be
served over HTTPS (the default) — mini-coi's service worker needs a secure
context, so the live cells break on plain http.

## Files

- `pyscript.json` — config for the default `demo` env (just spiceypy, from PyPI;
  needs spiceypy >= 8.1.2 for the pyodide wheel).
- `pyscript_replay.json` — config for the `replay` env (numpy + spiceypy, the `cassini_flyby`
  kernel bundle, and `py/spice_replay.py`). Unlike the other configs its URLs are **relative**
  (`./kernels/...`), not raw.githubusercontent: same-origin means it works locally before anything is
  pushed, and sidesteps the COEP traps below. Prefer this style for new demos.
- `pyscript_cassini.json` — config for the `cass` env: numpy, matplotlib,
  spiceypy, plus kernel files fetched from the AndrewAnnex/spiceypylessonkernels
  GitHub repo into the browser FS (copied from the docs' cassini example config).
- `mini-coi.js` — COI service-worker shim, originally copied from `../SpiceyPy/docs/`
  but PATCHED (don't overwrite it with the docs copy): COEP is `credentialless`
  instead of `require-corp`, and the worker skips cross-origin `no-cors` requests.
  Without the patch, Leaflet map tiles (folium slide) fail with `net::ERR_FAILED`:
  the worker's re-fetch returns an opaque response that never loads, while the
  same tile works as a plain `<img>`. Tradeoff: Safari lacks `credentialless`, so
  the deck may not be cross-origin isolated there — present from Chrome/Firefox.
- Folium basemap (`M20_HiRISE_RGB_CTX_mosaic_25cm_v7_Merge_LERC_clip`, MMGIS) is a
  web-mercator **TMS** tileset (rows count from the bottom; see its
  `tilemapresource.xml`), zoom 8–19: needs `tms=True`, default CRS (no
  `crs='EPSG4326'`), `max_native_zoom=19`. Wrong scheme = 403s. The `map-slide`
  class gives equal `minmax(0, 1fr)` columns and stretches the folium iframe to the
  editor's height (plain `1fr` lets long code lines widen the editor column).

## The 3D replay demo (`#replay-demo` .. the `.replay-slide`)

Four PyScript cells build a telemetry payload with spiceypy and hand it to a three.js viewer; the
fifth slide is the viewer. Built from `../spice_replay` (see its README); the pieces here are copies.

- **Assets are all same-origin, committed here** (~5 MB): `kernels/cassini_flyby/` (1.8 MB, sliced
  from 505 MB of archive by `../kernel_minifier`, `kmin all demos/cassini_flyby.toml`),
  `py/spice_replay.py` (a **vendored copy** — re-copy it if the upstream module changes),
  `js/spice-replay.min.js` (the esbuild IIFE, defines `window.SpiceReplay`), and `assets/`
  (Cassini glTF, Saturn USDZ, Enceladus mosaic). Cross-origin would have to satisfy both CORS and
  COEP; same-origin satisfies neither requirement by construction.
- The ISS NAC frames themselves ARE cross-origin (OPUS previews) and work, because OPUS sends
  `Access-Control-Allow-Origin: *` and the viewer's TextureLoader sets `crossOrigin="anonymous"`.
- **`window.showReplay(json)`** in the html is the single call the Python makes. Every viewer option
  lives there so the slide stays one line. It is called **from the worker** through pyscript's
  `window` proxy, which needs SharedArrayBuffer -> cross-origin isolation -> mini-coi. If mini-coi
  fails to register, the symptom is `Unable to use 'window' or 'document' in worker. This requires
  SharedArrayBuffer support` and the cell dies at the last line, having done all the SPICE work.
- **Do not reuse the id `replay`**: the slide is `#replay-demo`, the viewer div is `#replay`. They
  were both `replay` at first and `getElementById` returned the section, so the viewer mounted into
  the slide.
- The viewer is created while its slide is off-screen, where the div is 0x0 and `resize()` bails.
  `Reveal.on('slidechanged', ...)` calls `__replay.resize()` so the canvas sizes on arrival.
- **`pixelRatio`**: reveal CSS-scales the slide, so the viewer is given
  `devicePixelRatio * Reveal.getScale()`. Without it the canvas renders at the unscaled size and is
  upscaled — invisible on a laptop, soft on a projector.
- Clicking a viewer control puts focus inside it, and the viewer stops keydown propagation to protect
  its own controls, so the deck's smart spacebar goes quiet until you click off it.
- The viewer's size dropdown reports how oversized the spacecraft is drawn: it reads `fit ×76k` at
  17,000 km. Worth saying out loud — the default 90 px model reads as a third the size of Enceladus,
  when the true ratio is 1:75,000. Picking `1:1` makes it honestly invisible (0.001 px at 15,000 km).
- Target view puts the camera 8 body-radii along the spacecraft's direction, so for most of the flyby
  the spacecraft is BEHIND the camera and no size setting makes it appear; orbit round to see it.
- Cell 4 prints the builder's own progress line (`168 state samples, attitude 3648 -> 729`) because
  `spice_replay` logs to stderr; that is the attitude thinning, and it is worth showing.

## How the deck works (all inline in the html)

- **Plugin order matters**: `PyScriptPromote` is registered between
  `RevealMarkdown` and `RevealHighlight`. Reveal awaits each plugin's init in
  order, so promotion sees rendered markdown but runs before highlight.js
  claims the blocks.
- Reveal's markdown renderer emits `<code class="python">`, NOT marked's
  default `language-python` — the promote selector accepts both.
- Fence annotations via reveal comments on the line after the closing fence:
  `<!-- .element: data-env="name" data-config="./file.json" -->`. The first
  editor of each env (DOM order) gets the `config=` attribute; config defaults
  to `./pyscript.json`. Opt a fence out of promotion with
  `<!-- .element: class="static" -->` or by using `[1-2]` line-number
  annotations (those stay static highlighted code).
- Raw HTML blocks in the markdown (e.g. `<div id="mpl"></div>`) pass through
  marked untouched — but a blank line inside an HTML block ends it, so never
  put blank lines inside one. Keep every template line at the common
  indentation; reveal dedents on the first line's indent before parsing.
- **Editor theming**: CodeMirror lives in a shadow root page CSS can't reach.
  A MutationObserver injects a monokai stylesheet (matching reveal's
  `monokai.css`) into each editor's shadow root, and hides `.cm-gutters`
  (line numbers) there. The `.ͼx` token classes are CodeMirror-generated names,
  stable only for the pinned PyScript release (currently 2026.7.3):
  `ͼb` keywords, `ͼe`/`ͼf` strings, `ͼd` numbers, `ͼc` True/False,
  `ͼm` comments, `ͼg`/`ͼj` def/class names. If the pyscript.net version in
  `<head>` is bumped, re-derive this mapping (render a token-rich sample and
  inspect the span classes) — wrong mappings fail silently.
- The editor theme tracks reveal's HIGHLIGHT theme (`plugin/highlight/monokai.css`),
  not the slide theme — swapping `theme/*.css` needs no editor changes. If the
  highlight stylesheet itself is swapped, update only the color VALUES (never
  the selectors) in two places: the `.pyscript-demo py-editor` rule and
  `EDITOR_THEME_CSS`, mapping the new theme's `.hljs-keyword/string/comment/...`
  colors onto the corresponding `ͼx` slots.
- The `<meta charset="utf-8">` is REQUIRED: without it browsers fall back to
  windows-1252 and the `ͼ` selectors get mangled into `Í¼` while the runtime
  class names stay correct — token colors silently revert to defaults. Also
  beware the lookalike codepoint: the real class prefix is U+037C `ͼ`, not
  U+03FC `ϼ`.
- The observer also calls `deck.layout()` whenever an image lands in a slide:
  reveal vertically centers slides before plot output exists, so matplotlib
  images would otherwise push content off the bottom.
- **`side-by-side` slide class** (set with `<!-- .slide: class="side-by-side" -->`
  as the slide's first line): CSS grid, heading spans both columns, code left,
  output div right. The `display: grid !important` is scoped to
  `section.present.side-by-side` on purpose — reveal manages slide visibility
  partly via inline display styles; scoping to `.present` avoids fighting it.
  Reusable for any code+output slide; give the output div an id and add an
  `#id img` sizing rule.
- **Images**: a plain markdown `![](https://…)` for a CROSS-ORIGIN image fails
  silently (blank slide, `net::ERR_FAILED` in console). mini-coi enables
  COEP `require-corp`; a plain `<img>` is fetched no-cors, so the service worker
  receives an opaque response it cannot attach `Cross-Origin-Resource-Policy`
  to, and the browser blocks it. Fixes: raw
  `<img crossorigin="anonymous" src="…">` (needs the host to send
  `access-control-allow-origin`, as readthedocs does), or commit the file to
  the repo and use a relative path — same-origin, no CORS, works offline, and
  the safer choice for presenting. Local images can use plain `![]()`.
  Reveal's default `section img` frame (4px border + background) is overridden
  by the `.reveal .side-by-side img` rule.
- **Run feedback**: the promote plugin watches each run button's `.running` class
  (PyScript sets it for the whole run) to pulse the editor and show a live timer
  in a `.cell-status` line, then `✓ ran in X` / `✗ failed after X` (traceback in
  output). First run per env is labeled as including Python startup.
  Line-by-line highlighting was considered: feasible via `sys.monitoring`
  (pyodide is Python 3.14, cell code runs as `<exec>` with editor-matching line
  numbers), but installing it needs a PyScript `setup` cell, and setup cells boot
  their env EAGERLY at page load — declined for now. A lazy install via the
  editor element's API was not investigated.
- **Smart spacebar**: custom `keyboard: {32: ...}` binding — space runs the
  first unrun editor on the current slide, else advances; shift+space goes
  back; arrows always just navigate. "Run" is tracked via a `data-ran` marker
  set by a capture-phase click listener on `.py-editor-run-button`, so
  mouse-run cells count too. Space never re-runs a cell (use the mouse to
  re-run after live edits). A running cell doesn't block advancing.
- PyScript discovers the injected `<script type="py-editor">` tags via its own
  MutationObserver — scripts added post-load work fine (browsers never execute
  custom-type scripts natively, so innerHTML/createElement injection is safe).
- Plot cells use `matplotlib.use("AGG")` + `from pyscript import display` +
  `display(fig, target="mpl", append=False)` into a `<div id="mpl">` on the
  slide (same pattern as the docs).

## Verifying changes

A headless test harness was built in a past session (scratchpad, not kept):
Playwright + chromium (`npm i playwright && npx playwright install chromium`;
this machine already has the chromium system libs apt-installed), a tiny node
http server for this folder, then drive the deck. Gotchas learned:

- `page.keyboard.press` doesn't reach reveal in headless — navigate with
  `page.evaluate(() => Reveal.slide(n))` and test the space binding by
  dispatching `new KeyboardEvent('keydown', {keyCode: 32, ...})` on `document`.
- Editors mount as light-DOM `.py-editor-box` (queryable from the page); the
  run button is `.py-editor-run-button`, visible only on hover/focus
  (opacity 0 otherwise) — hover the box first, or just `.click()` it.
- Verify styling by reading computed styles inside the shadow root, not by
  eyeballing CSS — both historical bugs here (charset, lookalike codepoint)
  were invisible in source.
- Replay slides: `node ../spice_replay/web/test/deck.mjs <outdir>` drives all four cells and asserts
  the viewer loaded (set `DECK=` to point at another checkout). Known-good: `12 kernels, 46 ISS NAC
  frames`; `position km [-27780.8170017 -17741.74801824 1919.3393481]`; `RECTANGLE FOV in
  CASSINI_ISS_NAC, boresight [0. 0. 1.]`; `94 kB of telemetry loaded`; then `window.__replay.payload`
  set and a canvas in `#replay`. About 12 s of cell time once the env is warm.
  NOTE: PyScript upgrades a promoted `<script type="py-editor">` asynchronously — poll for
  `.py-editor-box` before clicking Run, or the first cell looks like it has no editor.
- Known-good outputs to assert, in slide order: `hello`; `CSPICE_N0067`;
  Cassini env: `SpiceyPy for CSPICE_N0067 ready!`, `Loaded 8 kernels`,
  `ET One: 140961664.18440723, ET Two: 186667264.18308285`,
  `[140961664.18440723, ...`, first position
  `[-5461446.61080924 -4434793.40785864 -1200385.93315424]`, and an `<img>`
  appearing in `#mpl`. Full pipeline (cold caches) takes ~3–5 min headless.
