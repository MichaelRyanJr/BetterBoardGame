import unittest

from board.token_scanner import (
    TokenScanner,
    clone_scan_matrix,
    empty_scan_matrix,
    normalize_scan_matrix,
)
from shared.constants import BOARD_SIZE


def make_matrix_with_occupied_squares(squares):
    matrix = empty_scan_matrix()

    for row, col in squares:
        matrix[row][col] = True

    return matrix


class TestTokenScannerHelpers(unittest.TestCase):
    def test_empty_scan_matrix_returns_8x8_false_matrix(self):
        matrix = empty_scan_matrix()

        self.assertEqual(len(matrix), BOARD_SIZE)

        for row in matrix:
            self.assertEqual(len(row), BOARD_SIZE)

            for value in row:
                self.assertFalse(value)

    def test_clone_scan_matrix_returns_independent_copy(self):
        original = make_matrix_with_occupied_squares([(2, 1)])
        cloned = clone_scan_matrix(original)

        self.assertEqual(cloned, original)

        cloned[2][1] = False
        self.assertTrue(original[2][1])

    def test_normalize_scan_matrix_converts_values_to_bools(self):
        matrix = empty_scan_matrix()
        matrix[1][2] = 1
        matrix[3][4] = "occupied"

        normalized = normalize_scan_matrix(matrix)

        self.assertTrue(normalized[1][2])
        self.assertTrue(normalized[3][4])
        self.assertFalse(normalized[0][0])

    def test_normalize_scan_matrix_rejects_wrong_row_count(self):
        bad_matrix = []

        for _ in range(BOARD_SIZE - 1):
            row = []
            for _ in range(BOARD_SIZE):
                row.append(False)
            bad_matrix.append(row)

        with self.assertRaises(ValueError):
            normalize_scan_matrix(bad_matrix)

    def test_normalize_scan_matrix_rejects_wrong_column_count(self):
        bad_matrix = empty_scan_matrix()
        bad_matrix[0].append(False)

        with self.assertRaises(ValueError):
            normalize_scan_matrix(bad_matrix)


class TestTokenScanner(unittest.TestCase):
    def test_read_scan_matrix_returns_current_mock_matrix(self):
        scanner = TokenScanner()

        expected_matrix = make_matrix_with_occupied_squares([(2, 1), (5, 4)])
        scanner.set_mock_scan_matrix(expected_matrix)

        result = scanner.read_scan_matrix()

        self.assertEqual(result, expected_matrix)

    def test_get_latest_scan_matrix_is_none_before_first_read(self):
        scanner = TokenScanner()

        self.assertIsNone(scanner.get_latest_scan_matrix())
        self.assertFalse(scanner.is_current_scan_stable())

    def test_get_latest_scan_matrix_returns_last_read(self):
        scanner = TokenScanner()

        expected_matrix = make_matrix_with_occupied_squares([(4, 3)])
        scanner.set_mock_scan_matrix(expected_matrix)

        scanner.read_scan_matrix()
        latest = scanner.get_latest_scan_matrix()

        self.assertEqual(latest, expected_matrix)

    def test_get_latest_scan_matrix_returns_copy(self):
        scanner = TokenScanner()

        expected_matrix = make_matrix_with_occupied_squares([(4, 3)])
        scanner.set_mock_scan_matrix(expected_matrix)

        scanner.read_scan_matrix()
        latest = scanner.get_latest_scan_matrix()

        latest[4][3] = False

        latest_again = scanner.get_latest_scan_matrix()
        self.assertTrue(latest_again[4][3])

    def test_read_stable_scan_matrix_requires_repeated_matching_reads(self):
        scanner = TokenScanner(stable_reads_required=2)

        expected_matrix = make_matrix_with_occupied_squares([(2, 1)])
        scanner.set_mock_scan_matrix(expected_matrix)

        first_result = scanner.read_stable_scan_matrix()
        second_result = scanner.read_stable_scan_matrix()

        self.assertIsNone(first_result)
        self.assertEqual(second_result, expected_matrix)
        self.assertTrue(scanner.is_current_scan_stable())

    def test_stability_counter_increases_for_matching_reads(self):
        scanner = TokenScanner(stable_reads_required=3)

        expected_matrix = make_matrix_with_occupied_squares([(2, 1)])
        scanner.set_mock_scan_matrix(expected_matrix)

        scanner.read_scan_matrix()
        self.assertEqual(scanner.get_matching_scan_count(), 1)
        self.assertFalse(scanner.is_current_scan_stable())

        scanner.read_scan_matrix()
        self.assertEqual(scanner.get_matching_scan_count(), 2)
        self.assertFalse(scanner.is_current_scan_stable())

        scanner.read_scan_matrix()
        self.assertEqual(scanner.get_matching_scan_count(), 3)
        self.assertTrue(scanner.is_current_scan_stable())

    def test_stability_counter_resets_when_scan_changes(self):
        first_matrix = make_matrix_with_occupied_squares([(2, 1)])
        second_matrix = make_matrix_with_occupied_squares([(3, 2)])

        scanner = TokenScanner(stable_reads_required=2)
        scanner.set_mock_scan_sequence([first_matrix, first_matrix, second_matrix])

        scanner.read_scan_matrix()
        self.assertEqual(scanner.get_matching_scan_count(), 1)

        scanner.read_scan_matrix()
        self.assertEqual(scanner.get_matching_scan_count(), 2)
        self.assertTrue(scanner.is_current_scan_stable())

        scanner.read_scan_matrix()
        self.assertEqual(scanner.get_matching_scan_count(), 1)
        self.assertFalse(scanner.is_current_scan_stable())

    def test_mock_scan_sequence_advances_then_holds_last_matrix(self):
        first_matrix = make_matrix_with_occupied_squares([(2, 1)])
        second_matrix = make_matrix_with_occupied_squares([(4, 3)])

        scanner = TokenScanner()
        scanner.set_mock_scan_sequence([first_matrix, second_matrix])

        result_1 = scanner.read_scan_matrix()
        result_2 = scanner.read_scan_matrix()
        result_3 = scanner.read_scan_matrix()

        self.assertEqual(result_1, first_matrix)
        self.assertEqual(result_2, second_matrix)
        self.assertEqual(result_3, second_matrix)

    def test_reset_stability_tracking_clears_stability_state(self):
        scanner = TokenScanner(stable_reads_required=2)

        expected_matrix = make_matrix_with_occupied_squares([(2, 1)])
        scanner.set_mock_scan_matrix(expected_matrix)

        scanner.read_scan_matrix()
        scanner.read_scan_matrix()

        self.assertTrue(scanner.is_current_scan_stable())

        scanner.reset_stability_tracking()

        self.assertEqual(scanner.get_matching_scan_count(), 0)
        self.assertFalse(scanner.is_current_scan_stable())

    def test_set_mock_scan_sequence_rejects_empty_sequence(self):
        scanner = TokenScanner()

        with self.assertRaises(ValueError):
            scanner.set_mock_scan_sequence([])

    def test_stable_reads_required_must_be_at_least_one(self):
        with self.assertRaises(ValueError):
            TokenScanner(stable_reads_required=0)

    def test_gpio_mode_not_implemented_yet(self):
        scanner = TokenScanner(mode="gpio")

        with self.assertRaises(NotImplementedError):
            scanner.read_scan_matrix()

    def test_invalid_mode_raises_value_error(self):
        scanner = TokenScanner(mode="invalid-mode")

        with self.assertRaises(ValueError):
            scanner.read_scan_matrix()


if __name__ == "__main__":
    unittest.main()
