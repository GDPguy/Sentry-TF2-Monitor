import threading
import unittest
from unittest.mock import Mock

from sentry_app.logic import AppLogic
from sentry_app.tf2_monitor import TF2Monitor


class TF2ParserTests(unittest.TestCase):
    def test_map_paths(self):
        for separator in ("\\", "/"):
            response = f"maps{separator}koth_harvest_event.bsp"
            parsed = TF2Monitor.parse_dumpstringtables(response)
            self.assertEqual(parsed["name"], "koth_harvest_event")
            self.assertEqual(parsed["contract_page"], "official maps")

    def test_multiple_party_members(self):
        response = (
            "In 2 queues:\nLeaderID: [U:1:123]\n"
            "member_ids: 76561197960265729, 76561197960265730\n"
        )
        party = TF2Monitor.parse_TPD(response)
        self.assertEqual(party["member_ids"], ["[U:1:1]", "[U:1:2]"])
        self.assertEqual(party["in_queue"], 2)


class PlayerPollingTests(unittest.TestCase):
    def test_timeout_preserves_players(self):
        logic = AppLogic.__new__(AppLogic)
        logic.state_lock = threading.RLock()
        logic.connected_red_players = ["cached"]
        logic.connected_blue_players = []
        logic.connected_spectator_players = []
        logic.connected_unassigned_players = []
        logic.rcon = Mock()
        logic.rcon.execute.return_value = (False, "__TIMEOUT__")
        logic._reset_state = Mock()

        players, state = logic.get_players()
        self.assertEqual(players, (["cached"], [], []))
        self.assertEqual(state, "timeout")
        logic._reset_state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
