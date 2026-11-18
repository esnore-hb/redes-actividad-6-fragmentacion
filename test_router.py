from pathlib import Path
import tempfile
import unittest
from router import check_routes, load_routes


class RouteTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
