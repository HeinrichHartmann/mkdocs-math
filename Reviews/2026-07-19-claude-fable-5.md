# Code Review — mkdocs-math (full plugin)

Date: 2026-07-19. Reviewer: Claude (claude-fable-5). Scope: whole plugin
(`plugin.py`, `elements.py`, `lint.py`, `environment_regex.py`, templates),
checked against the ADRs in `math/adr/` (elements-theory-tree,
mkdocs-math-elements-support, content-layers, elements-validation).

Working-tree state at review time: uncommitted sidebar work
(`templates/partials/toc.html`, `self._files` + dest-path URL computation,
`on_env` ChoiceLoader).

## Bugs

1. **Preamble cache never invalidated during `mkdocs serve`**
   (plugin.py:411-414). The comment claims `on_startup` resets the cache
   per build, but MkDocs calls `on_startup` once per *process*. Editing
   `preamble.tex` while serving keeps the stale preamble. Fix: reset in
   `on_config`. Also make `_preamble_cache` an instance attribute instead
   of a module global.

2. **Three inconsistent URL builders, two of them wrong.**
   - `_element_link` / `_autolink_element_ids` (plugin.py:874-877,
     984-993): relpath over `src_path` (`.md` links). Correct — MkDocs
     rewrites internal `.md` links.
   - Sidebar (plugin.py:717-723): relpath over `dest_path` *directories* —
     breaks with `use_directory_urls: false` (links the folder, not the
     `.html` file) and emits no trailing slash, forcing a redirect per
     click.
   - `registry_to_json` (elements.py:129-132): strip-`.md`-add-slash —
     same `use_directory_urls` bug, plus unencoded spaces in `index.json`
     URLs. The ADR calls `elements/index.json` the machine interface for
     external tooling, so these URLs must be right.

   Fix: consolidate on `File.url` + `mkdocs.utils.get_relative_url`.

3. **Cross-page anchor references broken by construction.**
   `_resolve_anchor_references` (plugin.py:1125) always emits a same-page
   fragment `(#target_id)`, but the anchor registry is global and cached
   across builds — so `[#id]` on page A referencing an anchor on page B
   "resolves" to a dead fragment. Store the source page in the registry
   and emit cross-page links, or scope resolution per page.

4. **`.cache/` anchored to CWD** (plugin.py:402, 405), not the config
   dir. `mkdocs build -f path/to/mkdocs.yml` from elsewhere litters the
   invoking directory and misses the warm cache.

5. **Duplicate-ID error is a raw `RuntimeError`** (elements.py:116). ADR
   says build error — right intent; raise
   `mkdocs.exceptions.PluginError` for a clean message instead of a
   traceback.

6. **`_extract_outline_from_content` drops formatted headings**
   (plugin.py:772): the `([^<]+)` group cannot match headings containing
   `<code>`, links, or MathJax spans — they silently vanish from the
   article outline.

## ADR alignment

- Registry, `index.json`, backlinks, autolinking, notation chain,
  `elements_dir` config: all present and match the mkdocs-math ADR.
- **Lint has no error/warn distinction.** The ADR assigns severities to
  every E-* check; `lint.py` flattens everything into warnings with one
  exit code. CI cannot tell `E-REF-RESOLVE` (error) from
  `E-ID-FILENAME` (warn).
- **`E-ID-UNIQUE` in `lint_elements_node` is dead logic**
  (lint.py:241-244): registry keys are unique by construction;
  duplicates already abort with `FATAL` at registry build
  (lint.py:399-401). The check only fires when the file isn't under the
  detected elements dir, where the "duplicate or conflict" message is
  wrong. The FATAL abort also suppresses all other lint output on a
  single duplicate — consider reporting and continuing.
- **ADR is stale vs. code**: the mkdocs-math ADR documents
  `checked: [numeric, adversarial, lean]`; code (post-b5010ab) has
  `validation:` with types `{numeric, symbolic, ai, human, formal}` and
  deprecates `checked:`. Update the ADR.
- Autolink code/math skipping is line-heuristic (``` toggling,
  `$`-parity per line, plugin.py:995-1067): misses indented code
  blocks, `~~~` fences, multi-line `$...$`. Acceptable for now, but this
  is the most fragile code in the plugin and has one happy-path test.
- Mild tension: the Elements sidebar lists *all* nodes on every
  Elements page vs. theory-tree ADR §4 "No global index." Defensible as
  generated navigation (backlinks addendum: "navigation, not an
  index"), but it becomes a de-facto index as the tree grows.

## Structure & duplication

- **plugin.py is five plugins in one file** (1341 lines): theorem
  environments, outline, preamble, citations, article listing,
  Elements. Elements is well-factored into `elements.py`; do the same
  for the rest. Imports (`re`, `yaml`, `os`, `jinja2`) scattered inside
  functions.
- **Three frontmatter parsers**: `lint.parse_frontmatter`,
  `elements.parse_node_frontmatter`, inline in
  `_generate_article_listing` (plugin.py:514-524).
- **Three slugify variants**: `convert_theorem_environments.slugify`,
  `make_id`'s label slug, outline anchor generation
  (plugin.py:260-263). The outline one must mirror Python-Markdown's
  `toc` slugify or anchors drift on punctuation.
- **`pcre2` dependency unjustified** (environment_regex.py:10): header
  claims recursive matching, but `LABEL_PATTERN` is one fixed nesting
  level — stdlib `re` handles it. Native build dep for nothing.
- **Stale class docstring** (plugin.py:376-380) documents
  `proofs`/`environments`/`preamble` options not in `config_scheme`;
  `on_config` logs `self.config.get('proofs')` — always `None`.

## Template/CSS mixing between plugin and site repo

- `templates/partials/toc.html` is byte-identical to
  `math/overrides/partials/toc.html` — two sources of truth. Pick one
  home (plugin, per "mkdocs-math is the primary rendering frontend"),
  delete the other in the same change.
- `theme.dirs.insert(0, …)` (plugin.py:424) puts plugin templates
  *ahead of* the site's `custom_dir`, so site overrides can never win.
  Insert after `custom_dir`.
- The `on_env` ChoiceLoader duplicates the `theme.dirs` registration —
  remove it.
- Kind-badge palette lives in three places: toc.html inline `<style>`,
  math repo `extra.css:105-112`, class names emitted at plugin.py:906.
  `_render_elements_header`'s docstring says "CSS lives with the
  consuming site" while toc.html ships CSS — contradictory policy.
  Recommendation: ship one plugin CSS asset defining the palette as CSS
  custom properties; site `extra.css` re-themes variables only. Plugin
  owns semantic markup + default presentation as overridable assets;
  site owns theming.
- Inline `<style>` in the partial is re-emitted in every Elements page
  body — bloats pages, defeats caching.

## ADR coverage

All ADRs live in the math repo (`adr/`); this repo has none. Coverage
by plugin feature:

- Covered: Elements (schema, registry, index.json, autolink, backlinks,
  notation chain, E-* lint) — mkdocs-math-elements-support; validation
  badges — elements-validation; Elements semantics — elements-theory-tree;
  layer context — content-layers.
- Not covered (README-only or undocumented): theorem environments,
  preamble injection, citation pipeline, article layout/listing (despite
  active churn), cross-references `[#id]`, article lint codes
  (F/E/C/M/L/R), LaTeX/PDF export, and the **Elements sidebar**
  (current uncommitted work — visual design is explicitly out of scope
  in the elements-support ADR; nothing specifies the TOC replacement or
  template-override policy).

Recommendation: give mkdocs-math its own `adr/` for plugin-internal
decisions (template precedence, CSS ownership, cache strategy, parser
deps), and write a short sidebar ADR that also settles template/CSS
ownership between the two repos.

## Tests

Covered: registry, lint E-* checks, environments, preamble, outline,
LaTeX export, Elements build integration.

Missing:
- `build_nav_sections` (zero tests); sidebar rendering and URL
  correctness.
- `use_directory_urls: false` build (would catch bug 2).
- Template override precedence (site `custom_dir` beats plugin).
- Cross-page `[#id]` behavior (would catch bug 3).
- Serve-mode preamble invalidation (bug 1).
- Citation transform chain (`_preprocess_citation_tags` →
  `_link_citation_tags_to_references`) has no direct tests.

## Nits

- `<a class="el-check">` without `href` (plugin.py:925) — use `<span>`.
- `node['url'] = '#'` silent fallback in sidebar — log a warning.
- `markdown.replace(bib_command, …)` (plugin.py:1313) would rewrite a
  literal `\bibliography` inside a code sample.
- `self._files` not initialized in `__init__`.

## Suggested priority

1. Preamble serve invalidation (bug 1)
2. URL consolidation on `File.url` (bug 2, incl. `index.json`)
3. Template precedence + dedupe toc.html / CSS ownership
4. Lint severities (error vs. warn) + dead `E-ID-UNIQUE` check
5. Structural dedup (frontmatter parsers, slugify, drop `pcre2`)
