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
- `pyscript_cassini.json` — config for the `cass` env: numpy, matplotlib,
  spiceypy, plus kernel files fetched from the AndrewAnnex/spiceypylessonkernels
  GitHub repo into the browser FS (copied from the docs' cassini example config).
- `mini-coi.js` — COI service-worker shim, copied from `../SpiceyPy/docs/`.

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
- Known-good outputs to assert, in slide order: `hello`; `CSPICE_N0067`;
  Cassini env: `SpiceyPy for CSPICE_N0067 ready!`, `Loaded 8 kernels`,
  `ET One: 140961664.18440723, ET Two: 186667264.18308285`,
  `[140961664.18440723, ...`, first position
  `[-5461446.61080924 -4434793.40785864 -1200385.93315424]`, and an `<img>`
  appearing in `#mpl`. Full pipeline (cold caches) takes ~3–5 min headless.
