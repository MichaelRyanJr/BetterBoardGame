import unittest

from board.led_driver import (
    LEDDriver,
    build_opponent_led_matrix,
    build_piece_led_matrix_for_player,
    clone_led_matrix,
    empty_led_matrix,
    normalize_led_matrix,
)
from shared.constants import BOARD_SIZE, LED_OFF, LED_ON, Player
from shared.game_state import Coordinate, GameState, Piece


def make_state():
    return GameState(
        board=GameState.empty_board()
    )


def place_piece(state, row, col, owner, is_king=False):
    state.set_piece(
        Coordinate(row, col),
        Piece(owner=owner, is_king=is_king)
    )


class TestLedDriverHelpers(unittest.TestCase):
    def test_empty_led_matrix_returns_8x8_off_matrix(self):
        matrix = empty_led_matrix()

        self.assertEqual(len(matrix), BOARD_SIZE)

        for row in matrix:
            self.assertEqual(len(row), BOARD_SIZE)

            for value in row:
                self.assertEqual(value, LED_OFF)

    def test_clone_led_matrix_returns_independent_copy(self):
        original = empty_led_matrix()
        original[2][1] = LED_ON

        cloned = clone_led_matrix(original)

        self.assertEqual(cloned, original)

        cloned[2][1] = LED_OFF
        self.assertEqual(original[2][1], LED_ON)

    def test_normalize_led_matrix_converts_values_to_led_states(self):
        matrix = empty_led_matrix()
        matrix[1][2] = 1
        matrix[3][4] = "on"
        matrix[5][6] = 0

        normalized = normalize_led_matrix(matrix)

        self.assertEqual(normalized[1][2], LED_ON)
        self.assertEqual(normalized[3][4], LED_ON)
        self.assertEqual(normalized[5][6], LED_OFF)

    def test_normalize_led_matrix_rejects_wrong_row_count(self):
        bad_matrix = []

        for _ in range(BOARD_SIZE - 1):
            row = []
            for _ in range(BOARD_SIZE):
                row.append(LED_OFF)
            bad_matrix.append(row)

        with self.assertRaises(ValueError):
            normalize_led_matrix(bad_matrix)

    def test_normalize_led_matrix_rejects_wrong_column_count(self):
        bad_matrix = empty_led_matrix()
        bad_matrix[0].append(LED_OFF)

        with self.assertRaises(ValueError):
            normalize_led_matrix(bad_matrix)

    def test_build_piece_led_matrix_for_player_lights_only_selected_player(self):
        state = make_state()
        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 3, 2, Player.RED)
        place_piece(state, 5, 4, Player.BLACK)

        matrix = build_piece_led_matrix_for_player(state, Player.BLACK)

        self.assertEqual(matrix[2][1], LED_ON)
        self.assertEqual(matrix[5][4], LED_ON)
        self.assertEqual(matrix[3][2], LED_OFF)
        self.assertEqual(matrix[0][0], LED_OFF)

    def test_build_opponent_led_matrix_lights_opponent_pieces(self):
        state = make_state()
        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 5, 0, Player.RED)
        place_piece(state, 5, 2, Player.RED)

        matrix = build_opponent_led_matrix(state, Player.BLACK)

        self.assertEqual(matrix[5][0], LED_ON)
        self.assertEqual(matrix[5][2], LED_ON)
        self.assertEqual(matrix[2][1], LED_OFF)


class TestLedDriver(unittest.TestCase):
    def test_initial_led_matrix_is_empty(self):
        driver = LEDDriver()

        matrix = driver.get_led_matrix()

        self.assertEqual(matrix, empty_led_matrix())

    def test_set_led_matrix_replaces_full_matrix(self):
        driver = LEDDriver()

        matrix = empty_led_matrix()
        matrix[2][1] = LED_ON
        matrix[4][3] = LED_ON

        driver.set_led_matrix(matrix)

        self.assertEqual(driver.get_led_matrix(), matrix)

    def test_get_led_matrix_returns_copy(self):
        driver = LEDDriver()

        matrix = empty_led_matrix()
        matrix[2][1] = LED_ON
        driver.set_led_matrix(matrix)

        returned_matrix = driver.get_led_matrix()
        returned_matrix[2][1] = LED_OFF

        self.assertEqual(driver.get_led_matrix()[2][1], LED_ON)

    def test_clear_turns_off_every_led(self):
        driver = LEDDriver()

        matrix = empty_led_matrix()
        matrix[2][1] = LED_ON
        matrix[4][3] = LED_ON
        driver.set_led_matrix(matrix)

        driver.clear()

        self.assertEqual(driver.get_led_matrix(), empty_led_matrix())

    def test_set_square_updates_one_square(self):
        driver = LEDDriver()

        driver.set_square(2, 1, LED_ON)

        matrix = driver.get_led_matrix()
        self.assertEqual(matrix[2][1], LED_ON)
        self.assertEqual(matrix[0][0], LED_OFF)

    def test_set_square_rejects_invalid_row(self):
        driver = LEDDriver()

        with self.assertRaises(ValueError):
            driver.set_square(-1, 1, LED_ON)

        with self.assertRaises(ValueError):
            driver.set_square(BOARD_SIZE, 1, LED_ON)

    def test_set_square_rejects_invalid_col(self):
        driver = LEDDriver()

        with self.assertRaises(ValueError):
            driver.set_square(1, -1, LED_ON)

        with self.assertRaises(ValueError):
            driver.set_square(1, BOARD_SIZE, LED_ON)

    def test_set_square_from_coordinate_updates_one_square(self):
        driver = LEDDriver()

        driver.set_square_from_coordinate(Coordinate(4, 3), LED_ON)

        matrix = driver.get_led_matrix()
        self.assertEqual(matrix[4][3], LED_ON)

    def test_set_squares_updates_multiple_squares(self):
        driver = LEDDriver()

        squares = [
            Coordinate(2, 1),
            Coordinate(4, 3),
            Coordinate(6, 5),
        ]

        driver.set_squares(squares, LED_ON)

        matrix = driver.get_led_matrix()
        self.assertEqual(matrix[2][1], LED_ON)
        self.assertEqual(matrix[4][3], LED_ON)
        self.assertEqual(matrix[6][5], LED_ON)
        self.assertEqual(matrix[0][0], LED_OFF)

    def test_set_squares_rejects_invalid_square_row(self):
        driver = LEDDriver()

        squares = [Coordinate(-1, 2)]

        with self.assertRaises(ValueError):
            driver.set_squares(squares, LED_ON)

    def test_set_squares_rejects_invalid_square_col(self):
        driver = LEDDriver()

        squares = [Coordinate(2, BOARD_SIZE)]

        with self.assertRaises(ValueError):
            driver.set_squares(squares, LED_ON)

    def test_display_player_pieces_lights_selected_player(self):
        driver = LEDDriver()

        state = make_state()
        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 3, 2, Player.RED)
        place_piece(state, 4, 3, Player.BLACK)

        driver.display_player_pieces(state, Player.BLACK)

        matrix = driver.get_led_matrix()
        self.assertEqual(matrix[2][1], LED_ON)
        self.assertEqual(matrix[4][3], LED_ON)
        self.assertEqual(matrix[3][2], LED_OFF)

    def test_display_opponent_pieces_lights_only_opponent(self):
        driver = LEDDriver()

        state = make_state()
        place_piece(state, 2, 1, Player.BLACK)
        place_piece(state, 5, 0, Player.RED)
        place_piece(state, 5, 2, Player.RED)

        driver.display_opponent_pieces(state, Player.BLACK)

        matrix = driver.get_led_matrix()
        self.assertEqual(matrix[5][0], LED_ON)
        self.assertEqual(matrix[5][2], LED_ON)
        self.assertEqual(matrix[2][1], LED_OFF)

    def test_display_capture_removal_squares_lights_only_requested_squares(self):
        driver = LEDDriver()

        squares_to_remove = [
            Coordinate(3, 2),
            Coordinate(5, 4),
        ]

        driver.display_capture_removal_squares(squares_to_remove)

        matrix = driver.get_led_matrix()
        self.assertEqual(matrix[3][2], LED_ON)
        self.assertEqual(matrix[5][4], LED_ON)
        self.assertEqual(matrix[0][0], LED_OFF)

    def test_display_capture_removal_squares_rejects_invalid_row(self):
        driver = LEDDriver()

        with self.assertRaises(ValueError):
            driver.display_capture_removal_squares([Coordinate(-1, 2)])

    def test_display_capture_removal_squares_rejects_invalid_col(self):
        driver = LEDDriver()

        with self.assertRaises(ValueError):
            driver.display_capture_removal_squares([Coordinate(2, BOARD_SIZE)])

    def test_hardware_mode_not_implemented_yet(self):
        driver = LEDDriver(mode="hardware")

        with self.assertRaises(NotImplementedError):
            driver.set_led_matrix(empty_led_matrix())

    def test_invalid_mode_raises_value_error(self):
        driver = LEDDriver(mode="invalid-mode")

        with self.assertRaises(ValueError):
            driver.set_led_matrix(empty_led_matrix())


if __name__ == "__main__":
    unittest.main()
