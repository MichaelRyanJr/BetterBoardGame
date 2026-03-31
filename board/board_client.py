from shared.constants import EventType

from board.local_state_cache import LocalStateCache
from server.event_protocol import (
    build_candidate_move_message,
    build_desync_detected_message,
    build_heartbeat_message,
    build_illegal_state_detected_message,
    build_scan_snapshot_message,
    build_stable_scan_message,
    message_from_json,
    message_to_json,
    parse_desync_detected_message,
    parse_error_message,
    parse_heartbeat_message,
    parse_illegal_state_detected_message,
    parse_piece_removed_required_message,
    parse_state_sync_message,
)


DEFAULT_SERVER_HOST = "bbg-server"
DEFAULT_SERVER_PORT = 8765


class BoardClient:
    def __init__(
        self,
        board_id,
        game_id=None,
        session_id=None,
        server_host=DEFAULT_SERVER_HOST,
        server_port=DEFAULT_SERVER_PORT,
        initial_state=None
    ):
        # Store the board's identity and current game/session context.
        self.board_id = board_id
        self.game_id = game_id
        self.session_id = session_id

        # Store where the board expects the server to be.
        self.server_host = server_host
        self.server_port = server_port

        # Store the latest server-approved state here.
        self.state_cache = LocalStateCache(initial_state)

        # Store the latest non-state messages here so other code can inspect them.
        self.last_error = None
        self.last_desync = None
        self.last_piece_removed_required = None
        self.last_illegal_state = None
        self.last_heartbeat_status = None

    def set_game_context(self, game_id=None, session_id=None):
        # Update the current game/session values if new ones are provided.
        if game_id is not None:
            self.game_id = game_id

        if session_id is not None:
            self.session_id = session_id

    def get_server_address(self):
        # Return a simple host:port string for display or logging.
        return self.server_host + ":" + str(self.server_port)

    def has_state(self):
        # Return True if a canonical state is currently cached.
        return self.state_cache.has_state()

    def get_state(self):
        # Return a clone of the cached state.
        return self.state_cache.get_state()

    def get_state_version(self):
        # Return the cached state's version number.
        return self.state_cache.get_version()

    def clear_last_error(self):
        # Remove the stored error information.
        self.last_error = None

    def update_context_from_message(self, message):
        # Copy game/session values from an incoming message when present.
        if message.get("game_id") is not None:
            self.game_id = message["game_id"]

        if message.get("session_id") is not None:
            self.session_id = message["session_id"]

    def encode_message(self, message):
        # Convert a message dictionary into JSON text.
        return message_to_json(message)

    def decode_message(self, json_text):
        # Convert JSON text into a message dictionary.
        return message_from_json(json_text)

    def build_scan_snapshot_message(self, scan_matrix):
        # Build a raw scan message using the current board/game context.
        return build_scan_snapshot_message(
            scan_matrix=scan_matrix,
            game_id=self.game_id,
            session_id=self.session_id,
            source=self.board_id
        )

    def build_scan_snapshot_json(self, scan_matrix):
        # Build a raw scan message and immediately convert it to JSON.
        message = self.build_scan_snapshot_message(scan_matrix)
        return self.encode_message(message)

    def build_stable_scan_message(self, scan_matrix):
        # Build a stable scan message using the current board/game context.
        return build_stable_scan_message(
            scan_matrix=scan_matrix,
            game_id=self.game_id,
            session_id=self.session_id,
            source=self.board_id
        )

    def build_stable_scan_json(self, scan_matrix):
        # Build a stable scan message and immediately convert it to JSON.
        message = self.build_stable_scan_message(scan_matrix)
        return self.encode_message(message)

    def build_candidate_move_message(self, move):
        # Build a candidate move message using the current board/game context.
        return build_candidate_move_message(
            move=move,
            game_id=self.game_id,
            session_id=self.session_id,
            source=self.board_id
        )

    def build_candidate_move_json(self, move):
        # Build a candidate move message and immediately convert it to JSON.
        message = self.build_candidate_move_message(move)
        return self.encode_message(message)

    def build_heartbeat_message(self):
        # Build a heartbeat message using the current board/game context.
        return build_heartbeat_message(
            game_id=self.game_id,
            session_id=self.session_id,
            source=self.board_id
        )

    def build_heartbeat_json(self):
        # Build a heartbeat message and immediately convert it to JSON.
        message = self.build_heartbeat_message()
        return self.encode_message(message)

    def build_desync_detected_message(self, message_text):
        # Build a desync report message using the current board/game context.
        return build_desync_detected_message(
            message_text=message_text,
            game_id=self.game_id,
            session_id=self.session_id,
            source=self.board_id
        )

    def build_desync_detected_json(self, message_text):
        # Build a desync report message and immediately convert it to JSON.
        message = self.build_desync_detected_message(message_text)
        return self.encode_message(message)

    def build_illegal_state_detected_message(self, message_text, error_code=None):
        # Build an illegal-state report using the current board/game context.
        return build_illegal_state_detected_message(
            message_text=message_text,
            error_code=error_code,
            game_id=self.game_id,
            session_id=self.session_id,
            source=self.board_id
        )

    def build_illegal_state_detected_json(self, message_text, error_code=None):
        # Build an illegal-state report and immediately convert it to JSON.
        message = self.build_illegal_state_detected_message(
            message_text,
            error_code
        )
        return self.encode_message(message)

    def handle_incoming_message(self, message):
        # Update the stored game/session values first.
        self.update_context_from_message(message)

        event_type = EventType(message["event_type"])

        if event_type == EventType.STATE_SYNC:
            # Read the server's canonical state and store it if it is newer.
            state = parse_state_sync_message(message)
            state_updated = self.state_cache.update_if_newer(state)

            return {
                "event_type": event_type,
                "state_updated": state_updated
            }

        if event_type == EventType.ERROR:
            # Store the latest server error payload.
            self.last_error = parse_error_message(message)

            return {
                "event_type": event_type,
                "error": self.last_error
            }

        if event_type == EventType.HEARTBEAT:
            # Store the latest heartbeat status string.
            self.last_heartbeat_status = parse_heartbeat_message(message)

            return {
                "event_type": event_type,
                "status": self.last_heartbeat_status
            }

        if event_type == EventType.DESYNC_DETECTED:
            # Store the latest desync payload.
            self.last_desync = parse_desync_detected_message(message)

            return {
                "event_type": event_type,
                "desync": self.last_desync
            }

        if event_type == EventType.PIECE_REMOVED_REQUIRED:
            # Store the list of squares that still need to be cleared physically.
            self.last_piece_removed_required = parse_piece_removed_required_message(message)

            return {
                "event_type": event_type,
                "squares_to_remove": self.last_piece_removed_required
            }

        if event_type == EventType.ILLEGAL_STATE_DETECTED:
            # Store the latest illegal-state payload.
            self.last_illegal_state = parse_illegal_state_detected_message(message)

            return {
                "event_type": event_type,
                "illegal_state": self.last_illegal_state
            }

        # Return unknown messages unchanged so later code can decide what to do.
        return {
            "event_type": event_type,
            "message": message
        }

    def handle_incoming_json(self, json_text):
        # Decode the JSON first, then handle it like any other incoming message.
        message = self.decode_message(json_text)
        return self.handle_incoming_message(message)
