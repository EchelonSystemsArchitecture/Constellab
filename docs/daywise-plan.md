# Constellab — Day-wise AI-Agent Execution Plan

**Purpose:** Build Constellab as a software-only orbital/swarm simulation and autonomous-swarm testing platform. The visual orbital simulator must be usable first. After that foundation, implement configurable simulation systems, simulated swarm behavior, heavily trained neural policies, adversarial test generation, failure analysis, and reproducible evidence.

**Schedule:** 70 consecutive implementation days, starting 11/10/2026. This is an aggressive sequence, not a promise that every quality gate will pass on its scheduled day. A failed gate must be fixed before dependent work is called complete.

## Non-negotiable implementation rules

1. **Visual simulation first.** Days 1–14 produce a working orbital scene driven by real simulation state. No satellite-to-satellite communication or swarm coordination before the visual gate passes.
2. **One source of truth.** The simulation core owns time, state, orbital positions, random streams, events and outputs. The renderer only displays snapshots; rendering frame rate must not alter simulation outcomes.
3. **Software only.** All spacecraft, sensors, communications, compute, energy, storage, events and failures are virtual. No hardware-in-the-loop path is required.
4. **Config-driven, not a giant `if/else` tree.** Parameter definitions live in versioned schemas/registries. Behaviors are implemented as reusable component plugins behind typed interfaces. Adding a supported parameter should generally be a schema/config change, not a new special case in the core loop.
5. **Thousands of parameters means data-driven scale, not thousands of bespoke code branches.** Support thousands of registered/configured fields and large numbers of simulated entities. Every active parameter must have a defined consumer/plugin, type, unit, bounds, normalization and validation behavior. Reject or warn on ignored/unknown effective parameters instead of silently pretending they work.
6. **Variable-size neural models.** Do not hard-code a fixed satellite count or a giant fixed input vector for every possible setting. Use set/graph-based encoders, masks, metadata-aware parameter encoders and shared per-satellite policies. A new configuration is not automatically supported merely because it parses: check schema/model compatibility and out-of-distribution status.
7. **Safety is not delegated to the neural model.** Learned policies propose actions. A separate deterministic runtime shield checks configured constraints and rejects unsafe/infeasible actions. Record every rejected action and fallback.
8. **Reproducibility everywhere.** Seeded simulation, per-entity random streams, versioned configs/schemas, dataset manifests, saved checkpoints, fixed evaluation scenarios and trace hashes are required.
9. **No fake progress.** A stub, screenshot, untrained model or passing synthetic unit test is not evidence of end-to-end capability. Every day ends with runnable code and observable acceptance evidence.
10. **Keep the supported stack simple.** Suggested default: TypeScript + Vite + React + Three.js for the visual client; Python for the simulation core, schemas, testing and PyTorch training; FastAPI/WebSocket only as a local frontend-to-core bridge. Pin dependencies and change technologies only when a measured technical blocker justifies it.

## Milestone gates

| Gate | Target day | Required result |
|---|---:|---|
| G0 — Visual orbital simulator | 14 | Earth, moving satellites, orbit paths, camera/time controls, selection and inspector work from simulation state. No swarm links yet. |
| G1 — Configurable simulation foundation | 24 | Schema-driven parameters, component registry, constraint validation, seeded scenario generation and scalable state. |
| G2 — First reproducible swarm failure | 34 | Simulated tasking and communication faults expose a known baseline-policy failure; trace is replayable. |
| G3 — Trained swarm policy | 56 | Multiple neural policy families have been trained/evaluated against non-neural baselines across held-out configurations; safety shield remains independent. |
| G4 — Learned adversarial testing | 62 | Learned scenario search is compared fairly with random/fixed search and produces reproducible counterexamples. |
| G5 — Integrated Constellab build | 70 | Visual simulator, configurable parameters, trained policies, test engine, failure analysis, evidence packs and clean-start verification operate together. |

---

## Day 1: 11/10/2026
**Task: Establish a runnable code baseline and inspect the actual repository.** Inspect the current Constellab files and repository state, identify whether source code exists, then create or repair the minimum project structure without assuming that designs or snippets are implemented. Set up the frontend and Python-core directories, ignore generated data/checkpoints/build products, and add a single local command path for starting the application in development mode.

**Detailed execution:** Add a minimal frontend shell and a minimal Python simulation service that starts, returns a version/status payload and exits predictably on invalid configuration. Add a smoke test that imports the Python package and a frontend build check. Keep the simulator state minimal today; do not add networking between simulated satellites. The frontend may display an empty scene shell so the next days can render into the actual application rather than creating a throwaway prototype.

**Completion evidence:** clean install instructions encoded in the repo, frontend build passes, Python smoke test passes, application health/status command works, and repository changes contain no generated model/data blobs.

## Day 2: 12/10/2026
**Task: Create the simulation/visualization contract.** Define typed schemas for `SimulationConfig`, `SimulationSnapshot`, `SatelliteState`, `OrbitElements`, `SimulationClock`, `EntityId` and version metadata. Define units, reference-frame assumptions, timestamp semantics and optional-field behavior. Use one versioned source for the JSON schema and generated TypeScript/Python types where possible.

**Detailed execution:** The frontend must consume snapshots rather than calculate satellite positions independently. Include an explicit schema version and reject incompatible snapshots. Distinguish configuration from runtime state and runtime state from rendered objects. Add test fixtures for an empty scenario, four satellites and malformed configuration. Define stable identifiers; never use array position as the entity identity. Avoid parameter-specific branches inside serializers—use typed models and schema validation.

**Completion evidence:** versioned state/config schemas, generated or contract-tested frontend/backend types, round-trip serialization tests and predictable errors for missing fields, invalid units and incompatible schema versions.

## Day 3: 13/10/2026 ✅
**Task: Implement the 3D scene and Earth placeholder.** Build the actual Three.js scene, camera, renderer, resize handling, basic lighting and an Earth sphere. Use a simple generated or replaceable texture so the scene is runnable without depending on an external asset. Separate scene setup from simulation state ingestion.

**Detailed execution:** Implement camera orbit, zoom and reset controls; prevent resize events from leaking render loops or creating duplicate canvases. Use the renderer only to draw state—no hidden simulation clock or orbital equations in React components. Keep visual assets replaceable through an asset interface and place material/texture settings in named configuration rather than scattering constants through components.

**Completion evidence:** Earth renders in a clean browser start, camera controls work, resizing is stable, the render loop is cleaned up on unmount and a basic frontend test/build succeeds.

**Status: COMPLETE** — Earth renders with schematic texture, OrbitControls (orbit/zoom/reset), ResizeObserver-based sizing, single render loop with proper cleanup, VSCode dark theme UI, loading screen with rotating Earth, Electron desktop app with native menu.

## Day 4: 14/10/2026
**Task: Render virtual satellites and their orbital paths.** Add reusable satellite marker/model components and orbit-path rendering. Start with four illustrative satellites loaded from scenario configuration. Display a stable satellite ID and distinguish satellites visually without relying on color alone.

**Detailed execution:** Build orbit geometry from the same `OrbitElements`/snapshot contract used by the core; do not let the renderer own a second orbital simulation. Keep model creation data-driven so adding a satellite does not require adding another JSX branch. Render path lines and current positions with shared IDs. For large fleets, use instancing or batched geometry rather than one expensive independent draw object per satellite.

**Completion evidence:** four configured satellites and four paths render, IDs match the input config, all paths can be toggled, and adding a fifth satellite through configuration requires no frontend source edit.

## Day 5: 15/10/2026
**Task: Implement the first deterministic orbit state and visible motion.** Implement a simple circular two-body orbit model in the Python core and calculate position from initial state plus simulation time. Render those positions from snapshots. Clearly mark the initial orbit model as a simplified simulation level, not mission-grade orbital propagation.

**Detailed execution:** Keep calculations independent of render-frame frequency. Add explicit epoch, orbital plane/orientation values and unit conversions. Use a fixed simulation-time step or analytic state-at-time propagation; do not advance orbit state by “pixels per frame.” Test that rendering at different frame rates produces the same state for the same simulated timestamp.

**Completion evidence:** satellites move around Earth according to the core state, path and position remain aligned, and exact same config/time/seed yields matching numerical positions within the declared tolerance.

## Day 6: 16/10/2026
**Task: Implement simulation-time controls.** Add pause, resume, reset, single-step and configurable time-scale controls. Make the core clock explicit and let the frontend request/control time while only the core advances simulation state.

**Detailed execution:** Handle pause/resume races, reset state cleanly and define what happens when a requested time scale is invalid or too large. Keep wall-clock time separate from simulation time. Add tests around pause, reset, time scale, repeated single-step and simulation stop/start. Rendering should continue while the simulation is paused, so camera interactions remain responsive.

**Completion evidence:** all time controls work, resetting restores the exact initial state, pause does not mutate simulation state, and tests prove time scale affects simulated time rather than rendering math.

## Day 7: 17/10/2026
**Task: Implement satellite selection, focus and the inspector shell.** Add picking/select-by-ID, selected-satellite highlighting and camera focus. Create a typed inspector view for the selected satellite's identity, orbit configuration, simulated position and current simulation time.

**Detailed execution:** The inspector must render fields described by the snapshot schema rather than contain one-off code for every satellite type. If a field is missing, show an explicit unavailable state, not a fabricated zero. Ensure switching selection cannot retain stale values from the prior satellite. Keep selection and camera state separate from simulation state so UI interactions cannot alter the physics.

**Completion evidence:** selecting any configured satellite updates its highlight and inspector, camera focus works, invalid IDs are handled and selection does not change the simulation trace hash.

## Day 8: 18/10/2026
**Task: Load scenarios from validated configuration.** Implement a scenario loader for YAML/JSON with defaults, schema versions, satellite arrays and initial orbital parameters. The default scene must be generated from a scenario file, not from hard-coded UI arrays.

**Detailed execution:** Validate types, required fields, ranges, units and duplicate IDs before starting a run. Add a sample four-satellite visual scenario and at least one larger scenario fixture. Never execute user-provided Python, JavaScript or expression strings from configuration. Return structured validation errors identifying the exact field path. Preserve unknown metadata only where the schema explicitly allows extension fields; unknown operational fields should not be silently ignored.

**Completion evidence:** CLI and application can load a scenario file, invalid cases fail with field-specific errors, and a test adds/removes satellites only by editing config.

## Day 9: 19/10/2026
**Task: Build a schema-driven parameter inspector/editor.** Generate UI controls from the configuration schema for supported orbital values and simulation time options. Add typed controls for numeric, enum, boolean and structured fields, including defaults, units, bounds and reset-to-default behavior.

**Detailed execution:** Do not implement a separate hand-written component for each parameter. Use a control registry keyed by parameter type/widget kind, metadata-driven labels and a generic validation display. Keep editing separate from the running state; apply config changes through a validated restart/reconfigure transaction. Unknown parameter types must show a clear unsupported-type error rather than silently rendering a text field that corrupts values.

**Completion evidence:** supported fields render automatically from schema metadata, invalid values are blocked/reported, defaults restore correctly and adding another same-type parameter requires only schema/config changes.

## Day 10: 20/10/2026
**Task: Add the canonical simulation API and state snapshot loop.** Expose local endpoints for creating/loading a scenario, starting/pausing/resetting/stepping the simulation, reading a snapshot and retrieving status. Add a local WebSocket or equivalent stream for state updates only if polling cannot meet the visual requirement.

**Detailed execution:** The API is between the UI and the simulation core; it is not the simulated satellite-to-satellite network. Add bounded message sizes, request IDs, schema validation and predictable error responses. Ensure stale snapshots cannot roll the UI backward to an older state. Keep the core runnable headlessly for tests and large batch training. Do not couple neural-training code into the visual process.

**Completion evidence:** frontend and core communicate locally, API contract tests pass, headless simulation can run without a browser, and no satellite-to-satellite messages or swarm coordination code exists yet.

## Day 11: 21/10/2026
**Task: Make the visual renderer scale beyond four satellites.** Add instanced markers, bounded orbit-path geometry, efficient selection lookup and level-of-detail controls. Use synthetic scenarios with 100, 500 and 1,000 satellites to find major UI bottlenecks.

**Detailed execution:** Avoid React state updates per satellite per render frame. Batch scene updates from snapshots, maintain stable ID-to-instance mappings and clean old objects when scenarios change. Put visual density/label thresholds in renderer configuration. The goal is that the architecture supports large fleets without special cases, not to promise a universal frame rate on every machine.

**Completion evidence:** 1,000-satellite scenario loads, selection is still stable, memory does not grow on repeated resets, and a repeatable benchmark records frame time and approximate memory on the current development environment.

## Day 12: 22/10/2026
**Task: Add visual diagnostics and robust scene-state transitions.** Add optional overlays for satellite IDs, orbit plane, current simulation time, selected position and snapshot age. Add loading, invalid-config, disconnected-local-core and simulation-error states.

**Detailed execution:** The overlays must use typed snapshot data and be toggleable independently. Keep diagnostic rendering from affecting simulation execution. Verify that restarting the core reconnects the UI cleanly and that an invalid scenario does not leave half-created scene objects. Include error boundaries and resource cleanup for geometries, materials, and listeners.

**Completion evidence:** overlays can be enabled/disabled, broken local service states are visible, repeated load/reset cycles do not duplicate objects or listeners and UI error paths have tests.

## Day 13: 23/10/2026
**Task: Add end-to-end visual simulation tests and rendering performance baselines.** Build automated tests that load a known scenario, advance time, check satellite state, select an entity and verify UI controls. Capture stable test snapshots only for critical UI state; numerical orbital state remains the primary correctness evidence.

**Detailed execution:** Separate pure simulation tests from browser-level tests. Test slow/fast time scale, pause, reset, config reload, dynamic satellite count and resizing. Make performance measurements opt-in and report distributions rather than a single fastest frame. Ensure any test requiring WebGL has a documented headless/browser fallback so core tests still run in CI.

**Completion evidence:** automated visual E2E test passes from a clean start, orbit/time determinism tests pass, and performance output includes machine/runtime metadata.

## Day 14: 24/10/2026 — G0 VISUAL GATE
**Task: Finish the usable visual orbital simulator before adding swarm communications.** Correct visual/state bugs, make the demo scenario a one-command launch, and verify Earth, satellites, orbits, controls, selection, inspector and config loading as one integrated vertical slice.

**Detailed execution:** Run the end-to-end flow from a clean checkout. Delete generated caches and verify startup does not depend on a developer-specific path. No inter-satellite links, shared state, swarm allocation, communication fault injection or trained model is allowed to be a hidden dependency of the visual milestone. Keep the orbital model limitation visible in the application and scenario metadata.

**Completion evidence:** G0 checklist passes, a repeatable automated run demonstrates all required interactions, and the application stays functional at four and 1,000 virtual satellites within recorded environment-specific performance limits.

## Day 15: 25/10/2026
**Task: Upgrade the orbital propagator to a documented Keplerian two-body model.** Implement propagation from classical orbital elements, including anomaly conversion and coordinate transforms needed by the scene. Keep the old circular case as a special test fixture, not a separate code path spread across the renderer.

**Detailed execution:** Use a trusted reference or independently derived test vectors for representative eccentricities and inclinations. Normalize angular units and define epoch/time handling. Exclude perturbations at this level and record them as model assumptions. Separate orbital propagation from rendering and scenario parsing behind a `DynamicsModel` interface so later fidelity levels do not require editing the main simulation loop.

**Completion evidence:** Keplerian propagation handles circular and non-circular test cases, produces stable positions across time, and is invoked through a registered dynamics component.

## Day 16: 26/10/2026
**Task: Establish coordinate frames, units and physical-value validation.** Implement typed quantity conversion and documented frame transforms used by orbit, Earth rotation, sensor geometry and later contact calculations.

**Detailed execution:** Avoid mixing kilometres/metres, degrees/radians, simulation seconds/wall-clock seconds or inertial/Earth-fixed coordinates. Put allowed units and conversions in a centralized unit registry. Validate orbital inputs against physical/numerical domain constraints before propagating. Add tests for frame transformations, epoch changes, angular wraparound and unit conversion. Do not invent customer-specific physical defaults in code; keep illustrative values in scenario files.

**Completion evidence:** unit/frame contract, conversion tests, frame-aware state type and validation errors that identify incompatible or invalid units.

## Day 17: 27/10/2026
**Task: Add numerical validation and orbit regression tests.** Create golden trajectories, compare the propagator with an independent reference implementation where available, and test long-duration propagation, edge cases and configuration perturbations.

**Detailed execution:** Include near-circular orbits, eccentric cases supported by the solver, boundary eccentricities, high inclinations, elapsed-time extremes and invalid elements. Use justified numeric tolerances and retain raw expected/reference values. Keep physics failures separate from renderer failures. Add property tests for periodicity where the chosen assumptions make it valid, and explicit tests for cases where a simplification means exact agreement is not expected.

**Completion evidence:** orbital test suite detects a deliberately injected sign/unit error, golden trajectories pass, and numerical limitations are recorded in code-level metadata.

## Day 18: 28/10/2026
**Task: Add generic virtual spacecraft subsystems and resource state.** Implement component interfaces for power/energy, storage, compute budget, fuel budget, sensor capability and payload capability. Each subsystem updates state from declared parameters and simulation time.

**Detailed execution:** Create protocols/interfaces such as `ResourceModel`, `SensorModel`, `PayloadModel` and `ComputeModel`. Register implementations by component identifier; do not branch across hundreds of satellite types in the simulation loop. Use normalized units and explicit update cadence. Keep resources virtual and configurable; no real hardware interface is allowed or needed. Add default reference components that make the visual demo useful without forcing every scenario to specify every field.

**Completion evidence:** at least two interchangeable implementations can be registered for a subsystem, component validation catches missing required parameters, and a satellite can expose different capabilities through config alone.

## Day 19: 29/10/2026
**Task: Implement the dynamic parameter registry for high-dimensional client configurations.** Define `ParameterSpec` with a namespaced key, owner component, type, units, default, bounds, enum values, distribution, normalization, mutability, update cadence, model visibility and schema/version metadata.

**Detailed execution:** Support nested namespacing, typed defaults, constrained optional fields and extension metadata. Store the registry as data files, not as a thousands-line conditional. Every supported runtime variable must identify the registered component that consumes it. Add schema migrations and stable field identifiers so renaming a display label does not change model meaning. For custom keys with no registered consumer, reject the effective config or clearly mark the key metadata-only; never silently claim that an unconsumed parameter changes behavior.

**Completion evidence:** registry loads hundreds to thousands of definitions in a synthetic stress fixture, validates defaults/ranges/units, emits a schema hash and identifies unconsumed operational fields.

## Day 20: 30/10/2026
**Task: Build a plugin/component registry instead of parameter-specific branching.** Create a common lifecycle for component discovery, schema registration, config validation, initialization, state update, snapshot serialization and teardown. Add explicit registration for orbit, resource, sensor, task and event-source components.

**Detailed execution:** The core should loop through registered components according to lifecycle/priority metadata. Do not add `if parameter_name == ...` or `if satellite_type == ...` blocks to the global engine. Keep plugins trusted executable code shipped with Constellab; client configuration itself remains data-only. Add tests for a third-party-style example plugin registered without changing the simulation core, duplicate plugin IDs and incompatible plugin versions.

**Completion evidence:** adding an example component requires a plugin and schema registration, not a core-loop edit; invalid/duplicate registrations fail during startup with actionable diagnostics.

## Day 21: 31/10/2026
**Task: Implement declarative parameter constraints and dependencies.** Support constraints such as range, relation, required-if, one-of, sum budget and dependency ordering using a safe, limited expression/operator model. Do not use `eval`, arbitrary code strings or user-loaded scripts.

**Detailed execution:** Represent dependency relationships as a graph and detect cycles before simulation startup. Provide field-path diagnostics when constraints fail. Apply config edits as transactions: either all dependent values validate and the new config is accepted, or none of it is applied. Separate physical validity constraints from model-training support constraints so a physically valid but out-of-training-distribution config can still be simulated with a warning/fallback state.

**Completion evidence:** constraint unit/property tests pass, cycles and impossible dependency sets are rejected, and no arbitrary expression execution path exists in config handling.

## Day 22: 01/11/2026
**Task: Scale the client parameter UI to thousands of fields.** Generate controls from `ParameterSpec`, grouped by component/namespace, and add search, tags, filtering, edited-only view, validation summaries and schema-driven help text. Use list virtualization or pagination so a 10,000-field config does not create 10,000 expensive UI components at once.

**Detailed execution:** The UI must support import/export of versioned scenario files and preview the changes before applying. Keep numeric formatting and unit display driven by schema metadata. Add a path-based deep editor that does not require hand-coded forms for each component. Preserve unknown optional extension metadata only where allowed. Avoid losing values when filters change, tabs switch or a validation error appears.

**Completion evidence:** load, search, edit, validate, revert and export a 10,000-field synthetic config; round-trip config semantics remain identical and measured UI latency/memory are recorded.

## Day 23: 02/11/2026
**Task: Build a deterministic configuration and scenario sampler.** Generate varied valid configurations using explicit distributions, bounds, correlations and constraints. Use random sampling first, then low-discrepancy/space-filling methods such as Latin hypercube or Sobol where appropriate.

**Detailed execution:** Sampling must operate from registry metadata rather than a list of hard-coded variable names. Persist sampler seed, schema hash, selected distributions, constraint outcomes and all generated configuration identifiers. Separate training, validation and test configuration families before model training. Add support for categorical choices and conditional parameters without evaluating arbitrary code. Keep a small quick sample mode and a resumable large campaign mode.

**Completion evidence:** same sampler version/seed/schema produces the same canonical config set; constraints hold for generated configs and distributions can be summarized automatically.

## Day 24: 03/11/2026 — G1 CONFIGURABLE FOUNDATION GATE
**Task: Prove the variable-driven architecture handles high-dimensional configs without special cases.** Run stress tests for thousands of registered variables, many entities and multiple plugin combinations. Close schema, unit, reset, config transaction and reproducibility defects before task/communication behavior depends on them.

**Detailed execution:** Verify that core behavior is dispatched through component interfaces and that the runtime identifies unknown/unconsumed operational fields. Test a synthetic plugin with new parameters and behavior, and test a config with irrelevant metadata to make sure it cannot silently affect physics or policy. Check that large config load/validation time remains bounded enough for the target environment and record the measurement rather than guessing an absolute performance guarantee.

**Completion evidence:** G1 acceptance report generated by automated tests, including schema hash, parameter count, plugin count, config load time, valid/invalid examples and exact limitations.

## Day 25: 04/11/2026
**Task: Add simulated Earth-observation targets and geospatial event sources.** Define targets/events as configurable entities with stable IDs, locations or regions, start/end times, urgency, confidence, observation requirements and ground truth. Begin with synthetic event types such as wildfire-like hotspot, flood-like region change and generic change detection.

**Detailed execution:** Generate target scenarios through an `EventSource` plugin registry. Keep event metadata separate from what a simulated satellite can observe so ground truth cannot leak into policy inputs. Validate geographic ranges, time intervals and event lifecycle. Do not require real image data for this stage; the first policy can use simulated sensor observations with explicit noise and visibility.

**Completion evidence:** deterministic event traces can be generated from config, ground-truth metadata remains separate from observations, and multiple event-source plugins work without editing the event loop.

## Day 26: 05/11/2026
**Task: Implement sensor footprint and observation opportunity models.** For each virtual satellite, calculate when a target is potentially observable based on orbit state, configured field of view, pointing limits, resolution proxy, cloud/weather mask and sensor availability.

**Detailed execution:** Put sensor behaviors behind `SensorModel` plugins and keep all sensor parameters in schema/config. Distinguish geometric visibility from usable observation quality. Use explicit model-fidelity labels for simplifications. Add tests for horizon/footprint boundaries, sensor disabled, target outside bounds, event time windows and unavailable observations. This stage models opportunities; it does not perform real-world sensor acquisition.

**Completion evidence:** access windows are deterministic, boundary tests pass, and generated opportunities include both timing and quality/resource metadata.

## Day 27: 06/11/2026
**Task: Define task lifecycle and observation reward data.** Implement tasks with states such as available, assigned, in-progress, completed, expired and cancelled. Add observation outcomes, target urgency, freshness, confidence and resource cost using generic task types and typed state transitions.

**Detailed execution:** Avoid encoding each event type directly into a global `if/else` dispatcher. Use task/observation handlers registered by type. Define idempotent state transitions and explicit handling of repeated or stale actions. Task outcomes must be generated by simulator state plus sensor model, not by the learned policy. Add invariants for illegal transitions, deadlines and resource use.

**Completion evidence:** task-state-machine tests cover legal/illegal transitions, deadlines and repeat actions; at least two task types share the same core lifecycle.

## Day 28: 07/11/2026
**Task: Implement policy interface and non-neural reference baselines.** Define the common policy interface: observation in, proposed action(s) out, hidden-state persistence if needed, and a structured policy metadata record. Implement simple local-greedy and fixed-priority policies as transparent baselines.

**Detailed execution:** Every policy must use the same observation/action schema. The policy cannot read simulator ground truth or hidden future events. Include configurable task scoring and deterministic tie-breaking rather than branching on individual target IDs. Add an oracle policy only as a clearly labeled diagnostic upper-bound for small scenarios; do not compare it as if it were deployable. Keep policy outputs as proposals that the runtime validates.

**Completion evidence:** local-greedy and fixed-priority policies run in the same episode harness, produce comparable traces and pass observation-leakage tests.

## Day 29: 08/11/2026
**Task: Implement geometry-driven simulated inter-satellite contact opportunities.** Only after G0 and the configurable state model work, add candidate links based on configured range, line-of-sight/obstruction assumptions and orbital state. Store contact opportunities as simulation events.

**Detailed execution:** Separate physical/geometric opportunity from whether a message is actually delivered. Parameterize range, link capability and scheduling assumptions through communication plugins. Avoid calculating links in the renderer. Build simple scenarios that include fully connected, intermittently connected and disconnected fleet arrangements; record the exact fidelity assumptions for each.

**Completion evidence:** deterministic contact plans are produced from orbit/config state, geometry boundary tests pass and link topology changes when its declared configuration changes.

## Day 30: 09/11/2026
**Task: Implement simulated message transport and network partitions.** Add message queues, bandwidth, latency, loss, delay, duplication, reordering and partition duration. Keep these as software-only event models. The transport receives messages from policy/components and delivers them only when the simulated link rules permit.

**Detailed execution:** Use explicit event timestamps and seeded random streams. Bound queues and define overflow behavior. A partition must prevent messages that should not pass, not merely draw a red line in the UI. Reconnection should trigger queued-message policy and state reconciliation as configured. Make transport events visible in traces so every delivery/drop/delay is reproducible.

**Completion evidence:** test fixtures prove delivery, drop, delay, duplication, reordering and partition cases; the same seed and config produce the same message trace.

## Day 31: 10/11/2026
**Task: Implement configurable fault injection and the first swarm failure.** Add random fault and worst-moment fault strategies that can cut links at specified lifecycle transitions, fail a satellite, degrade a sensor or delay a message. Keep the injection policy separate from the simulator’s normal transport logic.

**Detailed execution:** The fault generator must state its scope, timing window, target selection rule, duration and random seed. Add a duplicate-tasking invariant and a lost/expired-task invariant. Construct a baseline scenario where disconnected local-greedy agents can independently claim the same task. Verify the failure is caused by the configured outage and that removing the outage changes the outcome in the controlled example.

**Completion evidence:** Constellab can reproduce one known policy violation and identify the satellite/task/event IDs involved; controls also prove the baseline passes in the no-fault control case.

## Day 32: 11/11/2026
**Task: Create the deterministic event trace and replay engine.** Record every state-changing event in stable order, including simulation time, entity IDs, event type, payload schema version and cause/source metadata. Replaying a run must reconstruct the same relevant state and outcomes.

**Detailed execution:** Seed each subsystem/entity independently from a master seed so adding a random draw in one subsystem does not scramble every other stream. Define canonical serialization and sorting rules for hashes. Keep wall-clock performance metrics outside the deterministic state hash. Test replay through the same simulation core, not by merely reprinting stored final state.

**Completion evidence:** repeated same-seed runs and replay produce identical canonical trace hashes, while changing one meaningful config input yields a trace difference with an attributable starting point.

## Day 33: 12/11/2026
**Task: Expand invariant monitoring and baseline comparisons.** Implement state invariants and simple temporal rules for resource floors, duplicate claims, assignment expiry, event deadlines and policy action validity. Compare the greedy policy with leases-only and deterministic-priority allocation.

**Detailed execution:** Store invariant definitions as declarative rule configurations where possible. Return structured findings rather than free-form strings. Keep units and threshold source alongside each rule. Allow multiple invariants to fire on the same trace. Add tests where each rule is deliberately violated and where a near-boundary valid trace passes.

**Completion evidence:** invariant registry is extensible, every rule has positive and negative tests, and a baseline comparison report is generated from computed trace data.

## Day 34: 13/11/2026 — G2 FIRST REPRODUCIBLE FAILURE GATE
**Task: Integrate visual simulation, policy execution, simulated communication and fault monitoring.** In the 3D view, show active satellites, selected task, contact-link status, injected fault markers and the first detected invariant violation. The visualization must consume recorded/core state rather than independently determine correctness.

**Detailed execution:** Provide a single reproducible demo scenario and a command-line run that does not need the browser. Link/communication overlay is now allowed because the visual foundation has already passed. Run the same scenario twice, compare trace hashes, then run the no-fault control. Keep the UI readable; prioritize visible causality and diagnostic access over decorative effects.

**Completion evidence:** G2 passes with an automated test showing fault-on violation, fault-off control, identical same-seed hashes, and a visible matching event timeline.

## Day 35: 14/11/2026
**Task: Create the scalable ML episode environment and observation/action contract.** Wrap the simulator with reset/step semantics, structured observations, candidate actions, rewards, termination reasons and episode metadata. Support variable fleet sizes, task counts and connectivity graphs.

**Detailed execution:** Use a Gymnasium-compatible single-agent wrapper for centralized training first, then an explicit multi-agent interface for decentralized policies. Do not mix ground truth, future events or injection labels into policy observations. Add masked variable-size entity collections and stable entity ordering. Define rewards as separately logged terms—coverage, latency, duplicate work, resource use, task loss and constraint penalties—before collapsing them into a training objective.

**Completion evidence:** deterministic environment tests cover reset/step, variable numbers of agents/tasks, action masks, termination and reward decomposition; policies cannot inspect hidden simulator state.

## Day 36: 15/11/2026
**Task: Build a large-scale scenario/data-generation pipeline for neural training.** Generate episodes by sampling configuration schemas, orbital parameters, sensor/resource budgets, target/event schedules, communication conditions and failure timings. Start with thousands of distinct valid configurations and scale to larger campaigns using resumable batches.

**Detailed execution:** Store config hashes, seeds, simulator version, schema versions, initial state, event schedule, episode outcomes and observation/action records. Split train/validation/test by configuration families or scenario seeds, not by adjacent rows from the same episode. Include parameter-range coverage reports and leakage checks. Data generated after a model has been tuned must not be silently mixed into a held-out test set.

**Completion evidence:** dataset generator can resume interrupted batches, regenerate small fixtures deterministically, summarize variable coverage and produce a manifest with actual counts/hashes.

## Day 37: 16/11/2026
**Task: Implement an expert/reference policy for supervised training data.** Generate action demonstrations from transparent baseline methods and, for small scenarios only, a constrained offline optimizer or diagnostic oracle. Keep the expert clearly distinguished from policies meant to run onboard.

**Detailed execution:** Record candidate actions, chosen action, scores, constraints and outcome for each demonstration. Prevent oracle access to future information from leaking into student observations. Label records with source-policy version and scenario metadata. Use imitation data as an initialization signal, not as proof that the learned policy is optimal. Include examples where the expert abstains or has no feasible action.

**Completion evidence:** deterministic expert dataset with schema-checked observations/actions, known baseline metrics and tests proving no hidden future/ground-truth fields enter the student model input.

## Day 38: 17/11/2026
**Task: Implement the reusable PyTorch training framework.** Create configurable model/training entry points, dataset loaders, normalization fitted only on training data, seeded dataloaders, checkpoints, metric logging, early stopping, resume-from-checkpoint and model export.

**Detailed execution:** Training configuration must be declarative YAML/JSON with validated model name, dimensions, optimizer, learning-rate schedule, loss, batch size, epoch/step budget and seed. Use a model registry/factory rather than `if model_name == ...` branches throughout training code. Store the full resolved config, code revision, schema hashes and library versions with every checkpoint. CPU mode must work for smoke tests; GPU acceleration is optional for larger training campaigns.

**Completion evidence:** tiny training run completes, resumes, evaluates and exports a checkpoint; identical seeds/configs are reproducible within documented backend tolerances.

## Day 39: 18/11/2026
**Task: Train a non-neural baseline and neural MLP/DeepSets policy baseline.** Create a per-satellite MLP and a permutation-aware set encoder so performance can be compared against a policy that does not yet use message passing across the contact graph.

**Detailed execution:** Train by behavior cloning on expert data. Test invariance to input ordering, masks for missing agents and variable entity counts. Evaluate on held-out seeds and configuration families. Save per-task and per-scenario metrics, not only aggregate loss. This is the first trained neural result and a baseline for the graph model—not the final “smart swarm” implementation.

**Completion evidence:** reproducible checkpoint and evaluation report for rule-based, MLP and DeepSets policies; permutation and variable-size tests pass.

## Day 40: 19/11/2026
**Task: Implement metadata-aware encoding for thousands of configurable variables.** Build an encoder for parameter tokens using normalized value, validity/missingness, type, unit category, bounds/range metadata, namespace/component embedding and supported-field identity. Aggregate variable-length parameter sets into a parameter-context representation.

**Detailed execution:** Do not create a unique hard-coded neural input column for every possible client variable. The encoder should support a variable number of declared fields while preserving their semantics and schema version. Use stable IDs for known fields and metadata features for registered extensions. Unknown semantics or unsupported component types must trigger a compatibility/OOD result, not be treated as fully understood by the model. Do not rely on parameter display names alone for behavior.

**Completion evidence:** a single model path accepts configs with different numbers of registered fields, invariant fields are order-independent, schema/model compatibility is checked and unrecognized operational semantics are surfaced.

## Day 41: 20/11/2026
**Task: Implement the variable-size graph neural policy.** Represent satellites as nodes, feasible communication/contact/task relationships as edges or typed relations, and node/edge/global features as configured tensors. Use shared message-passing layers and permutation-invariant pooling so the same weights can run on different fleet sizes.

**Detailed execution:** Implement batching via edge indices and graph masks; do not pad to a single fixed satellite count unless a benchmark-specific adapter needs it. Use stable feature names/indices generated from schemas. Keep task scoring/action selection modular so adding a registered task type does not alter every graph layer. Compare graph policy results with Day 39 baselines on identical episodes.

**Completion evidence:** GNN forward/training/evaluation works for multiple fleet sizes, entity order permutations preserve expected behavior and the model accepts graph structures with different edge counts.

## Day 42: 21/11/2026
**Task: Add temporal memory to the graph policy.** Implement a recurrent GRU-based policy head first, with optional Transformer temporal encoder behind the same model interface. Temporal state must be isolated by simulation episode and agent identity.

**Detailed execution:** The model should use time-aligned observations/action history available to the agent, not future event labels. Test sequence lengths, truncated episodes, reset masks, missing observations and variable fleet membership. Keep the GRU model as the primary sequence baseline; only promote a Transformer variant if evaluation shows a measurable benefit on the current data/compute budget.

**Completion evidence:** recurrent model trains on sequential rollouts, episode resets prevent hidden-state leakage, and a model-family config can switch temporal encoders without changing the environment contract.

## Day 43: 22/11/2026
**Task: Build systematic architecture and hyperparameter sweeps.** Add a sweep runner covering MLP/DeepSets, GNN, GNN+GRU and GNN+attention variants, as well as selected hidden sizes, learning rates, loss weights and regularization settings.

**Detailed execution:** Use a bounded search budget and record failed runs, not just winning trials. Keep training and validation strictly separated; select checkpoints by predeclared validation metrics and only report the held-out test once the selection is frozen. Track GPU/CPU time and memory. The run manager must support resuming after interruption and avoid checkpoint filename collisions.

**Completion evidence:** sweep results are machine-readable, runs are resumable, selection criteria are applied consistently and each selected checkpoint maps back to its full training configuration.

## Day 44: 23/11/2026
**Task: Expand domain randomization and parameter-space coverage.** Add structured sampling for thousands of config entries across orbit, sensor, energy, storage, compute, target density, task deadlines, network capability and fault intensity. Use correlated distributions and conditional constraints where the simulation semantics require them.

**Detailed execution:** Avoid creating combinations that are invalid by construction. Keep the sampling distributions versioned and report coverage by parameter family, joint slices and scenario family. Include nominal, boundary, noisy, degraded and rare-event conditions. Use train-only distributions for training generation and independently held-out ranges/combinations for robustness evaluation.

**Completion evidence:** large campaign covers configured parameter families, invalid combinations are rejected explicitly, and coverage reports show which regions were sampled or left unexplored.

## Day 45: 24/11/2026
**Task: Train the imitation-learning policy across randomized configurations.** Train the parameter-conditioned GNN+GRU model across varied satellite counts, task loads, sensor/resource settings and communication conditions. Use curriculum stages from small/easy missions to larger/harder episodes.

**Detailed execution:** Record reward and supervised loss separately, evaluation by scenario family, convergence curves, parameter coverage and seed-to-seed variation. Use balanced sampling so common easy scenarios do not dominate rare but important conditions. Add checkpoint selection and automatic stop criteria. Do not describe more training steps as better unless held-out metrics improve.

**Completion evidence:** trained policy checkpoint, reproducible training manifest, curriculum progression report and held-out evaluation against the expert and non-neural baselines.

## Day 46: 25/11/2026
**Task: Evaluate generalization to unseen fleet sizes and parameter combinations.** Create a frozen test suite including fleet sizes not used in the same proportions during training, new random seeds, rare event arrangements, resource limits near boundaries and combinations held out from training.

**Detailed execution:** Report each slice independently. Measure task coverage, event response time, duplicate assignments, missed deadlines, resource cost, constraint attempts and policy inference latency. Test configurations with new registered fields separately from ordinary numeric extrapolation: if new semantics are unsupported, the system must declare incompatibility or use its safe fallback. Do not conflate successful parsing with successful generalization.

**Completion evidence:** generalization report identifies in-distribution and out-of-distribution cases, includes baselines and confidence intervals where sample size supports them, and lists known failure slices.

## Day 47: 26/11/2026
**Task: Implement a centralized-training/decentralized-execution reinforcement-learning path.** Start with a simple PPO implementation using a centralized critic and shared per-satellite actor; use the graph encoder where supported. Maintain a transparent non-learning policy as a baseline.

**Detailed execution:** Keep environment transitions and reward terms separate from the algorithm. Add rollout storage, advantage estimation, clipped objective, value loss, entropy regularization, gradient clipping and checkpoint recovery. Test on a small deterministic environment before launching large runs. Keep training-time global information out of each deployed agent’s observation/action path.

**Completion evidence:** a small PPO run learns on a known toy task, rollout/reward tests pass, checkpoints resume and the deployed policy receives only its allowed observation.

## Day 48: 27/11/2026
**Task: Implement constrained action selection and the independent runtime safety shield.** Define feasible-action masks and a post-policy validator for configured resource floors, task ownership rules, deadlines and permitted action types. The learned policy proposes; the shield independently accepts/rejects and supplies a documented fallback.

**Detailed execution:** Keep policy scores and safety decisions in separate modules and logs. Ensure the shield cannot be disabled by a model output. Add test actions designed to cross each boundary and verify rejection. Where state uncertainty means a constraint cannot be checked, return “not certifiable/blocked” rather than silently approving the action. This is a simulator-level constraint mechanism, not a claim that physical collision/fuel safety is universally guaranteed.

**Completion evidence:** all action types pass through the shield, boundary tests prove rejection/acceptance behavior, and traces expose proposed action, shield result and fallback.

## Day 49: 28/11/2026
**Task: Train the reinforcement-learning policy on progressively harder swarm episodes.** Use curriculum learning and domain randomization to grow from small, well-connected scenarios to larger fleets, longer network gaps, resource scarcity and competing event priorities.

**Detailed execution:** Run multiple seeds, save intermediate checkpoints and evaluate on a fixed validation suite every configured interval. Avoid reward-only selection: use the full metrics table and constraint-violation counts. Track reward components to catch reward hacking—for example, minimizing resource use by never observing anything. Keep test configurations out of the curriculum and reward tuning loop.

**Completion evidence:** resumable multi-seed training campaign, validation curves and frozen checkpoints selected by predeclared metrics rather than final-test performance.

## Day 50: 29/11/2026
**Task: Run reward, curriculum and algorithm ablations.** Compare imitation-only, PPO-finetuned, no-communication-feature, no-temporal-memory, no-parameter-context and no-safety-shield diagnostic variants. The no-shield version is for offline measurement only and must not be presented as the usable policy.

**Detailed execution:** Change one factor at a time for the primary ablations and record every configuration. Evaluate whether reward terms lead to the intended behavior. A learned policy that scores well only under one parameter range fails the goal of a configurable simulator. Use repeat runs and report uncertainty; don't silently discard unstable runs.

**Completion evidence:** ablation table generated from raw results, policy choice justified by measured trade-offs and any unstable/unhelpful variants retained in the report as negative results.

## Day 51: 30/11/2026
**Task: Test model compatibility, calibration and safe fallback for client-supplied configurations.** Add a model manifest with accepted simulation schema/component versions, training parameter-space range, input schema hash, checkpoint hash and expected feature encodings. Add a compatibility checker before inference.

**Detailed execution:** Distinguish ordinary continuous-value extrapolation from an unknown component/field semantic. Add an OOD score using a validated method such as held-out distance/ensemble disagreement; treat it as a warning/fallback signal, not a magical guarantee. Unsupported configs must run baseline policy or enter blocked mode according to configuration. Preserve the exact fallback reason in the event trace.

**Completion evidence:** compatibility tests cover matching schema, compatible extension, unsupported component, out-of-range values and mismatched checkpoint hashes; each case yields deterministic behavior.

## Day 52: 01/12/2026
**Task: Conduct a full neural-policy comparison on the frozen evaluation suite.** Compare fixed-priority, greedy, leases-only/reference policy, MLP/DeepSets, GNN, GNN+GRU, imitation-only and PPO-finetuned versions where applicable.

**Detailed execution:** Use the same scenario seeds, compute budgets and environmental conditions for paired comparisons. Report mission metrics, failure rates, confidence intervals, parameter/fleet-size slices and inference cost. Include no-learning baselines. Freeze the policy candidate only if it gives a measured benefit on the declared objectives without unacceptable safety-shield rejection or robustness regressions.

**Completion evidence:** reproducible benchmark command, raw per-run result files, aggregated comparison report and explicit retained/rejected model versions.

## Day 53: 02/12/2026
**Task: Implement the adversarial scenario grammar and mutation engine.** Represent faults as typed events with target selector, start condition, duration, intensity, dependency and scope. Generate mutations such as shift timing, extend duration, change target, combine faults, delay delivery or trigger at a policy transition.

**Detailed execution:** Use a mutation registry and valid operator set; do not implement an `if/else` branch per fault type in the search loop. Revalidate each mutated scenario through the same config/constraint engine. Give every mutation a deterministic ID and parent ID so a discovered failure can be traced back to the seed scenario. Keep the random-search baseline using exactly this same mutation space.

**Completion evidence:** valid scenarios can be mutated reproducibly, invalid mutations are rejected with reason codes and mutation ancestry is saved in output metadata.

## Day 54: 03/12/2026
**Task: Build the search objective and collect labeled adversarial-search data.** Score a scenario by whether it triggers a new invariant violation, whether the failure is distinct, the number of prior executions needed, severity/impact under declared rules, and computational cost.

**Detailed execution:** Keep raw components of the score visible; avoid hiding arbitrary weights inside code. Generate a baseline campaign using random mutation and fixed worst-moment strategies. Record both failures and non-failures so a learned ranking model does not train solely on positive examples. Deduplicate scenarios by canonical hash and define what counts as a distinct failure family.

**Completion evidence:** versioned objective, labeled search dataset with class balance and provenance, and repeatable random/fixed-search metrics under a fixed simulation budget.

## Day 55: 04/12/2026
**Task: Train a neural candidate-ranking model for adaptive adversarial search.** Train a model to estimate failure likelihood, novelty potential or expected test utility from scenario/mutation descriptors and prior trace summaries. Start with a small MLP/attention-based set model and compare it to simple statistical ranking.

**Detailed execution:** Include data splitting by scenario family to reduce leakage, calibrate prediction confidence, and report ranking metrics and actual downstream discovered failures. Do not mistake prediction accuracy for test effectiveness. Keep the scenario searcher constrained to valid mutation actions and feed each result back into the dataset with an audit record.

**Completion evidence:** saved ranking checkpoint, training manifest, held-out ranking report and an interface that can be disabled to compare against the same non-learning search process.

## Day 56: 05/12/2026 — G3 TRAINED SWARM POLICY GATE
**Task: Freeze and verify the best trained swarm policy candidate.** Run the complete neural-policy comparison, compatibility checks, action-shield suite and held-out generalization suite from a clean artifact set.

**Detailed execution:** Verify each checkpoint against its input schema and training manifest. Re-run selected evaluations from saved seeds and compare output hashes where deterministic behavior is expected. Any model that lacks acceptable generalization must be restricted to its validated parameter envelope or excluded. The fact that a model trained successfully is not enough to pass G3.

**Completion evidence:** versioned policy artifact, manifest, accepted parameter envelope, baseline comparison and test reports; model is promoted only if measured acceptance criteria are met, otherwise use the strongest simpler baseline and preserve the failed candidate for analysis.

## Day 57: 06/12/2026
**Task: Implement guided adaptive search with fallback to random exploration.** Integrate the trained ranker with the scenario mutation engine. Select high-potential candidates while preserving an exploration fraction for unexpected failure families.

**Detailed execution:** Bound candidate count, simulation budget, memory and mutation depth. Prevent the learned searcher from bypassing config validation or modifying the evaluation protocol. Log why each candidate was selected, its predicted score, actual outcome and policy checkpoint. Support an ablation switch between random search, fixed heuristics and learned ranking.

**Completion evidence:** guided campaign runs end-to-end, all candidates are schema-valid, every decision is logged and disabling the learned ranker returns to the same random baseline path.

## Day 58: 07/12/2026
**Task: Implement failure shrinking/minimization.** Given a failing trace, systematically remove or simplify events, satellites, faults, timing intervals and parameter overrides while checking whether the same invariant still fails.

**Detailed execution:** Use a generic reducer interface and domain-specific shrink operators registered by component. Preserve the failure signature/invariant and relevant simulation seed. Avoid declaring a case minimal after only one greedy pass; report the reduction strategy and whether minimality is local/approximate or formally established. Cache test results by canonical scenario hash to avoid rerunning identical candidates.

**Completion evidence:** planted multi-event failure reduces to a smaller reproducible case, minimization logs show every accepted/rejected reduction and rerun reproduces the same invariant violation.

## Day 59: 08/12/2026
**Task: Implement counterfactual intervention replay.** Re-run a minimized failure with one defined intervention changed—for example, removing a link cut, changing task-claim timing or restoring one message—to investigate whether that intervention is associated with the violation.

**Detailed execution:** Add negative controls that change unrelated variables and a no-change replay. Keep all other random streams/config fields fixed where meaningful. Report “supported causal hypothesis” only when the intervention result matches the predeclared condition; do not call a single replay proof of universal causality. Preserve the original and intervention traces side by side.

**Completion evidence:** intervention runner, no-change and unrelated-change controls, reproduced comparison traces and a structured conclusion that records assumptions and uncertainty.

## Day 60: 09/12/2026
**Task: Add differential and metamorphic testing.** Run policy versions or implementations on identical scenarios and compare events, task completion, resource use and invariant results. Implement metamorphic transforms only where an expected relation is justified, such as renaming non-semantic IDs or permuting independent input records.

**Detailed execution:** Store the transform definition, preconditions and expected relation. Do not assume every changed seed or reordered event should produce identical behavior; only test properties that the simulator contract guarantees. Provide a report showing exact first-divergence index and differing fields. Convert confirmed regressions into permanent fixtures.

**Completion evidence:** differential runner and metamorphic transform registry work on known positive/negative cases; saved failing examples become automated regression tests.

## Day 61: 10/12/2026
**Task: Build temporal invariant monitoring and a configurable rule registry.** Support sequence rules for task expiry, duplicate ownership, resource thresholds, stale observations, delayed recovery and deadline violation. Keep state-based invariants and temporal invariants separate but interoperable.

**Detailed execution:** Define the minimum temporal rule language with typed events, time windows, predicates and bounded temporal operators. Parse and validate rules instead of evaluating arbitrary user expressions. Keep per-rule severity and assumptions in config. Ensure a client can add a supported declarative rule without editing the monitor loop; unsupported operators must fail clearly.

**Completion evidence:** rule parser/validator, temporal monitor tests, positive and negative rule examples and event-level violation records with exact timestamps.

## Day 62: 11/12/2026 — G4 ADAPTIVE TEST SEARCH GATE
**Task: Compare learned adversarial search against random and fixed strategies under equal budgets.** Run blind held-out scenario families and compare distinct failures, time to first failure, minimized case size, repeated discovery rate, compute time and number of simulator executions.

**Detailed execution:** Freeze search-model parameters before the test campaign. Preserve all seeds and raw traces. Include confidence intervals or descriptive uncertainty appropriate to the number of runs. If learned search does not outperform baselines, keep it as an optional experimental tool or fall back to random/mutation search; never manufacture a positive result by changing the metric after the run.

**Completion evidence:** benchmark report generated from the frozen campaign, with actual resource costs, unique failure counts and a clear retain/reject decision backed by results.

## Day 63: 12/12/2026
**Task: Implement a neural trace encoder for failure triage.** Encode event timelines, invariant IDs, action records, resource changes and communication events into sequences or event graphs. Train a temporal CNN/GRU/Transformer encoder to predict broad failure families when labeled data supports it; otherwise train a representation model for clustering and keep its output advisory.

**Detailed execution:** Generate trace labels from explicit simulator ground truth and invariant metadata, never from model predictions. Hold out entire scenario families. Compare against rule-based signatures and simple statistical/TF-IDF-style baselines. Include calibrated confidence and an “unknown family” path. Do not allow a triage model to decide whether a failure is real; the invariant monitor remains authoritative.

**Completion evidence:** trained trace-model artifact (or documented no-go if labels are insufficient), held-out evaluation report, feature/data manifest and tests proving triage cannot suppress a recorded invariant violation.

## Day 64: 13/12/2026
**Task: Implement failure clustering and duplicate-report detection.** Use normalized trace features and/or learned embeddings to group similar failures and reduce repeated findings. Maintain representative counterexamples and cluster confidence.

**Detailed execution:** Compare simple distance-based clustering with the learned embedding if available. Make cluster thresholds configurable and report uncertain assignments. Do not discard raw findings when clustering; retain links to every member trace. Evaluate cluster purity/consistency on known synthetic failure families and include cases where different root causes produce similar symptoms.

**Completion evidence:** repeatable clustering report, cluster membership manifest, retained raw trace links and measured cluster-quality results on generated labeled examples.

## Day 65: 14/12/2026
**Task: Build the evidence pack, integrity ledger and verifier.** Package scenario config, seeds, tool/model/schema versions, policy/checkpoint hashes, run traces, invariant findings, minimized counterexamples, interventions and summary metrics. Use a hash-chained event/evidence manifest and a verifiable signature for the final package where keys are configured.

**Detailed execution:** A hash chain alone is not proof of who created a report; keep signature verification and key provenance separate. Make the verifier check schema, hashes, trace reproduction and expected outputs. Use canonical serialization and never include secrets in the package. Generated reports must read saved raw results rather than fabricate numbers or reuse stale summaries.

**Completion evidence:** tampering with a record causes verification failure; an untouched sample pack verifies from a clean environment and reproduces its headline metrics from raw files.

## Day 66: 15/12/2026
**Task: Add multi-fidelity execution and escalation.** Define L0 fast event-driven simulation, L1 geometry-driven orbital/contact simulation and optional L2 additional dynamics/noise fidelity. Escalate selected failures from faster models to more detailed ones and classify each finding as persists, disappears or inconclusive.

**Detailed execution:** Keep each fidelity level explicit in config and result manifests. Model changes between levels must be intentional and documented in code metadata, not hidden behind unexplained defaults. A finding disappearing at higher fidelity does not necessarily prove the lower-level result was useless; it indicates a model-sensitivity issue to report. Do not claim flight-grade fidelity merely because more equations were added.

**Completion evidence:** fidelity registry, escalation runner, same-scenario cross-fidelity reports and tests that prove the report records the model level and assumptions for every run.

## Day 67: 16/12/2026
**Task: Add CI regression gates for simulation, models and evidence packs.** Build automated checks for formatting/types, unit/property tests, deterministic replay, schema compatibility, tiny model-training smoke test, checkpoint loading, invariant regression cases and evidence verification.

**Detailed execution:** Keep full dataset generation and long training sweeps out of every pull-request run; add separate manually triggered or scheduled commands for heavier workloads, with no external-service dependency required for the core path. Store small deterministic fixtures in the repository and keep large generated datasets/checkpoints outside version control with manifests. Add a regression fixture for each fixed failure.

**Completion evidence:** clean CI run passes from a fresh checkout; intentional breaking changes fail the appropriate gate and produce understandable logs.

## Day 68: 17/12/2026
**Task: Run scalability, stress and fault-combination campaigns.** Exercise large fleets, thousands of registered variables, high task volume, dense/sparse contact graphs, prolonged partitions, event bursts, sensor outages and resource depletion combinations.

**Detailed execution:** Measure simulation throughput, memory, rendering responsiveness, policy inference latency, trace size and test-search cost. Use controlled scaling points and record machine/dependency metadata. Ensure all queues and event stores have explicit bounds or documented growth behavior. Separate simulator bottlenecks from frontend bottlenecks and model-inference bottlenecks.

**Completion evidence:** benchmark matrix with raw measurement outputs, stress test results, known scaling limits and no unbounded memory/queue growth in defined maximum test campaigns.

## Day 69: 18/12/2026
**Task: Perform an end-to-end integration and defect-fix pass.** Run the complete sequence: load client config, create the visible orbital scene, execute event/task behavior, apply simulated link faults, run a policy, monitor invariants, search/minimize a failure, replay an intervention, train/load selected models, and generate/verify an evidence pack.

**Detailed execution:** Execute from a clean environment, not from a long-lived development process with hidden cached state. Fix integration defects before visual polish. Regenerate outputs after any code or model change that affects results. Ensure the UI displays the actual core state and actual recorded findings. Mark any advanced model/module that fails its acceptance criteria as experimental or disabled rather than letting it silently replace a stable baseline.

**Completion evidence:** one-command or clearly scripted end-to-end smoke path passes, every stage's outputs are trace-linked and an evidence pack verifies independently.

## Day 70: 19/12/2026 — G5 INTEGRATED BUILD GATE
**Task: Freeze a runnable Constellab candidate with visual simulation, configurable virtual spacecraft, trained model artifacts and the testing engine integrated.** Run the complete automated suite and the demo scenario from a clean checkout. Confirm no stage requires physical hardware, cloud access or untracked local files.

**Detailed execution:** Verify that the visual application still works with ML modules disabled, the policy still runs headlessly, simulator configs remain schema-versioned and supported parameters all have consumers. Re-run key model and search evaluations from saved manifests, check hashes and regenerate the final metric report from raw results. Do not claim that all models generalize to arbitrary customer configurations; state the validated config envelope and enforce compatibility/fallback behavior at runtime.

**Completion evidence:** tagged candidate, clean-build/test logs, schema and plugin manifests, model manifests/checkpoints, reproducible demo scenario, benchmark outputs, verified evidence pack and a list of known technical limitations derived from actual tests.

---

## Required training and data-generation commands

The exact CLI names may follow the implementation, but the final repository must provide equivalent runnable commands for these workflows. Do not leave them as examples that cannot execute.

```bash
# Validate a client scenario and print all parameter/configuration errors
python -m Constellab.cli validate scenarios/visual_orbit_demo.yaml

# Run one deterministic simulation and save the canonical trace
python -m Constellab.cli run scenarios/wildfire_partition.yaml --seed 7 --out runs/seed-7/

# Generate a resumable set of randomized training episodes
python -m Constellab.ml.generate --config ml/configs/dataset.yaml --resume

# Train a selected registered model from a versioned training configuration
python -m Constellab.ml.train --config ml/configs/gnn_gru_bc.yaml

# Evaluate checkpoints against the frozen benchmark suite
python -m Constellab.ml.evaluate --suite evaluation/frozen_suite.yaml --checkpoint models/candidate/

# Search for failures using random or learned candidate ranking
python -m Constellab.cli search scenarios/search_suite.yaml --strategy adaptive --budget 10000 --seed 7

# Minimize a failing scenario and replay the causal intervention
python -m Constellab.cli shrink evidence/failure-001/ --out evidence/minimized-001/
python -m Constellab.cli why evidence/minimized-001/ --intervention remove_link_cut

# Verify all evidence hashes and re-run the reproducibility checks
python -m Constellab.cli verify evidence/final-pack/
```

## Final acceptance conditions

- The initial visual simulator is completed before simulated crosslinks or swarm coordination are added.
- The simulator has one canonical clock/state source and reproducible numerical state.
- Scenario and client parameters are schema-driven, validated, unit-aware and versioned.
- Thousands of registered/configured fields can be loaded and searched without hand-coded per-field UI logic; every behavior-changing parameter has a registered consumer.
- Simulation components and scenario/fault behaviors are registered through typed plugin interfaces rather than a giant per-variable/per-satellite `if/else` structure.
- Virtual fleet size and graph topology can change without rebuilding a fixed-size neural input layer.
- Neural training is a repeatable pipeline with held-out configurations, multiple seeds, checkpoints, manifests, baselines, ablations and OOD handling.
- The learned policy cannot bypass the deterministic action shield or invariant monitor.
- The learned adversarial search is evaluated against random and fixed baselines under comparable budgets.
- Every detected failure can be traced to a scenario/seed and, where supported, minimized and replayed.
- Evidence can be verified from a clean environment; metrics are computed from saved raw results.
- Any feature/model that does not pass its evidence gate remains experimental or disabled instead of being described as complete.
