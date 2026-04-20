from shared.constants import ErrorCode, EventType, GameMode, Player
from shared.game_state import Coordinate, GameState, Move
from shared.move_validation import legal_moves_for_player
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


# Map each physical board name to the player side it permanently represents.
# If you want to swap the sides, swap these two values.
BOARD_PLAYER_BY_SOURCE = {
    "bbg-boarda": Player.BLACK,
    "bbg-boardb": Player.RED,
}


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
        # The older single-value fields are preserved for compatibility with
        # existing tests and debugging code.
        self.last_scan_snapshot = None
        self.last_stable_scan = None
        self.last_desync_report = None
        self.last_illegal_state_report = None

        # Keep board reports per source board so the server can reason about
        # both boards independently.
        self.last_scan_snapshot_by_source = {}
        self.last_stable_scan_by_source = {}

        # Track which captured squares must still be physically cleared by each
        # player's board after a capture.
        self.pending_capture_removal_by_player = {}

        # Track the full capture replay path that should be shown on the captured
        # player's board while waiting for physical piece removal.
        self.pending_capture_replay_by_player = {}

    def get_state(self):
        # Return a clone so outside code does not modify the real server state.
        return self.state.clone()

    def set_state(self, new_state):
        # Replace the canonical state directly.
        self.state = new_state.clone()

    def reset_game(self, mode=GameMode.MULTIPLAYER):
        # Start a fresh game with a new initial state.
        self.state = GameState.initial(mode=mode)
        self.last_scan_snapshot = None
        self.last_stable_scan = None
        self.last_desync_report = None
        self.last_illegal_state_report = None
        self.last_scan_snapshot_by_source = {}
        self.last_stable_scan_by_source = {}
        self.pending_capture_removal_by_player = {}
        self.pending_capture_replay_by_player = {}

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

    def normalize_source(self, source):
        """
        Normalize the source board name so lookups stay consistent.

        The board hostnames are treated case-insensitively.
        """
        if source is None:
            return None

        return str(source).strip().lower()

    def get_player_for_source(self, source):
        """
        Return the player side assigned to the given board source name.

        Known sources:
        - BBG-BoardA
        - BBG-BoardB
        """
        normalized_source = self.normalize_source(source)
        return BOARD_PLAYER_BY_SOURCE.get(normalized_source)

    def get_source_for_player(self, player):
        """
        Return the board source name assigned to the given player side.
        """
        for source_name, source_player in BOARD_PLAYER_BY_SOURCE.items():
            if source_player == player:
                return source_name

        return None

    def build_empty_scan_matrix(self):
        """
        Build a fresh 8x8 matrix of False values.

        False means the square is physically empty.
        True means a physical piece is present on that square.
        """
        scan_matrix = []

        for row in range(8):
            current_row = []

            for col in range(8):
                current_row.append(False)

            scan_matrix.append(current_row)

        return scan_matrix

    def build_expected_scan_for_player(self, state, player):
        """
        Build the physical occupancy matrix that this player's board should see.

        Important assumption:
        each physical board only contains that player's real pieces.
        The opponent is represented with LEDs instead of physical pieces.
        """
        scan_matrix = self.build_empty_scan_matrix()

        for row in range(8):
            for col in range(8):
                square = Coordinate(row, col)
                piece = state.piece_at(square)

                if piece is None:
                    continue

                if piece.owner != player:
                    continue

                scan_matrix[row][col] = True

        return scan_matrix

    def scan_matrices_match(self, first_matrix, second_matrix):
        """
        Return True if two 8x8 scan matrices are identical.
        """
        for row in range(8):
            for col in range(8):
                if bool(first_matrix[row][col]) != bool(second_matrix[row][col]):
                    return False

        return True

    def required_removal_is_complete(self, scan_matrix, squares_to_remove):
        """
        Return True if every required captured-piece square is now empty.
        """
        for square in squares_to_remove:
            if scan_matrix[square.row][square.col]:
                return False

        return True

    def build_move_from_candidate_action(self, player, action):
        """
        Convert a CandidateAction into a Move object.

        We only need the player, source square, and destination square here.
        The shared rules engine will recalculate the canonical captured squares.
        """
        return Move(
            player=player,
            from_square=Coordinate(action.from_square.row, action.from_square.col),
            to_square=Coordinate(action.to_square.row, action.to_square.col),
            captured_squares=list(action.captured_squares)
        )

    def infer_matching_move_from_scan(self, player, scan_matrix):
        """
        Try to infer one legal move from the player's stable scan.

        Method:
        1. Enumerate all legal moves for the current canonical state.
        2. Simulate each legal move on a cloned state.
        3. Build the expected post-move physical scan for this player.
        4. If exactly one legal move matches the incoming scan, return it.

        Return value format:
        {
            "status": "match" | "no_match" | "ambiguous",
            "move": Move or None
        }
        """
        matching_moves = []

        legal_actions = legal_moves_for_player(self.state, player)

        for action in legal_actions:
            candidate_move = self.build_move_from_candidate_action(player, action)

            temp_state = self.state.clone()
            applied_move, validation = apply_move(temp_state, candidate_move)

            if not validation.is_legal:
                continue

            expected_scan = self.build_expected_scan_for_player(temp_state, player)

            if self.scan_matrices_match(scan_matrix, expected_scan):
                matching_moves.append(candidate_move)

        if len(matching_moves) == 1:
            return {
                "status": "match",
                "move": matching_moves[0]
            }

        if len(matching_moves) == 0:
            return {
                "status": "no_match",
                "move": None
            }

        return {
            "status": "ambiguous",
            "move": None
        }

    def build_recovery_messages(self, message_text, error_code):
        """
        Build a small recovery response:
        - a direct error back to the reporting board
        - a canonical state_sync so boards can realign
        """
        error_message = self.build_error_message(message_text, error_code)
        state_sync_message = self.build_state_sync_message()

        return [error_message, state_sync_message]

    def merge_pending_capture_removals(self, player, new_squares):
        """
        Merge newly captured squares into the existing pending-removal list.

        This matters for multi-capture turns. If the capturing player takes more
        than one jump before the opponent has physically removed the earlier
        captured pieces, the server must keep prompting for the full outstanding
        set instead of only the most recent capture.
        """
        merged_squares = []
        existing_squares = self.pending_capture_removal_by_player.get(player, [])

        for square in existing_squares:
            if square not in merged_squares:
                merged_squares.append(square)

        for square in new_squares:
            if square not in merged_squares:
                merged_squares.append(square)

        self.pending_capture_removal_by_player[player] = merged_squares
        return list(merged_squares)

    def merge_pending_capture_replay(self, player, applied_move):
        """
        Merge one newly applied capture segment into the replay path that should
        be shown on the captured player's board.

        For a normal single capture this becomes: [from_square, to_square]

        For a multi-jump chain this becomes something like:
            [start_square, landing_after_jump_1, landing_after_jump_2, ...]
        """
        merged_squares = []
        existing_squares = self.pending_capture_replay_by_player.get(player, [])

        for square in existing_squares:
            if square not in merged_squares:
                merged_squares.append(square)

        if len(merged_squares) == 0:
            merged_squares.append(applied_move.move.from_square)

        destination_square = applied_move.move.to_square

        if len(merged_squares) == 0:
            merged_squares.append(destination_square)
        else:
            previous_square = merged_squares[len(merged_squares) - 1]

            if previous_square.row != destination_square.row:
                merged_squares.append(destination_square)
            elif previous_square.col != destination_square.col:
                merged_squares.append(destination_square)

        self.pending_capture_replay_by_player[player] = merged_squares
        return list(merged_squares)

    def build_post_move_messages(self, applied_move):
        """
        Build the server responses after one legal move is successfully applied.

        This always sends state_sync.

        If the move captured pieces, this also:
        - records which player must physically remove pieces
        - accumulates all still-pending captured squares for that board
        - builds a piece_removed_required message for the full outstanding set
        - attaches target_board_id so the next server layer can route it
          to the correct board instead of broadcasting it
        """
        response_messages = [self.build_state_sync_message()]

        if len(applied_move.captured_squares) == 0:
            return response_messages

        captured_player = applied_move.move.player.get_opponent()
        captured_board_id = self.get_source_for_player(captured_player)

        outstanding_squares = self.merge_pending_capture_removals(
            captured_player,
            applied_move.captured_squares
        )
        replay_squares = self.merge_pending_capture_replay(
            captured_player,
            applied_move
        )

        piece_removed_message = build_piece_removed_required_message(
            squares_to_remove=outstanding_squares,
            replay_squares=replay_squares,
            game_id=self.state.game_id,
            session_id=self.state.session_id,
            source=self.server_id
        )

        # This is a routing hint for server_main.py.
        # The next server edit should use this field so only the correct board
        # receives the removal prompt.
        piece_removed_message["target_board_id"] = captured_board_id

        response_messages.append(piece_removed_message)
        return response_messages

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

        return self.build_post_move_messages(applied_move)

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
        source = self.normalize_source(message.get("source"))
        scan_matrix = parse_scan_snapshot_message(message)

        self.last_scan_snapshot = scan_matrix

        if source is not None:
            self.last_scan_snapshot_by_source[source] = scan_matrix

        # No immediate response is required for now.
        return []

    def handle_stable_scan_message(self, message):
        """
        Handle a stable physical scan from one board.

        Current multiplayer behavior:
        1. store the stable scan
        2. determine which player this board represents
        3. if capture removal is pending for this board, wait for those squares
           to become empty
        4. if the scan already matches canonical state, do nothing
        5. if it is this player's turn, try to infer one legal move
        6. otherwise, treat the mismatch as a desync/out-of-turn physical state
        """
        if self.state.mode != GameMode.MULTIPLAYER:
            error_message = self.build_error_message(
                "Server is not in multiplayer mode.",
                ErrorCode.INVALID_MODE
            )
            return [error_message]

        source = self.normalize_source(message.get("source"))
        player = self.get_player_for_source(source)
        scan_matrix = parse_stable_scan_message(message)

        self.last_stable_scan = scan_matrix

        if source is not None:
            self.last_stable_scan_by_source[source] = scan_matrix

        if player is None:
            return self.build_recovery_messages(
                "Unknown board source. Server cannot assign this board to a player.",
                ErrorCode.SERVER_REJECTED_STATE
            )

        # If this board still needs to physically remove captured pieces,
        # wait until those required squares become empty.
        pending_squares = self.pending_capture_removal_by_player.get(player)

        if pending_squares is not None:
            if self.required_removal_is_complete(scan_matrix, pending_squares):
                del self.pending_capture_removal_by_player[player]

                if player in self.pending_capture_replay_by_player:
                    del self.pending_capture_replay_by_player[player]

                expected_scan = self.build_expected_scan_for_player(self.state, player)

                if self.scan_matrices_match(scan_matrix, expected_scan):
                    return []

                return self.build_recovery_messages(
                    "Captured piece was removed, but the board still does not match the canonical state.",
                    ErrorCode.DESYNC
                )

            # Do not keep spamming new removal prompts here.
            # The board already holds the current removal prompt locally.
            return []

        # If the board already matches the canonical state, there is nothing to do.
        expected_scan = self.build_expected_scan_for_player(self.state, player)

        if self.scan_matrices_match(scan_matrix, expected_scan):
            return []

        # If it is not this board's turn, any mismatch is a physical desync or
        # out-of-turn change. Send the canonical state back.
        if player != self.state.current_player:
            return self.build_recovery_messages(
                "Stable scan changed on a board that is not the current player.",
                ErrorCode.OUT_OF_TURN
            )

        inference_result = self.infer_matching_move_from_scan(player, scan_matrix)
        inference_status = inference_result["status"]

        if inference_status == "ambiguous":
            return self.build_recovery_messages(
                "Stable scan matches more than one legal move.",
                ErrorCode.AMBIGUOUS_SCAN
            )

        if inference_status == "no_match":
            return self.build_recovery_messages(
                "Stable scan does not match any legal move from the current state.",
                ErrorCode.DESYNC
            )

        inferred_move = inference_result["move"]
        applied_move, validation = apply_move(self.state, inferred_move)

        if not validation.is_legal:
            return self.build_recovery_messages(
                validation.message,
                validation.error_code
            )

        return self.build_post_move_messages(applied_move)

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
