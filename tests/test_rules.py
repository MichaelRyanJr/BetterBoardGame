import unittest

from shared.constants import Player, Winner
from shared.game_state import Coordinate, GameState, Move, Piece
from shared.rules import apply_move


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


def make_move(player, from_row, from_col, to_row, to_col):
    return Move(
        player=player,
        from_square=Coordinate(from_row, from_col),
        to_square=Coordinate(to_row, to_col)
    )


class TestRules(unittest.TestCase):

    def test_simple_move_updates_board_and_turn(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 5, 4, Player.RED)

        move = make_move(Player.BLACK, 2, 1, 3, 0)
        applied_move, validation = apply_move(state, move)

        self.assertTrue(validation.is_legal)
        self.assertIsNotNone(applied_move)

        self.assertIsNone(state.piece_at(Coordinate(2, 1)))
        self.assertIsNotNone(state.piece_at(Coordinate(3, 0)))
        self.assertEqual(state.piece_at(Coordinate(3, 0)).owner, Player.BLACK)

        self.assertEqual(state.current_player, Player.RED)
        self.assertEqual(state.move_number, 2)
        self.assertEqual(state.version, 1)
        self.assertIsNone(state.pending_multi_jump)
        self.assertIsNone(state.winner)

        self.assertEqual(applied_move.next_player, Player.RED)
        self.assertFalse(applied_move.promoted)
        self.assertFalse(applied_move.requires_continuation)

    def test_capture_removes_piece_and_requires_continuation(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 3, 2, Player.RED)
        place_piece(state, 5, 4, Player.RED)
        place_piece(state, 7, 6, Player.RED)

        move = make_move(Player.BLACK, 2, 1, 4, 3)
        applied_move, validation = apply_move(state, move)

        self.assertTrue(validation.is_legal)
        self.assertIsNotNone(applied_move)

        self.assertIsNone(state.piece_at(Coordinate(2, 1)))
        self.assertIsNone(state.piece_at(Coordinate(3, 2)))
        self.assertIsNotNone(state.piece_at(Coordinate(4, 3)))
        self.assertEqual(state.piece_at(Coordinate(4, 3)).owner, Player.BLACK)

        self.assertEqual(state.current_player, Player.BLACK)
        self.assertEqual(state.move_number, 1)
        self.assertEqual(state.version, 1)
        self.assertEqual(state.pending_multi_jump, Coordinate(4, 3))
        self.assertIsNone(state.winner)

        self.assertTrue(applied_move.requires_continuation)
        self.assertEqual(applied_move.continuation_square, Coordinate(4, 3))
        self.assertEqual(applied_move.next_player, Player.BLACK)
        self.assertEqual(len(applied_move.captured_squares), 1)
        self.assertEqual(applied_move.captured_squares[0], Coordinate(3, 2))

    def test_second_jump_finishes_multi_jump_turn(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 3, 2, Player.RED)
        place_piece(state, 5, 4, Player.RED)
        place_piece(state, 7, 6, Player.RED)

        first_move = make_move(Player.BLACK, 2, 1, 4, 3)
        first_applied, first_validation = apply_move(state, first_move)

        self.assertTrue(first_validation.is_legal)
        self.assertTrue(first_applied.requires_continuation)

        second_move = make_move(Player.BLACK, 4, 3, 6, 5)
        second_applied, second_validation = apply_move(state, second_move)

        self.assertTrue(second_validation.is_legal)
        self.assertIsNotNone(second_applied)

        self.assertIsNone(state.piece_at(Coordinate(4, 3)))
        self.assertIsNone(state.piece_at(Coordinate(5, 4)))
        self.assertIsNotNone(state.piece_at(Coordinate(6, 5)))
        self.assertEqual(state.piece_at(Coordinate(6, 5)).owner, Player.BLACK)

        self.assertEqual(state.current_player, Player.RED)
        self.assertEqual(state.move_number, 2)
        self.assertEqual(state.version, 2)
        self.assertIsNone(state.pending_multi_jump)
        self.assertIsNone(state.winner)

        self.assertFalse(second_applied.requires_continuation)
        self.assertEqual(second_applied.next_player, Player.RED)

    def test_simple_move_promotion_to_king(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 6, 1, Player.BLACK)
        place_piece(state, 5, 4, Player.RED)

        move = make_move(Player.BLACK, 6, 1, 7, 0)
        applied_move, validation = apply_move(state, move)

        self.assertTrue(validation.is_legal)
        self.assertIsNotNone(applied_move)

        moved_piece = state.piece_at(Coordinate(7, 0))
        self.assertIsNotNone(moved_piece)
        self.assertEqual(moved_piece.owner, Player.BLACK)
        self.assertTrue(moved_piece.is_king)

        self.assertTrue(applied_move.promoted)
        self.assertEqual(state.current_player, Player.RED)
        self.assertIsNone(state.pending_multi_jump)
        self.assertIsNone(state.winner)

    def test_promotion_capture_ends_chain_under_current_rules(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 5, 0, Player.BLACK)
        place_piece(state, 6, 1, Player.RED)
        place_piece(state, 6, 3, Player.RED)

        move = make_move(Player.BLACK, 5, 0, 7, 2)
        applied_move, validation = apply_move(state, move)

        self.assertTrue(validation.is_legal)
        self.assertIsNotNone(applied_move)

        moved_piece = state.piece_at(Coordinate(7, 2))
        self.assertIsNotNone(moved_piece)
        self.assertTrue(moved_piece.is_king)

        self.assertIsNone(state.pending_multi_jump)
        self.assertEqual(state.current_player, Player.RED)
        self.assertTrue(applied_move.promoted)
        self.assertFalse(applied_move.requires_continuation)

    def test_winner_when_last_enemy_piece_is_captured(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 3, 2, Player.RED)

        move = make_move(Player.BLACK, 2, 1, 4, 3)
        applied_move, validation = apply_move(state, move)

        self.assertTrue(validation.is_legal)
        self.assertIsNotNone(applied_move)

        self.assertEqual(state.winner, Winner.BLACK)
        self.assertEqual(applied_move.winner, Winner.BLACK)

    def test_winner_when_next_player_has_no_legal_moves(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 0, 1, Player.RED)

        move = make_move(Player.BLACK, 2, 1, 3, 0)
        applied_move, validation = apply_move(state, move)

        self.assertTrue(validation.is_legal)
        self.assertIsNotNone(applied_move)

        self.assertEqual(state.winner, Winner.BLACK)
        self.assertEqual(applied_move.winner, Winner.BLACK)


if __name__ == "__main__":
    unittest.main()
