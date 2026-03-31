from shared.constants import ErrorCode, EventType, GameMode
from shared.game_state import GameState
from shared.rules import apply_move

from server.event_protocol import (
    build_error_message,
    build_heartbeat_message,
    build_piece_removed_required_message,
    build_state_sync_message,
    message_from_json,
    message_to_json,
    parse_candidate_move_message,
    parse_desync_detected_message,
    parse_illegal_state_detected_message,
    parse_scan_snapshot_message,
    parse_stable_scan_message,
)


class GameService:
    def __init__(self, initial_state=None, server_id="server"):
        # Store the canonical game state here.
        if initial_state is None:
            self.state = GameState.initial(mode=GameMode.MULTIPLAYER)
        else:
            self.state = initial_state.clone()

        # Store the identity used in outgoing messages.
        self.server_id = server_id

        # Keep the latest board-side reports here in case they are useful later.
        self.last_scan_snapshot = None
        self.last_stable_scan = None
        self.last_desync_report = None
        self.last_illegal_state_report = None

    def get_state(self):
        # Return a clone so outside code does not modify the real server state.
        return self.state.clone()

    def set_state(self, new_state):
        # Replace the canonical state directly.
        self.state = new_state.clone()

    def reset_game(self, mode=GameMode.MULTIPLAYER):
        # Start a fresh game with a new initial state.
        self.state = GameState.initial(mode=mode)

    def encode_message(self, message):
        # Convert one message dictionary into JSON text.
        return message_to_json(message)

    def decode_message(self, json_text):
        # Convert JSON text into a message dictionary.
        return message_from_json(json_text)

    def encode_message_list(self, messages):
        # Convert a list of message dictionaries into JSON strings.
        json_list = []

        for message in messages:
            json_list.append(self.encode_message(message))

        return json_list

    def build_state_sync_message(self):
        # Build a state_sync message using the current canonical state.
        return build_state_sync_message(
            state=self.state,
            game_id=self.state.game_id,
            session_id=self.state.session_id,
            source=self.server_id
        )

    def build_error_message(self, message_text, error_code=None):
        # Build an error message using the current game/session context.
        return build_error_message(
            message_text=message_text,
            error_code=error_code,
            game_id=self.state.game_id,
            session_id=self.state.session_id,
            source=self.server_id
        )

    def handle_candidate_move_message(self, message):
        # Reject multiplayer messages if the current state is not in multiplayer mode.
        if self.state.mode != GameMode.MULTIPLAYER:
            error_message = self.build_error_message(
                "Server is not in multiplayer mode.",
                ErrorCode.INVALID_MODE
            )
            return [error_message]

        # Rebuild the Move object from the incoming message.
        move = parse_candidate_move_message(message)

        # Validate and apply the move using the shared rules engine.
        applied_move, validation = apply_move(self.state, move)

        # If the move is illegal, return an error message.
        if not validation.is_legal:
            error_message = self.build_error_message(
                validation.message,
                validation.error_code
            )
            return [error_message]

        # Always send the new canonical state after a legal move.
        response_messages = [self.build_state_sync_message()]

        # If pieces were captured, also tell the board which squares must be cleared.
        if len(applied_move.captured_squares) > 0:
            piece_removed_message = build_piece_removed_required_message(
                squares_to_remove=applied_move.captured_squares,
                game_id=self.state.game_id,
                session_id=self.state.session_id,
                source=self.server_id
            )
            response_messages.append(piece_removed_message)

        return response_messages

    def handle_heartbeat_message(self):
        # Return a small heartbeat reply.
        heartbeat_message = build_heartbeat_message(
            game_id=self.state.game_id,
            session_id=self.state.session_id,
            source=self.server_id
        )
        return [heartbeat_message]

    def handle_scan_snapshot_message(self, message):
        # Store the latest raw scan report.
        self.last_scan_snapshot = parse_scan_snapshot_message(message)

        # No immediate response is required for now.
        return []

    def handle_stable_scan_message(self, message):
        # Store the latest stable scan report.
        self.last_stable_scan = parse_stable_scan_message(message)

        # No immediate response is required for now.
        return []

    def handle_desync_detected_message(self, message):
        # Store the latest desync report.
        self.last_desync_report = parse_desync_detected_message(message)

        # Send the current canonical state so the board can resync.
        return [self.build_state_sync_message()]

    def handle_illegal_state_detected_message(self, message):
        # Store the latest illegal-state report.
        self.last_illegal_state_report = parse_illegal_state_detected_message(message)

        # Send the current canonical state so the board can recover.
        return [self.build_state_sync_message()]

    def handle_incoming_message(self, message):
        # Read the event type string and convert it into the enum.
        event_type = EventType(message["event_type"])

        if event_type == EventType.CANDIDATE_MOVE:
            return self.handle_candidate_move_message(message)

        if event_type == EventType.HEARTBEAT:
            return self.handle_heartbeat_message()

        if event_type == EventType.SCAN_SNAPSHOT:
            return self.handle_scan_snapshot_message(message)

        if event_type == EventType.STABLE_SCAN:
            return self.handle_stable_scan_message(message)

        if event_type == EventType.DESYNC_DETECTED:
            return self.handle_desync_detected_message(message)

        if event_type == EventType.ILLEGAL_STATE_DETECTED:
            return self.handle_illegal_state_detected_message(message)

        # Reject any message types this class does not handle yet.
        error_message = self.build_error_message(
            "Unsupported event type.",
            ErrorCode.SERVER_REJECTED_STATE
        )
        return [error_message]

    def handle_incoming_json(self, json_text):
        # Decode the JSON first, then process it like any other message.
        message = self.decode_message(json_text)
        return self.handle_incoming_message(message)

    def handle_incoming_json_and_encode_responses(self, json_text):
        # Decode the input, process it, then encode all response messages.
        response_messages = self.handle_incoming_json(json_text)
        return self.encode_message_list(response_messages)
