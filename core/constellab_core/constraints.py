"""Day 21: declarative parameter constraints and dependencies.

Parameter bounds (Day 19) check one value against its own spec. Day 21 adds the
rules that relate values to each other — as data, never as code strings:

* **relation** — a comparison between two fields or a field and a literal
  (``base_load_w <= supply_w``). Operators are the six mathematical relations,
  checked by code; there is no ``eval`` and no expression language to escape.
* **sum-budget** — several fields add up to a shared maximum (duty-cycle style
  allocations). Every operand must measure the same unit kind.
* **requires** — dependency ordering between fields (B may only be configured
  once A is). The dependency edges form a graph the registry checks for cycles
  before any simulation can start, so an impossible rule set fails loudly.
* **required-if** — a field becomes mandatory when a condition on another field
  holds (equality with a declared value, or presence).
* **one-of** — exactly ``N`` (usually one) of the enumerated fields is declared.
* **range** — numeric bounds on a field, usable where spec bounds are absent.

Every rule carries a stable ``id``, a ``scope`` (which owner's effective values
it sees — rules with no scope act on the fully qualified keys of the whole
mapping), and a category: ``physical`` failures are hard errors, while
``model_support`` failures mean the configuration is physically valid but
outside what the training data supports, so the caller reports a warning or a
fallback state instead of refusing to simulate.

Config edits are transactions: :meth:`ConstraintRegistry.check_transaction`
 accepts a candidate only when every rule passes. Otherwise nothing changes
and the caller receives one field-path diagnostic per violation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .parameters import ParameterRegistry, builtin_registry
from .units import UnitError, unit_kind

OPERATORS = ("<", "<=", ">", ">=", "==", "!=")
CATEGORIES = ("physical", "model_support")

RULE_KINDS = ("relation", "sum-budget", "requires", "required-if", "one-of", "range")


class ConstraintError(ValueError):
    """A rule definition is invalid, or a configuration violates a constraint."""

    def __init__(self, issues: list[dict[str, str]]):
        self.issues = issues
        super().__init__("constraint error: " + "; ".join(
            f"{i['path']}: {i['message']}" for i in issues))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


@dataclass(frozen=True)
class Operand:
    """One side of a relation: a parameter path (``field``) or a literal value."""

    field: str | None = None
    value: Any = None

    @classmethod
    def literal(cls, value: Any) -> "Operand":
        return cls(value=value)

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field} if self.field is not None else {"value": self.value}


def _operand_from(payload: Any, path: str, issues: list[dict[str, str]]) -> Operand:
    if isinstance(payload, Mapping) and set(payload) <= {"field", "value"}:
        if payload.get("field") is not None:
            return Operand(field=payload["field"])
        return Operand(value=payload.get("value"))
    issues.append({"path": path, "message": "an operand must be {\"field\": key} or {\"value\": literal}"})
    return Operand()


@dataclass(frozen=True)
class ConstraintRule:
    """Base identity of one declarative rule; concrete rules carry the extras."""

    id: str
    kind: str
    category: str = "physical"
    scope: str | None = None
    description: str = ""


@dataclass(frozen=True)
class RelationRule(ConstraintRule):
    """``left operator right`` on effective parameter values."""

    left: Operand = field(default_factory=Operand)
    operator: str = "<="
    right: Operand = field(default_factory=Operand)


@dataclass(frozen=True)
class SumBudgetRule(ConstraintRule):
    """The named fields must together stay below ``maximum``."""

    fields: tuple[str, ...] = ()
    maximum: float = 1.0


@dataclass(frozen=True)
class RequiresRule(ConstraintRule):
    """Configuring ``field`` requires ``requires_field`` to be configured too."""

    field: str = ""
    requires_field: str = ""


@dataclass(frozen=True)
class RequiredIfRule(ConstraintRule):
    """``field`` must be present when ``condition_field`` equals ``equals``."""

    field: str = ""
    condition_field: str = ""
    equals: Any = None
    condition_is_set: bool = False


@dataclass(frozen=True)
class OneOfRule(ConstraintRule):
    """Exactly ``exactly`` of ``fields`` must be declared (default: exactly one)."""

    fields: tuple[str, ...] = ()
    exactly: int = 1


@dataclass(frozen=True)
class RangeRule(ConstraintRule):
    """Numeric bounds on one field, where the registry spec has none."""

    field: str = ""
    minimum: float | None = None
    maximum: float | None = None


_RULE_TYPES = {
    "relation": RelationRule,
    "sum-budget": SumBudgetRule,
    "requires": RequiresRule,
    "required-if": RequiredIfRule,
    "one-of": OneOfRule,
    "range": RangeRule,
}

# Rule fields that name other parameters: they form the dependency graph.
_FIELDS_ATTR = {"sum-budget": ("fields",), "one-of": ("fields",)}


class ConstraintRegistry:
    """Validated declarative rules, checked against a parameter registry."""

    def __init__(self, rules: Sequence[ConstraintRule] = (),
                 registry: ParameterRegistry | None = None, *,
                 source: str = "<memory>"):
        self.source = source
        self.registry = registry
        self._rules: dict[str, ConstraintRule] = {}
        issues: list[dict[str, str]] = []
        for rule in rules:
            for report in self._definition_issues(rule):
                issues.append(report)
            if rule.id in self._rules:
                issues.append({"path": f"{self.source}:{rule.id}",
                               "message": f"duplicate rule id {rule.id!r}"})
                continue
            self._rules[rule.id] = rule
        if issues:
            raise ConstraintError(issues)

    # -- definition validation ------------------------------------------------

    def _definition_issues(self, rule: ConstraintRule) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        prefix = f"{self.source}:{rule.id}"

        def issue(message: str) -> None:
            issues.append({"path": prefix, "message": message})

        if not isinstance(rule.id, str) or not rule.id:
            issue("every rule needs a non-empty id")
            return issues
        if rule.kind not in RULE_KINDS:
            issue(f"rule kind must be one of {', '.join(RULE_KINDS)}, got {rule.kind!r}")
            return issues
        if rule.category not in CATEGORIES:
            issue(f"category must be one of {', '.join(CATEGORIES)}")
        if self.registry is not None:
            for path in self._referenced_paths(rule):
                if path not in self.registry:
                    issue(f"field {path!r} is not a registered parameter")
        if isinstance(rule, RelationRule):
            if rule.operator not in OPERATORS:
                issue(f"operator must be one of {', '.join(OPERATORS)}, got {rule.operator!r}")
            if rule.left.field is None and rule.right.field is None:
                issue("a relation needs at least one field operand")
            if (self.registry is not None and rule.left.field and rule.right.field
                    and self._unit_kinds_match(rule.left.field, rule.right.field) is False):
                issue(f"operands {rule.left.field!r} and {rule.right.field!r} "
                      "measure different quantity kinds")
            if rule.left.field is not None and _is_number(rule.left.value):
                issue("an operand is either a field or a literal, not both")
        if isinstance(rule, SumBudgetRule):
            if len(rule.fields) < 2:
                issue("a sum budget needs at least two fields")
            if not _is_number(rule.maximum) or rule.maximum < 0:
                issue("maximum must be a finite non-negative number")
            if self.registry is not None and len({self._unit_kind_of(f) for f in rule.fields}) > 1:
                issue("sum budget fields must measure the same quantity kind")
        if isinstance(rule, RequiresRule):
            if not rule.field or not rule.requires_field:
                issue("a requires rule names two fields")
            elif rule.field == rule.requires_field:
                issue("a field cannot require itself")
        if isinstance(rule, RequiredIfRule):
            if not rule.condition_is_set and rule.equals is None:
                issue("a required-if condition needs an equals value or condition_is_set")
            if not rule.field or not rule.condition_field:
                issue("a required-if rule names a field and a condition field")
            elif rule.field == rule.condition_field:
                issue("a field cannot be conditioned on itself")
            if self.registry is not None and rule.condition_field in self.registry:
                spec = self.registry.get(rule.condition_field)
                if spec.enum and not rule.condition_is_set and rule.equals not in spec.enum:
                    issue(f"impossible condition: {rule.condition_field!r} can never equal "
                          f"{rule.equals!r} (allowed: {list(spec.enum)!r})")
        if isinstance(rule, OneOfRule):
            if len(set(rule.fields)) != len(rule.fields):
                issue("one-of names each field at most once")
            if len(rule.fields) < max(1, rule.exactly):
                issue("one-of has fewer fields than required choices")
        if isinstance(rule, RangeRule):
            if not rule.field:
                issue("a range rule names one field")
            if rule.minimum is None and rule.maximum is None:
                issue("a range rule needs a minimum or a maximum")
            if _is_number(rule.minimum) and _is_number(rule.maximum) and rule.minimum > rule.maximum:
                issue("minimum exceeds maximum; no value could ever satisfy it")
        return issues

    def _referenced_paths(self, rule: ConstraintRule) -> list[str]:
        paths: list[str] = []
        for operand in getattr(rule, "left", None), getattr(rule, "right", None):
            if operand is not None and getattr(operand, "field", None):
                paths.append(operand.field)
        for attr in _FIELDS_ATTR.get(rule.kind, ()):
            paths.extend(getattr(rule, attr, ()))
        for attr in ("field", "requires_field", "condition_field"):
            value = getattr(rule, attr, None)
            if value:
                paths.append(value)
        return paths

    def _unit_kind_of(self, path: str) -> str:
        if not (self.registry and path in self.registry):
            return "?"
        spec = self.registry.get(path)
        try:
            return unit_kind(spec.unit)
        except UnitError:
            return "?"

    def _unit_kinds_match(self, left: str, right: str) -> bool | None:
        kind_left, kind_right = self._unit_kind_of(left), self._unit_kind_of(right)
        if "?" in (kind_left, kind_right):
            return None
        return kind_left == kind_right

    # -- dependency graph -------------------------------------------------------

    def dependencies(self) -> dict[str, set[str]]:
        """Field → fields whose presence it depends on.

        Only *ordering* rules create edges: ``requires`` names a strict
        prerequisite, and ``required-if`` ties a field's availability to a
        condition. Relations and budgets are symmetric instantaneous checks,
        not stages, so they add no ordering edges — otherwise every comparison
        would look like a dependency cycle.
        """
        graph: dict[str, set[str]] = {}
        for rule in self._rules.values():
            if rule.kind == "requires":
                graph.setdefault(rule.field, set()).add(rule.requires_field)
            elif rule.kind == "required-if":
                graph.setdefault(rule.field, set()).add(rule.condition_field)
        return graph

    def dependency_cycles(self) -> list[list[str]]:
        """Cycles among the named dependency edges (canonical node order)."""
        graph = {node: sorted(edges) for node, edges in self.dependencies().items()}
        cycles: list[list[str]] = []
        bodies: list[list[str]] = []
        for start in sorted(graph):
            # DFS carrying the current path; revisiting a node already in the
            # path closes a cycle, reported once in canonical rotation order.
            stack: list[tuple[str, tuple[str, ...]]] = [(start, ())]
            while stack:
                node, path = stack.pop()
                if node in path:
                    rotation = path[path.index(node):]
                    if sorted(rotation) not in bodies:
                        bodies.append(sorted(rotation))
                        cycles.append([*rotation, rotation[0]])
                    continue
                for neighbour in graph.get(node, ()):
                    stack.append((neighbour, path + (node,)))
        return cycles

    def check_graph(self) -> None:
        """Fail loudly with field paths if the dependency graph has cycles."""
        cycles = self.dependency_cycles()
        if cycles:
            raise ConstraintError([
                {"path": f"{self.source}:dependencies[{index}]",
                 "message": "dependency cycle: " + " -> ".join(cycle)}
                for index, cycle in enumerate(cycles)
            ])

    # -- evaluation ---------------------------------------------------------------

    def rules_for_scope(self, scope: str | None) -> list[ConstraintRule]:
        """All rules when no scope is given; otherwise matching + scopeless rules."""
        if scope is None:
            return list(self._rules.values())
        return [rule for rule in self._rules.values()
                if rule.scope is None or rule.scope == scope]

    def _lookup(self, values: Mapping[str, Any], name: str,
                scope: str | None = None) -> tuple[bool, Any]:
        """Resolve a rule field in ``values``: fully qualified name, else the
        scope-relative short key (``scope`` maps like a satellite's component
        parameter map). Returns ``(present, value)``."""
        if name in values:
            return True, values[name]
        if scope is not None and name.startswith(scope + "."):
            short = name[len(scope) + 1:]
            if short in values:
                return True, values[short]
        return False, None

    def _resolved_operand(self, operand: Operand, values: Mapping[str, Any],
                          scope: str | None) -> tuple[bool, Any]:
        if operand.field is None:
            return True, operand.value
        return self._lookup(values, operand.field, scope)

    def check(self, values: Mapping[str, Any], *, scope: str | None = None,
              path: str = "$") -> list[dict[str, str]]:
        """Evaluate the applicable rules; return one diagnostic per violation.

        ``values`` may hold fully qualified keys or, when ``scope`` names an
        owner, that owner's short keys (e.g. effective component parameters).
        A rule is *active* only when at least one of its referenced fields is
        present — absent keys mean "registry default applies", never "violated
        by doing nothing". Callers wanting complete checking pass
        defaults-merged values (``ParameterRegistry.effective_values``).
        """
        issues: list[dict[str, str]] = []
        for rule in self.rules_for_scope(scope):
            if rule.kind != "required-if" and not self._rule_active(rule, values, scope):
                continue
            issues.extend(self._evaluate_rule(rule, values, scope, path))
        return issues

    def _rule_active(self, rule: ConstraintRule, values: Mapping[str, Any],
                     scope: str | None) -> bool:
        if rule.kind == "required-if":
            return True
        return any(self._lookup(values, name, scope)[0]
                   for name in self._referenced_paths(rule))

    def _evaluate_rule(self, rule: ConstraintRule, values: Mapping[str, Any],
                       scope: str | None, path: str) -> list[dict[str, str]]:
        where = f"{path}.{rule.id}"

        def issue_at(name: str, message: str) -> dict[str, str]:
            return {"path": f"{path}.{name}", "message": message}

        def present(name: str) -> bool:
            return self._lookup(values, name, scope)[0]

        if rule.kind == "relation":
            has_left, left = self._resolved_operand(rule.left, values, scope)
            has_right, right = self._resolved_operand(rule.right, values, scope)
            if not has_left or not has_right:
                # A missing field operand means "registry default applies".
                # Callers that want full checking pass effective values
                # (defaults merged) from the parameter registry.
                return []
            if not (_is_number(left) and _is_number(right)) and str(left) != str(right):
                return [issue_at(rule.left.field or "left",
                                 f"{rule.id}: relation operands must be numbers of the same unit")]
            ok = {
                "<": left < right, "<=": left <= right, ">": left > right,
                ">=": left >= right, "==": left == right, "!=": left != right,
            }[rule.operator]
            if not ok:
                return [issue_at(rule.left.field or "left",
                                 f"{rule.id}: {left!r} must be {rule.operator} {right!r}")]
            return []

        if rule.kind == "sum-budget":
            total = 0.0
            for name in rule.fields:
                is_present, value = self._lookup(values, name, scope)
                if not is_present or not _is_number(value):
                    # Unset fields are not judged: the budget sees declared
                    # allocations only (merged defaults cover the rest).
                    continue
                total += float(value)
            if total > rule.maximum:
                return [issue_at(rule.fields[0],
                                 f"{rule.id}: allocation sums to {total:g}, budget is {rule.maximum:g}")]
            return []

        if rule.kind == "requires":
            if present(rule.field) and not present(rule.requires_field):
                return [issue_at(rule.field, f"{rule.id}: {rule.field!r} requires {rule.requires_field!r}")]
            return []

        if rule.kind == "required-if":
            has_condition, condition_value = self._lookup(values, rule.condition_field, scope)
            if rule.condition_is_set:
                condition = has_condition
            else:
                condition = has_condition and condition_value == rule.equals
            if condition and not present(rule.field):
                return [issue_at(rule.field, f"{rule.id}: {rule.field!r} is required by the "
                                 f"{rule.condition_field!r} condition")]
            return []

        if rule.kind == "one-of":
            count = sum(1 for name in rule.fields if present(name))
            if count != rule.exactly:
                return [issue_at(rule.fields[0] if rule.fields else "one-of",
                                 f"{rule.id}: expected exactly {rule.exactly} of "
                                 f"{list(rule.fields)!r}, got {count}")]
            return []

        if rule.kind == "range":
            is_present, value = self._lookup(values, rule.field, scope)
            if not is_present or not _is_number(value):
                return []
            value = float(value)
            if rule.minimum is not None and value < rule.minimum:
                return [issue_at(rule.field, f"{rule.id}: {value:g} must be >= {rule.minimum:g}")]
            if rule.maximum is not None and value > rule.maximum:
                return [issue_at(rule.field, f"{rule.id}: {value:g} must be <= {rule.maximum:g}")]
            return []

        return [{"path": where, "message": f"{rule.id}: rule kind {rule.kind!r} is not evaluated"}]

    # -- transactions -------------------------------------------------------------

    def check_transaction(self, current: Mapping[str, Any], candidate: Mapping[str, Any],
                          *, scope: str | None = None, path: str = "$") -> list[dict[str, str]]:
        """Issues in ``candidate`` — the caller applies it only when the list is empty.

        Edit semantics: a field present in ``current`` but absent from
        ``candidate`` falls back to its registry default, so the merged view is
        what gets checked. Nothing is committed on any failure.
        """
        merged = dict(candidate)
        for key in current:
            if key not in merged and self.registry is not None and key in self.registry:
                default = self.registry.get(key).default
                if default is not None:
                    merged[key] = default
        return self.check(merged, scope=scope, path=path)

    # -- data ---------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Machine-readable rule list: every rule is data, none is code."""
        out: list[dict[str, Any]] = []
        for rule in self._rules.values():
            entry: dict[str, Any] = {"id": rule.id, "kind": rule.kind,
                                     "category": rule.category}
            if rule.scope:
                entry["scope"] = rule.scope
            if rule.description:
                entry["description"] = rule.description
            for attr in ("left", "right"):
                operand = getattr(rule, attr, None)
                if operand is not None:
                    entry[attr] = operand.as_dict()
            for attr in ("operator", "maximum", "equals", "exactly",
                         "condition_is_set", "condition_field", "requires_field"):
                value = getattr(rule, attr, None)
                if value is not None and value != "":
                    entry[attr] = value
            for attr in ("fields",):
                value = getattr(rule, attr, ())
                if value:
                    entry[attr] = list(value)
            for attr in ("minimum", "maximum"):
                value = getattr(rule, attr, None)
                if value is not None:
                    entry[attr] = value
            out.append(entry)
        return {"count": len(out), "rules": out, "dependencies": self.dependencies()}


# --- builtin rule set -----------------------------------------------------------------

_BUILTIN: ConstraintRegistry | None = None
_NO_REGISTRY = ConstraintRegistry()


def builtin_rules(registry: ParameterRegistry | None = None) -> ConstraintRegistry:
    """Rules that hold for the shipped reference components.

    Kept here instead of a data file so they are versioned with the code that
    evaluates them; :meth:`to_dict` shows exactly what they say.
    """
    global _BUILTIN
    if _BUILTIN is None:
        index = registry or builtin_registry()
        _BUILTIN = ConstraintRegistry([
            RelationRule(
                id="power.base-load-within-supply",
                kind="relation",
                left=Operand(field="power.constant.base_load_w"),
                operator="<=",
                right=Operand(field="power.constant.supply_w"),
                scope="power.constant",
                description="a regulated supply cannot serve more base load than it provides",
            ),
            OneOfRule(
                id="power.exactly-one-source",
                kind="one-of",
                fields=("power.constant.supply_w", "power.solar-battery.array_area_m2"),
                exactly=1,
                description="a satellite declares exactly one power model",
            ),
            RelationRule(
                id="sensor.half-angle-within-cone",
                kind="relation",
                left=Operand(field="sensor.conical.half_angle_deg"),
                operator="<",
                right=Operand.literal(90.0),
                scope="sensor.conical",
                description="a half-angle of 90 degrees would claim the whole hemisphere",
            ),
            SumBudgetRule(
                id="compute.duty-budget",
                kind="sum-budget",
                fields=("compute.capacity.duty_cycle_ratio", "sensor.conical.duty_cycle_ratio"),
                maximum=1.0,
                description="reserved duty cycles sum to the available on-board time budget",
            ),
        ], registry=index, source="<builtin>")
    return _BUILTIN


def check_parameters(values: Mapping[str, Any], *, scope: str | None = None,
                     registry: ParameterRegistry | None = None,
                     path: str = "$") -> list[dict[str, str]]:
    """One-call check of effective parameter values against the builtin rules."""
    return builtin_rules(registry or builtin_registry()).check(values, scope=scope, path=path)
