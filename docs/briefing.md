# Constellab: Final Product, Engineering & Research Briefing

**One sentence:** Constellab is a software-only crash-test lab for autonomous satellite swarms: it deliberately searches for failures in simulation, minimizes and investigates them, and produces evidence that another person can independently replay and verify.

**Product boundary:** Constellab is a testing and verification platform, not a satellite, not a flight-control product, and not a certification authority. All spacecraft, sensors, orbital conditions, communication links, resources and failures are simulated. No hardware or hardware-in-the-loop testing is required.

**Current status:** design and research stage. Nothing is a shipped feature unless explicitly marked **WORKING**. Code snippets are starter sketches, not production components. Claims tagged **(H)** are hypotheses to test with users. Research claims, competitor details, and patent leads must be re-verified against primary sources before publication.

**Development-order decision:** build a visible orbital simulation first. The first deliverable must render Earth and moving virtual satellites, let the user inspect them, and control simulated time. Do **not** implement satellite-to-satellite communication, distributed coordination, stakeholder outreach or customer interviews at the beginning. Add the communication model after the visual/orbital foundation works, and approach stakeholders only after there is a credible demonstration of both the visual simulation and at least one reproducible swarm-policy failure.


---

## 0. Who should read what

| You are... | Read this | Time |
|---|---|---|
| Someone with **zero background** | Part 1 (the story) and the Glossary at the end | 10 minutes |
| A **client** or buyer | Part 1, then Part 2 | 20 minutes |
| A **developer** building it | Part 1, then Parts 3 and 4 (code and the week-by-week plan) | 45 minutes |
| Someone deciding whether to **trust the claims** | Part 5 (honest limits) and the Evidence list | 10 minutes |

If you only have two minutes: read the box in Part 1.1 and the visual-first checklist in Part 4.1.

---

# PART 1: The story (for everyone)

## 1.1 The 60-second version

> **Picture 12 small satellites circling Earth, all working together to spot wildfires.**
> They are supposed to talk to each other, but they fly so fast that their radio links keep cutting out, like a group chat in a tunnel.
> When the chat drops, two satellites can each spot the same fire, each decide "I'll handle it," and both burn fuel to chase it. Nobody noticed because they could not talk.
> **Constellab is the test lab that makes this happen on purpose, in a computer simulation, before the satellites ever launch.** It cuts the "group chat" at selected moments, watches the satellites' modeled decisions, flags monitored-rule violations, searches for a minimal failing case, and creates an evidence pack that another person can replay and verify.

## 1.2 An everyday analogy

Think of a **group of friends doing a scavenger hunt, each with their own phone**.

| In the analogy | In real life |
|---|---|
| Friends with phones | Satellites in a swarm |
| The group chat | Radio links between satellites ("crosslinks") |
| Phone loses signal in a tunnel | A **partition**: part of the swarm cannot talk to the rest |
| Two friends both buy the same gift because neither saw the other's message | **Duplicate tasking**: wasted fuel and time |
| "Reserve this item for 15 minutes" sticker | A **lease**: a temporary claim that expires |
| House rules ("never go below 20% battery") | **Invariants**: rules that must never be broken |
| A prankster who unplugs the router at the worst moment | The **nemesis**: our tool that cuts links on purpose |
| Rolling the same dice again to replay a game exactly | **Seeds**: a replayable simulation |
| "Find the smallest recipe that still burns the cake" | **Shrinking**: reduce a failure to its simplest form |
| "Rewind the tape, change one thing, press play" | **Intervention replay**: test a candidate explanation by changing one modeled factor |
| A notebook where each page contains a fingerprint of the page before | A **hash-chained ledger**: changes can be detected when the chain is checked against a trusted final hash or signature |

The tile in the name helps too: a *Constellab* is one small tile of a mosaic. Each satellite holds a **partial picture** of the mission. Constellab checks that the tiles still fit together after the satellites reconnect.

## 1.3 Why this matters now

- Swarm autonomy is real: NASA's Starling mission demonstrated distributed autonomy with four CubeSats. In August 2026, Sedaro, Shield AI and NOVI Space announced an on-orbit demonstration using one physical NOVI satellite plus five virtual satellites in a six-member constellation model.
- A September 2026 paper evaluates a CRDT-based shared-state service in a simulated/emulated 66-satellite constellation.
- These projects show that autonomy, simulation and distributed-state research already exist. A possible gap to investigate is an independent, repeatable test workflow that actively searches for autonomy failures, minimizes them and packages the evidence. **(H)** whether teams need and will pay for this workflow.

## 1.4 What Constellab is NOT

- **Not a satellite.** No hardware at all.
- **Not merely a dashboard or a 3D globe.** A functional visual orbital simulator is the first deliverable and the product's front door. The long-term product is the testing workflow behind it: controlled faults, rule checking, failure investigation and replayable evidence. The visual layer must display real simulation state, not a disconnected animation or decorative mock-up.
- **Not "the first system that does everything."** Competitors exist (Part 5). We aim to be the *independent tester*, not the only player.
- **Not a certification stamp.** We produce evidence a reviewer can re-run. We do not claim NASA or military approval.

---

# PART 2: For clients

## 2.1 The problem in business terms

You are building or buying software that lets satellites make decisions by themselves. Before anyone lets it run in orbit, a reviewer will ask: **"What does it do when things go wrong?"** Today answering that means:

- weeks of custom simulation work, done late
- failures found by luck
- reports nobody else can reproduce

## 2.2 What you get

| Deliverable | What it is, in plain words |
|---|---|
| **Test scenarios** | Realistic situations (a wildfire spotted during a link outage, a satellite dying mid-task) written down in a simple file |
| **A failure list** | Each violation of a configured, monitored rule found in the modelled runs, with a one-line description |
| **A minimized counterexample** | Each failure reduced by the implemented shrinker to a smaller case that still fails; the report states what was minimized and what was not |
| **A counterfactual investigation** | Candidate explanations tested by replaying the same scenario with a controlled change, plus negative controls and the limits of the inference |
| **Policy comparisons** | Side-by-side outcomes when supported baselines are run against the same scenarios and seeds |
| **Adversarial search results** | Once implemented, a record of generated fault sequences, search budgets, new failures found and replays that confirm them |
| **Failure clusters and regression cases** | Once implemented, related failures grouped for triage, with confirmed examples saved so future changes can be tested against them |
| **A sealed evidence pack** | A folder with the scenario, settings, versions, results, hashes, signatures where enabled, and verifier/replay instructions so another person can check the pack's integrity and reproduce the test |

## 2.3 What you give us

1. **Your swarm software, or a way to call it.** Even a simple rule-based version is fine.
2. **Basic facts:** how many satellites, rough orbits, sensors, how often they can talk.
3. **Your rules:** what must never happen (for example: battery below a set level, two satellites chasing the same target).
4. **One person** who can review results with us.

## 2.4 What a pilot looks like (proposed, H)

| Week | What happens |
|---|---|
| 1 | We set up your scenario and run a baseline: your swarm with perfect communication |
| 2 | We add communication outages and compare |
| 3 | We hunt for the worst cases, shrink them, and explain them |
| 4 | We hand over the evidence pack and walk your team through it |

## 2.5 What we do NOT promise

- We **cannot prove** your hardware will survive in orbit. A simulation is a model, and every report states how detailed the model was.
- We **cannot prove** a rule is never broken. If there are zero failures in 1,000 independent trials drawn from the same defined test distribution, the rule-of-three approximation gives a one-sided 95% upper bound of about 0.3% for that distribution. This depends on the statistical assumptions and says nothing about failures the scenario/model does not represent.
- We do **not** certify anything.
- We do **not** replace your own testing. We add an independent check.

## 2.6 Keeping your information safe

- Your software and scenarios stay yours. We can run everything on your own machines if you prefer. **(H)** which customers need this.
- Reports contain hashes (digital fingerprints), not your source code.
- Anything involving defense or export-controlled work needs a legal check first.

## 2.7 Client FAQ

**Is this just another simulator?** No. A simulator shows what happens. Constellab is built to *attack* your swarm's decisions and report failures, in the way a security tester attacks software.

**Will this work with our own autonomy?** The plan is a single narrow interface: you give us "what the satellite sees" and we take back "what it decides." **(H)** that this fits real systems.

**How is it different from Sedaro or Slingshot?** They build digital twins and autonomy infrastructure. We aim to be the independent tester that works with any of them. We have not yet confirmed customers see it that way. **(H)**

**How much does it cost?** To be discovered. The idea is: free open-source core, paid hosting for big runs, and enterprise licences for private use.

---

# PART 3: For developers: what to build

## 3.1 The big picture: build order and final architecture

The architecture has two connected layers, but they are **not built in the same order**:

1. **Visual Orbital Simulator (build first):** a functional 3D scene renders Earth, virtual satellites, orbit paths, labels, a camera, simulated time controls and a selected-satellite inspector. It is driven by actual orbital/simulation state. At this stage, satellites do not communicate with one another and there is no swarm coordination logic.
2. **Constellab Bench (build after the visual base):** the same simulation state grows an event log, policy interface, simulated communication model, fault injection, rule monitoring, failure search, replay, reporting and evidence verification.

```text
                      USER
                        │
                        ▼
       ┌───────────────────────────────────┐
       │ VISUAL ORBITAL SIMULATOR          │  BUILD FIRST
       │ Earth • satellites • orbit paths  │
       │ camera • labels • time controls   │
       │ selected-satellite inspector      │
       └─────────────────┬─────────────────┘
                         │ reads/displays
                         ▼
       ┌───────────────────────────────────┐
       │ CANONICAL SIMULATION STATE        │
       │ simulation clock • orbital state  │
       │ units • IDs • model assumptions   │
       └─────────────────┬─────────────────┘
                         │ extended later with events
                         ▼
       ┌───────────────────────────────────┐
       │ Constellab BENCH                     │  BUILD SECOND
       │ scenario + policy adapter         │
       │ modeled links + fault injection   │
       │ state/temporal rule monitors      │
       │ trace store + deterministic replay│
       │ search + shrink + counterfactuals │
       │ comparisons + failure triage      │
       │ report + evidence ledger/verifier │
       └─────────────────┬─────────────────┘
                         ▼
              RE-RUNNABLE EVIDENCE PACK
```

The visualization is a real first deliverable, not final polish. However, rendering quality must not outrun the simulation: every displayed satellite position, orbit path, status and later network link must come from the canonical simulation state. Rendering frame rate must never change simulation-time results or seeded outcomes.

**Recommended implementation boundary:** use a browser renderer such as TypeScript + Three.js for the 3D scene and a stable, versioned state schema for the simulation. The canonical simulation logic can live in the chosen core runtime; keep exactly one source of truth for orbital propagation and simulated time. If the visual client and core run as separate processes, connect them locally first—no cloud service is required. Keep the first model simple and explicit, then increase orbital fidelity only when the use case requires it.

**Explicitly out of scope for the first visual milestone:** inter-satellite messages, communication-link overlays based on modeled network state, auctions, leases, distributed consensus/shared-state logic, AI-trained search, image AI and stakeholder outreach. Those come only after the visible orbital foundation works. Static orbit lines are allowed; they are not communication links.

The two product components remain:

- **Bench** (primary product): scenario-driven testing, fault injection, invariant monitoring, failure search, shrinking, counterfactual investigation, comparisons, reporting and evidence verification.
- **Fabric** (optional reference policy): a small open-source example of a swarm policy that handles task claims and partitions. It demonstrates that Bench can find and measure meaningful behavior. A decision gate determines whether Fabric deserves continued development.

The research extension is **adaptive adversarial testing**: Constellab learns or searches for fault sequences that reveal failures more efficiently than random or fixed scenarios. AI/ML is used to improve test generation and failure triage—not to bypass deterministic safety checks or to claim that a policy is safe merely because a model says so.

## 3.2 Suggested folder layout

```text
Constellab/
  frontend/      scene/ camera/ controls/ inspector/ state_client/
  core/          sim.py  clock.py  rng.py  orbital_state.py  events.py
  schemas/       simulation_state.schema.json  policy.schema.json
  adapters/      base.py  python_policy.py  examples.py
  swarm/         facts.py  leases.py  margins.py       # Fabric reference policy
  scenarios/     visual_orbit_demo.yaml  wildfire_partition.yaml  node_loss.yaml
  nemesis/       partitions.py  faults.py  strategies.py
  search/        mutations.py  guided_search.py  scoring.py
  probe/         invariants.py  temporal.py  runner.py
  shrink/        events.py  time.py  satellites.py
  why/           graph.py  replay.py  interventions.py
  differential/  compare.py  metamorphic.py
  fidelity/      levels.py  escalation.py  model_assumptions.py
  triage/        signatures.py  clustering.py  summaries.py
  ledger/        chain.py  sign.py  verify.py
  reports/       metrics.py  html.py  schemas.py
  integrations/  cli.py  github_actions/
  policies/      greedy.py  auction.py  leases_only.py  fabric.py
  tests/         unit/  property/  scenarios/  regression/
```

Keep the implementation small. Start with the visible orbital simulator and its canonical state model; do not begin with polished cinematic graphics, Rust, C++, hardware-in-the-loop or a large distributed deployment. The visual scene must feed the eventual test engine; do not build a throwaway animation and then rewrite the simulation separately. After the orbital foundation works, add the deterministic event/test engine until it can find one real failure in a simple policy and produce a re-runnable report.

## 3.3 First build: the visible orbital simulation

This section takes priority over the test-engine steps below. Implement a minimum visual simulator before implementing modeled satellite communication or distributed swarm behavior.

### Minimum scene

- A 3D Earth sphere with a placeholder texture if necessary; art quality can improve later.
- A starfield/background only if it does not distract from readability or performance.
- Four virtual satellite models, each with a stable ID and clearly distinguishable marker/model.
- Visible orbital paths and current satellite positions derived from the same orbital state.
- Orbit/zoom/pan camera controls, a reset-camera action, readable labels and selection of an individual satellite.
- A selected-satellite panel showing at least its ID, orbit/model parameters, simulated position and current simulation time.
- Pause, resume, reset and a small set of simulation-time speed controls.
- A deterministic clock: with the same initial state and time, each satellite appears in the same position regardless of rendering frame rate.

### Physics and visuals: keep the first version honest

Start with a deliberately simple orbit model, such as circular two-body motion, and document its assumptions. The purpose of the first milestone is to render moving objects whose positions come from a real model—not to claim mission-grade orbital accuracy. Upgrade to Keplerian propagation and documented reference frames/time conventions before using orbital geometry to derive communication windows. Avoid inventing realistic values: mark example orbital parameters as illustrative.

The renderer must consume a canonical simulation snapshot rather than independently calculating a second set of orbits. The scene should continue to work when the renderer is paused, slowed down or sped up. Do not implement crosslinks or message passing in this milestone; orbit lines represent trajectories only.

### Visual milestone acceptance checklist

- [ ] Earth and four virtual satellites render in a navigable 3D scene.
- [ ] Orbit paths are visible and align with the displayed satellite motion.
- [ ] Pause, resume, reset and time-scale controls work.
- [ ] Selecting a satellite updates a stable inspector panel.
- [ ] The same starting state and simulated time yield the same canonical positions.
- [ ] No inter-satellite communication or swarm coordination is implemented yet.
- [ ] A short screen recording and a clean-start demo are reproducible from the repository.

**Do not polish textures, add a huge star catalog or build a complex solar system before this checklist passes.** A basic but functioning orbital scene is better than a beautiful static mock-up.

## 3.4 Build step 2: the scenario file

A scenario is a plain-text, versioned file. It should be reviewable by a human and replayable by the tool.

```yaml
# scenarios/wildfire_partition.yaml
schema_version: 1
name: wildfire-partition-demo
satellites: 4                    # begin small; scale later
seeds: {start: 0, count: 100}
fidelity: L0                     # L0 fast event model, L1 orbital contacts, L2 detailed model

world:
  event: {type: wildfire, t: 3600, lat: 34.05, lon: -118.24}

contact_plan:
  source: scheduled              # replace with geometry-derived windows at L1
  links:
    - {a: s1, b: s2, start_s: 0, end_s: 7200}

nemesis:
  strategy: random               # random | worst_moment | search-generated
  actions:
    - {type: cut_link, duration_s: 300}

invariants:
  - id: no_duplicate_tasking
    params: {window_s: 600}
    severity: error
  - id: battery_floor
    params: {min_fraction: 0.20}
    severity: error
  - id: expired_lease_not_used
    params: {grace_s: 0}
    severity: error

search:
  enabled: false                 # enable after random baselines are working
  strategy: mutation_search
  budget: {runs: 1000, max_fault_events: 8}
  objective: {maximize: [new_invariant_violations, novel_failure_signatures]}

report:
  save_full_trace: true
  save_counterexample: true
  sign_manifest: false           # enable only after key management is implemented
```

**Important:** start with L0 and four virtual satellites. The example is illustrative, not proof that any particular contact pattern or wildfire dataset is realistic. Geometry-derived contacts, orbital propagation and image inputs are added as a separately validated layer.

## 3.5 Build step 3: make everything replayable

If two runs with the same seed give different results, nothing else works. Every random choice must come from a seeded generator.

```python
import hashlib, random

def sat_rng(seed: int, sat_id: str) -> random.Random:
    """Each satellite gets its own stable random stream from one master seed."""
    s = int.from_bytes(hashlib.sha256(f"{seed}:{sat_id}".encode()).digest()[:8], "big")
    return random.Random(s)

# same seed + same satellite -> same numbers, every time
assert sat_rng(1, "s1").random() == sat_rng(1, "s1").random()
```

**Rules for the sim core:** fixed time step, no real clock, no unordered dictionaries in anything that affects results, record the version of every dependency.

**Test (WORKING idea):** run seed 7 twice, compare the full trace hash. They must match exactly.

## 3.6 Build step 4: the policy interface (how any swarm plugs in)

One narrow door: what a satellite sees goes in, what it decides comes out.

```python
from typing import Protocol

class Policy(Protocol):
    def act(self, obs: dict) -> list[dict]:
        """obs: what this satellite can see right now. Returns actions."""

class GreedyLocal:
    """Baseline B: acts only on what it knows, never reconciles."""
    def act(self, obs):
        actions = []
        for target in obs["visible_targets"]:
            if obs["battery_margin"] > 0.25:
                actions.append({"type": "image", "target": target["id"]})
        return actions
```

This greedy brain is the villain in our demo: it will duplicate work during a partition.

## 3.7 Build step 5: the nemesis (the prankster)

```python
class WorstMomentNemesis:
    """Cut a satellite's links right after it claims a target."""
    def __init__(self, duration_s=300):
        self.duration_s = duration_s

    def on_event(self, event, network):
        if event.kind == "claim_made":
            network.cut(event.sat, reconnect_after_s=self.duration_s)
```

Start with three deterministic/replayable modes: **random**, **geometry-driven** (derived from simulated orbit/contact opportunities), and **worst-moment** (triggered by an event such as a task claim). Then add satellite loss, sensor degradation, delayed or duplicated messages, stale telemetry and command-replay scenarios. Keep each injected fault explicit in the event trace.

The **adaptive search engine** comes later. It mutates candidate scenarios (for example, fault timing, duration, link pair, number of faults and event ordering), evaluates them against a fixed budget, and retains candidates that find a new violation or a distinct failure signature. Begin with simple mutation search and novelty scoring; only train an ML-based generator after a reproducible baseline exists.

## 3.8 Build step 6: the rules (invariants)

An invariant is a check that returns a list of violations. Early checks can examine the finished event log; later checks should also monitor events as the simulation runs so the engine can stop, branch or preserve a failure immediately. **An empty violation list means no violation was observed under that checker and run—not a universal proof that the policy is safe.**

Support two types:

- **State invariants:** a condition on a state, such as battery fraction never dropping below a configured floor.
- **Temporal invariants:** a rule about the order, timing or relationship of events, such as “an expired lease must not authorize a new observation” or “after a reconnect, conflicting claims must be resolved within the configured bound under the scenario's assumptions.”

Keep the rule language deliberately small and explicit at first. Every rule must name its assumptions, units, severity and whether it is an error, warning or metric.

```python
def no_duplicate_tasking(trace, window_s=600):
    """Violation: two different satellites image the same target within window_s."""
    last, bad = {}, []
    for e in trace.events("imaging_started"):
        prev = last.get(e.target)
        if prev and prev[1] != e.sat and e.t - prev[0] <= window_s:
            bad.append((e.target, prev[1], e.sat, e.t))
        last[e.target] = (e.t, e.sat)
    return bad
```

Report results as rates with limits, never as a flat "passed":

```python
def upper_bound_95(failures: int, runs: int) -> float:
    """If failures == 0, the 'rule of three' says the true rate is probably below 3/runs."""
    return 3 / runs if failures == 0 else float("nan")  # use a proper interval otherwise
```

## 3.9 Build step 7: shrink failures to a minimal counterexample

```python
def shrink(scenario: dict, still_fails) -> dict:
    """Remove events one at a time while the failure still happens."""
    events = list(scenario["events"])
    changed = True
    while changed:
        changed = False
        for i in range(len(events)):
            trial = events[:i] + events[i + 1:]
            if still_fails({**scenario, "events": trial}):
                events, changed = trial, True
                break
    return {**scenario, "events": events}
```

Later also shrink time span, number of satellites, number of fault events, message delays and event parameters. “Smallest” is usually relative to the available shrink operations and ordering; report a **minimal counterexample found by this shrinker**, not a mathematically globally smallest case unless that claim is actually established.

## 3.10 Build step 8: rewind, change one thing, replay (the "why" engine)

```python
def intervene(run_config: dict, change: dict):
    """Same seed, one change. If the failure disappears, that change was the cause."""
    return simulate({**run_config, **change})

# Example: did the link cut cause the duplicate tasking?
baseline = intervene(failing_cfg, {})
fixed    = intervene(failing_cfg, {"nemesis": []})     # remove the cuts
confirmed_cause = bool(baseline.violations) and not fixed.violations
```

Report this as **counterfactual evidence**: under the controlled replay and its assumptions, removing the intervention made the failure disappear. This is strong debugging evidence, but not a universal proof of causation in every possible model or real-world system. Also run negative controls: remove unrelated events and verify that the same failure generally persists.

## 3.11 Build step 9: Fabric, the reference swarm brain

Fabric is how a swarm should *behave* during partitions. Three ideas, each simple.

**Idea 1: share facts, not opinions.** Each satellite publishes facts about itself (battery, fuel, how well it can see a target) with a logical clock number. When two satellites reconnect, they merge facts and **the newer fact wins**. The merge must give the same answer in any order:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Fact:
    sat_id: str
    key: str        # e.g. "battery_margin"
    value: float
    stamp: int      # logical clock: bigger = newer

def _rank(f): return (f.stamp, f.value)      # total order: same winner everywhere

def merge_facts(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, f in b.items():
        if k not in out or _rank(f) > _rank(out[k]):
            out[k] = f
    return out
```

**Idea 2: decide with a pure score.** The score uses only shared facts, so every satellite computes the same winner for a target:

```python
import hashlib

def claim_score(sat, target, facts):
    g  = facts[(sat, f"geometry:{target}")].value
    b  = facts[(sat, "battery_margin")].value
    fu = facts[(sat, "fuel_margin")].value
    return round(0.4 * g + 0.3 * b + 0.3 * fu, 6)

def winner(candidates, target, facts):
    return max(candidates, key=lambda s: (
        claim_score(s, target, facts),
        hashlib.sha256(f"{s}:{target}".encode()).hexdigest(),   # deterministic tie-break
    ))
```

Why this matters: an earlier draft used each satellite's *own private* battery number. Two satellites could then pick different winners from the same data. Scoring only shared facts fixes that.

**Idea 3: claims are leases.** A claim on a target expires. If two satellites both claimed during a cut, the better score keeps it and the other lets go when links return.

```python
@dataclass(frozen=True)
class Lease:
    target: str
    holder: str
    expires_at: int     # simulation seconds
    stamp: int
```

**Prove the merge is safe with a property test** (random inputs, three laws):

```python
from hypothesis import given, strategies as st

fact = st.builds(Fact,
    sat_id=st.sampled_from(["s1", "s2", "s3"]),
    key=st.sampled_from(["battery_margin", "fuel_margin"]),
    value=st.floats(0, 1, allow_nan=False),
    stamp=st.integers(0, 50))

def put(d, f): return merge_facts(d, {(f.sat_id, f.key): f})
def build(fs):
    d = {}
    for f in fs: d = put(d, f)
    return d
facts_st = st.lists(fact, max_size=12).map(build)

@given(facts_st, facts_st, facts_st)
def test_merge_laws(a, b, c):
    assert merge_facts(a, b) == merge_facts(b, a)                              # order does not matter
    assert merge_facts(merge_facts(a, b), c) == merge_facts(a, merge_facts(b, c))  # grouping does not matter
    assert merge_facts(a, a) == a                                              # merging twice changes nothing
```

(These three laws are what make a merge "conflict-free". If this test ever fails, fix the merge. Do not loosen the test.)

**Resource margins.** Express every limit as **normalized slack** with a clear unit. Do not mix units in one formula.

```python
def slack(value, minimum, capacity):
    return (value - minimum) / capacity          # 0 = at the limit, 1 = full

def admit(action_cost: dict, state: dict, limits: dict) -> bool:
    """Allow an action only if every margin stays above its floor afterwards."""
    for name, lim in limits.items():
        after = state[name] - action_cost.get(name, 0)
        if slack(after, lim["min"], lim["cap"]) < lim["floor"]:
            return False
    return True
```

## 3.12 Build step 10: the sealed evidence pack

Each record includes a fingerprint of the one before it. Change any old record and every later fingerprint breaks.

```python
import hashlib, json

GENESIS = "0" * 64

def record_hash(prev: str, rec: dict) -> str:
    payload = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(prev.encode() + payload).hexdigest()

class Ledger:
    def __init__(self):
        self.rows, self.head = [], GENESIS
    def append(self, rec: dict):
        h = record_hash(self.head, rec)
        self.rows.append({"prev": self.head, "record": rec, "hash": h})
        self.head = h

def verify(rows) -> bool:
    prev = GENESIS
    for r in rows:
        if r["prev"] != prev or record_hash(prev, r["record"]) != r["hash"]:
            return False
        prev = r["hash"]
    return True
```

**Important:** a hash chain alone only shows the records are consistent with each other. For real protection, **sign the final hash** (for example with Ed25519) and publish the public key, and record the time with a trusted timestamp. The verifier should re-run the pack and confirm every hash matches.

Evidence pack folder:

```
evidence/
  scenario.yaml            # what was tested
  versions.json            # tool and dependency versions
  policy.sha256            # fingerprint of the policy under test
  runs.jsonl               # one line per run (seed, result)
  ledger.jsonl             # the hash chain
  counterexamples/         # shrunk failing cases with replay commands
  report.html              # human-readable summary
  SIGNATURE                # signature over the final hash
```

## 3.13 New feature: adaptive adversarial scenario search

**Purpose:** move beyond hand-written and random faults to systematically search for fault sequences that expose a configured failure.

### Minimum viable version

1. Generate candidate scenarios from a known valid seed scenario.
2. Mutate a bounded set of parameters: fault type, link pair, fault start time, outage duration, message delay, node-loss time and event ordering.
3. Reject malformed or physically invalid candidates before simulation.
4. Run each candidate with a recorded seed and policy version.
5. Score candidates by newly discovered invariant violations, previously unseen failure signatures and useful counterexample diversity.
6. Keep the exact candidate and full trace for every discovery.
7. Compare against random search using the same simulation budget.

Start with mutation-based search, not reinforcement learning. Once that baseline is stable, explore bandit methods, evolutionary search or an ML-guided generator. A learned generator must not be allowed to edit the evaluator or silently change invariant definitions.

**Acceptance criteria:** the search is reproducible from stored candidate IDs and seeds; every result is validated by a replay; the evaluation budget is reported; and results include unique failure signatures per run budget, time-to-first-failure and compute cost. A useful result would show repeatable improvement over random search on held-out scenario families—not only on the cases used to tune the search.

## 3.14 New feature: temporal invariant language

Build a small declarative rule format that developers can read and that the simulator can evaluate consistently. Initial constructs should cover:

- **Always:** a condition must hold throughout a run (for example, a resource floor).
- **Never-after:** an event or state must not authorize an unsafe action (for example, a stale or expired claim).
- **Eventually-within:** a response must happen before a configured deadline, but only under stated reachability and communication assumptions.
- **Mutual exclusion:** incompatible assignments must not be active simultaneously, subject to explicitly defined partition semantics.
- **Count/window:** duplicate work or repeated events are limited in a defined time window.

Each rule definition needs a stable ID, severity, parameters, units, assumptions and a version. Provide positive and negative tests for every built-in rule. Do not claim formal verification merely because a runtime monitor checks a temporal condition. Bounded model checking or a temporal-logic backend can be considered later as a separate extension.

## 3.15 New feature: differential and metamorphic testing

**Differential testing** runs multiple policies—or two versions of the same policy—against identical scenarios and seeds, then compares their traces and outcomes. This can reveal regressions and behavior differences even when no known invariant fires.

**Metamorphic testing** applies transformations that should preserve behavior under stated conditions. Examples include renaming satellite IDs while consistently updating references, reordering independent input records, or splitting a batch of scenarios without changing their contents. If outputs change unexpectedly, preserve the transformed case as a defect candidate.

Every metamorphic relation must state its assumptions. Some transformations legitimately change deterministic tie-breaks or scheduling, so tests must not assert equivalence where the specification does not require it.

**Acceptance criteria:** include at least three explicitly justified metamorphic relations, run old and new policy versions on identical seeds, and create a regression case for each confirmed discrepancy.

## 3.16 New feature: multi-fidelity simulation and escalation

Run large searches on a cheap abstraction, then replay promising failures in more detailed simulation levels:

| Level | Scope | Appropriate use |
|---|---|---|
| **L0** | Discrete-event model, scheduled contacts, abstract resources | Fast search and logic debugging |
| **L1** | Orbital propagation and geometry-derived visibility/contact windows; more realistic timing | Check whether findings survive orbital and timing effects |
| **L2** | Higher-detail models for selected dynamics, communications or sensor assumptions | Investigate a narrow failure more deeply |

Implement L0 first. L1 should use a validated orbital library and documented frame/time conventions. L2 is future scope; do not build a high-fidelity physics engine from scratch unless there is a clear reason.

A failure found at L0 should be labelled **L0-only** until reproduced at a higher level. If it disappears at L1/L2, retain both results and explain which simplified assumption mattered. Passing a higher fidelity simulation is not a real-world flight-safety guarantee.

**Acceptance criteria:** scenario and model versions are recorded; assumptions and known omissions are listed per fidelity level; escalated cases are traceable to the original search candidate; and cross-level disagreement is reported rather than hidden.

## 3.17 New feature: failure clustering and triage

Large campaigns may discover hundreds of traces describing the same underlying defect. Create a stable failure signature from normalized facts such as invariant ID, involved event types, relevant task/target IDs, state transitions and a bounded causal window. Cluster related reports and show:

- number of runs and scenarios affected;
- first and smallest known counterexample;
- shared event patterns and candidate causal factors;
- policy and simulator versions;
- whether a proposed fix passes the whole regression set.

Begin with rule-based fingerprints and simple clustering. An embedding/ML-based triage component can be tested later, but must link each summary back to exact trace events and must not replace the underlying evidence. Treat “likely same root cause” as a ranking, not a fact, until an engineer verifies it.

**Acceptance criteria:** duplicates are reduced without merging demonstrably different invariant failures, and every cluster can be expanded to its source runs and replay commands.

## 3.18 New feature: policy adapters, plugins and CI regression gates

A stable policy adapter is the boundary between the simulated world and the decision-maker. Define a versioned observation/action schema with explicit timestamps, units, missing-data semantics, legal action names and validation errors. Provide an in-process Python adapter first; remote process or service adapters can come later.

A policy adapter must not get hidden access to simulator truth that a satellite would not know. The test harness can know the truth; each policy receives only its declared observation. Record policy identity, version, configuration and input/output events.

Add a command-line interface and a CI workflow that can:

1. run a small smoke suite on each change;
2. replay all previously confirmed counterexamples;
3. compare selected metrics against a stored baseline;
4. fail the build when a defined regression threshold is exceeded;
5. upload the evidence pack as a build artifact.

Never fail or pass a build using undocumented thresholds. Thresholds must be versioned and explainable. A test result is a modelled result, not certification.

## 3.19 Research hypothesis and evaluation protocol

**Primary hypothesis (to test, not assume):** adaptive adversarial scenario search combined with counterexample shrinking and counterfactual replay discovers actionable satellite-swarm policy defects more efficiently than random fault injection and fixed scenarios, while producing evidence that can be independently replayed.

**Secondary hypothesis:** differential testing, temporal invariants and failure clustering improve defect discovery and triage beyond final-state checks alone.

### Baselines

- **A — Oracle upper bound:** a diagnostic-only policy with perfect information, used only where it is meaningful; not a fair deployable baseline.
- **B — Greedy local:** each satellite makes decisions from local observations without coordination.
- **C — Auction with timeouts:** task allocation through a conventional bidding/timeout baseline.
- **D — Shared-state only:** state synchronization with simple decision rules.
- **E — Leases only:** task claims expire, with deterministic tie-breaking.
- **F — Fabric:** the full reference policy, if it passes the continuation gate.
- **Search baseline:** random fault generation with the same simulation budget as the adaptive search.

### Metrics

| Metric | What it tells us |
|---|---|
| Unique violation signatures per 1,000 runs | How much distinct failure behavior is found |
| Time or compute to first failure | How quickly a test strategy finds a defect |
| Minimal counterexample size | How much irrelevant scenario complexity the shrinker removes |
| Counterfactual replay success rate | How often the proposed intervention changes the failure outcome as expected |
| Reproduction rate | Whether the recorded seed and scenario reproduce the same trace and finding |
| Triage reduction | How many reports can be grouped without hiding distinct defects |
| Policy outcome metrics | Duplicate tasks, dropped tasks, deadline misses, resource violations and mission utility |
| Cost per unique defect | Compute time or simulation count needed for each distinct finding |

Run multiple seeds, separate tuning scenarios from held-out evaluation scenarios, publish the exact budgets, and report confidence intervals where appropriate. Include negative results. Do not report a single best run as evidence of general improvement.

## 3.20 The commands we are building toward (planned interface)

```bash
Constellab run scenarios/wildfire_partition.yaml --policy policies.greedy:GreedyLocal --seeds 100 --out evidence/
Constellab search scenarios/wildfire_partition.yaml --strategy mutation --budget 1000 --policy policies.greedy:GreedyLocal
Constellab shrink evidence/runs.jsonl --run 417
Constellab why evidence/runs.jsonl --run 417 --intervention remove_link_cut
Constellab compare --left policies.greedy:GreedyLocal --right policies.fabric:Fabric --scenario scenarios/wildfire_partition.yaml
Constellab triage evidence/
Constellab verify evidence/
```

These commands describe the intended interface, not commands that already exist. The exact CLI can change as the implementation develops.

## 3.21 How we know each piece is done

| Piece | Done when |
|---|---|
| Sim core | Same version + seed + config gives an identical canonical trace hash in repeated runs |
| Policy adapter | Valid actions execute; invalid actions are reported; no hidden simulator state leaks to the policy |
| Nemesis | It produces at least one real, replayable violation in the greedy baseline |
| Invariants | Every built-in rule has positive and negative tests and documented assumptions |
| Temporal monitor | Rules can be evaluated incrementally and in replay from the trace |
| Fact merge | Property tests cover idempotence, commutativity and associativity under the specified total order |
| Shrinker | A planted failure is reduced and remains failing on replay; minimality scope is documented |
| Why engine | Interventions and negative controls produce replayable comparisons without overstating causality |
| Adaptive search | Beats or usefully complements random search on held-out cases under a fixed budget, or the negative result is documented |
| Differential/metamorphic tests | Valid relations detect deliberately planted discrepancies without excessive false alarms |
| Multi-fidelity | L0 findings can be escalated and cross-level disagreements are explicitly reported |
| Failure triage | Each cluster links to source traces; unrelated planted failures remain distinguishable |
| Ledger | Editing any record is detected; signature verification works with a documented public key |
| CI integration | Confirmed counterexamples replay and defined regressions produce an explainable build failure |
| Demo | An outsider reproduces the documented core demo from a clean checkout in under 30 minutes |



# PART 4: What to do, in order

## 4.1 Do this first (days 1 to 7): make the satellites visible

Do not begin with stakeholder outreach or communication-network behavior. First create a small, functional orbital scene using a canonical simulation state.

- [ ] Create the repository and a minimal visual-app scaffold.
- [ ] Define a small `SimulationSnapshot` schema with simulation time, satellite IDs, orbital parameters and positions.
- [ ] Render an Earth sphere and **four virtual satellites**.
- [ ] Draw orbit paths and make the satellite positions move along those paths using the stated initial orbit model.
- [ ] Add camera controls, satellite labels, selection/inspector, pause/resume, reset and time-scale controls.
- [ ] Prove that a given initial state and simulation time produce the same position snapshot.
- [ ] Save a screenshot and short screen recording of the working scene.

**Week-one goal:** a person can open Constellab and see four satellites moving around Earth, control simulated time, select a satellite and inspect its state. No inter-satellite messaging, communication links, coordination policy, ML or customer outreach is part of week one.

## 4.2 The 14-week plan with checkpoints

This schedule deliberately puts the visible simulation first and stakeholder conversations last. Treat the later advanced-test features as prototypes, not production-complete products. The order can expand if an acceptance gate fails; do not skip the gate to preserve a calendar date.

| Weeks | Build | Checkpoint |
|---|---|---|
| 1–2 | **Visual Orbital Simulator:** Earth, four satellite models, orbit paths, labels, camera controls, selected-satellite inspector, pause/resume/reset and time-scale controls. Use a clearly documented simple orbit model. | **G0 — Visual proof:** clean start renders moving satellites whose positions come from actual simulation state; controls and deterministic-time checks pass. Save a short demo recording. |
| 3–4 | **Orbital/state foundation:** replace any temporary orbit approximation with a documented Keplerian/two-body model as appropriate; define coordinate/time conventions; keep one canonical state source; add simulated telemetry and a chronological event timeline. | **G1 — State integrity:** orbit display and inspector read the same state; fixed state/time gives reproducible results; assumptions and limitations are documented. |
| 5–6 | **Swarm behavior begins:** add the first simulated inter-satellite contact/link model, then a policy adapter, greedy local baseline, resource state, random and worst-moment link cuts, and duplicate-tasking invariant. This is the first stage in which simulated satellite communication is implemented. | **G2 — First real failure:** a modeled communication outage triggers a known baseline-policy violation, visible in the scene and recorded in a replayable trace. |
| 7–8 | **Rule monitoring and evidence:** expand state invariants; add the temporal-rule MVP, deterministic event trace, evidence ledger, baseline comparison and initial report. | **G3 — Reproducible finding:** rerunning the same configuration and seed reproduces the event trace and the rule violation. |
| 9–10 | **Failure investigation:** shrinking, counterfactual replay with negative controls, differential testing, and the first justified metamorphic relations. Display selected events and failure markers in the visual scene. | **G4 — Explainable defect:** at least one failure is minimized, replayed, compared with a controlled intervention and saved as a regression case. |
| 11–12 | **Research extensions:** mutation-based adaptive adversarial search, simple failure signatures/clustering, basic multi-fidelity design and the first CI regression gate. | **G5 — Comparative evidence:** compare adaptive search with random search under equal budgets; report actual outcomes, cost and any negative results. |
| 13 | **Demonstration package:** polish essential controls and readability; make a short walkthrough that goes from orbit view to injected outage to visible failure, minimized case, causal comparison and evidence verification. Add installation instructions and a clean-checkout test. | **G6 — Stakeholder-ready base:** visual simulator and at least one reproduced testing-engine finding work from a clean checkout; evidence pack and limits are understandable. |
| 14 | **Stakeholder discovery (only now):** show the working demo to people who build, integrate, test or buy autonomy software; ask about their workflow, evidence needs and pain points. Record what was said versus what remains a hypothesis. | **G7 — Direction decision:** use feedback to prioritize the next development phase; do not claim market validation from a few conversations. |

### Features deliberately deferred

Do not implement these before the visual simulator and first reproducible-failure demo work: federated learning, language-model interfaces, complex ML-trained search, elaborate 3D assets, a large solar-system model, remote/cloud execution, production-grade L2 physics, broad certification claims or formal verification. The first visual scene should be useful and inspectable, but must not consume the entire project in graphics polish.

The 14-week schedule is an ambitious planning target for a solo developer. If a gate fails, fix it before moving on. A smaller reproducible product is better than many half-finished modules.

## 4.3 The test that decides the future

**Fabric decision gate:** compare the full reference policy against simpler baselines on a predeclared scenario suite.

| Name | What it is |
|---|---|
| A | Diagnostic oracle with perfect information, where meaningful; not a fair deployable baseline |
| B | Greedy local decisions, no reconciliation |
| C | Auction-based assignment with timeouts |
| D | Shared-state synchronization with naive decisions |
| E | Leases with deterministic tie-break, otherwise simple |
| F | Full Fabric: shared facts, deterministic scoring, leases and resource margins |

**Question:** does F improve duplicate work, dropped tasks, deadline misses or resource violations under the scenarios where it is designed to help? If not, remove claims that Fabric is smarter. Bench remains the core product; the test result is valuable either way.

**Adaptive-search gate:** compare mutation-guided search against random fault generation using the same wall-clock or simulation budget. Hold out scenario families that were not used to tune the search. Keep the extension only if it discovers more distinct actionable failures, finds them faster, or offers another measured advantage without concealing increased cost.

## 4.4 Research and evaluation protocol

Before running the main experiments, write a short protocol with: hypotheses, scenarios, baselines, metrics, run budgets, random seeds, exclusions and success criteria. Preserve it in version control before reviewing headline outcomes.

Minimum experiment set:

1. **Determinism:** repeated execution of identical configuration and seed.
2. **Fault effectiveness:** prove that each nemesis mode can trigger a known planted defect and does not silently mutate unrelated scenario fields.
3. **Search comparison:** adaptive mutation search versus random search under equal budgets, on both tuning and held-out scenarios.
4. **Shrinking:** compare original and minimized cases; replay both and record the number of events/states removed.
5. **Counterfactuals:** test the hypothesized cause, an unrelated intervention and a no-change control.
6. **Differential/metamorphic:** test selected policies and transformations whose expected relationships are explicitly justified.
7. **Fidelity escalation:** replay selected L0 failures at L1 and report which findings persist, disappear or remain inconclusive.
8. **Regression:** introduce a known bug, make Constellab detect it, fix it, then verify that the saved counterexample prevents its return.

Report failures and successes. Do not tune on the test set and then present the same set as independent validation.

## 4.5 Stakeholder discovery — final stage only

**Do not contact stakeholders before G6.** The project should first have something concrete to show: an interactive orbital scene, working time/orbit controls, a demonstrated injected swarm-policy failure, a minimized/replayable example, and an evidence pack that can be checked from a clean checkout. A static mock-up alone is not enough.

After that base exists:

- Begin with 3 focused conversations with people who build, integrate, test or buy autonomous-swarm software.
- If their feedback suggests a recurring problem, work toward roughly 15 structured conversations before making a major product or pricing decision.
- Ask about current testing workflow, failure reproduction, fault injection, reviewer evidence, integration constraints and privacy requirements.
- Consider an open-source core with paid private scenario libraries, hosted large campaigns or enterprise deployment only if interviews support the model.
- Do not publish sensitive software, scenarios or findings without explicit permission and a clear disclosure process.

These conversations are for discovery, not a sales claim. Until they happen, customer demand, product fit and willingness to pay remain hypotheses.

## 4.6 Questions for the first conversations

Use the working demo to make the conversation concrete. Ask:

1. How do you test autonomy today, and which failures are hardest to reproduce?
2. What simulation, visualization and policy interfaces already exist in your workflow?
3. How do you inject faults and explore timing-sensitive edge cases?
4. What evidence do reviewers want before accepting a change to autonomy software?
5. Would minimal counterexamples and replayable reports save meaningful engineering time?
6. Would a standalone CLI/CI tool fit your workflow, or would it need to run inside your environment?
7. Which data or source code could you not send to an external service?
8. Would you share a non-sensitive example scenario as a design partner?

**Stop sign:** after around 15 conversations, if fewer than four people describe this as a recurring, costly problem with a deadline or budget, reconsider the customer segment or narrow the product. This is a decision heuristic, not a statistical law.

# PART 5: Honest limits, risks and competitors

## 5.1 What could go wrong

| Risk | Plain explanation | What we do |
|---|---|---|
| The smart merge does not beat simple leases | Our fancy idea may not be needed | Use the Fabric decision gate after the visual base and initial policy baselines exist; fall back to Bench |
| Nobody pays for independent testing **(H)** | Our whole bet | Validate only after the visual simulator and first reproducible-failure demo are ready; use the final-stage discovery gate |
| Few swarms are really partition-heavy | Dense constellations with constant laser links may not be | Scenarios take a *contact plan* so each customer tests their own reality |
| Sim is not reality | Models simplify | Every report states how detailed the model was |
| Bigger players add this | Sedaro and Slingshot are well funded | Win on scenario library and report quality |
| Too much scope for one team | Visualization, testing engine, learned search, orbital fidelity and business work can balloon | Visual-first but minimal; ship each gate before advanced modules |
| Adaptive search overfits | Search finds known benchmark quirks rather than general defects | Hold out scenario families and compare against equal-budget random search |
| False causal claims | A failure disappears in one replay but the explanation is incomplete | Say “counterfactual evidence”; use controls and retain the full trace |
| Model-fidelity mismatch | A failure exists only in a simplified simulator, or a real issue is absent | Label every result by fidelity and list model assumptions |
| Metamorphic test is invalid | A transformation was assumed harmless but actually changes valid policy semantics | State and test each relation’s assumptions before using it |

## 5.2 Who else is in the space (from research)

- **NASA Starling:** NASA's four-CubeSat mission has demonstrated distributed autonomy, cross-spacecraft status sharing and autonomous planning; it remains an important baseline for swarm-autonomy research. [NASA Starling](https://www.nasa.gov/smallspacecraft/what-is-starling/)
- **ESA Φsat-2:** demonstrates onboard AI applications including cloud filtering, image compression, vessel detection and environmental-event analysis. This makes clear that onboard image AI by itself is not Constellab's differentiator. [ESA Φsat-2](https://www.esa.int/Applications/Observing_the_Earth/FutureEO/Phsat-2/Introducing_Phsat-2)
- **Sedaro, Shield AI and NOVI Space:** their August 24, 2026 announcement describes an on-orbit Hivemind demonstration on one NOVI satellite, with five additional virtual satellites in a six-member constellation model and Sedaro's autonomy framework. This is adjacent autonomy and virtual-constellation work, not proof that Constellab's testing product is unnecessary. [Joint announcement](https://sedaro.com/news/shield-ai-novi-trusted-autonomy-demo)
- **Slingshot Aerospace:** announced a $69.2 million, 4.5-year U.S. Space Force contract in July 2026 for AI-powered mission rehearsal and operational training. That validates activity in space simulation and rehearsal, but does not by itself establish overlap with Constellab's proposed independent testing workflow. [Slingshot announcement](https://www.slingshot.space/news/slingshot-aerospace-wins-69-2-million-u-s-space-force-contract-to-advance-ai-powered-mission-readiness-for-space-defense)
- **Shared-state research (arXiv 2609.18839):** describes a CRDT-based distributed-state service evaluated with a simulated/emulated 66-satellite constellation. It is relevant prior research for Fabric and for testing shared-state behavior. [Paper](https://arxiv.org/abs/2609.18839)
- **Adjacent projects to investigate further:** Glass Box, OrbitReasoning Core and STARS are leads from the initial research notes; assess their actual scope and publication status before treating them as direct competitors.

**Prior-art warning:** the research notes identify published work and a possible patent lead around conflict-free shared-state approaches. This briefing has not re-verified the specific patent claims, so treat that as a warning to investigate—not as a legal conclusion. Constellab should not claim to have invented CRDTs or shared-state merging. Its bet is the test methodology, failure minimization, controlled replay and evidence workflow, subject to further prior-art review.

## 5.3 About patents and research novelty (plain version)

Most building blocks are established areas: fault injection, fuzzing/search, runtime monitoring, delta debugging, differential testing, causal debugging, digital signatures and simulation. Combining known blocks is not automatically a patentable invention.

Potential research contributions to investigate—not claims of novelty—include:

- a measurable adaptive search strategy tailored to timing-sensitive distributed-swarm failures;
- a shrinker that preserves temporal, network and orbital constraints while reducing a failure scenario;
- a traceable counterfactual workflow that distinguishes a plausible cause from correlated events;
- a multi-fidelity escalation policy that chooses which discovered failures merit more expensive simulation;
- an evidence-pack schema and regression workflow tailored to autonomous swarm policy evaluation.

The project should first establish technical usefulness and compare against prior work. A patent attorney should conduct a claim-level prior-art review before any filing or public disclosure. Public code, a paper, a demo video or a detailed online post can affect patent options depending on jurisdiction and timing. This briefing is not legal advice and does not establish novelty, non-obviousness or freedom to operate.

---

# Glossary (for beginners)

| Term | Plain meaning |
|---|---|
| **Satellite swarm** | A group of small satellites working as a team |
| **Autonomy** | Software that makes decisions without waiting for humans |
| **Crosslink / ISL** | A radio or laser link between two satellites |
| **Partition** | The swarm splits into groups that cannot talk to each other for a while |
| **Policy** | The "brain": rules or AI that decide what each satellite does |
| **Simulation** | A computer model of the satellites, orbits and events |
| **Deterministic** | Same inputs always give the same output, so a run can be replayed exactly |
| **Seed** | The starting number for the random dice; same seed, same game |
| **Nemesis** | Our tool that deliberately causes trouble (cuts links, kills satellites) |
| **Invariant** | A rule that must never be broken |
| **Shrinking** | Reducing a failing case to the smallest version that still fails |
| **Intervention replay** | Re-run the same scenario with one change to see if the failure goes away |
| **Lease** | A temporary claim ("I'll handle this target for the next 5 minutes") |
| **CRDT** | A type of shared data that always ends up identical on every copy once updates arrive, in any order |
| **Hash** | A short digital fingerprint of a file; any change to the file changes the fingerprint |
| **Hash chain** | Records where each one includes the fingerprint of the previous one |
| **Digital signature** | A cryptographic check that data matches a signature made by the corresponding private key; the key's real-world identity depends on how the public key is trusted |
| **Evidence pack** | The folder of results and checkers someone else can re-run |
| **Adaptive adversarial search** | Search that changes fault scenarios based on which tests find useful failures |
| **Counterexample** | A concrete run showing a policy violates a specified rule |
| **Differential testing** | Running two implementations under the same conditions and comparing outcomes |
| **Metamorphic testing** | Checking whether transformations that should preserve behavior actually do so |
| **Temporal invariant** | A rule about event order, timing or behavior across a period |
| **Multi-fidelity simulation** | Using different levels of model detail, from cheap abstractions to more detailed replay |
| **Failure signature** | A normalized description used to group potentially related failures |
| **CI regression gate** | An automated test that checks changes and blocks a build when defined criteria fail |
| **Design partner** | An early customer who helps shape the product |
| **(H)** | A hypothesis: our best guess, not yet confirmed |

---

# Evidence list (checked October 11, 2026)

- NASA Starling mission and distributed spacecraft autonomy: https://www.nasa.gov/smallspacecraft/what-is-starling/ and https://www.nasa.gov/centers-and-facilities/ames/what-is-nasas-distributed-spacecraft-autonomy/
- ESA Φsat-2 onboard AI applications: https://www.esa.int/Applications/Observing_the_Earth/FutureEO/Phsat-2/Introducing_Phsat-2
- Sedaro, Shield AI and NOVI Space announcement, August 24, 2026: https://sedaro.com/news/shield-ai-novi-trusted-autonomy-demo
- Slingshot Aerospace U.S. Space Force contract announcement, July 15, 2026: https://www.slingshot.space/news/slingshot-aerospace-wins-69-2-million-u-s-space-force-contract-to-advance-ai-powered-mission-readiness-for-space-defense
- Shared-state framework for satellite swarms, arXiv:2609.18839, published September 16, 2026: https://arxiv.org/abs/2609.18839
- YC satellite companies (industry discovery, not proof of direct competition): https://www.ycombinator.com/companies/industry/satellites
- Initial research leads to verify independently: https://arxiv.org/abs/2606.02967 (Glass Box), https://roxanneardary.com/orbitreasoning-core/ (OrbitReasoning Core), https://arxiv.org/html/2501.05984v1 (STARS).
- Patent-specific search results should be recorded in a separate prior-art log with patent/publication numbers, jurisdictions, claims reviewed and search date. No claim-level patent conclusion is made in this briefing.

**Limits:** competitor facts come from public web sources and may be promotional or incomplete. No customer has validated any hypothesis marked (H). Code examples are starter sketches and must be tested in the actual project environment before relying on them. This is a planning document, not legal or investment advice.

---

## Final operating principles

1. **Bench is the product.** Fabric is optional and must earn its place through evidence.
2. **Visual first, not visual only.** Build a functioning Earth-and-satellites orbital scene before the communication model and test engine; keep it connected to real simulation state.
3. **Stakeholders last.** Do not conduct discovery outreach until the visual simulator and first reproducible failure/evidence demonstration are ready.
4. **Software-only means software-only.** All satellites, sensors, networks, resources and faults can be simulated. No hardware is required for the project.
5. **Determinism before intelligence.** A learned search strategy is useful only if its findings can be replayed and checked.
6. **A failure is an artifact.** Preserve scenario, seed, trace, versions, invariant, minimized case and replay instructions.
7. **Do not overclaim.** Simulation results are conditional on model assumptions; hash integrity is not truth; a monitor is not automatically a formal proof; and zero observed failures is not proof of zero risk.
8. **Compare against simple baselines.** If a complicated feature does not improve a predeclared metric, simplify or remove it.
9. **Novelty is a research result, not a slogan.** Validate the gap against papers, products and patents before making novelty or patentability claims.
10. **Keep user data private by design.** Start with local execution. Add hosted execution only after security, isolation, retention and customer requirements are understood.

**Final positioning:** Constellab is an independent, simulation-first test bench for autonomous satellite-swarm software. It searches for failures, minimizes them, tests explanations, compares policies and produces replayable evidence. Its central research bet is that adaptive adversarial testing can find more actionable defects per unit of testing effort than random or fixed scenarios. That claim must be tested—and reported honestly—before it becomes a headline.
