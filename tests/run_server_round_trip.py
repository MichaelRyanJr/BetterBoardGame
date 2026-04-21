import argparse
import socket
import sys
import time

from board.board_client import BoardClient, DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT
from shared.constants import ErrorCode, EventType
from shared.game_state import Coordinate, Move
from shared.move_validation import legal_moves_for_player

try:
    from websockets.sync.client import connect
except ImportError:
    connect = None


DEFAULT_RESPONSE_TIMEOUT_SECONDS = 5.0
DEFAULT_TRIALS = 10
DEFAULT_MODE = "heartbeat"
SUPPORTED_MODES = [
    "heartbeat",
    "desync",
    "illegal-state",
    "legal-move",
    "illegal-move",
]


def can_reach_server(host, port, timeout_seconds=1.0):
    test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    test_socket.settimeout(timeout_seconds)

    try:
        test_socket.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        test_socket.close()


class LiveRoundTripLatencyRunner:
    """
    Measure server round-trip latency using one board connection and one local
    monotonic clock.

    This avoids clock synchronization issues between separate Pis. The timing is:
        local board client -> server -> same board client

    That is not the exact one-way board-to-board latency, but it is a practical
    and repeatable measurement of the live transport path using the board's
    internal clock.
    """

    def __init__(
        self,
        board_id,
        server_host,
        server_port,
        mode,
        trials,
        timeout_seconds,
    ):
        self.board_id = board_id
        self.server_host = server_host
        self.server_port = int(server_port)
        self.mode = mode
        self.trials = int(trials)
        self.timeout_seconds = float(timeout_seconds)

        self.client = None
        self.websocket = None

    def build_server_uri(self):
        return "ws://" + self.server_host + ":" + str(self.server_port)

    def connect(self):
        if connect is None:
            raise RuntimeError(
                "websockets is not installed. Install it with: pip install websockets"
            )

        if not can_reach_server(self.server_host, self.server_port):
            raise RuntimeError(
                "Live server is not reachable at "
                + self.server_host
                + ":"
                + str(self.server_port)
            )

        self.client = BoardClient(
            board_id=self.board_id,
            server_host=self.server_host,
            server_port=self.server_port,
        )

        self.websocket = connect(
            self.build_server_uri(),
            open_timeout=10,
            ping_interval=20,
            ping_timeout=20,
        )

        initial_result = self.receive_expected_event({EventType.STATE_SYNC})
        if initial_result["event_type"] != EventType.STATE_SYNC:
            raise RuntimeError("Did not receive initial state_sync after connect.")

    def close(self):
        if self.websocket is not None:
            try:
                self.websocket.close()
            finally:
                self.websocket = None

    def receive_one_message(self, timeout=None):
        if timeout is None:
            timeout = self.timeout_seconds

        message_text = self.websocket.recv(timeout=timeout)

        if not isinstance(message_text, str):
            raise RuntimeError("Received a non-text WebSocket message.")

        return self.client.handle_incoming_json(message_text)

    def receive_expected_event(self, expected_event_types):
        deadline_ns = time.perf_counter_ns() + int(self.timeout_seconds * 1_000_000_000)

        while True:
            remaining_ns = deadline_ns - time.perf_counter_ns()

            if remaining_ns <= 0:
                expected_names = []

                for event_type in expected_event_types:
                    expected_names.append(event_type.value)

                raise TimeoutError(
                    "Timed out waiting for one of these event types: "
                    + ", ".join(expected_names)
                )

            remaining_seconds = remaining_ns / 1_000_000_000.0
            result = self.receive_one_message(timeout=remaining_seconds)

            if result["event_type"] in expected_event_types:
                return result

    def build_legal_move(self):
        state = self.client.get_state()
        if state is None:
            raise RuntimeError("No canonical state is cached.")

        candidate_actions = legal_moves_for_player(state, state.current_player)
        if len(candidate_actions) == 0:
            raise RuntimeError("No legal moves are available from the current state.")

        selected_action = None

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
                selected_action.from_square.col,
            ),
            to_square=Coordinate(
                selected_action.to_square.row,
                selected_action.to_square.col,
            ),
            captured_squares=captured_squares,
        )

    def build_illegal_move(self):
        state = self.client.get_state()
        if state is None:
            raise RuntimeError("No canonical state is cached.")

        candidate_actions = legal_moves_for_player(state, state.current_player)
        if len(candidate_actions) == 0:
            raise RuntimeError("No legal baseline move exists to mutate.")

        selected_action = candidate_actions[0]
        captured_squares = []

        for square in selected_action.captured_squares:
            captured_squares.append(Coordinate(square.row, square.col))

        return Move(
            player=state.current_player.get_opponent(),
            from_square=Coordinate(
                selected_action.from_square.row,
                selected_action.from_square.col,
            ),
            to_square=Coordinate(
                selected_action.to_square.row,
                selected_action.to_square.col,
            ),
            captured_squares=captured_squares,
        )

    def build_send_function_and_expected_events(self):
        if self.mode == "heartbeat":
            def send_function():
                json_text = self.client.build_heartbeat_json()
                self.websocket.send(json_text)

            return send_function, {EventType.HEARTBEAT}

        if self.mode == "desync":
            def send_function():
                json_text = self.client.build_desync_detected_json(
                    "latency probe desync"
                )
                self.websocket.send(json_text)

            return send_function, {EventType.STATE_SYNC}

        if self.mode == "illegal-state":
            def send_function():
                json_text = self.client.build_illegal_state_detected_json(
                    "latency probe illegal state",
                    ErrorCode.AMBIGUOUS_SCAN,
                )
                self.websocket.send(json_text)

            return send_function, {EventType.STATE_SYNC}

        if self.mode == "legal-move":
            def send_function():
                legal_move = self.build_legal_move()
                json_text = self.client.build_candidate_move_json(legal_move)
                self.websocket.send(json_text)

            return send_function, {EventType.STATE_SYNC}

        if self.mode == "illegal-move":
            def send_function():
                illegal_move = self.build_illegal_move()
                json_text = self.client.build_candidate_move_json(illegal_move)
                self.websocket.send(json_text)

            return send_function, {EventType.ERROR}

        raise ValueError("Unsupported mode: " + str(self.mode))

    def run(self):
        self.connect()

        send_function, expected_event_types = self.build_send_function_and_expected_events()
        round_trip_ms_values = []

        print("Live round-trip latency test")
        print("Board ID:", self.board_id)
        print("Server:", self.server_host + ":" + str(self.server_port))
        print("Mode:", self.mode)
        print("Trials:", self.trials)
        print()

        for trial_index in range(self.trials):
            send_time_ns = time.perf_counter_ns()
            send_function()
            result = self.receive_expected_event(expected_event_types)
            receive_time_ns = time.perf_counter_ns()

            round_trip_ms = (receive_time_ns - send_time_ns) / 1_000_000.0
            round_trip_ms_values.append(round_trip_ms)

            print(
                "Trial "
                + str(trial_index + 1)
                + ": sent="
                + str(send_time_ns)
                + " ns, received="
                + str(receive_time_ns)
                + " ns, round_trip="
                + format(round_trip_ms, ".3f")
                + " ms, event="
                + result["event_type"].value
            )

        print()
        average_ms = sum(round_trip_ms_values) / len(round_trip_ms_values)
        minimum_ms = min(round_trip_ms_values)
        maximum_ms = max(round_trip_ms_values)

        print("Summary")
        print("Average round-trip: " + format(average_ms, ".3f") + " ms")
        print("Minimum round-trip: " + format(minimum_ms, ".3f") + " ms")
        print("Maximum round-trip: " + format(maximum_ms, ".3f") + " ms")


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Measure live server round-trip latency using one board connection and "
            "one local monotonic clock."
        )
    )

    parser.add_argument(
        "--board-id",
        default="BBG-BoardA",
        help="Board identity to use for the live connection.",
    )
    parser.add_argument(
        "--server-host",
        default=DEFAULT_SERVER_HOST,
        help="Server hostname or IP address.",
    )
    parser.add_argument(
        "--server-port",
        type=int,
        default=DEFAULT_SERVER_PORT,
        help="Server port.",
    )
    parser.add_argument(
        "--mode",
        choices=SUPPORTED_MODES,
        default=DEFAULT_MODE,
        help=(
            "Which live round-trip to measure. heartbeat is the simplest pure "
            "transport probe; legal-move includes shared rules and state update."
        ),
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=DEFAULT_TRIALS,
        help="How many round-trip samples to collect.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_RESPONSE_TIMEOUT_SECONDS,
        help="Response timeout in seconds for each trial.",
    )

    return parser


def main():
    parser = build_argument_parser()
    args = parser.parse_args()

    runner = LiveRoundTripLatencyRunner(
        board_id=args.board_id,
        server_host=args.server_host,
        server_port=args.server_port,
        mode=args.mode,
        trials=args.trials,
        timeout_seconds=args.timeout,
    )

    try:
        runner.run()
    finally:
        runner.close()


if __name__ == "__main__":
    main()
