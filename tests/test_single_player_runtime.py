import unittest

from board.led_driver import LEDDriver
from board.single_player_runtime import SinglePlayerRuntime
from board.token_scanner import TokenScanner
from shared.constants import Difficulty, ErrorCode, GameMode, LED_ON, Player
from shared.game_state import Coordinate, Move
from shared.rules import apply_move


def build_runtime(human_player=Player.BLACK, difficulty=Difficulty.EASY):
    return SinglePlayerRuntime(
        human_player=human_player,
        difficulty=difficulty,
        scanner=TokenScanner(mode="mock"),
        led_driver=LEDDriver(mode="mock"),
    )


def count_lit_squares(led_matrix):
    count = 0

    for row in led_matrix:
        for value in row:
            if value == LED_ON:
                count += 1

    return count


class TestSinglePlayerRuntime(unittest.TestCase):
    def test_start_new_game_uses_single_player_mode(self):
        runtime = build_runtime()

        state = runtime.get_state()

        self.assertEqual(state.mode, GameMode.SINGLE_PLAYER)
        self.assertEqual(state.current_player, Player.BLACK)
        self.assertEqual(state.version, 0)
        self.assertEqual(state.move_number, 1)

    def test_start_new_game_shows_ai_pieces_on_leds_for_black_human(self):
        runtime = build_runtime(human_player=Player.BLACK)

        led_matrix = runtime.get_led_matrix()

        self.assertEqual(count_lit_squares(led_matrix), 12)

    def test_setting_human_to_red_makes_ai_take_first_turn(self):
        runtime = build_runtime(human_player=Player.RED)

        state = runtime.get_state()

        self.assertEqual(state.mode, GameMode.SINGLE_PLAYER)
        self.assertEqual(state.current_player, Player.RED)
        self.assertEqual(state.version, 1)
        self.assertEqual(state.move_number, 2)
        self.assertIsNone(state.winner)

    def test_handle_stable_scan_returns_no_change_when_board_matches_state(self):
        runtime = build_runtime(human_player=Player.BLACK)

        expected_scan = runtime.build_expected_scan_for_human(runtime.get_state())
        result = runtime.handle_stable_scan(expected_scan)

        self.assertEqual(result["status"], "no_change")
        self.assertIsNone(result["error_code"])

    def test_handle_stable_scan_rejects_impossible_board_change(self):
        runtime = build_runtime(human_player=Player.BLACK)

        bad_scan = runtime.build_expected_scan_for_human(runtime.get_state())
        bad_scan[2][1] = False

        result = runtime.handle_stable_scan(bad_scan)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], ErrorCode.DESYNC)

    def test_handle_stable_scan_applies_human_move_then_ai_move(self):
        runtime = build_runtime(human_player=Player.BLACK, difficulty=Difficulty.EASY)

        starting_state = runtime.get_state()

        human_move = Move(
            player=Player.BLACK,
            from_square=Coordinate(2, 1),
            to_square=Coordinate(3, 0),
        )

        expected_state_after_human_move = starting_state.clone()
        applied_move, validation = apply_move(expected_state_after_human_move, human_move)

        self.assertTrue(validation.is_legal)
        self.assertIsNotNone(applied_move)

        stable_scan = runtime.build_expected_scan_for_human(expected_state_after_human_move)
        result = runtime.handle_stable_scan(stable_scan)

        self.assertEqual(result["status"], "human_and_ai_turn_complete")
        self.assertEqual(result["human_move"], human_move)

        ai_result = result["ai_result"]
        self.assertEqual(ai_result["status"], "ai_turn_complete")

        final_state = runtime.get_state()

        self.assertEqual(final_state.current_player, Player.BLACK)
        self.assertEqual(final_state.version, 2)
        self.assertEqual(final_state.move_number, 3)
        self.assertIsNotNone(final_state.piece_at(Coordinate(3, 0)))

    def test_capture_removal_complete_clears_pending_squares(self):
        runtime = build_runtime(human_player=Player.BLACK)

        runtime.pending_human_piece_removal_squares = [Coordinate(2, 1)]
        runtime.refresh_led_display()

        current_state = runtime.get_state()
        expected_scan = runtime.build_expected_scan_for_human(current_state)
        expected_scan[2][1] = False

        result = runtime.handle_stable_scan(expected_scan)

        self.assertEqual(result["status"], "capture_removal_complete")
        self.assertFalse(runtime.has_pending_human_piece_removal())

    def test_missing_capture_removal_returns_waiting_status(self):
        runtime = build_runtime(human_player=Player.BLACK)

        runtime.pending_human_piece_removal_squares = [Coordinate(2, 1)]
        runtime.refresh_led_display()

        current_state = runtime.get_state()
        scan_with_piece_still_present = runtime.build_expected_scan_for_human(current_state)
        scan_with_piece_still_present[2][1] = True

        result = runtime.handle_stable_scan(scan_with_piece_still_present)

        self.assertEqual(result["status"], "waiting_for_capture_removal")
        self.assertEqual(result["error_code"], ErrorCode.MISSING_CAPTURE_REMOVAL)

    def test_process_next_scan_ignores_duplicate_stable_scan_after_first_handling(self):
        runtime = build_runtime(human_player=Player.BLACK)

        stable_scan = runtime.build_expected_scan_for_human(runtime.get_state())
        runtime.scanner.set_mock_scan_matrix(stable_scan)

        first_result = runtime.process_next_scan()
        second_result = runtime.process_next_scan()
        third_result = runtime.process_next_scan()

        self.assertIsNone(first_result)
        self.assertEqual(second_result["status"], "no_change")
        self.assertEqual(third_result["status"], "stable_scan_already_processed")


if __name__ == "__main__":
    unittest.main()
