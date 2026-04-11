import unittest

from board.board_controller import BoardController
from board.led_driver import empty_led_matrix
from shared.constants import EventType, LED_OFF, LED_ON, Player
from shared.game_state import Coordinate, GameState, Piece
from server.event_protocol import (
    build_piece_removed_required_message,
    build_state_sync_message,
)


def make_matrix_with_occupied_squares(squares):
    matrix = []

    for _ in range(8):
        row = []
        for _ in range(8):
            row.append(False)
        matrix.append(row)

    for row, col in squares:
        matrix[row][col] = True

    return matrix


def make_state():
    return GameState(
        board=GameState.empty_board()
    )


def place_piece(state, row, col, owner, is_king=False):
    state.set_piece(
        Coordinate(row, col),
        Piece(owner=owner, is_king=is_king)
    )


class TestBoardController(unittest.TestCase):
    def test_initial_state_has_no_cached_state_or_pending_capture_removal(self):
        controller = BoardController(
            board_id="bbg-boarda",
            local_player=Player.BLACK
        )

        self.assertFalse(controller.has_state())
        self.assertIsNone(controller.get_state())
        self.assertIsNone(controller.get_state_version())
        self.assertFalse(controller.has_pending_capture_removal())
        self.assertIsNone(controller.get_latest_scan_matrix())
        self.assertIsNone(controller.get_latest_stable_scan_matrix())

    def test_read_scan_matrix_stores_latest_raw_and_latest_stable_scan(self):
        controller = BoardController(
            board_id="bbg-boarda",
            local_player=Player.BLACK
        )

        stable_matrix = make_matrix_with_occupied_squares([(2, 1)])
        controller.scanner.set_mock_scan_matrix(stable_matrix)

        first_result = controller.read_scan_matrix()
        second_result = controller.read_scan_matrix()

        self.assertEqual(first_result, stable_matrix)
        self.assertEqual(second_result, stable_matrix)
        self.assertEqual(controller.get_latest_scan_matrix(), stable_matrix)
        self.assertEqual(controller.get_latest_stable_scan_matrix(), stable_matrix)

    def test_read_stable_scan_matrix_returns_none_until_scan_becomes_stable(self):
        controller = BoardController(
            board_id="bbg-boarda",
            local_player=Player.BLACK
        )

        stable_matrix = make_matrix_with_occupied_squares([(2, 1)])
        controller.scanner.set_mock_scan_matrix(stable_matrix)

        first_result = controller.read_stable_scan_matrix()
        second_result = controller.read_stable_scan_matrix()

        self.assertIsNone(first_result)
        self.assertEqual(second_result, stable_matrix)

    def test_poll_scanner_builds_scan_snapshot_every_time_and_stable_scan_once(self):
        controller = BoardController(
            board_id="bbg-boarda",
            local_player=Player.BLACK
        )

        matrix = make_matrix_with_occupied_squares([(2, 1)])
        controller.scanner.set_mock_scan_sequence([matrix, matrix, matrix])

        first_messages = controller.poll_scanner_and_build_outgoing_messages()
        second_messages = controller.poll_scanner_and_build_outgoing_messages()
        third_messages = controller.poll_scanner_and_build_outgoing_messages()

        self.assertEqual(len(first_messages), 1)
        self.assertEqual(first_messages[0]["event_type"], EventType.SCAN_SNAPSHOT.value)

        self.assertEqual(len(second_messages), 2)
        self.assertEqual(second_messages[0]["event_type"], EventType.SCAN_SNAPSHOT.value)
        self.assertEqual(second_messages[1]["event_type"], EventType.STABLE_SCAN.value)

        self.assertEqual(len(third_messages), 1)
        self.assertEqual(third_messages[0]["event_type"], EventType.SCAN_SNAPSHOT.value)

    def test_poll_scanner_sends_new_stable_scan_when_stable_matrix_changes(self):
        controller = BoardController(
            board_id="bbg-boarda",
            local_player=Player.BLACK
        )

        matrix_a = make_matrix_with_occupied_squares([(2, 1)])
        matrix_b = make_matrix_with_occupied_squares([(4, 3)])

        controller.scanner.set_mock_scan_sequence([
            matrix_a,
            matrix_a,
            matrix_b,
            matrix_b,
        ])

        first_messages = controller.poll_scanner_and_build_outgoing_messages()
        second_messages = controller.poll_scanner_and_build_outgoing_messages()
        third_messages = controller.poll_scanner_and_build_outgoing_messages()
        fourth_messages = controller.poll_scanner_and_build_outgoing_messages()

        self.assertEqual(len(first_messages), 1)

        self.assertEqual(len(second_messages), 2)
        self.assertEqual(second_messages[1]["event_type"], EventType.STABLE_SCAN.value)

        self.assertEqual(len(third_messages), 1)

        self.assertEqual(len(fourth_messages), 2)
        self.assertEqual(fourth_messages[1]["event_type"], EventType.STABLE_SCAN.value)

    def test_handle_state_sync_updates_leds_to_show_opponent_pieces(self):
        controller = BoardController(
            board_id="bbg-boarda",
            local_player=Player.BLACK
        )

        state = make_state()
        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 5, 0, Player.RED)
        place_piece(state, 5, 2, Player.RED)

        message = build_state_sync_message(
            state=state,
            game_id=state.game_id,
            session_id=state.session_id,
            source="server"
        )

        result = controller.handle_incoming_message(message)
        led_matrix = controller.get_led_matrix()

        self.assertEqual(result["event_type"], EventType.STATE_SYNC)
        self.assertTrue(controller.has_state())
        self.assertEqual(led_matrix[5][0], LED_ON)
        self.assertEqual(led_matrix[5][2], LED_ON)
        self.assertEqual(led_matrix[2][1], LED_OFF)

    def test_handle_piece_removed_required_overrides_opponent_display(self):
        controller = BoardController(
            board_id="bbg-boarda",
            local_player=Player.BLACK
        )

        state = make_state()
        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 5, 0, Player.RED)

        state_message = build_state_sync_message(
            state=state,
            game_id=state.game_id,
            session_id=state.session_id,
            source="server"
        )
        controller.handle_incoming_message(state_message)

        removal_squares = [
            Coordinate(3, 2),
            Coordinate(5, 4),
        ]

        removal_message = build_piece_removed_required_message(
            squares_to_remove=removal_squares,
            game_id=state.game_id,
            session_id=state.session_id,
            source="server"
        )

        result = controller.handle_incoming_message(removal_message)
        led_matrix = controller.get_led_matrix()

        self.assertEqual(result["event_type"], EventType.PIECE_REMOVED_REQUIRED)
        self.assertTrue(controller.has_pending_capture_removal())
        self.assertEqual(led_matrix[3][2], LED_ON)
        self.assertEqual(led_matrix[5][4], LED_ON)
        self.assertEqual(led_matrix[5][0], LED_OFF)

    def test_clear_pending_capture_removal_restores_opponent_display(self):
        controller = BoardController(
            board_id="bbg-boarda",
            local_player=Player.BLACK
        )

        state = make_state()
        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 5, 0, Player.RED)

        state_message = build_state_sync_message(
            state=state,
            game_id=state.game_id,
            session_id=state.session_id,
            source="server"
        )
        controller.handle_incoming_message(state_message)

        removal_message = build_piece_removed_required_message(
            squares_to_remove=[Coordinate(3, 2)],
            game_id=state.game_id,
            session_id=state.session_id,
            source="server"
        )
        controller.handle_incoming_message(removal_message)

        controller.clear_pending_capture_removal()
        led_matrix = controller.get_led_matrix()

        self.assertFalse(controller.has_pending_capture_removal())
        self.assertEqual(led_matrix[5][0], LED_ON)
        self.assertEqual(led_matrix[3][2], LED_OFF)

    def test_capture_removal_is_complete_returns_true_only_when_required_squares_are_empty(self):
        controller = BoardController(
            board_id="bbg-boarda",
            local_player=Player.BLACK
        )

        controller.pending_capture_removal_squares = [
            Coordinate(3, 2),
            Coordinate(5, 4),
        ]

        incomplete_scan = make_matrix_with_occupied_squares([(3, 2)])
        complete_scan = make_matrix_with_occupied_squares([])

        self.assertFalse(controller.capture_removal_is_complete(incomplete_scan))
        self.assertTrue(controller.capture_removal_is_complete(complete_scan))

    def test_stable_scan_clears_pending_capture_removal_when_squares_are_empty(self):
        controller = BoardController(
            board_id="bbg-boarda",
            local_player=Player.BLACK
        )

        state = make_state()
        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 5, 0, Player.RED)

        state_message = build_state_sync_message(
            state=state,
            game_id=state.game_id,
            session_id=state.session_id,
            source="server"
        )
        controller.handle_incoming_message(state_message)

        controller.pending_capture_removal_squares = [Coordinate(3, 2)]
        controller.refresh_led_display()

        empty_matrix = make_matrix_with_occupied_squares([])
        controller.scanner.set_mock_scan_matrix(empty_matrix)

        controller.read_scan_matrix()
        self.assertTrue(controller.has_pending_capture_removal())

        controller.read_scan_matrix()
        self.assertFalse(controller.has_pending_capture_removal())

        led_matrix = controller.get_led_matrix()
        self.assertEqual(led_matrix[5][0], LED_ON)
        self.assertEqual(led_matrix[3][2], LED_OFF)

    def test_refresh_led_display_clears_leds_when_no_state_exists(self):
        controller = BoardController(
            board_id="bbg-boarda",
            local_player=Player.BLACK
        )

        controller.refresh_led_display()

        self.assertEqual(controller.get_led_matrix(), empty_led_matrix())

    def test_refresh_led_display_clears_leds_when_local_player_is_unknown(self):
        controller = BoardController(
            board_id="bbg-boarda",
            local_player=None
        )

        state = make_state()
        place_piece(state, 5, 0, Player.RED)

        message = build_state_sync_message(
            state=state,
            game_id=state.game_id,
            session_id=state.session_id,
            source="server"
        )
        controller.handle_incoming_message(message)

        self.assertEqual(controller.get_led_matrix(), empty_led_matrix())

    def test_handle_incoming_json_updates_state_and_leds(self):
        controller = BoardController(
            board_id="bbg-boarda",
            local_player=Player.BLACK
        )

        state = make_state()
        place_piece(state, 5, 0, Player.RED)

        message = build_state_sync_message(
            state=state,
            game_id=state.game_id,
            session_id=state.session_id,
            source="server"
        )

        json_text = controller.client.encode_message(message)
        result = controller.handle_incoming_json(json_text)

        self.assertEqual(result["event_type"], EventType.STATE_SYNC)
        self.assertEqual(controller.get_led_matrix()[5][0], LED_ON)


if __name__ == "__main__":
    unittest.main()
