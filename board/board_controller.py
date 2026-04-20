import time

from board.board_client import BoardClient, DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT
from board.led_driver import LEDDriver, build_opponent_led_matrix
from board.token_scanner import TokenScanner, clone_scan_matrix, empty_scan_matrix
from shared.constants import EventType, LED_ON
from shared.game_state import Coordinate, Move
from shared.move_validation import legal_moves_for_player
from shared.rules import apply_move


DEFAULT_CAPTURE_REPLAY_STEP_SECONDS = 0.5
DEFAULT_CAPTURE_REMOVAL_BLINK_STEP_SECONDS = 0.5
DEFAULT_ILLEGAL_BLINK_STEP_SECONDS = 0.35
DEFAULT_OPPONENT_KING_BLINK_STEP_SECONDS = 0.18


class BoardController:
    """
    Coordinate board-side scanning, protocol handling, and LED output.

    This class does not open sockets and does not run the WebSocket runtime.
    Instead, it sits between:
    - TokenScanner for board input
    - BoardClient for protocol/state handling
    - LEDDriver for board output

    Multiplayer LED behavior mirrors the single-player runtime where practical:
    - opponent kings blink quickly
    - opponent capture replay blinks until the local captured piece is removed
    - if the local player makes an illegal physical move, every missing expected
      local-piece square blinks until the board is corrected
    """

    def __init__(
        self,
        board_id,
        local_player=None,
        game_id=None,
        session_id=None,
        server_host=DEFAULT_SERVER_HOST,
        server_port=DEFAULT_SERVER_PORT,
        scanner=None,
        led_driver=None,
        client=None,
        scanner_mode="gpio",
        scanner_stable_reads_required=2,
        led_mode="hardware",
        capture_replay_step_seconds=DEFAULT_CAPTURE_REPLAY_STEP_SECONDS,
        capture_removal_blink_step_seconds=DEFAULT_CAPTURE_REMOVAL_BLINK_STEP_SECONDS,
        illegal_blink_step_seconds=DEFAULT_ILLEGAL_BLINK_STEP_SECONDS,
        opponent_king_blink_step_seconds=DEFAULT_OPPONENT_KING_BLINK_STEP_SECONDS,
    ):
        self.board_id = board_id
        self.local_player = local_player

        if client is None:
            self.client = BoardClient(
                board_id=board_id,
                game_id=game_id,
                session_id=session_id,
                server_host=server_host,
                server_port=server_port
            )
        else:
            self.client = client

        if scanner is None:
            self.scanner = TokenScanner(
                mode=scanner_mode,
                stable_reads_required=scanner_stable_reads_required
            )
        else:
            self.scanner = scanner

        if led_driver is None:
            self.led_driver = LEDDriver(mode=led_mode)
        else:
            self.led_driver = led_driver

        self.latest_raw_scan_matrix = None
        self.latest_stable_scan_matrix = None
        self.last_stable_scan_sent = None

        self.pending_capture_removal_squares = []
        self.pending_opponent_capture_replay_squares = []
        self.pending_illegal_return_squares = []

        self.capture_replay_step_seconds = float(capture_replay_step_seconds)
        self.capture_removal_blink_step_seconds = float(capture_removal_blink_step_seconds)
        self.illegal_blink_step_seconds = float(illegal_blink_step_seconds)
        self.opponent_king_blink_step_seconds = float(opponent_king_blink_step_seconds)

        self.capture_replay_started_at = None
        self.illegal_blink_started_at = None
        self.king_blink_started_at = time.monotonic()

    def set_local_player(self, local_player):
        """Store which side this physical board belongs to."""
        self.local_player = local_player
        self.refresh_led_display()

    def set_game_context(self, game_id=None, session_id=None):
        """Update the board's current game/session context."""
        self.client.set_game_context(game_id=game_id, session_id=session_id)

    def has_state(self):
        """Return True if the board has a cached canonical state."""
        return self.client.has_state()

    def get_state(self):
        """Return a clone of the cached canonical state."""
        return self.client.get_state()

    def get_state_version(self):
        """Return the cached state's version number."""
        return self.client.get_state_version()

    def get_led_matrix(self):
        """Return the LED matrix currently being displayed."""
        return self.led_driver.get_led_matrix()

    def get_latest_scan_matrix(self):
        """Return the latest raw scan that was read."""
        if self.latest_raw_scan_matrix is None:
            return None

        return clone_scan_matrix(self.latest_raw_scan_matrix)

    def get_latest_stable_scan_matrix(self):
        """Return the latest stable scan that was observed."""
        if self.latest_stable_scan_matrix is None:
            return None

        return clone_scan_matrix(self.latest_stable_scan_matrix)

    def has_pending_capture_removal(self):
        """Return True if captured pieces still need physical removal."""
        return len(self.pending_capture_removal_squares) > 0

    def clear_pending_capture_removal(self):
        """Clear the current capture-removal requirement."""
        self.pending_capture_removal_squares = []
        self.pending_opponent_capture_replay_squares = []
        self.capture_replay_started_at = None
        self.refresh_led_display()

    def clear_pending_illegal_return_squares(self):
        """Clear local illegal-move guidance LEDs."""
        self.pending_illegal_return_squares = []
        self.illegal_blink_started_at = None
        self.refresh_led_display()

    def has_pending_illegal_return_square(self):
        """
        Kept for compatibility with earlier logic/tests.
        """
        return len(self.pending_illegal_return_squares) > 0

    def capture_removal_is_complete(self, scan_matrix):
        """
        Return True if all required captured-piece squares are now empty.

        scan_matrix[row][col] should be True when a physical piece is present
        and False when the square is empty.
        """
        if not self.has_pending_capture_removal():
            return False

        for square in self.pending_capture_removal_squares:
            if scan_matrix[square.row][square.col]:
                return False

        return True

    def get_blink_phase_is_on(self, started_at, step_seconds):
        if started_at is None:
            return True

        if step_seconds <= 0:
            return True

        elapsed_seconds = time.monotonic() - started_at
        phase_index = int(elapsed_seconds / step_seconds)
        return (phase_index % 2) == 0

    def get_replay_square_for_current_phase(self, squares, started_at, step_seconds):
        if len(squares) == 0:
            return None

        if started_at is None:
            return squares[0]

        if step_seconds <= 0:
            return squares[0]

        elapsed_seconds = time.monotonic() - started_at
        phase_index = int(elapsed_seconds / step_seconds)
        square_index = phase_index % len(squares)
        return squares[square_index]

    def build_led_matrix_with_highlighted_squares(self, base_led_matrix, squares):
        led_matrix = []

        for row in range(8):
            led_row = []

            for col in range(8):
                led_row.append(base_led_matrix[row][col])

            led_matrix.append(led_row)

        for square in squares:
            if square is None:
                continue

            led_matrix[square.row][square.col] = LED_ON

        return led_matrix

    def get_opponent_king_squares(self, state):
        king_squares = []

        if state is None:
            return king_squares

        if self.local_player is None:
            return king_squares

        opponent = self.local_player.get_opponent()

        for row in range(8):
            for col in range(8):
                piece = state.board[row][col]

                if piece is None:
                    continue

                if piece.owner != opponent:
                    continue

                if not piece.is_king:
                    continue

                king_squares.append(Coordinate(row, col))

        return king_squares

    def has_blinking_opponent_king(self):
        state = self.get_state()
        return len(self.get_opponent_king_squares(state)) > 0

    def build_opponent_led_matrix_with_blinking_kings(self, state):
        if state is None:
            return empty_scan_matrix()

        if self.local_player is None:
            return empty_scan_matrix()

        led_matrix = build_opponent_led_matrix(state, self.local_player)
        king_squares = self.get_opponent_king_squares(state)

        if len(king_squares) == 0:
            return led_matrix

        blink_is_on = self.get_blink_phase_is_on(
            self.king_blink_started_at,
            self.opponent_king_blink_step_seconds
        )

        for square in king_squares:
            if blink_is_on:
                led_matrix[square.row][square.col] = LED_ON
            else:
                led_matrix[square.row][square.col] = 0

        return led_matrix

    def build_expected_scan_for_local_player(self, state):
        """
        Build the physical occupancy matrix this board should show for the
        local player's real pieces.
        """
        scan_matrix = empty_scan_matrix()

        if state is None:
            return scan_matrix

        if self.local_player is None:
            return scan_matrix

        for row in range(8):
            for col in range(8):
                square = Coordinate(row, col)
                piece = state.piece_at(square)

                if piece is None:
                    continue

                if piece.owner != self.local_player:
                    continue

                scan_matrix[row][col] = True

        return scan_matrix

    def scan_matrices_match(self, first_matrix, second_matrix):
        for row in range(8):
            for col in range(8):
                if bool(first_matrix[row][col]) != bool(second_matrix[row][col]):
                    return False

        return True

    def find_missing_piece_return_squares(self, expected_scan, actual_scan):
        missing_squares = []

        for row in range(8):
            for col in range(8):
                expected_has_piece = bool(expected_scan[row][col])
                actual_has_piece = bool(actual_scan[row][col])

                if expected_has_piece and not actual_has_piece:
                    missing_squares.append(Coordinate(row, col))

        return missing_squares

    def build_move_from_candidate_action(self, action):
        captured_squares = []

        for square in action.captured_squares:
            captured_squares.append(Coordinate(square.row, square.col))

        return Move(
            player=self.local_player,
            from_square=Coordinate(action.from_square.row, action.from_square.col),
            to_square=Coordinate(action.to_square.row, action.to_square.col),
            captured_squares=captured_squares
        )

    def infer_matching_local_move_from_scan(self, scan_matrix):
        """
        Infer whether a stable physical scan matches exactly one legal local move.

        This is guidance-only. The board still sends stable_scan snapshots to the
        server and the server remains authoritative.
        """
        state = self.get_state()

        if state is None:
            return {
                "status": "no_state",
                "move": None
            }

        if self.local_player is None:
            return {
                "status": "no_local_player",
                "move": None
            }

        matching_moves = []
        legal_actions = legal_moves_for_player(state, self.local_player)

        for action in legal_actions:
            candidate_move = self.build_move_from_candidate_action(action)

            temp_state = state.clone()
            applied_move, validation = apply_move(temp_state, candidate_move)

            if not validation.is_legal:
                continue

            expected_scan = self.build_expected_scan_for_local_player(temp_state)

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

    def update_illegal_move_guidance_from_scan(self, scan_matrix):
        """
        Decide whether the stable local scan should show illegal-move guidance.
        """
        if self.has_pending_capture_removal():
            self.pending_illegal_return_squares = []
            self.illegal_blink_started_at = None
            return

        state = self.get_state()

        if state is None or self.local_player is None:
            self.pending_illegal_return_squares = []
            self.illegal_blink_started_at = None
            return

        expected_scan = self.build_expected_scan_for_local_player(state)

        if self.scan_matrices_match(scan_matrix, expected_scan):
            self.pending_illegal_return_squares = []
            self.illegal_blink_started_at = None
            return

        inference_result = self.infer_matching_local_move_from_scan(scan_matrix)
        inference_status = inference_result["status"]

        if inference_status == "match":
            self.pending_illegal_return_squares = []
            self.illegal_blink_started_at = None
            return

        if inference_status == "ambiguous":
            self.pending_illegal_return_squares = []
            self.illegal_blink_started_at = None
            return

        missing_squares = self.find_missing_piece_return_squares(
            expected_scan,
            scan_matrix
        )

        self.pending_illegal_return_squares = missing_squares

        if len(self.pending_illegal_return_squares) > 0:
            if self.illegal_blink_started_at is None:
                self.illegal_blink_started_at = time.monotonic()
        else:
            self.illegal_blink_started_at = None

    def refresh_led_display(self):
        """
        Update the LEDs based on the current board-side situation.

        Priority:
        1. if the opponent just captured, replay the authoritative capture path
           until the local captured piece is physically removed
        2. if the local player made an illegal physical move, blink every square
           where a local piece must be restored
        3. otherwise show the opponent's current positions, with opponent kings
           blinking quickly
        4. otherwise clear the LEDs
        """
        state = self.client.get_state()

        if self.has_pending_capture_removal():
            if state is None or self.local_player is None:
                self.led_driver.clear()
                return

            base_led_matrix = self.build_opponent_led_matrix_with_blinking_kings(state)

            if len(self.pending_opponent_capture_replay_squares) > 0:
                if self.capture_replay_started_at is None:
                    self.capture_replay_started_at = time.monotonic()

                replay_square = self.get_replay_square_for_current_phase(
                    self.pending_opponent_capture_replay_squares,
                    self.capture_replay_started_at,
                    self.capture_replay_step_seconds
                )

                for replay_path_square in self.pending_opponent_capture_replay_squares:
                    if replay_path_square is None:
                        continue

                    base_led_matrix[replay_path_square.row][replay_path_square.col] = False

                if replay_square is not None:
                    base_led_matrix[replay_square.row][replay_square.col] = LED_ON

                self.led_driver.set_led_matrix(base_led_matrix)
                return

            removal_blink_is_on = self.get_blink_phase_is_on(
                self.capture_replay_started_at,
                self.capture_removal_blink_step_seconds
            )

            if removal_blink_is_on:
                self.led_driver.display_capture_removal_squares(
                    self.pending_capture_removal_squares
                )
            else:
                self.led_driver.clear()

            return

        self.capture_replay_started_at = None

        if self.has_pending_illegal_return_square():
            if state is None or self.local_player is None:
                self.led_driver.clear()
                return

            if self.illegal_blink_started_at is None:
                self.illegal_blink_started_at = time.monotonic()

            base_led_matrix = self.build_opponent_led_matrix_with_blinking_kings(state)
            blink_is_on = self.get_blink_phase_is_on(
                self.illegal_blink_started_at,
                self.illegal_blink_step_seconds
            )

            if blink_is_on:
                led_matrix = self.build_led_matrix_with_highlighted_squares(
                    base_led_matrix,
                    self.pending_illegal_return_squares
                )
                self.led_driver.set_led_matrix(led_matrix)
            else:
                self.led_driver.set_led_matrix(base_led_matrix)

            return

        self.illegal_blink_started_at = None

        if state is None or self.local_player is None:
            self.led_driver.clear()
            return

        led_matrix = self.build_opponent_led_matrix_with_blinking_kings(state)
        self.led_driver.set_led_matrix(led_matrix)

    def read_scan_matrix(self):
        """
        Read one raw scan from the scanner.
        """
        scan_matrix = self.scanner.read_scan_matrix()
        self.latest_raw_scan_matrix = clone_scan_matrix(scan_matrix)

        if self.scanner.is_current_scan_stable():
            self.latest_stable_scan_matrix = clone_scan_matrix(scan_matrix)

            if self.capture_removal_is_complete(scan_matrix):
                self.pending_capture_removal_squares = []
                self.pending_opponent_capture_replay_squares = []
                self.capture_replay_started_at = None

            self.update_illegal_move_guidance_from_scan(scan_matrix)
            self.refresh_led_display()

        return clone_scan_matrix(scan_matrix)

    def read_stable_scan_matrix(self):
        """
        Read one scan and return it only if it is stable right now.
        """
        scan_matrix = self.read_scan_matrix()

        if self.scanner.is_current_scan_stable():
            return clone_scan_matrix(scan_matrix)

        return None

    def poll_scanner_and_build_outgoing_messages(self):
        """
        Read the scanner and build any outbound protocol messages.
        """
        if (
            self.has_pending_capture_removal()
            or self.has_pending_illegal_return_square()
            or self.has_blinking_opponent_king()
        ):
            self.refresh_led_display()

        scan_matrix = self.read_scan_matrix()

        outbound_messages = [
            self.client.build_scan_snapshot_message(scan_matrix)
        ]

        if self.scanner.is_current_scan_stable():
            should_send_stable = False

            if self.last_stable_scan_sent is None:
                should_send_stable = True
            elif scan_matrix != self.last_stable_scan_sent:
                should_send_stable = True

            if should_send_stable:
                stable_message = self.client.build_stable_scan_message(scan_matrix)
                outbound_messages.append(stable_message)

            self.last_stable_scan_sent = clone_scan_matrix(scan_matrix)
        else:
            self.last_stable_scan_sent = None

        return outbound_messages

    def poll_scanner_and_build_outgoing_json(self):
        """
        Read the scanner and return outbound messages as JSON strings.
        """
        outbound_messages = self.poll_scanner_and_build_outgoing_messages()
        outbound_json = []

        for message in outbound_messages:
            outbound_json.append(self.client.encode_message(message))

        return outbound_json

    def handle_incoming_message(self, message):
        """
        Process one incoming protocol message and update board output.
        """
        result = self.client.handle_incoming_message(message)
        event_type = result["event_type"]

        if event_type == EventType.STATE_SYNC:
            self.refresh_led_display()
            return result

        if event_type == EventType.PIECE_REMOVED_REQUIRED:
            squares_to_remove = result.get("squares_to_remove", [])
            replay_squares = result.get("replay_squares", [])

            self.pending_capture_removal_squares = list(squares_to_remove)
            self.pending_opponent_capture_replay_squares = list(replay_squares)

            if len(self.pending_capture_removal_squares) > 0:
                if self.capture_replay_started_at is None:
                    self.capture_replay_started_at = time.monotonic()
            else:
                self.capture_replay_started_at = None
                self.pending_opponent_capture_replay_squares = []

            self.refresh_led_display()
            return result

        return result

    def handle_incoming_json(self, json_text):
        """
        Process one incoming JSON protocol message and update board output.
        """
        message = self.client.decode_message(json_text)
        return self.handle_incoming_message(message)

    def shutdown(self):
        """Clean up controller-owned board resources."""
        self.scanner.shutdown()
        self.led_driver.shutdown()
