# Weekend Restart Checklist

Use this checklist to resume ESC-configurator work quickly after a break.

## 0) Quick context

- Project area: `python/imgui_bundle_esc_config/`
- Latest known test baseline: **156 passed** (`python/unitTests/`)
- Recent completed work:
  - catalog snapshot cache fallback + startup auto-refresh
  - cache-origin UI flag (`(cached)`)
  - firmware release search/filter
  - log window search/filter
  - compact bottom status-bar behavior for narrow widths

## 1) Bring-up (5 minutes)

- [ ] Open workspace at repo root
- [ ] Activate virtual environment (`.venv`)
- [ ] Run full unit tests and confirm baseline remains green
- [ ] Launch app and confirm it starts without tracebacks

## 2) Startup/catalog smoke check

- [ ] Verify firmware catalog appears quickly from cache at startup (if cache exists)
- [ ] Verify background refresh updates catalog without freezing UI
- [ ] Verify `(cached)` indicator is shown only when catalog source is cache

## 3) UI parity smoke checks

- [ ] Resize main window to narrow width; verify bottom status bar remains readable
- [ ] Hover truncated status/port text and verify tooltips show full values
- [ ] In firmware panel, verify release search filters by name/key
- [ ] In log window, verify filter narrows displayed entries by source/message

## 4) Hardware-in-loop smoke checks

- [ ] Connect/disconnect serial bridge cleanly
- [ ] Enter/exit passthrough on at least two ESC indices
- [ ] Read settings on multiple ESCs and verify target alignment
- [ ] Flash one ESC and verify success path
- [ ] Trigger cancel once during flash and verify recovery UX
- [ ] Run Flash All and verify summary/result counts

## 5) Diagnostics + persistence

- [ ] Export diagnostics bundle and verify expected files are present
- [ ] Restart app and verify persisted prefs restore correctly

## 6) Offline/resilience check

- [ ] Simulate no-network condition
- [ ] Refresh catalog and verify snapshot fallback works
- [ ] Confirm no crash when cache file is missing/corrupt

## 7) Next priorities (if time remains)

- [ ] Add stale cache age warning badge (e.g., >24h)
- [ ] Add UI-level tests for status-bar compact behavior (if harness allows)
- [ ] Add UI-level tests for search/filter widgets

## 8) End-of-session wrap-up

- [ ] Run full `python/unitTests/` suite one last time
- [ ] Update `PARITY_CHECKLIST.md` current priority queue if priorities changed
- [ ] Note any hardware-only findings in a short markdown log
