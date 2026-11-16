# VMS UI refresh, Search and Assistant

Requested by the owner on 2026-11-11: make the current VMS look and work more like the old VMS and restore missing Search / AI features.

## Implemented

- Shared visual finish, improved light/dark surfaces, grouped navigation, descriptive page introductions, header search and Command/Ctrl+K.
- Cameras opens an overview with grid/list modes, status/location filters, and explicit camera-specific Live, Playback and Settings actions. Static camera posters are clearly labeled links, not fabricated live thumbnails.
- Live View keeps primary controls visible and moves favorites, camera selection and saved-view tools into View options. Camera links open the requested feed, and Back to grid clears the camera URL parameter.
- `/search` searches the actual recorder index through authenticated `/api/v1/search`. Collections: events, active recording segments and gallery snapshots. Camera grants apply to results, counts and explicit camera filters. Hidden events and missing/truncated segments are excluded. Recording intervals overlap date filters; custom dates use the site timezone, including DST. Saved searches are local to the browser and user account.
- Snapshot search results open the corresponding gallery preview, including items outside the first page.
- `/assistant` provides read-only recorder commands and an optional Ollama mode. Replies offer reviewed navigation links; neither model output nor natural-language input executes camera commands. Data sent to the configured model contains only the user's camera names, locations, states, recording evidence and a bounded recent event sample. Credentials, stream URLs and images are excluded.
- Owners can list installed Ollama models and connect/disconnect one in the UI. Selection is stored atomically as `assistant-model.json` in the NVR data directory. `NVR_ASSISTANT_MODEL` overrides UI selection for managed installations; `NVR_ASSISTANT_URL` defaults to `http://127.0.0.1:11434`. No model downloads or mandatory AI dependency.
- `/playback/compare` compares up to four accessible cameras using one shared wall clock, date, time, seek position and speed. Per-camera recording gaps remain empty rather than jumping a view ahead. Single-camera playback retains export and snapshot tools.

## Scope boundaries

Object search uses camera-reported events, not visual inference. Clothing colors, faces, license plates, PPE and other visual attributes from the old demonstration UI are not indexed and are not presented as working filters. AI model answer quality depends on the selected installed model. The recorder assistant works without one.

PTZ, two-way talk and zone drawing still require camera API support. Four-camera comparison is browser playback synchronization, not frame-accurate forensic synchronization; source timestamps and decoding can introduce small differences.

## Verification

Frontend build/typecheck, design gates, full Vitest suite including contrast thresholds and new search/assistant/comparison tests. Python integration coverage includes camera access restrictions, hidden results, pagination, interval overlap, literal text queries, model isolation, owner-only model selection and model error handling. Browser review uses an isolated NVR with preview cameras/events; no real camera streams are represented by these fixtures.

Ollama chat integration follows its [official API](https://docs.ollama.com/api/chat) (`stream: false`); model discovery uses `/api/tags`.


### Verified result

- Production frontend build and TypeScript: passed.
- Design gates: passed with zero violations.
- Vitest: 39 files, 383 tests passed.
- Search/assistant, events, gallery, recording and OpenAPI API regressions: 25 passed.
- Ruff on changed Python code and `git diff --check`: passed.
- Browser: inspected Dashboard, Cameras, Search, Assistant and comparison. Search and comparison have no horizontal document overflow at 390px. Restored the normal desktop viewport afterward.
- Connected the already-installed `gemma:2b` model in the isolated preview and verified a real response using the scoped recorder snapshot.
- Hardware video feeds were not exercised; preview cameras/events are isolated fixtures, not additions to the user's recorder.

### Preview images

- [Cameras](previews/cameras-refresh.png)
- [Search](previews/search-refresh.png)
- [Assistant](previews/assistant-refresh.png)
