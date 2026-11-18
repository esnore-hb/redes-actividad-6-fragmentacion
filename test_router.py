import random
from pathlib import Path
import tempfile
import unittest
from router import (check_routes, load_routes, HEADER_SIZE, create_packet,
                    parse_packet, fragment_IP_packet, reassemble_IP_packet)


def packet(payload=b"hola!", identifier=347, **fields):
    return create_packet({**dict(ip="127.0.0.1", puerto=8885, ttl=10,
        id=identifier, offset=0, flag=0, mensaje=payload), **fields})


class RouteTests(unittest.TestCase):
    def test_cidr_prefix_membership_and_bare_ip(self):
        cases = [
            ("0.0.0.0/0", "255.255.255.255", True),
            ("10.0.0.1/8", "10.255.255.255", True),
            ("10.0.0.1/8", "11.0.0.1", False),
            ("10.2.0.1/16", "10.2.255.255", True),
            ("10.2.0.1/16", "10.3.0.1", False),
            ("10.2.3.99/24", "10.2.3.0", True),
            ("10.2.3.99/24", "10.2.3.255", True),
            ("10.2.3.99/24", "10.2.4.0", False),
            ("10.2.3.1/31", "10.2.3.0", True),
            ("10.2.3.1/31", "10.2.3.2", False),
            ("10.2.3.1/32", "10.2.3.1", True),
            ("10.2.3.1/32", "10.2.3.2", False),
            ("127.0.0.1", "127.0.0.1", True),
            ("127.0.0.1", "127.0.0.2", False),
        ]
        with tempfile.TemporaryDirectory() as directory:
            routes = Path(directory) / "rutas.txt"
            for network, destination, matches in cases:
                with self.subTest(network=network, destination=destination):
                    routes.write_text(f"{network} 8881 8885 127.0.0.1 9001 100\n")
                    result = check_routes(routes, (destination, 8885), {})
                    self.assertEqual(result, (("127.0.0.1", 9001), 100) if matches else None)

    def test_invalid_ipv4_and_prefixes(self):
        with tempfile.TemporaryDirectory() as directory:
            routes = Path(directory) / "rutas.txt"
            for network in ("127.0.0.1/33", "127.0.0.1/-1", "256.0.0.1/24",
                            "127.0.1/24", "no-es-ip/24"):
                with self.subTest(network=network):
                    routes.write_text(f"{network} 8881 8885 127.0.0.1 9001 100\n")
                    with self.assertRaises(ValueError):
                        load_routes(routes)
            routes.write_text("127.0.0.1/24 8881 8885 127.0.0.999 9001 100\n")
            with self.assertRaises(ValueError):
                load_routes(routes)
            routes.write_text("127.0.0.1/24 8881 8885 127.0.0.1 9001 100\n")
            with self.assertRaises(ValueError):
                check_routes(routes, ("127.0.0.999", 8885), {})

    def test_equivalent_cidr_addresses_share_round_robin_area(self):
        with tempfile.TemporaryDirectory() as directory:
            routes = Path(directory) / "rutas.txt"
            routes.write_text(
                "10.2.3.99/24 8881 8885 127.0.0.1 9001 100\n"
                "10.2.3.0/24 8881 8885 127.0.0.1 9002 80\n")
            turns = {}
            self.assertEqual(check_routes(routes, ("10.2.3.7", 8881), turns),
                             (("127.0.0.1", 9001), 100))
            self.assertEqual(check_routes(routes, ("10.2.3.8", 8885), turns),
                             (("127.0.0.1", 9002), 80))

    def test_round_robin_mtu_and_no_route(self):
        routes = Path(__file__).with_name("rutas_R2_v3_mtu.txt")
        counters = {}
        selected = [check_routes(routes, ("127.0.0.1", 8885), counters) for _ in range(4)]
        self.assertEqual(selected, [(("127.0.0.1", 8883), 50),
            (("127.0.0.1", 8884), 80)] * 2)
        self.assertIsNone(check_routes(routes, ("192.0.2.1", 8885), counters))
        self.assertEqual(len(load_routes("rutas_R5_v3_mtu.txt")), 2)

    def test_round_robin_shared_area_and_independent_areas(self):
        with tempfile.TemporaryDirectory() as directory:
            routes = Path(directory) / "rutas.txt"
            routes.write_text(
                "127.0.0.1/24 8881 8882 127.0.0.1 9001 100\n"
                "127.0.0.1/24 8881 8882 127.0.0.1 9002 80\n"
                "127.0.0.1/24 8881 8882 127.0.0.1 9003 50\n"
                "127.0.0.1/24 8883 8885 127.0.0.1 9004 80\n"
                "127.0.0.1/24 8883 8885 127.0.0.1 9005 50\n"
                "0.0.0.0/0 0 65535 127.0.0.1 7000 100\n")
            counters = {}
            destinations = (8881, 8883, 8882, 8884, 8881, 8882)
            selected = [check_routes(routes, ("127.0.0.1", port), counters)[0][1]
                        for port in destinations]
            self.assertEqual(selected, [9001, 9004, 9002, 9005, 9003, 9001])
            self.assertEqual(check_routes(routes, ("192.0.2.1", 80), counters),
                             (("127.0.0.1", 7000), 100))



class FragmentationTests(unittest.TestCase):
    def test_fragmentation_boundaries(self):
        raw = packet(b"a" * 130)
        self.assertEqual(fragment_IP_packet(raw, 150), [raw])
        self.assertEqual(fragment_IP_packet(raw, 151), [raw])
        fragments = fragment_IP_packet(raw, 100)
        self.assertEqual([len(f) for f in fragments], [100, 70])
        self.assertEqual([parse_packet(f)["offset"] for f in fragments], [0, 80])
        self.assertEqual([parse_packet(f)["flag"] for f in fragments], [1, 0])
        with self.assertRaises(ValueError):
            fragment_IP_packet(raw, HEADER_SIZE)

    def test_refragmentation_preserves_parent_flag_and_offsets(self):
        raw = packet(bytes(range(130)))
        fragments = fragment_IP_packet(raw, 100)
        smaller = [child for parent in fragments
                   for child in fragment_IP_packet(parent, 50)]
        self.assertEqual([parse_packet(f)["offset"] for f in smaller], [0, 30, 60, 80, 110])
        self.assertEqual([parse_packet(f)["flag"] for f in smaller], [1, 1, 1, 1, 0])
        self.assertTrue(all(len(f) <= 50 for f in smaller))
        self.assertEqual(b"".join(parse_packet(f)["mensaje"] for f in smaller),
                         parse_packet(raw)["mensaje"])
        self.assertTrue(all(parse_packet(f)["id"] == 347 and
                            parse_packet(f)["ttl"] == 10 for f in smaller))

    def test_refragmentation_of_nonfinal_parent(self):
        parent = packet(bytes(range(60)), offset=37, flag=1)
        fragments = fragment_IP_packet(parent, 50)
        self.assertEqual([len(f) for f in fragments], [50, 50])
        self.assertEqual([parse_packet(f)["offset"] for f in fragments], [37, 67])
        self.assertEqual([parse_packet(f)["flag"] for f in fragments], [1, 1])
        self.assertEqual(b"".join(parse_packet(f)["mensaje"] for f in fragments),
                         bytes(range(60)))



class ReassemblyTests(unittest.TestCase):
    def test_missing_duplicate_and_interleaved(self):
        originals = [packet(b"a" * 130, 1), packet("á🐶".encode() * 25, 2)]
        groups = [fragment_IP_packet(raw, 50) for raw in originals]
        self.assertIsNone(reassemble_IP_packet([]))
        self.assertEqual(reassemble_IP_packet([packet()]), packet())
        for group in groups:
            for index in range(len(group)):
                self.assertIsNone(reassemble_IP_packet(group[:index] + group[index+1:]))
            self.assertEqual(reassemble_IP_packet(group + [group[0]]),
                             originals[groups.index(group)])
        pending = {1: [], 2: []}
        stream = groups[0] + groups[1]
        random.Random(6).shuffle(stream)
        completed = {}
        for raw in stream:
            identifier = parse_packet(raw)["id"]
            pending[identifier].append(raw)
            complete = reassemble_IP_packet(pending[identifier])
            if complete:
                completed[identifier] = complete
        self.assertEqual(completed, dict(zip((1, 2), originals)))
        self.assertIsNone(reassemble_IP_packet(groups[0] + groups[1]))

    def test_overlap_rejected(self):
        fragments = fragment_IP_packet(packet(b"a" * 130), 100)
        modified = parse_packet(fragments[1])
        modified["offset"] = 79
        self.assertIsNone(reassemble_IP_packet([fragments[0], create_packet(modified)]))

    def test_empty_payload_and_single_incomplete_fragments(self):
        self.assertEqual(reassemble_IP_packet([packet(b"")]), packet(b""))
        self.assertIsNone(reassemble_IP_packet([packet(b"abc", flag=1)]))
        self.assertIsNone(reassemble_IP_packet([packet(b"abc", offset=3)]))

    def test_mixed_ttl_after_different_paths(self):
        fragments = fragment_IP_packet(packet(b"a" * 130), 50)
        changed = [create_packet({**parse_packet(raw), "ttl": 9 - i})
                   for i, raw in enumerate(fragments)]
        assembled = parse_packet(reassemble_IP_packet(changed[::-1]))
        self.assertEqual(assembled["mensaje"], b"a" * 130)
        self.assertEqual(assembled["ttl"], 5)

    def test_reassemble_refragmented_packet(self):
        original = packet(bytes(range(130)))
        fragments = [child for parent in fragment_IP_packet(original, 100)
                     for child in fragment_IP_packet(parent, 50)]
        self.assertEqual(reassemble_IP_packet(fragments[::-1]), original)



class HeaderTests(unittest.TestCase):
    def test_binary_roundtrip(self):
        raw = (b"\x7f\x00\x00\x01" + (8885).to_bytes(2, "big") + b"\x0a"
               + (347).to_bytes(4, "big") + bytes(4)
               + (256).to_bytes(4, "big") + b"\x00" + bytes(range(256)))
        self.assertEqual(HEADER_SIZE, 20)
        parsed = parse_packet(raw)
        self.assertEqual(parsed, dict(ip="127.0.0.1", puerto=8885, ttl=10,
            id=347, offset=0, tamano=256, flag=0, mensaje=bytes(range(256))))
        self.assertEqual(create_packet(parsed), raw)
        boundary = dict(ip="255.255.255.255", puerto=65535, ttl=255,
            id=2**32 - 1, offset=2**32 - 1, tamano=0, flag=1, mensaje=b"")
        self.assertEqual(parse_packet(create_packet(boundary)), boundary)

    def test_invalid_packets(self):
        for raw in (b"short", packet()[:-1], packet() + b"extra"):
            with self.assertRaises(ValueError):
                parse_packet(raw)
        for field, value in (("puerto", 65536), ("ttl", 256), ("id", 2**32),
                             ("offset", -1), ("flag", 2), ("ttl", "10")):
            with self.subTest(field=field, value=value):
                fields = parse_packet(packet())
                fields[field] = value
                with self.assertRaises(ValueError):
                    create_packet(fields)


if __name__ == "__main__":
    unittest.main()
