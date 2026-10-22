## TypeScript / web navigation (webnav)
JavaScript, TypeScript, HTML and CSS code is handled with the `webnav` tools, not with grep or `sed`. Their schemas
are already loaded; call them directly.
- To find the definition, usages, callers or implementations of a JS/TS symbol, use `symbol_info`, `references`,
  `callers`, `implementations`, `search_symbol` or `outline`. For CSS custom properties and selectors across HTML and
  CSS, use `css_var` and `selector`. Do not grep for them.
- To rename or move a symbol (or a CSS custom property, id or class) or a file, use `rename_symbol` or `move`. Never
  rename with `sed` or by editing each call site by hand.
- Prefer `edit_symbol` / `edit` for edits: they type-check before writing. If a write tool returns a preview, apply it
  with `apply_edit`; undo with `undo_edit`. Use `quick_fix` for language-server fixes.
- Before reporting, run `diagnostics` (or `verify_changes`) on what you touched.
- `webnav` checks with its own TypeScript 7 unless the project has version 7 or later, which no longer loads
  `@types/*` unless `compilerOptions.types` lists them. If `diagnostics` reports missing-types errors (e.g. TS2591 for
  `node:` imports) that the project's own `tsc` doesn't, trust `tsc` and mention it under Friction.
- Grep and `sed` are for files `webnav` doesn't cover and for text that is not a symbol (strings, docs, config). If
  you used them on a symbol anyway, say why under Deviations.
- If a webnav tool errors or is unavailable, say so under Friction, then fall back to grep and your own edits.
