import unittest

from shared.constants import Difficulty, Player
from shared.game_state import Coordinate, GameState, Piece
from shared.move_validation import legal_moves_for_player
from shared.rules import apply_move

from ai.difficulty_profiles import get_depth_for_difficulty
from ai.evaluator import evaluate_state
from ai.minimax import choose_best_move


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


class TestDifficultyProfiles(unittest.TestCase):

    def test_depths_increase_with_difficulty(self):
        easy_depth = get_depth_for_difficulty(Difficulty.EASY)
        medium_depth = get_depth_for_difficulty(Difficulty.MEDIUM)
        hard_depth = get_depth_for_difficulty(Difficulty.HARD)

        self.assertIsInstance(easy_depth, int)
        self.assertIsInstance(medium_depth, int)
        self.assertIsInstance(hard_depth, int)

        self.assertGreaterEqual(easy_depth, 1)
        self.assertGreater(medium_depth, easy_depth)
        self.assertGreater(hard_depth, medium_depth)


class TestEvaluator(unittest.TestCase):

    def test_more_pieces_is_better_for_the_ai_player(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 2, 3, Player.BLACK)
        place_piece(state, 5, 0, Player.RED)

        black_score = evaluate_state(state, Player.BLACK)
        red_score = evaluate_state(state, Player.RED)

        self.assertGreater(black_score, 0)
        self.assertLess(red_score, 0)

    def test_king_is_worth_more_than_man(self):
        man_state = make_state(current_player=Player.BLACK)
        king_state = make_state(current_player=Player.BLACK)

        place_piece(man_state, 2, 1, Player.BLACK, is_king=False)
        place_piece(king_state, 2, 1, Player.BLACK, is_king=True)

        man_score = evaluate_state(man_state, Player.BLACK)
        king_score = evaluate_state(king_state, Player.BLACK)

        self.assertGreater(king_score, man_score)


class TestMinimax(unittest.TestCase):

    def test_choose_best_move_returns_a_legal_move(self):
        state = GameState.initial()

        best_move = choose_best_move(state, Player.BLACK, depth=1)

        self.assertIsNotNone(best_move)
        self.assertEqual(best_move.player, Player.BLACK)

        legal_actions = legal_moves_for_player(state, Player.BLACK)

        matching_action_found = False
        for action in legal_actions:
            if action.from_square == best_move.from_square and action.to_square == best_move.to_square:
                matching_action_found = True
                break

        self.assertTrue(matching_action_found)

    def test_choose_best_move_returns_forced_capture(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 3, 2, Player.RED)
        place_piece(state, 5, 6, Player.RED)

        best_move = choose_best_move(state, Player.BLACK, depth=1)

        self.assertIsNotNone(best_move)
        self.assertEqual(best_move.from_square, Coordinate(2, 1))
        self.assertEqual(best_move.to_square, Coordinate(4, 3))

    def test_choose_best_move_respects_pending_multi_jump(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 4, 3, Player.BLACK)
        place_piece(state, 5, 4, Player.RED)
        place_piece(state, 1, 0, Player.BLACK)

        state.pending_multi_jump = Coordinate(4, 3)

        best_move = choose_best_move(state, Player.BLACK, depth=1)

        self.assertIsNotNone(best_move)
        self.assertEqual(best_move.from_square, Coordinate(4, 3))
        self.assertEqual(best_move.to_square, Coordinate(6, 5))

    def test_choose_best_move_returns_none_when_no_legal_moves_exist(self):
        state = make_state(current_player=Player.RED)

        place_piece(state, 0, 1, Player.RED)
        place_piece(state, 2, 1, Player.BLACK)

        best_move = choose_best_move(state, Player.RED, depth=1)

        self.assertIsNone(best_move)

    def test_chosen_move_can_be_applied_cleanly(self):
        state = make_state(current_player=Player.BLACK)

        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 5, 0, Player.RED)

        best_move = choose_best_move(state, Player.BLACK, depth=1)

        self.assertIsNotNone(best_move)

        applied_move, validation = apply_move(state, best_move)

        self.assertTrue(validation.is_legal)
        self.assertIsNotNone(applied_move)


if __name__ == "__main__":
    unittest.main()
