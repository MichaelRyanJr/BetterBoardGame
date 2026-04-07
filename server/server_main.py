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

        # Only let one message update the canonical state at a time.
        self.state_lock = Lock()

    def register_connection(self, websocket):
        """Add a client connection to the active set."""
        with self.connections_lock:
            self.connections.add(websocket)

    def unregister_connection(self, websocket):
        """Remove a client connection from the active set."""
        with self.connections_lock:
            self.connections.discard(websocket)

    def get_connection_count(self):
        """Return the number of currently connected clients."""
        with self.connections_lock:
            return len(self.connections)

    def encode_message(self, message):
        """Convert a protocol message dictionary into JSON."""
        return self.game_service.encode_message(message)

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
        """Return True if this response should go to every connected board."""
        event_type = EventType(message["event_type"])

        if event_type == EventType.STATE_SYNC:
            return True

        if event_type == EventType.PIECE_REMOVED_REQUIRED:
            return True

        return False

    def split_response_messages(self, messages):
        """
        Split server responses into:
        - direct replies for the sender
        - broadcast messages for all connected boards
        """
        direct_messages = []
        broadcast_messages = []

        for message in messages:
            if self.should_broadcast_message(message):
                broadcast_messages.append(message)
            else:
                direct_messages.append(message)

        return direct_messages, broadcast_messages

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

    def process_incoming_json(self, json_text):
        """Pass one incoming JSON message through the GameService."""
        with self.state_lock:
            response_messages = self.game_service.handle_incoming_json(json_text)

        return response_messages

    def handle_message(self, websocket, message_text):
        """Handle one incoming WebSocket text message."""
        if not isinstance(message_text, str):
            error_message = self.game_service.build_error_message(
                "Only text JSON messages are supported."
            )
            self.send_message(websocket, error_message)
            return

        try:
            response_messages = self.process_incoming_json(message_text)
        except Exception:
            logging.exception("Failed to process incoming message.")
            error_message = self.game_service.build_error_message(
                "Server could not process the message."
            )
            self.send_message(websocket, error_message)
            return

        direct_messages, broadcast_messages = self.split_response_messages(response_messages)

        if len(direct_messages) > 0:
            self.send_message_list(websocket, direct_messages)

        if len(broadcast_messages) > 0:
            self.broadcast_messages(broadcast_messages)

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
