import threading
import unittest
from unittest.mock import Mock, patch

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

    def test_empty_lobby_does_not_mark_server_connected(self):
        logic = AppLogic.__new__(AppLogic)
        logic.state_lock = threading.RLock()
        logic.state = {"process": False, "rcon": None, "server": None, "party": None}
        logic.rcon = Mock()
        logic.rcon.block_reason = None
        logic.rcon.execute.side_effect = [
            (True, "Failed to find party shared object"),
            (True, "remote IP: 127.0.0.1:27015\n"),
            (True, "maps\\\\koth_harvest_event.bsp"),
        ]
        logic.get_setting_bool = Mock(return_value=False)
        logic.get_players = Mock(return_value=(([], [], []), "connected"))

        with patch("sentry_app.logic.TF2Monitor.is_process_running", return_value=True):
            result = logic.update_state()

        self.assertEqual(result["rcon"], "connected")
        self.assertFalse(result["server"]["connected"])

    def test_empty_lobby_drops_cached_connection(self):
        logic = AppLogic.__new__(AppLogic)
        logic.state_lock = threading.RLock()
        logic.state = {
            "process": True,
            "rcon": "connected",
            "server": {"ip": "127.0.0.1:27015", "map": "cp_badlands", "connected": True, "lobby": (["old"], [], [])},
            "party": None,
        }
        logic.rcon = Mock()
        logic.rcon.block_reason = None
        logic.rcon.execute.return_value = (True, "Failed to find party shared object")
        logic.get_players = Mock(return_value=(([], [], []), "connected"))
        logic._process_chat_queue = Mock()

        with patch("sentry_app.logic.TF2Monitor.is_process_running", return_value=True):
            result = logic.update_state()

        self.assertIsNone(result["server"])
        self.assertIsNone(logic.state["server"])

    def test_nonempty_lobby_marks_server_connected(self):
        logic = AppLogic.__new__(AppLogic)
        logic.state_lock = threading.RLock()
        logic.state = {"process": False, "rcon": None, "server": None, "party": None}
        logic.rcon = Mock()
        logic.rcon.block_reason = None
        logic.rcon.execute.side_effect = [
            (True, "Failed to find party shared object"),
            (True, "remote IP: 127.0.0.1:27015\n"),
            (True, "maps\\\\koth_harvest_event.bsp"),
        ]
        logic.get_setting_bool = Mock(return_value=False)
        logic.get_players = Mock(return_value=((["player"], [], []), "connected"))

        with patch("sentry_app.logic.TF2Monitor.is_process_running", return_value=True):
            result = logic.update_state()

        self.assertTrue(result["server"]["connected"])




if __name__ == "__main__":
    unittest.main()
