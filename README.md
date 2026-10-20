<p align="center"><img src="assets/icons/icon.png" alt="ConstellaLab logo" width="120"></p>

# ConstellaLab — Day 10: Canonical Simulation API

Software-only crash-test lab for autonomous satellite swarms — a Three.js Earth viewport built on the versioned Python/TypeScript simulation contract. Satellites orbit Earth from snapshots produced by the local Python core, which can also run headlessly for batch work.

## Quick Start

| Action | Command |
|---|---|
| Run Python core status | `npm run status` |
| Print the epoch snapshot | `npm run snapshot` |
| Run the simulation headlessly | `npm run headless -- swarm-48 --duration 3600 --step 5` |
| Regenerate TS contract types | `npm run gen:contract` |
| Start dev mode (core + Vite + Electron) | `npm run dev` |
| Build frontend | `npm run build` |
| Fetch embedded Python | `npm run fetch-python` |
| Build .exe (portable) | `npm run dist:win` |
| Regenerate app icons | `npm run icon` |

The app opens with a brief `constellab` splash, then the landing page, then the viewport.

## .exe Application

**`dist-electron\ConstellaLab-<version>-portable.exe`** — portable Windows executable.

- Native desktop app (no browser, no internet required after build)
- Embedded Python 3.14 service (autofetched via `npm run fetch-python`)
- VSCode dark theme UI with system font
- Splash → landing page → viewport, all over a rotating Earth
- `npm run dist:win` verifies icons in both portable launcher and inner exe

## Day 8–10: scenarios, parameters and the canonical API

- Scenarios load at runtime from validated configuration. `GET /api/scenarios` lists the built-in
  catalog; `POST /api/scenario` accepts `{"key": "swarm-48"}` or `{"config": {...}}`. Inline configs
  go through the same validator and a rejected load leaves the running scenario untouched.
- Mission Parameters (rail icon) is generated from the contract schema: labels, units, steps and
  bounds come from the schema's `x-ui` block through a widget registry, so a new same-type parameter
  needs no editor code. Edits stay in a draft, are validated locally, and apply as a restart at epoch.
- `GET /api/state` is the canonical stream: `{request_id, revision, scenario_id, clock, snapshot}`.
  `revision` is monotonic, and the renderer drops any reply that is older than the state it already
  shows, so a slow response can never roll the view backward. `GET /api/snapshot` stays a pure
  contract payload.
- Every reply echoes `X-Request-Id` (caller-supplied when valid) and `X-Revision`; errors are
  `{error, message, request_id, ...}` with a stable code. Bodies are bounded at 1 MiB (413), non-JSON
  content types are rejected (415) and unknown routes return a structured 404.
- `constellab_core run` advances a scenario with no server and no browser, streaming one NDJSON
  record per step (about 110k satellite states/s on a laptop), which is the entry point for batch
  work. Training code is not coupled into the visual process.
- The API is strictly renderer ↔ core. There is no satellite-to-satellite messaging or swarm
  coordination yet.

## Day 4–5: satellites, orbit paths and motion

- Satellite markers and their orbit paths are built from the snapshot `OrbitElements`
- The core propagates position analytically (`F(t)`, two-body) at a fixed simulation-time step;
  frame rate never changes simulation state
- The renderer polls the core's state stream and moves markers; it never integrates orbits itself
- `state_from_elements_at_time(elements, 0)` equals the epoch `state_from_elements(elements)` and one
  full period returns to the starting position
- Orbit paths and satellite positions share one ECI → scene mapping (`scene/orbit.ts`), so markers
  ride their own trajectory lines
- The demo scenario runs at `time_scale` 300 (≈19 s per LEO revolution); controls arrive on Day 6

### Brand assets

Icons and the wordmark/symbol come from `assets/constellab_brand_assets/`. `assets/icons/icon.png`
(2048 px) is the single source for the generated `.ico` and favicon via `npm run icon`.

## Day 3: the Earth viewport

- Lit Earth sphere with generated schematic texture (no external assets)
- Drag to orbit; wheel/pinch or +/− buttons to zoom; Reset view restores camera
- Earth is static — camera animation never changes simulation time
- Renders even if core is unreachable; telemetry panel reports errors separately
- Valid snapshots appear in telemetry panel; expand Core state for satellite table
- Satellite meshes and orbit paths are Day 4; propagation is Day 5
- Scene follows viewport size via ResizeObserver, clamps DPR, owns one render loop
- Unmount cancels loop, disconnects resize, releases GPU resources

### Scene components

| Component | Responsibility |
|---|---|
| `frontend/src/scene/SceneShell.tsx` | React host, camera buttons, snapshot telemetry |
| `EarthScene.ts` | Three.js renderer, camera, OrbitControls |
| `EarthWorld.ts` | Earth geometry/material, lighting, disposal |
| `config.ts` | Named camera, geometry, lighting, texture settings |
| `assets.ts` | Canvas-generated Earth texture, no URL download |
| `camera.ts` | Camera reset and bounded zoom helpers |
| `lifecycle.ts` | Single animation loop, injectable runtime for tests |

## Day 2: the contract

`core/constellab_core/data/simulation_contract.schema.json` is the single versioned source of truth (v1.0.0).

| Layer | Artefact |
|---|---|
| Python typed models | `core/constellab_core/contract.py` |
| Python validation | `core/constellab_core/validation.py` — JSON-Schema-subset validator |
| TypeScript types | `frontend/src/contract/generated.ts` — generated by `npm run gen:contract` |
| TypeScript validation | `frontend/src/contract/validate.ts` + `parseSnapshot()` |
| Fixtures | `scenario_empty.json`, `scenario_four_satellites.json`, `malformed_*.json` |

### Core HTTP API (`http://127.0.0.1:8765`)

| Endpoint | Purpose |
|---|---|
| `GET /api/status`, `GET /api/health` | service metadata |
| `GET /api/contract` | JSON schema |
| `GET /api/scenario` | currently loaded SimulationConfig |
| `GET /api/scenarios` | built-in scenario catalog + active key |
| `POST /api/scenario` | load `{"key": ...}` or `{"config": ...}`; restarts at epoch |
| `GET /api/state` | canonical state stream: request id, revision, clock, snapshot |
| `GET /api/snapshot` | SimulationSnapshot at the current clock time |
| `POST /api/config/validate` | validate config |
| `POST /api/snapshot` | validate config and return its epoch snapshot |
| `GET /api/clock` | clock (epoch, simulation time, scale, paused) |
| `POST /api/clock/pause`, `/resume`, `/reset`, `/step`, `/time_scale` | simulation time controls |

Responses carry `X-Request-Id` and `X-Revision`. Errors are JSON with a stable `error` code, a
human `message` and the `request_id`; validation errors also carry field-path `errors`.

## Folder Structure

```
constellab/
  package.json     npm + electron-builder config
  vite.config.ts   Vite + React config
  pyproject.toml   Python package metadata
  assets/icons/    logo + generated icon.ico
  core/            Python constellab_core package
  frontend/        Vite + React + TS source
  electron/        Electron main + preload
  scripts/         dev/test/helpers
  dist-electron/   build output (gitignored)
```

## Development Commands

```bash
npm run test      # Python core, contract drift, tsc, TS tests, Vite build
npm run test:core # Python tests only
npm run test:contract  # TypeScript contract tests
npm run test:scene     # Scene lifecycle tests
npm run test:scenario  # Schema-driven editor tests
npm run test:api       # State stream / stale-snapshot guard tests
npm run headless -- swarm-48 --duration 600 --step 10  # browser-free run
npm run typecheck # tsc --noEmit
npm run dev       # Start core + Vite + Electron
npm run status    # Print core status as JSON
npm run snapshot  # Print demo scenario's epoch snapshot
npm run fetch-python  # Download embedded Python for .exe
npm run dist:win  # Build portable .exe
npm run icon      # Regenerate icons (needs Pillow)
```

## Progress

- **Day 1** ✅ runnable baseline, portable .exe, minimal folder structure
- **Day 2** ✅ versioned contract, generated TS types, round-trip tests
- **Day 3** ✅ Three.js Earth, offline texture, camera controls, stable lifecycle
- **Day 4** ✅ four configured satellites and their orbit paths, rendered from snapshot elements
- **Day 5** ✅ analytic two-body propagation, running core clock, live snapshot polling in the viewport
- **Day 6** ✅ simulation time controls (pause / resume / reset / step / time scale)
- **Day 7** ✅ satellite selection, camera focus and a typed inspector
- **Day 8** ✅ runtime scenario loading from validated configuration (catalog + 48-satellite fixture)
- **Day 9** ✅ schema-driven parameter editor with validated apply/restart
- **Day 10** ✅ canonical API: request ids, state revisions, stale-snapshot guard, headless run
- **Day 11** — next: agent policy loop over the headless core
