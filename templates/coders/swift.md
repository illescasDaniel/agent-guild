## Swift navigation (codenav-swift)
Swift (and Objective-C / C / C++) symbols are handled with the `codenav-swift` tools, not with grep or `sed`. Their
schemas are already loaded; call them directly.
- To find the definition, usages, callers, implementations or type of a symbol, use `symbol_info`, `references`,
  `callers`, `implementations`, `type_at`, `search_symbol` or `outline`. Do not grep for them.
- To rename, move, delete or change the signature of a symbol, use `rename_symbol`, `move_symbol`, `delete_symbol` or
  `change_signature`. Never rename with `sed` or by editing each call site by hand. Use `insert_member`,
  `add_conformance`, `edit_symbol` and `refactor` for the other structural edits, and `fix_diagnostics` for fixable
  compiler errors.
- Use `check_edit` to validate an edit before writing; apply a previewed edit with `apply_edit`, undo with `undo_edit`.
- Before reporting, run `diagnostics` and `verify` on what you touched, and use `affected_tests` to pick the tests to
  run.
- Grep and `sed` are for non-code files and for text that is not a symbol (strings, docs, config). If you used them
  on a symbol anyway, say why under Deviations.
- If a codenav-swift tool errors or is unavailable (for example the write tools are off, or an Xcode project has no
  `buildServer.json`), say so under Friction, then fall back to grep and your own edits.
