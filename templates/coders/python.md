## Python navigation (codenav)
Python symbols are handled with the `codenav` tools, not with grep or `sed`. Their schemas are already loaded; call
them directly.
- To find the definition, usages, callers or implementations of a Python symbol, use `symbol_info`, `references`,
  `callers`, `implementations`, `search_symbol` or `outline`. Do not grep for them.
- To rename, move or change the signature of a Python symbol, use `rename_symbol`, `move` or `change_signature`. Never
  rename with `sed` or by editing each call site by hand.
- Prefer `edit_symbol` / `edit` for Python edits: they type-check before writing. If a write tool returns a preview,
  apply it with `apply_edit`; undo with `undo_edit`.
- Before reporting, run `diagnostics` (or `verify_changes`) on what you touched.
- Grep and `sed` are for non-Python files and for text that is not a symbol (strings, docs, config). If you used them
  on a Python symbol anyway, say why under Deviations.
- If a codenav tool errors or is unavailable, say so under Friction, then fall back to grep and your own edits.
