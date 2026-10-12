"""ConstellaLab simulation core.

Day 2: the simulation/visualization contract. A stdlib-only service that
validates scenario configuration against the versioned JSON Schema in
``data/simulation_contract.schema.json`` and serves canonical snapshots to the
renderer. No inter-satellite communication or swarm coordination exists yet.
"""

from .contract import SCHEMA_VERSION

__version__ = "0.2.0"

__all__ = ["SCHEMA_VERSION", "__version__"]
