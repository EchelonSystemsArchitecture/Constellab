"""Day 30 acceptance tests: queues, loss, delay, duplication, reordering, partitions."""

import json
import unittest

from constellab_core import contacts, transport
from constellab_core.config import load_config
from constellab_core.transport import (
    FIDELITY,
    Message,
    Network,
    Partition,
    TransportConfig,
    TransportError,
    link_from_contact_plan,
    message_payload,
    network_from_contacts,
)


def msg(message_id: str, *, source: str = "sat-alpha", destination: str = "sat-bravo",
        created_s: float = 0.0, size_bit: float = 4_096.0) -> Message:
    return Message(
        id=message_id,
        source=source,
        destination=destination,
        kind="task-assignment",
        payload={"task": "task.hotspot.a"},
        size_bit=size_bit,
        created_s=created_s,
    )


def pair_nodes() -> list[str]:
    return ["sat-alpha", "sat-bravo"]


class TransportConfigTests(unittest.TestCase):
    def test_defaults_are_valid_and_published(self) -> None:
        payload = message_payload()
        self.assertEqual(payload["version"], transport.TRANSPORT_VERSION)
        self.assertEqual(set(payload["overflow_policies"]), {"drop-oldest", "drop-newest", "reject"})
        self.assertEqual(set(payload["reconnect_policies"]), {"flush", "hold", "drop"})
        self.assertTrue(FIDELITY)

    def test_invalid_configuration_is_rejected(self) -> None:
        with self.assertRaises(TransportError):
            TransportConfig(bandwidth_bps=0.0)
        with self.assertRaises(TransportError):
            TransportConfig(loss_probability=1.5)
        with self.assertRaises(TransportError):
            TransportConfig(overflow_policy="explode")
        with self.assertRaises(TransportError):
            TransportConfig(queue_capacity=0)

    def test_invalid_messages_are_rejected(self) -> None:
        with self.assertRaises(TransportError):
            msg("m", source="sat-alpha", destination="sat-alpha")
        with self.assertRaises(TransportError):
            Message(id="m", source="a", destination="b", size_bit=0.0)


class DeliveryTests(unittest.TestCase):
    def test_message_is_delivered_once_with_latency(self) -> None:
        network = Network(pair_nodes(), config=TransportConfig(latency_s=0.5))
        network.send(msg("m1"), time_s=0.0)
        network.advance(0.0)
        delivered = network.advance(10.0)
        self.assertEqual(len(delivered), 1)
        # latency plus the serialisation time of one 4,096-bit message at 1 Mbit/s
        self.assertAlmostEqual(delivered[0].delivered_s, 0.5 + 4_096.0 / 1.0e6, places=6)
        self.assertEqual(network.metrics()["delivered"], 1)
        self.assertEqual(len(network.received("sat-bravo")), 1)

    def test_bandwidth_sets_the_transmission_time(self) -> None:
        network = Network(pair_nodes(), config=TransportConfig(bandwidth_bps=1_000.0, latency_s=0.0))
        network.send(msg("m1", size_bit=2_000.0), time_s=0.0)
        network.advance(0.0)
        delivered = network.advance(10.0)
        self.assertAlmostEqual(delivered[0].delivered_s, 2.0, places=6)

    def test_loss_probability_one_drops_everything(self) -> None:
        network = Network(pair_nodes(), config=TransportConfig(loss_probability=1.0))
        network.send(msg("m1"), time_s=0.0)
        network.advance(0.0)
        self.assertEqual(network.advance(10.0), [])
        self.assertEqual(network.metrics()["dropped"], 1)
        self.assertIn("loss", network.metrics()["drop_reasons"])

    def test_duplication_delivers_twice(self) -> None:
        network = Network(pair_nodes(), config=TransportConfig(duplicate_probability=1.0))
        network.send(msg("m1"), time_s=0.0)
        network.advance(0.0)
        delivered = network.advance(10.0)
        self.assertEqual(len(delivered), 2)
        self.assertTrue(any(delivery.duplicate for delivery in delivered))
        self.assertEqual(network.metrics()["duplicates"], 1)

    def test_reordering_is_visible_in_the_trace(self) -> None:
        config = TransportConfig(reorder_window_s=10.0, seed=3)
        network = Network(pair_nodes(), config=config)
        network.send(msg("m1"), time_s=0.0)
        network.send(msg("m2"), time_s=0.0)
        network.advance(0.0)
        delivered = network.advance(20.0)
        self.assertEqual(len(delivered), 2)
        order = [delivery.message_id for delivery in delivered]
        self.assertNotEqual(order, ["m1", "m2"])
        self.assertTrue(any(delivery.reordered for delivery in delivered))

    def test_same_seed_and_events_produce_the_same_trace(self) -> None:
        def run() -> str:
            network = Network(pair_nodes(), config=TransportConfig(
                loss_probability=0.4, duplicate_probability=0.5, reorder_window_s=5.0, seed=17,
            ))
            for index in range(6):
                network.send(msg(f"m{index}", created_s=float(index)), time_s=float(index))
                network.advance(float(index))
            network.advance(60.0)
            return network.trace()

        self.assertEqual(run(), run())

    def test_unknown_nodes_and_repeated_ids_are_rejected(self) -> None:
        network = Network(pair_nodes())
        with self.assertRaises(TransportError):
            network.send(msg("m1", source="sat-unknown"))
        network.send(msg("m1"))
        with self.assertRaises(TransportError):
            network.send(msg("m1"))
        with self.assertRaises(TransportError):
            network.advance(-1.0)


class QueueTests(unittest.TestCase):
    def test_bounded_queue_drops_the_oldest(self) -> None:
        network = Network(pair_nodes(), config=TransportConfig(
            queue_capacity=1, overflow_policy="drop-oldest", ttl_s=1_000.0,
        ), link=lambda a, b, t: t >= 100.0)
        network.send(msg("m1"), time_s=0.0)
        network.send(msg("m2"), time_s=0.0)
        self.assertEqual(network.queued("sat-alpha"), 1)
        network.advance(0.0)
        network.advance(200.0)
        delivered = network.advance(210.0)
        self.assertEqual([delivery.message_id for delivery in delivered], ["m2"])
        self.assertEqual(network.metrics()["drop_reasons"], ["overflow"])

    def test_reject_policy_keeps_the_queue_and_refuses_new_messages(self) -> None:
        network = Network(pair_nodes(), config=TransportConfig(
            queue_capacity=1, overflow_policy="reject", ttl_s=1_000.0,
        ), link=lambda a, b, t: t >= 100.0)
        network.send(msg("m1"), time_s=0.0)
        network.send(msg("m2"), time_s=0.0)
        self.assertEqual(network.queued("sat-alpha"), 1)
        network.advance(0.0)
        network.advance(200.0)
        delivered = network.advance(210.0)
        self.assertEqual([delivery.message_id for delivery in delivered], ["m1"])

    def test_messages_expire(self) -> None:
        network = Network(pair_nodes(), config=TransportConfig(ttl_s=10.0),
                          link=lambda a, b, t: t >= 100.0)
        network.send(msg("m1", created_s=0.0), time_s=0.0)
        network.advance(0.0)
        network.advance(100.0)
        self.assertEqual(network.deliveries, [])
        self.assertEqual(network.metrics()["drop_reasons"], ["ttl"])


class PartitionTests(unittest.TestCase):
    def test_active_partition_blocks_delivery(self) -> None:
        partition = Partition(start_s=100.0, end_s=200.0, groups=(("sat-alpha",), ("sat-bravo",)))
        network = Network(pair_nodes(), config=TransportConfig(latency_s=0.1), partitions=[partition])
        network.send(msg("m1", created_s=150.0), time_s=150.0)
        network.advance(150.0)
        self.assertEqual(network.advance(180.0), [])
        self.assertEqual(network.metrics()["delivered"], 0)

    def test_flush_sends_what_waited_once_reconnected(self) -> None:
        partition = Partition(start_s=100.0, end_s=200.0, groups=(("sat-alpha",), ("sat-bravo",)))
        network = Network(pair_nodes(), config=TransportConfig(on_reconnect="flush"), partitions=[partition])
        network.send(msg("m1", created_s=150.0), time_s=150.0)
        network.advance(150.0)
        network.advance(200.0)
        delivered = network.advance(210.0)
        self.assertEqual(len(delivered), 1)
        self.assertGreaterEqual(delivered[0].delivered_s, 200.0)

    def test_drop_policy_discards_messages_born_inside_the_partition(self) -> None:
        partition = Partition(start_s=100.0, end_s=200.0, groups=(("sat-alpha",), ("sat-bravo",)))
        network = Network(pair_nodes(), config=TransportConfig(on_reconnect="drop"), partitions=[partition])
        network.send(msg("m1", created_s=150.0), time_s=150.0)
        network.advance(150.0)
        self.assertEqual(network.advance(300.0), [])
        self.assertEqual(network.metrics()["drop_reasons"], ["partition"])

    def test_hold_policy_waits_before_sending_after_reconnect(self) -> None:
        partition = Partition(start_s=100.0, end_s=200.0, groups=(("sat-alpha",), ("sat-bravo",)))
        network = Network(
            pair_nodes(),
            config=TransportConfig(on_reconnect="hold", reconnect_hold_s=50.0),
            partitions=[partition],
        )
        network.send(msg("m1", created_s=150.0), time_s=150.0)
        network.advance(150.0)
        network.advance(200.0)
        self.assertEqual(network.advance(240.0), [])
        network.advance(260.0)
        delivered = network.advance(270.0)
        self.assertEqual(len(delivered), 1)
        self.assertGreaterEqual(delivered[0].delivered_s, 250.0)

    def test_partition_groups_must_be_a_real_split(self) -> None:
        with self.assertRaises(TransportError):
            Partition(start_s=0.0, end_s=10.0, groups=(("a",),))
        with self.assertRaises(TransportError):
            Partition(start_s=0.0, end_s=10.0, groups=(("a",), ("a",)))


class ContactLinkTests(unittest.TestCase):
    def test_delivery_waits_for_the_contact_window(self) -> None:
        spec = contacts.topology_scenario("intermittently-connected")
        config = load_config(spec["config"])
        plan = contacts.contact_plan_for_config(
            config, link_key="link.optical", link_values=spec["link"], horizon_s=200.0, step_s=10.0
        )
        nodes = [satellite.id for satellite in config.satellites]
        network = network_from_contacts(
            nodes, plan, config=TransportConfig(ttl_s=1_000.0, latency_s=0.0)
        )
        network.send(msg("m1"), time_s=0.0)
        network.advance(0.0)
        delivered = network.advance(1_000.0)
        self.assertEqual(len(delivered), 1)
        window = next(item for item in plan if {item.a_id, item.b_id} == set(nodes))
        self.assertGreaterEqual(delivered[0].delivered_s, window.start_s)

    def test_link_predicate_follows_the_plan_direction_agnostically(self) -> None:
        spec = contacts.topology_scenario("fully-connected")
        config = load_config(spec["config"])
        plan = contacts.contact_plan_for_config(
            config, link_key="link.optical", link_values=spec["link"], horizon_s=60.0, step_s=30.0
        )
        predicate = link_from_contact_plan(plan)
        nodes = [satellite.id for satellite in config.satellites]
        for a in nodes:
            for b in nodes:
                if a != b:
                    self.assertTrue(predicate(a, b, 0.0), (a, b))
        self.assertFalse(predicate("sat-unknown", nodes[0], 0.0))


if __name__ == "__main__":
    unittest.main()
