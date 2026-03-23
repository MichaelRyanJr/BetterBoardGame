import unittest

from shared.constants import ErrorCode, Player, Winner
from shared.game_state import Coordinate, GameState, Move, Piece
from shared.move_validation import validate_move


def make_state(current_player=Player.BLACK):
    return GameState(
        board=GameState.empty_board(),
        current_player=current_player
    )


def place_piece(state, row, col, owner, is_king=False):
    state.set_piece(
        Coordinate(row, col),
        Piece(owner=owner, is_king=is_king)
    )


def make_move(player, from_row, from_col, to_row, to_col, captured_squares=None):
    if captured_squares is None:
        captured_squares = []

    return Move(
        player=player,
        from_square=Coordinate(from_row, from_col),
        to_square=Coordinate(to_row, to_col),
        captured_squares=captured_squares
    )


class TestIllegalMoves(unittest.TestCase):

    def assert_illegal(self, state, move, expected_error):
        result = validate_move(state, move)
        self.assertFalse(result.is_legal)
        self.assertEqual(result.error_code, expected_error)
        return result

    def test_game_already_over_rejected(self):
        state = make_state(current_player=Player.BLACK)
        state.winner = Winner.BLACK

        place_piece(state, 2, 1, Player.BLACK)

        move = make_move(Player.BLACK, 2, 1, 3, 0)
        self.assert_illegal(state, move, ErrorCode.SERVER_REJECTED_STATE)

    def test_out_of_turn_rejected(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 5, 0, Player.RED)

        move = make_move(Player.RED, 5, 0, 4, 1)
        self.assert_illegal(state, move, ErrorCode.OUT_OF_TURN)

    def test_out_of_bounds_rejected(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)

        move = make_move(Player.BLACK, 2, 1, 8, 1)
        self.assert_illegal(state, move, ErrorCode.OUT_OF_BOUNDS)

    def test_invalid_source_square_rejected(self):
        state = make_state(current_player=Player.BLACK)

        # (2, 2) is a light square
        place_piece(state, 2, 2, Player.BLACK)

        move = make_move(Player.BLACK, 2, 2, 3, 1)
        self.assert_illegal(state, move, ErrorCode.INVALID_SQUARE)

    def test_invalid_destination_square_rejected(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)

        # (3, 1) is a light square
        move = make_move(Player.BLACK, 2, 1, 3, 1)
        self.assert_illegal(state, move, ErrorCode.INVALID_SQUARE)

    def test_source_empty_rejected(self):
        state = make_state(current_player=Player.BLACK)

        move = make_move(Player.BLACK, 2, 1, 3, 0)
        self.assert_illegal(state, move, ErrorCode.SOURCE_EMPTY)

    def test_not_your_piece_rejected(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.RED)

        move = make_move(Player.BLACK, 2, 1, 3, 0)
        self.assert_illegal(state, move, ErrorCode.NOT_YOUR_PIECE)

    def test_destination_occupied_rejected(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 3, 0, Player.RED)

        move = make_move(Player.BLACK, 2, 1, 3, 0)
        self.assert_illegal(state, move, ErrorCode.DESTINATION_OCCUPIED)

    def test_illegal_direction_rejected(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)

        # Horizontal move to another dark square
        move = make_move(Player.BLACK, 2, 1, 2, 3)
        self.assert_illegal(state, move, ErrorCode.ILLEGAL_DIRECTION)

    def test_illegal_distance_rejected_for_three_square_move(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)

        move = make_move(Player.BLACK, 2, 1, 5, 4)
        self.assert_illegal(state, move, ErrorCode.ILLEGAL_DISTANCE)

    def test_illegal_distance_rejected_for_jump_over_empty_square(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)

        # Looks like a capture jump, but there is no jumped piece at (3, 2)
        move = make_move(Player.BLACK, 2, 1, 4, 3)
        self.assert_illegal(state, move, ErrorCode.ILLEGAL_DISTANCE)

    def test_backward_non_king_rejected(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)

        move = make_move(Player.BLACK, 2, 1, 1, 0)
        self.assert_illegal(state, move, ErrorCode.BACKWARD_NON_KING)

    def test_must_capture_rejected_for_simple_move(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 3, 2, Player.RED)

        # Black could capture to (4, 3), so this quiet move should be rejected
        move = make_move(Player.BLACK, 2, 1, 3, 0)
        self.assert_illegal(state, move, ErrorCode.MUST_CAPTURE)

    def test_multi_jump_required_rejected_for_wrong_piece(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 4, 3, Player.BLACK)
        place_piece(state, 2, 1, Player.BLACK)

        state.pending_multi_jump = Coordinate(4, 3)

        move = make_move(Player.BLACK, 2, 1, 3, 0)
        self.assert_illegal(state, move, ErrorCode.MULTI_JUMP_REQUIRED)

    def test_multi_jump_required_rejected_for_simple_step(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 4, 3, Player.BLACK)
        place_piece(state, 5, 4, Player.RED)

        state.pending_multi_jump = Coordinate(4, 3)

        # Same piece is chosen, but a capture continuation is required
        move = make_move(Player.BLACK, 4, 3, 5, 2)
        self.assert_illegal(state, move, ErrorCode.MULTI_JUMP_REQUIRED)

    def test_capture_metadata_mismatch_rejected(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 3, 2, Player.RED)

        # Actual jumped square should be (3, 2), but we lie in captured_squares
        move = make_move(
            Player.BLACK,
            2,
            1,
            4,
            3,
            captured_squares=[Coordinate(3, 0)]
        )

        self.assert_illegal(state, move, ErrorCode.SERVER_REJECTED_STATE)


if __name__ == "__main__":
    unittest.main()
