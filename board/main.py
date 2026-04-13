import argparse
import logging
import socket
from threading import Event, Lock, Thread

from board.board_client import DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT
from board.board_controller import BoardController
from shared.constants import EventType
from shared.game_state import Coordinate, Move

try:
    from websockets.exceptions import ConnectionClosed
    from websockets.sync.client import connect
except ImportError as exc:
    raise ImportError(
        "This file requires the 'websockets' package. "
        "Install it with: pip install -U websockets"
    ) from exc


DEFAULT_HEARTBEAT_INTERVAL = 15.0
DEFAULT_SCAN_INTERVAL = 1.0


class BoardMain:
    def __init__(
        self,
        board_id,
        server_host=DEFAULT_SERVER_HOST,
        server_port=DEFAULT_SERVER_PORT,
        heartbeat_interval=DEFAULT_HEARTBEAT_INTERVAL
    ):
        self.board_id = board_id
        self.server_host = server_host
        self.server_port = server_port
        self.heartbeat_interval = heartbeat_interval

        self.controller = BoardController(
            board_id=board_id,
            server_host=server_host,
            server_port=server_port,
            scanner_mode="gpio",
            led_mode="hardware"
        )

        # Keep these references for compatibility with the existing runtime code.
        self.client = self.controller.client
        self.scanner = self.controller.scanner
        self.led_driver = self.controller.led_driver

        self.websocket = None
        self.websocket_lock = Lock()
        self.stop_event = Event()

        self.scan_interval = DEFAULT_SCAN_INTERVAL

    def build_server_uri(self):
        """Build the WebSocket URI for the server."""
        return "ws://" + self.server_host + ":" + str(self.server_port)

    def set_websocket(self, websocket):
        """Store the current live WebSocket connection."""
        with self.websocket_lock:
            self.websocket = websocket

    def clear_websocket(self):
        """Clear the stored WebSocket connection."""
        with self.websocket_lock:
            self.websocket = None

    def send_json(self, json_text):
        """Send one JSON message over the live WebSocket connection."""
        with self.websocket_lock:
            if self.websocket is None:
                return False

            self.websocket.send(json_text)
            return True

    def send_heartbeat(self):
        """Send one protocol heartbeat message to the server."""
        json_text = self.client.build_heartbeat_json()
        return self.send_json(json_text)

    def send_scan_snapshot(self, scan_matrix):
        """Send a raw scan snapshot to the server."""
        json_text = self.client.build_scan_snapshot_json(scan_matrix)
        return self.send_json(json_text)

    def send_stable_scan(self, scan_matrix):
        """Send a stable scan to the server."""
        json_text = self.client.build_stable_scan_json(scan_matrix)
        return self.send_json(json_text)

    def send_candidate_move(self, move):
        """Send a candidate move to the server."""
        json_text = self.client.build_candidate_move_json(move)
        return self.send_json(json_text)

    def send_move_from_coordinates(
        self,
        player,
        from_row,
        from_col,
        to_row,
        to_col,
        sequence_id=None
    ):
        """
        Build a Move object from coordinates and send it.

        This is mainly a convenience helper for quick testing.
        """
        move = Move(
            player=player,
            from_square=Coordinate(from_row, from_col),
            to_square=Coordinate(to_row, to_col),
            sequence_id=sequence_id
        )
        return self.send_candidate_move(move)

    def send_desync_detected(self, message_text):
        """Send a desync report to the server."""
        json_text = self.client.build_desync_detected_json(message_text)
        return self.send_json(json_text)

    def send_illegal_state_detected(self, message_text, error_code=None):
        """Send an illegal-state report to the server."""
        json_text = self.client.build_illegal_state_detected_json(
            message_text,
            error_code
        )
        return self.send_json(json_text)

    def log_state_summary(self):
        """Log a short summary of the current cached canonical state."""
        state = self.client.get_state()

        if state is None:
            logging.info("No canonical state is cached yet.")
            return

        if state.winner is None:
            winner_text = "none"
        else:
            winner_text = state.winner.value

        logging.info(
            "State version=%s move=%s current_player=%s winner=%s",
            state.version,
            state.move_number,
            state.current_player.value,
            winner_text
        )

    def handle_server_message(self, message_text):
        """Pass one server JSON message into BoardController and log the result."""
        self.controller.client = self.client
        result = self.controller.handle_incoming_json(message_text)
        event_type = result["event_type"]

        if event_type == EventType.STATE_SYNC:
            state_updated = result.get("state_updated", False)

            if state_updated:
                logging.info("Received state_sync and updated local cache.")
            else:
                logging.info("Received state_sync but local cache was already newer.")

            self.log_state_summary()
            return

        if event_type == EventType.ERROR:
            error_info = result.get("error", {})
            logging.warning(
                "Server error: code=%s message=%s",
                error_info.get("error_code"),
                error_info.get("message")
            )
            return

        if event_type == EventType.HEARTBEAT:
            logging.debug(
                "Heartbeat reply received: %s",
                result.get("status")
            )
            return

        if event_type == EventType.PIECE_REMOVED_REQUIRED:
            squares_to_remove = result.get("squares_to_remove", [])
            logging.info(
                "Server says %s captured piece(s) must be removed physically.",
                len(squares_to_remove)
            )
            return

        if event_type == EventType.DESYNC_DETECTED:
            logging.warning("Desync message received from server.")
            return

        if event_type == EventType.ILLEGAL_STATE_DETECTED:
            logging.warning("Illegal-state message received from server.")
            return

        logging.info("Received message of type %s", event_type)

    def heartbeat_loop(self):
        """Send protocol heartbeats until the runtime stops."""
        if self.heartbeat_interval <= 0:
            return

        while not self.stop_event.wait(self.heartbeat_interval):
            try:
                sent = self.send_heartbeat()

                if sent:
                    logging.debug("Heartbeat sent.")
            except ConnectionClosed:
                logging.info("Heartbeat loop stopped because connection closed.")
                return
            except Exception:
                logging.exception("Heartbeat send failed.")
                return

    def scan_loop(self):
        """Read scanner updates through the controller and send scan messages."""
        if self.scan_interval <= 0:
            return

        while not self.stop_event.wait(self.scan_interval):
            try:
                self.controller.client = self.client
                self.controller.scanner = self.scanner

                outbound_messages = self.controller.poll_scanner_and_build_outgoing_messages()

                for message in outbound_messages:
                    event_type = EventType(message["event_type"])

                    if event_type == EventType.SCAN_SNAPSHOT:
                        scan_matrix = message["payload"]["scan_matrix"]
                        sent = self.send_scan_snapshot(scan_matrix)

                        if sent:
                            logging.debug("Raw scan_snapshot sent.")
                        continue

                    if event_type == EventType.STABLE_SCAN:
                        scan_matrix = message["payload"]["scan_matrix"]
                        sent = self.send_stable_scan(scan_matrix)

                        if sent:
                            logging.debug("Stable stable_scan sent.")
                        continue

                    json_text = self.client.encode_message(message)
                    sent = self.send_json(json_text)

                    if sent:
                        logging.debug("Scanner-generated message sent: %s", event_type.value)

            except ConnectionClosed:
                logging.info("Scan loop stopped because connection closed.")
                return
            except Exception:
                logging.exception("Scan loop failed.")
                return

    def receive_loop(self):
        """Receive messages from the server until the connection closes."""
        with self.websocket_lock:
            websocket = self.websocket

        if websocket is None:
            return

        for message_text in websocket:
            if not isinstance(message_text, str):
                logging.warning("Ignoring non-text WebSocket message.")
                continue

            self.handle_server_message(message_text)

    def run(self):
        """Connect to the server and keep the board runtime alive."""
        uri = self.build_server_uri()
        logging.info("Connecting to %s as %s", uri, self.board_id)

        try:
            with connect(uri, open_timeout=10, ping_interval=20, ping_timeout=20) as websocket:
                self.set_websocket(websocket)
                logging.info("Connected to server.")

                heartbeat_thread = Thread(
                    target=self.heartbeat_loop,
                    daemon=True
                )
                heartbeat_thread.start()

                scan_thread = Thread(
                    target=self.scan_loop,
                    daemon=True
                )
                scan_thread.start()

                self.receive_loop()

        except KeyboardInterrupt:
            logging.info("Board runtime stopped by user.")
        except ConnectionClosed:
            logging.info("Server connection closed.")
        finally:
            self.stop_event.set()
            self.clear_websocket()
            self.controller.shutdown()
            logging.info("Board runtime exited.")


def default_board_id():
    """Use the local hostname as the default board identity."""
    return socket.gethostname().lower()


def build_argument_parser():
    """Create the command-line parser for the board runtime."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--board-id", default=default_board_id())
    parser.add_argument("--server-host", default=DEFAULT_SERVER_HOST)
    parser.add_argument("--server-port", type=int, default=DEFAULT_SERVER_PORT)
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=DEFAULT_HEARTBEAT_INTERVAL
    )
    parser.add_argument("--debug", action="store_true")
    return parser


def main():
    """Parse command line arguments and run the board runtime."""
    parser = build_argument_parser()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="[%(levelname)s] %(message)s"
    )

    runtime = BoardMain(
        board_id=args.board_id,
        server_host=args.server_host,
        server_port=args.server_port,
        heartbeat_interval=args.heartbeat_interval
    )
    runtime.run()


if __name__ == "__main__":
    main()
