<p align="center"><img src="assets/icons/icon.png" alt="ConstellaLab logo" width="120"></p>

# ConstellaLab — Day 30: Swarm-Testing Layer

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
- The API is strictly renderer ↔ core at this point. Simulated inter-satellite contacts and
  message transport arrive later (Days 25–30, below); they are core-side and not yet driven by the
  visual client.

## Days 25–30: targets, sensors, tasks, policies, contacts and transport

The simulation core now carries the swarm-testing layer. Everything is config/
plugin driven, deterministic under a seed, and split so a policy can never read
the simulator's ground truth.

| Module | What it owns |
|---|---|
| `core/constellab_core/targets.py` | `EventTarget` (id, kind, location/radius, active interval, urgency, requirements, separate `truth`) and the `EventSource` registry (`hotspot`, `flood-region`, `change-detection`) |
| `core/constellab_core/sensors.py` | `SensorModel` plugins, footprint geometry (range, off-nadir, elevation, limb occlusion, resolution proxy), hash cloud mask, duty cycle, contiguous `AccessWindow`s |
| `core/constellab_core/tasks.py` | generic task lifecycle, idempotent/illegal transitions, deadlines, and observation outcomes with confidence, freshness and resource cost |
| `core/constellab_core/policy.py` | observation/action schema, `local-greedy` + `fixed-priority` baselines, diagnostic `oracle-upper-bound`, and the shared `run_episode` harness |
| `core/constellab_core/contacts.py` | `LinkModel` plugins (`link.uhf`, `link.optical`), deterministic contact plans, topology helpers, three reference arrangements |
| `core/constellab_core/transport.py` | bounded queues, bandwidth, latency, seeded loss/duplication/reordering, partitions, reconnect policy, replayable trace |

Key guarantees:

- **Ground truth stays simulator-side.** Policies receive `PolicyObservation`
  (active targets only, already-created tasks, predicted access windows) and
  nothing else; a target's `truth` payload is serialised in exactly one place,
  the simulator side, and observation construction rejects it.
- **Every outcome is reproducible.** Event traces, access windows, episode
  traces, contact plans and message traces are all functions of
  `(config, targets, seed, step)`, asserted by tests in each suite.
- **Partitions prevent delivery, not just drawing.** While a partition is
  active a message cannot cross between its groups; `flush`/`hold`/`drop`
  decide what happens to traffic that waited.
- **A policy only proposes.** The harness validates every proposal; illegal
  actions, unknown tasks and double claims are rejected and recorded.

`GET /api/swarm` publishes the Day 25–30 registries (event kinds, sensor models,
task types, policies, link models, transport defaults) for the renderer and
tests. Run the suites with `npm run test:core` or everything with `npm test`.

## Day 4–5: satellites, orbit paths and motion

- Satellite markers and their orbit paths are built from the snapshot `OrbitElements`;
  the scrubber's **Toggle Orbits** button hides or shows every path without touching state
- The core propagates position analytically (`F(t)`, two-body) at a fixed simulation-time step;
  frame rate never changes simulation state
- The renderer polls the core's state stream and moves markers; it never integrates orbits itself
- `state_from_elements_at_time(elements, 0)` equals the epoch `state_from_elements(elements)` and one
  full period returns to the starting position
- Orbit paths and satellite positions share one ECI → scene mapping (`scene/orbit.ts`), so markers
  ride their own trajectory lines
- The demo scenario runs at `time_scale` 300 (≈19 s per LEO revolution); the clock controls that
  drive it are described under Day 6 above

### Brand assets

Icons and the wordmark/symbol come from `assets/constellab_brand_assets/`. `assets/icons/icon.png`
(2048 px) is the single source for the generated `.ico` and favicon via `npm run icon`.

## Day 3: the Earth viewport

- Lit Earth sphere using the served tactical Earth texture (`frontend/public/earth-tactical-dark.png`),
  with a canvas-drawn schematic fallback if the image cannot load
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
| `GET /api/swarm` | Days 25–30 registries: target kinds, sensors, tasks, policies, links, transport |

Responses carry `X-Request-Id` and `X-Revision`. Errors are JSON with a stable `error` code, a
human `message` and the `request_id`; validation errors also carry field-path `errors`.

Clock semantics:

- `reset` returns to the scenario's epoch: `t = 0`, clock paused, the scenario's own `time_scale`.
- `step` advances exactly one simulated second, whatever the time scale, and never changes the
  paused/running state.
- `time_scale` must be a positive JSON number (`true`, strings and `null` are rejected with
  `400 invalid_time_scale`); accepted values are clamped to `[0.001, 1 000 000]`.

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
- **Day 3** ✅ Three.js Earth with the local tactical texture (canvas fallback), camera controls, stable lifecycle
- **Day 4** ✅ four configured satellites and their orbit paths, rendered from snapshot elements
- **Day 5** ✅ analytic two-body propagation, running core clock, live snapshot polling in the viewport
- **Day 6** ✅ simulation time controls (pause / resume / reset / step / time scale), covered by
  `core/tests/test_clock.py` (freeze, exact epoch restore, repeated step, scale rate, invalid scale)
- **Day 7** ✅ satellite selection, camera focus and a typed inspector
- **Day 8** ✅ runtime scenario loading from validated configuration (catalog + 48-satellite fixture)
- **Day 9** ✅ schema-driven parameter editor with validated apply/restart
- **Day 10** ✅ canonical API: request ids, state revisions, stale-snapshot guard, headless run
- **Day 11** — next: renderer scale beyond four satellites (instanced markers, bounded paths, 100/500/1,000-satellite benchmarks)
