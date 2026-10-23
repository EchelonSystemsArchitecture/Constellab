"""ConstellaLab simulation core.

A stdlib-only service that validates scenario configuration against the versioned
JSON Schema in ``data/simulation_contract.schema.json`` and serves canonical
snapshots to the renderer. Days 25-30 add the swarm-testing layer: configurable
Earth-observation targets and event sources (``targets``), sensor footprints and
access windows (``sensors``), the generic task lifecycle (``tasks``), the policy
interface with non-neural baselines (``policy``), inter-satellite contact
opportunities (``contacts``) and simulated message transport with partitions
(``transport``).
"""

from .contract import SCHEMA_VERSION  # noqa: E402
from .plugins import activate_builtins  # noqa: E402

__version__ = "0.4.0"

# Day 20: component and plugin registrations run once at import, before any
# scenario can be validated, so unknown components fail loudly from startup on.
_PLUGIN_REPORT = activate_builtins()

__all__ = ["SCHEMA_VERSION", "__version__", "_PLUGIN_REPORT"]
