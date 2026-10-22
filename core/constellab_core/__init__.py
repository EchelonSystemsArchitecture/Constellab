"""ConstellaLab simulation core.

Day 2: the simulation/visualization contract. A stdlib-only service that
validates scenario configuration against the versioned JSON Schema in
``data/simulation_contract.schema.json`` and serves canonical snapshots to the
renderer. No inter-satellite communication or swarm coordination exists yet.
"""

from .contract import SCHEMA_VERSION  # noqa: E402
from .plugins import activate_builtins  # noqa: E402

__version__ = "0.3.0"

# Day 20: component and plugin registrations run once at import, before any
# scenario can be validated, so unknown components fail loudly from startup on.
_PLUGIN_REPORT = activate_builtins()

__all__ = ["SCHEMA_VERSION", "__version__", "_PLUGIN_REPORT"]
