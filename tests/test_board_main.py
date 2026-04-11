import unittest

from board.main import BoardMain
from board.token_scanner import clone_scan_matrix, empty_scan_matrix


def make_matrix_with_occupied_squares(squares):
    matrix = empty_scan_matrix()

    for row, col in squares:
        matrix[row][col] = True

    return matrix


class FakeWebSocket:
    def __init__(self):
        self.sent_messages = []

    def send(self, message_text):
        self.sent_messages.append(message_text)


class SequencedStopEvent:
    """
    Return a controlled sequence of wait() results.

    False means the loop should keep running.
    True means the loop should stop.
    """

    def __init__(self, wait_results):
        self.wait_results = list(wait_results)

    def wait(self, timeout=None):
        if len(self.wait_results) == 0:
            return True

        return self.wait_results.pop(0)

    def set(self):
        return


class FakeScanner:
    def __init__(self, scan_matrices, stable_flags):
        if len(scan_matrices) == 0:
            raise ValueError("scan_matrices must contain at least one matrix.")

        if len(scan_matrices) != len(stable_flags):
            raise ValueError("scan_matrices and stable_flags must have the same length.")

        self.scan_matrices = []
        for matrix in scan_matrices:
            self.scan_matrices.append(clone_scan_matrix(matrix))

        self.stable_flags = list(stable_flags)
        self.read_index = -1
        self.shutdown_called = False

    def read_scan_matrix(self):
        if self.read_index < len(self.scan_matrices) - 1:
            self.read_index += 1

        return clone_scan_matrix(self.scan_matrices[self.read_index])

    def is_current_scan_stable(self):
        if self.read_index < 0:
            return False

        return self.stable_flags[self.read_index]

    def shutdown(self):
        self.shutdown_called = True


class TestBoardMain(unittest.TestCase):
    def test_build_server_uri(self):
        runtime = BoardMain(
            board_id="bbg-boarda",
            server_host="bbg-server",
            server_port=8765
        )

        self.assertEqual(runtime.build_server_uri(), "ws://bbg-server:8765")

    def test_send_json_returns_false_when_no_websocket_exists(self):
        runtime = BoardMain(board_id="bbg-boarda")

        result = runtime.send_json('{"test": true}')

        self.assertFalse(result)

    def test_send_json_uses_live_websocket_when_present(self):
        runtime = BoardMain(board_id="bbg-boarda")
        fake_websocket = FakeWebSocket()

        runtime.set_websocket(fake_websocket)
        result = runtime.send_json('{"test": true}')

        self.assertTrue(result)
        self.assertEqual(fake_websocket.sent_messages, ['{"test": true}'])

    def test_scan_loop_sends_raw_scan_every_cycle(self):
        matrix_a = make_matrix_with_occupied_squares([(2, 1)])

        runtime = BoardMain(board_id="bbg-boarda")
        runtime.scanner = FakeScanner(
            scan_matrices=[matrix_a, matrix_a, matrix_a],
            stable_flags=[False, False, False]
        )
        runtime.stop_event = SequencedStopEvent([False, False, False, True])

        raw_scans_sent = []
        stable_scans_sent = []

        def fake_send_scan_snapshot(scan_matrix):
            raw_scans_sent.append(clone_scan_matrix(scan_matrix))
            return True

        def fake_send_stable_scan(scan_matrix):
            stable_scans_sent.append(clone_scan_matrix(scan_matrix))
            return True

        runtime.send_scan_snapshot = fake_send_scan_snapshot
        runtime.send_stable_scan = fake_send_stable_scan

        runtime.scan_loop()

        self.assertEqual(raw_scans_sent, [matrix_a, matrix_a, matrix_a])
        self.assertEqual(stable_scans_sent, [])

    def test_scan_loop_sends_stable_scan_only_once_for_same_stable_matrix(self):
        matrix_a = make_matrix_with_occupied_squares([(2, 1)])

        runtime = BoardMain(board_id="bbg-boarda")
        runtime.scanner = FakeScanner(
            scan_matrices=[matrix_a, matrix_a, matrix_a],
            stable_flags=[False, True, True]
        )
        runtime.stop_event = SequencedStopEvent([False, False, False, True])

        raw_scans_sent = []
        stable_scans_sent = []

        def fake_send_scan_snapshot(scan_matrix):
            raw_scans_sent.append(clone_scan_matrix(scan_matrix))
            return True

        def fake_send_stable_scan(scan_matrix):
            stable_scans_sent.append(clone_scan_matrix(scan_matrix))
            return True

        runtime.send_scan_snapshot = fake_send_scan_snapshot
        runtime.send_stable_scan = fake_send_stable_scan

        runtime.scan_loop()

        self.assertEqual(raw_scans_sent, [matrix_a, matrix_a, matrix_a])
        self.assertEqual(stable_scans_sent, [matrix_a])

    def test_scan_loop_sends_new_stable_scan_when_stable_matrix_changes(self):
        matrix_a = make_matrix_with_occupied_squares([(2, 1)])
        matrix_b = make_matrix_with_occupied_squares([(3, 2)])

        runtime = BoardMain(board_id="bbg-boarda")
        runtime.scanner = FakeScanner(
            scan_matrices=[matrix_a, matrix_a, matrix_b, matrix_b],
            stable_flags=[False, True, False, True]
        )
        runtime.stop_event = SequencedStopEvent([False, False, False, False, True])

        raw_scans_sent = []
        stable_scans_sent = []

        def fake_send_scan_snapshot(scan_matrix):
            raw_scans_sent.append(clone_scan_matrix(scan_matrix))
            return True

        def fake_send_stable_scan(scan_matrix):
            stable_scans_sent.append(clone_scan_matrix(scan_matrix))
            return True

        runtime.send_scan_snapshot = fake_send_scan_snapshot
        runtime.send_stable_scan = fake_send_stable_scan

        runtime.scan_loop()

        self.assertEqual(
            raw_scans_sent,
            [matrix_a, matrix_a, matrix_b, matrix_b]
        )
        self.assertEqual(
            stable_scans_sent,
            [matrix_a, matrix_b]
        )

    def test_scan_loop_resets_last_stable_when_scan_becomes_unstable(self):
        matrix_a = make_matrix_with_occupied_squares([(2, 1)])

        runtime = BoardMain(board_id="bbg-boarda")
        runtime.scanner = FakeScanner(
            scan_matrices=[matrix_a, matrix_a, matrix_a, matrix_a],
            stable_flags=[False, True, False, True]
        )
        runtime.stop_event = SequencedStopEvent([False, False, False, False, True])

        stable_scans_sent = []

        def fake_send_scan_snapshot(scan_matrix):
            return True

        def fake_send_stable_scan(scan_matrix):
            stable_scans_sent.append(clone_scan_matrix(scan_matrix))
            return True

        runtime.send_scan_snapshot = fake_send_scan_snapshot
        runtime.send_stable_scan = fake_send_stable_scan

        runtime.scan_loop()

        self.assertEqual(stable_scans_sent, [matrix_a, matrix_a])

    def test_scan_loop_exits_cleanly_when_scan_interval_is_non_positive(self):
        runtime = BoardMain(board_id="bbg-boarda")
        runtime.scan_interval = 0

        raw_scans_sent = []

        def fake_send_scan_snapshot(scan_matrix):
            raw_scans_sent.append(clone_scan_matrix(scan_matrix))
            return True

        runtime.send_scan_snapshot = fake_send_scan_snapshot

        runtime.scan_loop()

        self.assertEqual(raw_scans_sent, [])


if __name__ == "__main__":
    unittest.main()
