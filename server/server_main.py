import argparse
import logging
from threading import Lock

from shared.constants import EventType
from server.game_service import GameService

try:
    from websockets.exceptions import ConnectionClosed
    from websockets.sync.server import serve
except ImportError as exc:
    raise ImportError(
        "This file requires the 'websockets' package. "
        "Install it with: pip install -U websockets"
    ) from exc


DEFAULT_BIND_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 8765
DEFAULT_SERVER_ID = "server"


class ServerMain:
    def __init__(
        self,
        host=DEFAULT_BIND_HOST,
        port=DEFAULT_SERVER_PORT,
        server_id=DEFAULT_SERVER_ID,
        initial_state=None
    ):
        self.host = host
        self.port = port
        self.server_id = server_id

        self.game_service = GameService(
            initial_state=initial_state,
            server_id=server_id
        )

        # Keep track of all connected boards so state updates can be broadcast.
        self.connections = set()
        self.connections_lock = Lock()

        # Track which websocket belongs to which board source name.
        # Example:
        # "bbg-boarda" -> websocket_for_board_a
        self.connection_by_board_id = {}

        # Also keep the reverse mapping so disconnect cleanup is simple.
        # Example:
        # websocket_for_board_a -> "bbg-boarda"
        self.board_id_by_connection = {}

        # Only let one message update the canonical state at a time.
        self.state_lock = Lock()

    def normalize_board_id(self, board_id):
        """
        Normalize a board ID so routing lookups stay consistent.

        Board names are treated case-insensitively.
        """
        if board_id is None:
            return None

        return str(board_id).strip().lower()

    def register_connection(self, websocket):
        """Add a client connection to the active set."""
        with self.connections_lock:
            self.connections.add(websocket)

    def unregister_connection(self, websocket):
        """Remove a client connection from the active set and clear routing info."""
        with self.connections_lock:
            self.connections.discard(websocket)

            board_id = self.board_id_by_connection.pop(websocket, None)

            if board_id is not None:
                current_websocket = self.connection_by_board_id.get(board_id)

                if current_websocket is websocket:
                    del self.connection_by_board_id[board_id]

    def register_connection_board_id(self, websocket, board_id):
        """
        Record which board ID belongs to this websocket connection.

        This is learned from the incoming message's "source" field.
        """
        normalized_board_id = self.normalize_board_id(board_id)

        if normalized_board_id is None:
            return

        with self.connections_lock:
            old_board_id = self.board_id_by_connection.get(websocket)

            if old_board_id is not None and old_board_id != normalized_board_id:
                current_websocket = self.connection_by_board_id.get(old_board_id)

                if current_websocket is websocket:
                    del self.connection_by_board_id[old_board_id]

            self.board_id_by_connection[websocket] = normalized_board_id
            self.connection_by_board_id[normalized_board_id] = websocket

    def get_connection_for_board_id(self, board_id):
        """Return the websocket currently associated with one board ID."""
        normalized_board_id = self.normalize_board_id(board_id)

        if normalized_board_id is None:
            return None

        with self.connections_lock:
            return self.connection_by_board_id.get(normalized_board_id)

    def get_connection_count(self):
        """Return the number of currently connected clients."""
        with self.connections_lock:
            return len(self.connections)

    def prepare_outgoing_message(self, message):
        """
        Remove server-only routing hints before sending a message to a board.

        Right now the main internal-only field is:
        - target_board_id
        """
        clean_message = dict(message)

        if "target_board_id" in clean_message:
            del clean_message["target_board_id"]

        return clean_message

    def encode_message(self, message):
        """Convert a protocol message dictionary into JSON."""
        clean_message = self.prepare_outgoing_message(message)
        return self.game_service.encode_message(clean_message)

    def send_message(self, websocket, message):
        """Send one protocol message to one client."""
        json_text = self.encode_message(message)
        websocket.send(json_text)

    def send_message_list(self, websocket, messages):
        """Send several protocol messages to one client in order."""
        for message in messages:
            self.send_message(websocket, message)

    def build_initial_messages(self):
        """Build the messages sent immediately after a client connects."""
        return [self.game_service.build_state_sync_message()]

    def should_broadcast_message(self, message):
        """
        Return True if this response should go to every connected board.

        state_sync should still broadcast.

        piece_removed_required should only broadcast when there is no specific
        target board. If target_board_id is present, it should be routed.
        """
        event_type = EventType(message["event_type"])

        if event_type == EventType.STATE_SYNC:
            return True

        if event_type == EventType.PIECE_REMOVED_REQUIRED:
            target_board_id = message.get("target_board_id")

            if target_board_id is None:
                return True

            return False

        return False

    def should_route_message(self, message):
        """
        Return True if this response should go to one specific board.
        """
        target_board_id = message.get("target_board_id")
        return target_board_id is not None

    def split_response_messages(self, messages):
        """
        Split server responses into:
        - direct replies for the sender
        - broadcast messages for all connected boards
        - routed messages for one specific board
        """
        direct_messages = []
        broadcast_messages = []
        routed_messages = []

        for message in messages:
            if self.should_route_message(message):
                routed_messages.append(message)
                continue

            if self.should_broadcast_message(message):
                broadcast_messages.append(message)
            else:
                direct_messages.append(message)

        return direct_messages, broadcast_messages, routed_messages

    def broadcast_messages(self, messages):
        """Send messages to every currently connected client."""
        with self.connections_lock:
            connection_list = list(self.connections)

        disconnected_clients = []

        for websocket in connection_list:
            try:
                self.send_message_list(websocket, messages)
            except Exception:
                disconnected_clients.append(websocket)

        for websocket in disconnected_clients:
            self.unregister_connection(websocket)

    def route_messages(self, messages):
        """
        Send each routed message only to its target board.

        If the target board is not currently known, log a warning and drop the
        routed message instead of broadcasting it to the wrong board.
        """
        disconnected_clients = []

        for message in messages:
            target_board_id = self.normalize_board_id(message.get("target_board_id"))
            target_websocket = self.get_connection_for_board_id(target_board_id)

            if target_websocket is None:
                logging.warning(
                    "Could not route message %s because target board '%s' is not connected or not identified yet.",
                    message.get("event_type"),
                    target_board_id
                )
                continue

            try:
                self.send_message(target_websocket, message)
            except Exception:
                disconnected_clients.append(target_websocket)

        for websocket in disconnected_clients:
            self.unregister_connection(websocket)

    def process_incoming_json(self, json_text):
        """Pass one incoming JSON message through the GameService."""
        with self.state_lock:
            response_messages = self.game_service.handle_incoming_json(json_text)

        return response_messages

    def learn_sender_identity_from_message(self, websocket, message_text):
        """
        Read the incoming message source field and associate it with the socket.

        This is what allows later server responses to be routed to a specific
        physical board by board name.
        """
        try:
            message = self.game_service.decode_message(message_text)
        except Exception:
            return

        source = message.get("source")

        if source is None:
            return

        self.register_connection_board_id(websocket, source)

    def handle_message(self, websocket, message_text):
        """Handle one incoming WebSocket text message."""
        if not isinstance(message_text, str):
            error_message = self.game_service.build_error_message(
                "Only text JSON messages are supported."
            )
            self.send_message(websocket, error_message)
            return

        self.learn_sender_identity_from_message(websocket, message_text)

        try:
            response_messages = self.process_incoming_json(message_text)
        except Exception:
            logging.exception("Failed to process incoming message.")
            error_message = self.game_service.build_error_message(
                "Server could not process the message."
            )
            self.send_message(websocket, error_message)
            return

        direct_messages, broadcast_messages, routed_messages = self.split_response_messages(
            response_messages
        )

        if len(direct_messages) > 0:
            self.send_message_list(websocket, direct_messages)

        if len(broadcast_messages) > 0:
            self.broadcast_messages(broadcast_messages)

        if len(routed_messages) > 0:
            self.route_messages(routed_messages)

    def handle_connection(self, websocket):
        """Handle the full lifetime of one board connection."""
        self.register_connection(websocket)
        logging.info(
            "Client connected. Active connections: %s",
            self.get_connection_count()
        )

        try:
            initial_messages = self.build_initial_messages()
            self.send_message_list(websocket, initial_messages)

            for message_text in websocket:
                self.handle_message(websocket, message_text)

        except ConnectionClosed:
            logging.info("Client disconnected normally.")
        except Exception:
            logging.exception("Connection ended with an unexpected error.")
        finally:
            self.unregister_connection(websocket)
            logging.info(
                "Connection closed. Active connections: %s",
                self.get_connection_count()
            )

    def run(self):
        """Start the WebSocket server and keep it running."""
        logging.info(
            "Starting Better Board Game server on ws://%s:%s",
            self.host,
            self.port
        )

        with serve(self.handle_connection, self.host, self.port) as server:
            server.serve_forever()


def build_argument_parser():
    """Create the CLI parser for the server entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_BIND_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_SERVER_PORT)
    parser.add_argument("--server-id", default=DEFAULT_SERVER_ID)
    return parser


def main():
    """Parse command line arguments and run the server."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s"
    )

    parser = build_argument_parser()
    args = parser.parse_args()

    server = ServerMain(
        host=args.host,
        port=args.port,
        server_id=args.server_id
    )
    server.run()


if __name__ == "__main__":
    main()
