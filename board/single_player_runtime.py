from ai.difficulty_profiles import get_depth_for_difficulty
from ai.minimax import choose_best_move
from board.led_driver import LEDDriver
from board.local_state_cache import LocalStateCache
from board.token_scanner import (
    TokenScanner,
    build_hardware_safe_scan_matrix,
    clone_scan_matrix,
    empty_scan_matrix,
    normalize_scan_matrix,
)
from shared.constants import Difficulty, ErrorCode, GameMode, Player
from shared.game_state import Coordinate, GameState, Move
from shared.move_validation import legal_moves_for_player
from shared.rules import apply_move


class SinglePlayerRuntime:
    """
    Run a local single-player game on one physical board.

    The board physically contains only the human player's pieces.
    The AI player's pieces are represented with LEDs.

    Flow:
    1. read a stable logical scan from the board
    2. infer the human move by comparing the scan against all legal moves
    3. apply the human move through the shared rules engine
    4. let the AI choose and apply its move through the same shared rules engine
    5. refresh LEDs from the canonical local GameState
    """

    def __init__(
        self,
        human_player=Player.BLACK,
        difficulty=Difficulty.MEDIUM,
        scanner=None,
        led_driver=None,
        scanner_mode="gpio",
        scanner_stable_reads_required=2,
        led_mode="hardware"
    ):
        self.human_player = human_player
        self.ai_player = human_player.get_opponent()
        self.difficulty = difficulty

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

        self.state_cache = LocalStateCache()

        self.latest_raw_scan_matrix = None
        self.latest_stable_scan_matrix = None
        self.last_handled_stable_scan = None

        self.pending_human_piece_removal_squares = []
        self.last_error_code = None
        self.last_message = ""

        self.start_new_game()

    def start_new_game(self):
        """Start a fresh local single-player game."""
        state = GameState.initial(mode=GameMode.SINGLE_PLAYER)
        self.state_cache.set_state(state)

        self.pending_human_piece_removal_squares = []
        self.latest_raw_scan_matrix = None
        self.latest_stable_scan_matrix = None
        self.last_handled_stable_scan = None
        self.last_error_code = None
        self.last_message = ""

        self.refresh_led_display()

        if self.get_state().current_player == self.ai_player:
            self._apply_ai_turn()

        return self.build_status_result("new_game_started")

    def set_difficulty(self, difficulty):
        """Change the AI difficulty for future turns."""
        self.difficulty = difficulty

    def set_human_player(self, human_player):
        """
        Change which side the human controls and restart the local game.
        """
        self.human_player = human_player
        self.ai_player = human_player.get_opponent()
        return self.start_new_game()

    def has_state(self):
        return self.state_cache.has_state()

    def get_state(self):
        return self.state_cache.get_state()

    def get_state_version(self):
        return self.state_cache.get_version()

    def get_led_matrix(self):
        return self.led_driver.get_led_matrix()

    def get_latest_scan_matrix(self):
        if self.latest_raw_scan_matrix is None:
            return None

        return clone_scan_matrix(self.latest_raw_scan_matrix)

    def get_latest_stable_scan_matrix(self):
        if self.latest_stable_scan_matrix is None:
            return None

        return clone_scan_matrix(self.latest_stable_scan_matrix)

    def has_pending_human_piece_removal(self):
        return len(self.pending_human_piece_removal_squares) > 0

    def clear_pending_human_piece_removal(self):
        self.pending_human_piece_removal_squares = []
        self.refresh_led_display()

    def build_status_result(self, status, extra=None):
        """Build a small result dictionary for debugging and caller logic."""
        result = {
            "status": status,
            "error_code": self.last_error_code,
            "message": self.last_message,
            "pending_human_piece_removal": list(self.pending_human_piece_removal_squares),
            "state": self.get_state()
        }

        if extra is not None:
            for key, value in extra.items():
                result[key] = value

        return result

    def set_error(self, error_code, message):
        self.last_error_code = error_code
        self.last_message = message

    def clear_error(self):
        self.last_error_code = None
        self.last_message = ""

    def build_expected_scan_for_human(self, state):
        """
        Build the physical occupancy matrix the human player's board should show.

        Only the human player's pieces physically exist on this board.
        The AI player's pieces are represented by LEDs.
        """
        scan_matrix = empty_scan_matrix()

        for row in range(8):
            for col in range(8):
                square = Coordinate(row, col)
                piece = state.piece_at(square)

                if piece is None:
                    continue

                if piece.owner != self.human_player:
                    continue

                scan_matrix[row][col] = True

        return scan_matrix

    def scan_matrices_match(self, first_matrix, second_matrix):
        for row in range(8):
            for col in range(8):
                if bool(first_matrix[row][col]) != bool(second_matrix[row][col]):
                    return False

        return True

    def required_removal_is_complete(self, scan_matrix, squares_to_remove):
        for square in squares_to_remove:
            if scan_matrix[square.row][square.col]:
                return False

        return True

    def refresh_led_display(self):
        """
        Update LEDs for the current local single-player situation.

        Priority:
        1. show required human piece removals after an AI capture
        2. otherwise show the AI player's current positions
        3. otherwise clear the LEDs
        """
        if self.has_pending_human_piece_removal():
            self.led_driver.display_capture_removal_squares(
                self.pending_human_piece_removal_squares
            )
            return

        state = self.get_state()

        if state is None:
            self.led_driver.clear()
            return

        self.led_driver.display_opponent_pieces(state, self.human_player)

    def read_scan_matrix(self):
        """Read one raw logical scan from the board scanner."""
        scan_matrix = self.scanner.read_scan_matrix()
        self.latest_raw_scan_matrix = clone_scan_matrix(scan_matrix)

        if self.scanner.is_current_scan_stable():
            self.latest_stable_scan_matrix = clone_scan_matrix(scan_matrix)

            if self.has_pending_human_piece_removal():
                if self.required_removal_is_complete(
                    scan_matrix,
                    self.pending_human_piece_removal_squares
                ):
                    self.pending_human_piece_removal_squares = []
                    self.refresh_led_display()

        return clone_scan_matrix(scan_matrix)

    def read_stable_scan_matrix(self):
        scan_matrix = self.read_scan_matrix()

        if self.scanner.is_current_scan_stable():
            return clone_scan_matrix(scan_matrix)

        return None

    def process_next_scan(self):
        """
        Read the scanner once and process the scan only if it is stable.
        """
        stable_scan = self.read_stable_scan_matrix()

        if stable_scan is None:
            return None

        if self.last_handled_stable_scan is not None:
            if stable_scan == self.last_handled_stable_scan:
                return self.build_status_result("stable_scan_already_processed")

        self.last_handled_stable_scan = clone_scan_matrix(stable_scan)
        return self.handle_stable_scan(stable_scan)

    def build_move_from_candidate_action(self, action):
        """
        Convert a CandidateAction into a shared Move object.
        """
        captured_squares = []

        for square in action.captured_squares:
            captured_squares.append(Coordinate(square.row, square.col))

        return Move(
            player=self.human_player,
            from_square=Coordinate(action.from_square.row, action.from_square.col),
            to_square=Coordinate(action.to_square.row, action.to_square.col),
            captured_squares=captured_squares
        )

    def infer_matching_human_move_from_scan(self, scan_matrix):
        """
        Infer exactly one legal human move from a stable physical scan.

        Method:
        1. enumerate legal human moves for the current canonical state
        2. simulate each move on a cloned state
        3. build the expected human-piece scan after that move
        4. compare to the real stable scan
        """
        state = self.get_state()

        if state is None:
            return {
                "status": "no_state",
                "move": None
            }

        matching_moves = []
        legal_actions = legal_moves_for_player(state, self.human_player)

        for action in legal_actions:
            candidate_move = self.build_move_from_candidate_action(action)

            temp_state = state.clone()
            applied_move, validation = apply_move(temp_state, candidate_move)

            if not validation.is_legal:
                continue

            expected_scan = self.build_expected_scan_for_human(temp_state)

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

    def _apply_human_move(self, move):
        """Apply one human move through the shared rules engine."""
        state = self.get_state()

        if state is None:
            self.set_error(ErrorCode.SERVER_REJECTED_STATE, "No local game state is loaded.")
            return self.build_status_result("error")

        applied_move, validation = apply_move(state, move)

        if not validation.is_legal:
            self.set_error(validation.error_code, validation.message)
            return self.build_status_result(
                "illegal_human_move",
                {
                    "move": move,
                    "validation": validation
                }
            )

        self.state_cache.set_state(state)
        self.clear_error()
        self.refresh_led_display()

        return self.build_status_result(
            "human_move_applied",
            {
                "move": move,
                "applied_move": applied_move,
                "validation": validation
            }
        )

    def _apply_ai_turn(self):
        """
        Let the AI complete its full turn.

        This includes automatic continuation of AI multi-jumps.
        If the AI captures human pieces, those squares are stored so the user
        can be prompted to physically remove them from the board.
        """
        applied_ai_moves = []
        all_captured_squares = []
        max_segments = 12

        for _ in range(max_segments):
            state = self.get_state()

            if state is None:
                self.set_error(ErrorCode.SERVER_REJECTED_STATE, "No local game state is loaded.")
                return self.build_status_result("error")

            if state.winner is not None:
                self.state_cache.set_state(state)
                self.clear_error()
                self.refresh_led_display()
                return self.build_status_result(
                    "game_over",
                    {
                        "ai_moves": applied_ai_moves
                    }
                )

            if state.current_player != self.ai_player:
                self.state_cache.set_state(state)
                self.clear_error()
                self.refresh_led_display()
                return self.build_status_result(
                    "ai_turn_complete",
                    {
                        "ai_moves": applied_ai_moves
                    }
                )

            depth = get_depth_for_difficulty(self.difficulty)
            ai_move = choose_best_move(state, self.ai_player, depth)

            if ai_move is None:
                self.state_cache.set_state(state)
                self.clear_error()
                self.refresh_led_display()
                return self.build_status_result(
                    "ai_has_no_move",
                    {
                        "ai_moves": applied_ai_moves
                    }
                )

            applied_move, validation = apply_move(state, ai_move)

            if not validation.is_legal:
                self.set_error(validation.error_code, validation.message)
                return self.build_status_result(
                    "ai_move_failed",
                    {
                        "move": ai_move,
                        "validation": validation,
                        "ai_moves": applied_ai_moves
                    }
                )

            self.state_cache.set_state(state)
            applied_ai_moves.append(applied_move)

            for square in applied_move.captured_squares:
                all_captured_squares.append(square)

            if not applied_move.requires_continuation:
                break

        self.pending_human_piece_removal_squares = all_captured_squares
        self.clear_error()
        self.refresh_led_display()

        state = self.get_state()
        if state is not None and state.winner is not None:
            return self.build_status_result(
                "game_over",
                {
                    "ai_moves": applied_ai_moves
                }
            )

        return self.build_status_result(
            "ai_turn_complete",
            {
                "ai_moves": applied_ai_moves
            }
        )

    def normalize_incoming_scan(self, scan_matrix):
        """
        Normalize a caller-provided scan into the same logical format used by the runtime.
        """
        normalized_scan = normalize_scan_matrix(scan_matrix)
        normalized_scan = build_hardware_safe_scan_matrix(normalized_scan)
        return normalized_scan

    def handle_stable_scan(self, scan_matrix):
        """
        Process one stable logical scan from the physical board.
        """
        normalized_scan = self.normalize_incoming_scan(scan_matrix)
        self.latest_stable_scan_matrix = clone_scan_matrix(normalized_scan)

        state = self.get_state()

        if state is None:
            self.set_error(ErrorCode.SERVER_REJECTED_STATE, "No local game state is loaded.")
            return self.build_status_result("error")

        if self.has_pending_human_piece_removal():
            if self.required_removal_is_complete(
                normalized_scan,
                self.pending_human_piece_removal_squares
            ):
                self.pending_human_piece_removal_squares = []
                self.refresh_led_display()

                expected_scan = self.build_expected_scan_for_human(state)

                if self.scan_matrices_match(normalized_scan, expected_scan):
                    self.clear_error()
                    return self.build_status_result("capture_removal_complete")

                self.set_error(
                    ErrorCode.DESYNC,
                    "Captured piece was removed, but the board still does not match the canonical local state."
                )
                return self.build_status_result("error")

            self.set_error(
                ErrorCode.MISSING_CAPTURE_REMOVAL,
                "A captured human piece still needs to be removed from the board."
            )
            return self.build_status_result("waiting_for_capture_removal")

        expected_scan = self.build_expected_scan_for_human(state)

        if self.scan_matrices_match(normalized_scan, expected_scan):
            self.clear_error()

            if state.winner is not None:
                return self.build_status_result("game_over")

            if state.current_player != self.human_player:
                return self.build_status_result("waiting_for_ai")

            return self.build_status_result("no_change")

        if state.winner is not None:
            self.set_error(
                ErrorCode.DESYNC,
                "The physical board does not match the finished game state."
            )
            return self.build_status_result("error")

        if state.current_player != self.human_player:
            self.set_error(
                ErrorCode.OUT_OF_TURN,
                "It is currently the AI player's turn."
            )
            return self.build_status_result("error")

        inference_result = self.infer_matching_human_move_from_scan(normalized_scan)
        inference_status = inference_result["status"]

        if inference_status == "ambiguous":
            self.set_error(
                ErrorCode.AMBIGUOUS_SCAN,
                "More than one legal human move matches this stable scan."
            )
            return self.build_status_result("error")

        if inference_status == "no_match":
            self.set_error(
                ErrorCode.DESYNC,
                "The stable scan does not match any legal human move from the current state."
            )
            return self.build_status_result("error")

        if inference_status == "no_state":
            self.set_error(
                ErrorCode.SERVER_REJECTED_STATE,
                "No local game state is loaded."
            )
            return self.build_status_result("error")

        human_move = inference_result["move"]
        human_result = self._apply_human_move(human_move)

        if human_result["status"] != "human_move_applied":
            return human_result

        updated_state = self.get_state()

        if updated_state is not None:
            if updated_state.winner is not None:
                return self.build_status_result(
                    "game_over",
                    {
                        "human_move": human_move
                    }
                )

            if updated_state.current_player == self.ai_player:
                ai_result = self._apply_ai_turn()
                return self.build_status_result(
                    "human_and_ai_turn_complete",
                    {
                        "human_move": human_move,
                        "ai_result": ai_result
                    }
                )

        return self.build_status_result(
            "human_turn_continues",
            {
                "human_move": human_move
            }
        )

    def shutdown(self):
        """Clean up hardware resources."""
        if hasattr(self.scanner, "shutdown"):
            self.scanner.shutdown()

        if hasattr(self.led_driver, "shutdown"):
            self.led_driver.shutdown()
