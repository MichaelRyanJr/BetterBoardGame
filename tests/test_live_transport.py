import os
import socket
import time
import unittest

from board.board_client import BoardClient, DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT
from shared.constants import ErrorCode, EventType
from shared.game_state import Coordinate, Move
from shared.move_validation import legal_moves_for_player

try:
    from websockets.sync.client import connect
except ImportError:
    connect = None


RESPONSE_TIMEOUT_SECONDS = 5.0
LATENCY_LIMIT_MS = 2000.0


def live_transport_tests_enabled():
    """
    Return True only when the user explicitly enables live transport tests.

    This keeps the default unit test suite fast and predictable while still
    allowing the live transport test to be run on demand.
    """
    value = os.environ.get("BBG_RUN_LIVE_TRANSPORT_TESTS", "0")
    return value == "1"


def can_reach_server(host, port, timeout_seconds=1.0):
    """
    Return True if a TCP connection to the live server can be opened.
    """
    test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    test_socket.settimeout(timeout_seconds)

    try:
        test_socket.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        test_socket.close()


@unittest.skipUnless(connect is not None, "websockets is not installed")
@unittest.skipUnless(
    live_transport_tests_enabled(),
    "Set BBG_RUN_LIVE_TRANSPORT_TESTS=1 to run live transport tests"
)
class LiveTransportTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server_host = os.environ.get("BBG_SERVER_HOST", DEFAULT_SERVER_HOST)
        cls.server_port = int(os.environ.get("BBG_SERVER_PORT", DEFAULT_SERVER_PORT))

        # Default to a real mapped board identity so the server can interpret it
        # consistently with the hostname-based multiplayer setup.
        cls.board_id = os.environ.get("BBG_TEST_BOARD_ID", "BBG-BoardA")

        if not can_reach_server(cls.server_host, cls.server_port):
            raise unittest.SkipTest(
                "Live server is not reachable at "
                + cls.server_host
                + ":"
                + str(cls.server_port)
            )

    def setUp(self):
        self.client = BoardClient(
            board_id=self.board_id,
            server_host=self.server_host,
            server_port=self.server_port
        )

        self.websocket = connect(
            self.build_server_uri(),
            open_timeout=10,
            ping_interval=20,
            ping_timeout=20
        )

        # Every new connection should receive an initial canonical state.
        initial_result = self.receive_expected_event({EventType.STATE_SYNC})
        self.assertEqual(initial_result["event_type"], EventType.STATE_SYNC)
        self.assertTrue(self.client.has_state())

    def tearDown(self):
        if self.websocket is not None:
            self.websocket.close()
            self.websocket = None

    def build_server_uri(self):
        return "ws://" + self.server_host + ":" + str(self.server_port)

    def receive_one_message(self, timeout=RESPONSE_TIMEOUT_SECONDS):
        message_text = self.websocket.recv(timeout=timeout)

        if not isinstance(message_text, str):
            self.fail("Received a non-text WebSocket message.")

        return self.client.handle_incoming_json(message_text)

    def receive_expected_event(self, expected_event_types, timeout=RESPONSE_TIMEOUT_SECONDS):
        deadline = time.perf_counter() + timeout

        while True:
            remaining_time = deadline - time.perf_counter()

            if remaining_time <= 0:
                expected_names = []

                for event_type in expected_event_types:
                    expected_names.append(event_type.value)

                self.fail(
                    "Timed out waiting for one of these event types: "
                    + ", ".join(expected_names)
                )

            result = self.receive_one_message(timeout=remaining_time)

            if result["event_type"] in expected_event_types:
                return result

    def measure_round_trip(self, send_function, expected_event_types):
        start_time = time.perf_counter()
        send_function()
        result = self.receive_expected_event(expected_event_types)
        end_time = time.perf_counter()

        round_trip_ms = (end_time - start_time) * 1000.0
        return result, round_trip_ms

    def build_legal_move(self):
        state = self.client.get_state()
        self.assertIsNotNone(state)

        candidate_actions = legal_moves_for_player(state, state.current_player)
        self.assertGreater(len(candidate_actions), 0)

        selected_action = None

        # Prefer a quiet move when possible so the test changes less state.
        for action in candidate_actions:
            if len(action.captured_squares) == 0:
                selected_action = action
                break

        if selected_action is None:
            selected_action = candidate_actions[0]

        captured_squares = []

        for square in selected_action.captured_squares:
            captured_squares.append(Coordinate(square.row, square.col))

        return Move(
            player=state.current_player,
            from_square=Coordinate(
                selected_action.from_square.row,
                selected_action.from_square.col
            ),
            to_square=Coordinate(
                selected_action.to_square.row,
                selected_action.to_square.col
            ),
            captured_squares=captured_squares
        )

    def build_out_of_turn_move(self):
        state = self.client.get_state()
        self.assertIsNotNone(state)

        candidate_actions = legal_moves_for_player(state, state.current_player)
        self.assertGreater(len(candidate_actions), 0)

        selected_action = candidate_actions[0]

        captured_squares = []

        for square in selected_action.captured_squares:
            captured_squares.append(Coordinate(square.row, square.col))

        return Move(
            player=state.current_player.get_opponent(),
            from_square=Coordinate(
                selected_action.from_square.row,
                selected_action.from_square.col
            ),
            to_square=Coordinate(
                selected_action.to_square.row,
                selected_action.to_square.col
            ),
            captured_squares=captured_squares
        )

    def test_initial_connection_receives_state_sync(self):
        state = self.client.get_state()
        self.assertIsNotNone(state)
        self.assertEqual(self.client.game_id, state.game_id)
        self.assertEqual(self.client.session_id, state.session_id)

    def test_heartbeat_round_trip_under_two_seconds(self):
        def send_heartbeat():
            json_text = self.client.build_heartbeat_json()
            self.websocket.send(json_text)

        result, round_trip_ms = self.measure_round_trip(
            send_function=send_heartbeat,
            expected_event_types={EventType.HEARTBEAT}
        )

        self.assertLess(round_trip_ms, LATENCY_LIMIT_MS)
        self.assertEqual(result["event_type"], EventType.HEARTBEAT)
        self.assertEqual(self.client.last_heartbeat_status, "ok")

    def test_desync_detected_returns_state_sync(self):
        def send_desync():
            json_text = self.client.build_desync_detected_json(
                "unittest desync probe"
            )
            self.websocket.send(json_text)

        result, round_trip_ms = self.measure_round_trip(
            send_function=send_desync,
            expected_event_types={EventType.STATE_SYNC}
        )

        self.assertLess(round_trip_ms, LATENCY_LIMIT_MS)
        self.assertEqual(result["event_type"], EventType.STATE_SYNC)
        self.assertTrue(self.client.has_state())

    def test_illegal_state_detected_returns_state_sync(self):
        def send_illegal_state():
            json_text = self.client.build_illegal_state_detected_json(
                "unittest illegal state probe",
                ErrorCode.AMBIGUOUS_SCAN
            )
            self.websocket.send(json_text)

        result, round_trip_ms = self.measure_round_trip(
            send_function=send_illegal_state,
            expected_event_types={EventType.STATE_SYNC}
        )

        self.assertLess(round_trip_ms, LATENCY_LIMIT_MS)
        self.assertEqual(result["event_type"], EventType.STATE_SYNC)
        self.assertTrue(self.client.has_state())

    def test_legal_candidate_move_returns_state_sync(self):
        state_before = self.client.get_state()
        self.assertIsNotNone(state_before)

        legal_move = self.build_legal_move()

        def send_legal_move():
            json_text = self.client.build_candidate_move_json(legal_move)
            self.websocket.send(json_text)

        result, round_trip_ms = self.measure_round_trip(
            send_function=send_legal_move,
            expected_event_types={EventType.STATE_SYNC}
        )

        self.assertLess(round_trip_ms, LATENCY_LIMIT_MS)
        self.assertEqual(result["event_type"], EventType.STATE_SYNC)

        state_after = self.client.get_state()
        self.assertIsNotNone(state_after)
        self.assertGreater(state_after.version, state_before.version)

    def test_illegal_candidate_move_returns_error(self):
        illegal_move = self.build_out_of_turn_move()

        def send_illegal_move():
            json_text = self.client.build_candidate_move_json(illegal_move)
            self.websocket.send(json_text)

        result, round_trip_ms = self.measure_round_trip(
            send_function=send_illegal_move,
            expected_event_types={EventType.ERROR}
        )

        self.assertLess(round_trip_ms, LATENCY_LIMIT_MS)
        self.assertEqual(result["event_type"], EventType.ERROR)
        self.assertIsNotNone(self.client.last_error)
        self.assertEqual(
            self.client.last_error["error_code"],
            ErrorCode.OUT_OF_TURN
        )


if __name__ == "__main__":
    unittest.main()
