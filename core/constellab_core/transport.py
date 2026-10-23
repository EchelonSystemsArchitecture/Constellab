"""Day 30: simulated message transport, queues and network partitions.

A contact opportunity (Day 29) says a link *can* carry traffic. This module is
what actually carries it: messages enter a bounded per-source queue, wait for an
open link, occupy that link's bandwidth for ``size_bit / bandwidth_bps`` seconds,
suffer the configured latency, and are then delivered — unless loss, expiry,
queue overflow or a partition stops them. Duplication and reordering are
explicit, seeded, and visible in the trace.

The transport is deliberately software-only and event-based:

* **link state** comes from a predicate (normally a Day 29 contact plan), never
  from the renderer;
* **partitions** are group splits — while a partition is active a message can
  not cross between two different groups, so a red line in the UI and the
  delivery rule are the same fact;
* **randomness** is a hash of ``(seed, message id, salt)`` rather than a stream
  consumed in queue order, so two runs with the same inputs produce the same
  trace even if a caller pumps the network in different-sized steps;
* **queues are bounded**; overflow behavior is configured (``drop-oldest``,
  ``drop-newest`` or ``reject``) and every decision is recorded.

Reconnection behavior is configured too: ``flush`` sends what waited while the
partition was active, ``hold`` waits ``reconnect_hold_s`` first, and ``drop``
discards messages that were born during the partition.

Every event carries a simulated timestamp, so a trace can be replayed step by
step. No message is ever delivered "because the UI drew a link": delivery is the
only thing that establishes delivery.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

TRANSPORT_VERSION = "message-transport-1"

OVERFLOW_POLICIES = ("drop-oldest", "drop-newest", "reject")
RECONNECT_POLICIES = ("flush", "hold", "drop")

FIDELITY = (
    "bandwidth is a per-source serial link budget; a message occupies the link for size_bit / bandwidth_bps",
    "latency is a constant added to every delivery; propagation is not range-dependent",
    "loss, duplication and reordering are hash-seeded probabilities, not RF or protocol simulation",
    "partitions are group splits over node ids; a message never crosses two different groups while active",
)


class TransportError(ValueError):
    """An invalid transport configuration, message or call order."""


def _uniform(seed: int, message_id: str, salt: str) -> float:
    """Deterministic uniform draw in [0, 1) for one (seed, message, salt)."""
    digest = hashlib.sha256(f"{seed}|{message_id}|{salt}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(0xFFFFFFFFFFFF)


def _finite(name: str, value: Any) -> float:
    import math

    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise TransportError(f"{name} must be a finite number, got {value!r}")
    return float(value)


@dataclass(frozen=True)
class TransportConfig:
    """Everything that decides whether, when and how often a message arrives."""

    bandwidth_bps: float = 1.0e6
    latency_s: float = 0.0
    loss_probability: float = 0.0
    duplicate_probability: float = 0.0
    reorder_window_s: float = 0.0
    duplicate_delay_s: float = 0.5
    queue_capacity: int = 16
    overflow_policy: str = "drop-oldest"
    ttl_s: float = 600.0
    seed: int = 0
    on_reconnect: str = "flush"
    reconnect_hold_s: float = 0.0

    def __post_init__(self) -> None:
        for name in ("bandwidth_bps", "latency_s", "loss_probability", "duplicate_probability",
                     "reorder_window_s", "duplicate_delay_s", "ttl_s", "reconnect_hold_s"):
            _finite(name, getattr(self, name))
        if self.bandwidth_bps <= 0.0:
            raise TransportError("bandwidth_bps must be positive")
        if self.latency_s < 0.0 or self.ttl_s < 0.0 or self.duplicate_delay_s < 0.0:
            raise TransportError("latency, ttl and duplicate delay must be non-negative")
        if not 0.0 <= self.loss_probability <= 1.0:
            raise TransportError("loss_probability must be within [0, 1]")
        if not 0.0 <= self.duplicate_probability <= 1.0:
            raise TransportError("duplicate_probability must be within [0, 1]")
        if self.overflow_policy not in OVERFLOW_POLICIES:
            raise TransportError(
                f"overflow_policy {self.overflow_policy!r} must be one of {OVERFLOW_POLICIES}"
            )
        if self.on_reconnect not in RECONNECT_POLICIES:
            raise TransportError(
                f"on_reconnect {self.on_reconnect!r} must be one of {RECONNECT_POLICIES}"
            )
        if self.queue_capacity < 1:
            raise TransportError("queue_capacity must be at least 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "bandwidth_bps": self.bandwidth_bps,
            "latency_s": self.latency_s,
            "loss_probability": self.loss_probability,
            "duplicate_probability": self.duplicate_probability,
            "reorder_window_s": self.reorder_window_s,
            "duplicate_delay_s": self.duplicate_delay_s,
            "queue_capacity": self.queue_capacity,
            "overflow_policy": self.overflow_policy,
            "ttl_s": self.ttl_s,
            "seed": self.seed,
            "on_reconnect": self.on_reconnect,
            "reconnect_hold_s": self.reconnect_hold_s,
        }


@dataclass(frozen=True)
class Message:
    """An immutable message envelope handed to the transport."""

    id: str
    source: str
    destination: str
    kind: str = "data"
    payload: Mapping[str, Any] = field(default_factory=dict)
    size_bit: float = 4_096.0
    created_s: float = 0.0

    def __post_init__(self) -> None:
        if not self.id:
            raise TransportError("message id must be non-empty")
        if not self.source or not self.destination:
            raise TransportError(f"message {self.id!r} needs a source and a destination")
        if self.source == self.destination:
            raise TransportError(f"message {self.id!r} is addressed to its own source")
        if not isinstance(self.size_bit, (int, float)) or isinstance(self.size_bit, bool) or self.size_bit <= 0:
            raise TransportError(f"message {self.id!r} must have a positive size_bit")
        _finite(f"message {self.id}.created_s", self.created_s)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "destination": self.destination,
            "kind": self.kind,
            "payload": dict(self.payload),
            "size_bit": self.size_bit,
            "created_s": self.created_s,
        }


@dataclass(frozen=True)
class Partition:
    """A time-bounded split of the fleet into groups that can not exchange."""

    start_s: float
    end_s: float
    groups: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        if self.end_s <= self.start_s:
            raise TransportError("a partition must have a positive duration")
        if len(self.groups) < 2:
            raise TransportError("a partition needs at least two groups")
        seen: set[str] = set()
        for group in self.groups:
            for node in group:
                if node in seen:
                    raise TransportError(f"node {node!r} appears in two partition groups")
                seen.add(node)

    def active(self, time_s: float) -> bool:
        return self.start_s <= time_s < self.end_s

    def separates(self, a: str, b: str) -> bool:
        group_a = next((index for index, group in enumerate(self.groups) if a in group), None)
        group_b = next((index for index, group in enumerate(self.groups) if b in group), None)
        return group_a is not None and group_b is not None and group_a != group_b

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_s": self.start_s,
            "end_s": self.end_s,
            "groups": [list(group) for group in self.groups],
        }


@dataclass
class Delivery:
    message_id: str
    source: str
    destination: str
    sent_s: float
    delivered_s: float
    duplicate: bool = False
    reordered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "source": self.source,
            "destination": self.destination,
            "sent_s": round(self.sent_s, 6),
            "delivered_s": round(self.delivered_s, 6),
            "duplicate": self.duplicate,
            "reordered": self.reordered,
        }


LinkPredicate = Callable[[str, str, float], bool]


class Network:
    """A deterministic store-and-forward network over simulated links."""

    def __init__(
        self,
        nodes: Iterable[str],
        *,
        config: TransportConfig | None = None,
        link: LinkPredicate | None = None,
        partitions: Sequence[Partition] = (),
    ) -> None:
        self.nodes = tuple(sorted(set(nodes)))
        if not self.nodes:
            raise TransportError("a network needs at least one node")
        self.config = config or TransportConfig()
        self._link = link or (lambda a, b, t: True)
        self.partitions = list(partitions)
        self._queues: dict[str, list[Message]] = {node: [] for node in self.nodes}
        self._inflight: list[tuple[float, int, Message, bool, float]] = []
        self._next_free: dict[str, float] = {node: 0.0 for node in self.nodes}
        self._hold_until: dict[tuple[str, str], float] = {}
        self._previous_blocked: set[tuple[str, str]] = set()
        self._now = 0.0
        self._sequence = 0
        self._message_counter = 0
        self.deliveries: list[Delivery] = []
        self.events: list[dict[str, Any]] = []
        self._sent_order: dict[str, float] = {}
        self._transmit_rank: dict[str, int] = {}
        self._last_arrived_rank: dict[tuple[str, str], int] = {}

    # --- helpers ---------------------------------------------------------------
    def _event(self, kind: str, time_s: float, message: Message | None, **detail: Any) -> None:
        payload: dict[str, Any] = {"type": kind, "time_s": round(time_s, 6)}
        if message is not None:
            payload.update({
                "message_id": message.id,
                "source": message.source,
                "destination": message.destination,
            })
        payload.update(detail)
        self.events.append(payload)

    def _blocked(self, a: str, b: str, time_s: float) -> bool:
        return any(partition.active(time_s) and partition.separates(a, b)
                   for partition in self.partitions)

    def _reachable(self, a: str, b: str, time_s: float) -> bool:
        return self._link(a, b, time_s) and not self._blocked(a, b, time_s)

    def _queue_total(self, source: str) -> int:
        return len(self._queues.setdefault(source, []))

    def queued(self, source: str | None = None) -> int:
        if source is not None:
            return len(self._queues.get(source, []))
        return sum(len(queue) for queue in self._queues.values())

    def next_message_id(self) -> str:
        self._message_counter += 1
        return f"msg-{self._message_counter:05d}"

    # --- sending ---------------------------------------------------------------
    def send(self, message: Message, *, time_s: float | None = None) -> str:
        """Enqueue a message; returns the message id (as accepted or dropped)."""
        now = self._now if time_s is None else float(time_s)
        if now < self._now:
            raise TransportError(f"time must not go backwards ({now} < {self._now})")
        if message.source not in self._queues:
            raise TransportError(f"unknown source node {message.source!r}")
        if message.destination not in self._queues:
            raise TransportError(f"unknown destination node {message.destination!r}")
        if message.id in self._sent_order:
            raise TransportError(f"duplicate message id {message.id!r}")
        self._sent_order[message.id] = now

        if self._blocked(message.source, message.destination, now):
            if self.config.on_reconnect == "drop":
                self._event("dropped", now, message, reason="partition")
                return message.id

        queue = self._queues[message.source]
        if len(queue) >= self.config.queue_capacity:
            if self.config.overflow_policy == "reject":
                self._event("dropped", now, message, reason="overflow")
                return message.id
            if self.config.overflow_policy == "drop-oldest":
                dropped = queue.pop(0)
                self._event("dropped", now, dropped, reason="overflow")
            else:  # drop-newest
                self._event("dropped", now, message, reason="overflow")
                return message.id
        queue.append(message)
        self._event("enqueued", now, message, size_bit=message.size_bit)
        return message.id

    # --- stepping ---------------------------------------------------------------
    def advance(self, time_s: float) -> list[Delivery]:
        """Deliver everything due by ``time_s`` and start every eligible send."""
        if time_s < self._now:
            raise TransportError(f"time must not go backwards ({time_s} < {self._now})")
        self._now = float(time_s)
        self._expire_and_reconnect()

        due = sorted(
            (item for item in self._inflight if item[0] <= self._now),
            key=lambda item: (item[0], item[1]),
        )
        self._inflight = [item for item in self._inflight if item[0] > self._now]
        delivered: list[Delivery] = []
        for deliver_at, _seq, message, duplicate, sent_at, rank in due:
            if deliver_at - message.created_s > self.config.ttl_s:
                self._event("dropped", self._now, message, reason="ttl")
                continue
            pair = (message.source, message.destination)
            # Reordering is a property of the delivery sequence: an older send
            # arriving after a newer one has already been handed over.
            previous = self._last_arrived_rank.get(pair, -1)
            reordered = rank < previous
            self._last_arrived_rank[pair] = max(previous, rank)
            delivery = Delivery(
                message_id=message.id,
                source=message.source,
                destination=message.destination,
                sent_s=sent_at,
                delivered_s=deliver_at,
                duplicate=duplicate,
                reordered=reordered,
            )
            delivered.append(delivery)
            self.deliveries.append(delivery)
            self._event("delivered", deliver_at, message,
                        duplicate=duplicate, reordered=reordered)

        self._transmit()
        return delivered

    def _expire_and_reconnect(self) -> None:
        """Expire stale queued messages and apply the reconnect policy."""
        now = self._now
        for source in sorted(self._queues):
            kept: list[Message] = []
            for message in self._queues[source]:
                if now - message.created_s > self.config.ttl_s:
                    self._event("dropped", now, message, reason="ttl")
                    continue
                pair = (message.source, message.destination)
                if pair in self._hold_until and now < self._hold_until[pair]:
                    kept.append(message)
                    continue
                kept.append(message)
            self._queues[source] = kept

        # Detect partition endings and configure the reconnection behavior.
        blocked_now = {
            (a, b) for a in self.nodes for b in self.nodes
            if a != b and self._blocked(a, b, now)
        }
        ended = self._previous_blocked - blocked_now
        for a, b in ended:
            if self.config.on_reconnect == "hold":
                self._hold_until[(a, b)] = now + self.config.reconnect_hold_s
                self._event("reconnected", now, None, source=a, destination=b,
                            action="hold", hold_s=self.config.reconnect_hold_s)
            else:
                self._hold_until.pop((a, b), None)
                self._event("reconnected", now, None, source=a, destination=b,
                            action=self.config.on_reconnect)
        self._previous_blocked = blocked_now

    def _transmit(self) -> None:
        now = self._now
        for source in self.nodes:
            queue = self._queues[source]
            while queue:
                message = queue[0]
                if now - message.created_s > self.config.ttl_s:
                    queue.pop(0)
                    self._event("dropped", now, message, reason="ttl")
                    continue
                if not self._reachable(source, message.destination, now):
                    break  # head-of-line blocking keeps FIFO order per source
                pair = (source, message.destination)
                if pair in self._hold_until and now < self._hold_until[pair]:
                    break
                queue.pop(0)
                if _uniform(self.config.seed, message.id, "loss") < self.config.loss_probability:
                    self._event("dropped", now, message, reason="loss")
                    continue
                start = max(now, self._next_free[source])
                duration = message.size_bit / self.config.bandwidth_bps
                self._next_free[source] = start + duration
                jitter = 0.0
                if self.config.reorder_window_s > 0.0:
                    jitter = _uniform(self.config.seed, message.id, "reorder") * self.config.reorder_window_s
                deliver_at = start + duration + self.config.latency_s + jitter
                self._sequence += 1
                rank = self._sequence
                self._transmit_rank[message.id] = rank
                self._event("transmitted", now, message, start_s=start, deliver_at=deliver_at)
                self._schedule(message, deliver_at, duplicate=False, sent_at=now, rank=rank)
                if _uniform(self.config.seed, message.id, "duplicate") < self.config.duplicate_probability:
                    duplicate_at = deliver_at + self.config.duplicate_delay_s
                    self._schedule(message, duplicate_at, duplicate=True, sent_at=now, rank=rank)
                    self._event("duplicated", now, message, deliver_at=duplicate_at)

    def _schedule(self, message: Message, deliver_at: float, *, duplicate: bool,
                  sent_at: float, rank: int) -> None:
        if deliver_at - message.created_s > self.config.ttl_s:
            self._event("dropped", self._now, message, reason="ttl")
            return
        self._inflight.append((deliver_at, self._sequence, message, duplicate, sent_at, rank))

    # --- reporting ---------------------------------------------------------------
    def received(self, node: str) -> list[Delivery]:
        return [delivery for delivery in self.deliveries if delivery.destination == node]

    def metrics(self) -> dict[str, Any]:
        delivered_ids = {delivery.message_id for delivery in self.deliveries if not delivery.duplicate}
        duplicates = sum(1 for delivery in self.deliveries if delivery.duplicate)
        dropped = [event for event in self.events if event["type"] == "dropped"]
        return {
            "sent": len(self._sent_order),
            "delivered": len(delivered_ids),
            "deliveries": len(self.deliveries),
            "duplicates": duplicates,
            "dropped": len(dropped),
            "drop_reasons": sorted({event.get("reason", "") for event in dropped}),
            "queued": self.queued(),
            "in_flight": len(self._inflight),
        }

    def trace_payload(self) -> dict[str, Any]:
        return {
            "version": TRANSPORT_VERSION,
            "fidelity": list(FIDELITY),
            "config": self.config.to_dict(),
            "partitions": [partition.to_dict() for partition in self.partitions],
            "nodes": list(self.nodes),
            "events": list(self.events),
            "deliveries": [delivery.to_dict() for delivery in self.deliveries],
            "metrics": self.metrics(),
        }

    def trace(self) -> str:
        return json.dumps(self.trace_payload(), sort_keys=True, separators=(",", ":"))


def link_from_contact_plan(plan: Sequence[Any]) -> LinkPredicate:
    """A link predicate backed by Day 29 contact opportunities."""
    windows = [(item.a_id, item.b_id, item.start_s, item.end_s) for item in plan]

    def predicate(a: str, b: str, time_s: float) -> bool:
        for left, right, start, end in windows:
            if start <= time_s <= end and ((left == a and right == b) or (left == b and right == a)):
                return True
        return False

    return predicate


def network_from_contacts(
    nodes: Iterable[str],
    plan: Sequence[Any],
    *,
    config: TransportConfig | None = None,
    partitions: Sequence[Partition] = (),
) -> Network:
    return Network(nodes, config=config, link=link_from_contact_plan(plan), partitions=partitions)


def message_payload() -> dict[str, Any]:
    """Registry-style description of transport behaviour for the API/UI."""
    return {
        "version": TRANSPORT_VERSION,
        "fidelity": list(FIDELITY),
        "overflow_policies": list(OVERFLOW_POLICIES),
        "reconnect_policies": list(RECONNECT_POLICIES),
        "defaults": TransportConfig().to_dict(),
    }
