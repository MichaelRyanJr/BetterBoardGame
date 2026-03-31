import unittest

from board.board_client import BoardClient
from shared.constants import ErrorCode, Player
from shared.game_state import Coordinate, GameState, Move
from server.event_protocol import (
    build_candidate_move_message,
    build_desync_detected_message,
    build_error_message,
    build_heartbeat_message,
    build_illegal_state_detected_message,
    build_piece_removed_required_message,
    build_scan_snapshot_message,
    build_stable_scan_message,
    build_state_sync_message,
    message_from_json,
    message_to_json,
    parse_candidate_move_message,
    parse_error_message,
    parse_heartbeat_message,
    parse_illegal_state_detected_message,
    parse_piece_removed_required_message,
    parse_scan_snapshot_message,
    parse_stable_scan_message,
    parse_state_sync_message,
)


class TestEventProtocol(unittest.TestCase):
    def test_candidate_move_round_trip(self):
        move = Move(
            player=Player.BLACK,
            from_square=Coordinate(2, 1),
            to_square=Coordinate(3, 2)
        )

        message = build_candidate_move_message(
            move=move,
            game_id="game-123",
            session_id="session-123",
            source="BBG-BoardA"
        )

        parsed_move = parse_candidate_move_message(message)

        self.assertEqual(message["event_type"], "candidate_move")
        self.assertEqual(parsed_move.player, Player.BLACK)
        self.assertEqual(parsed_move.from_square, Coordinate(2, 1))
        self.assertEqual(parsed_move.to_square, Coordinate(3, 2))

    def test_state_sync_round_trip(self):
        state = GameState.initial()
        state.version = 4
        state.move_number = 3

        message = build_state_sync_message(
            state=state,
            game_id=state.game_id,
            session_id=state.session_id,
            source="server"
        )

        parsed_state = parse_state_sync_message(message)

        self.assertEqual(message["event_type"], "state_sync")
        self.assertEqual(parsed_state.version, 4)
        self.assertEqual(parsed_state.move_number, 3)
        self.assertEqual(parsed_state.current_player, state.current_player)

    def test_error_message_round_trip(self):
        message = build_error_message(
            message_text="Illegal move.",
            error_code=ErrorCode.MUST_CAPTURE,
            game_id="game-123",
            session_id="session-123",
            source="server"
        )

        parsed_error = parse_error_message(message)

        self.assertEqual(message["event_type"], "error")
        self.assertEqual(parsed_error["message"], "Illegal move.")
        self.assertEqual(parsed_error["error_code"], ErrorCode.MUST_CAPTURE)

    def test_heartbeat_round_trip(self):
        message = build_heartbeat_message(
            game_id="game-123",
            session_id="session-123",
            source="BBG-BoardA"
        )

        parsed_status = parse_heartbeat_message(message)

        self.assertEqual(message["event_type"], "heartbeat")
        self.assertEqual(parsed_status, "ok")

    def test_scan_snapshot_round_trip(self):
        scan_matrix = []
        for row in range(8):
            current_row = []
            for col in range(8):
                current_row.append(False)
            scan_matrix.append(current_row)

        scan_matrix[2][1] = True
        scan_matrix[3][2] = True

        message = build_scan_snapshot_message(
            scan_matrix=scan_matrix,
            game_id="game-123",
            session_id="session-123",
            source="BBG-BoardA"
        )

        parsed_scan = parse_scan_snapshot_message(message)

        self.assertEqual(message["event_type"], "scan_snapshot")
        self.assertTrue(parsed_scan[2][1])
        self.assertTrue(parsed_scan[3][2])
        self.assertFalse(parsed_scan[0][0])

    def test_stable_scan_round_trip(self):
        scan_matrix = []
        for row in range(8):
            current_row = []
            for col in range(8):
                current_row.append(False)
            scan_matrix.append(current_row)

        scan_matrix[5][0] = True

        message = build_stable_scan_message(
            scan_matrix=scan_matrix,
            game_id="game-123",
            session_id="session-123",
            source="BBG-BoardA"
        )

        parsed_scan = parse_stable_scan_message(message)

        self.assertEqual(message["event_type"], "stable_scan")
        self.assertTrue(parsed_scan[5][0])
        self.assertFalse(parsed_scan[5][1])

    def test_piece_removed_required_round_trip(self):
        squares_to_remove = [
            Coordinate(4, 3),
            Coordinate(2, 5)
        ]

        message = build_piece_removed_required_message(
            squares_to_remove=squares_to_remove,
            game_id="game-123",
            session_id="session-123",
            source="server"
        )

        parsed_squares = parse_piece_removed_required_message(message)

        self.assertEqual(message["event_type"], "piece_removed_required")
        self.assertEqual(parsed_squares, squares_to_remove)

    def test_illegal_state_detected_round_trip(self):
        message = build_illegal_state_detected_message(
            message_text="Board state is ambiguous.",
            error_code=ErrorCode.AMBIGUOUS_SCAN,
            game_id="game-123",
            session_id="session-123",
            source="server"
        )

        parsed_data = parse_illegal_state_detected_message(message)

        self.assertEqual(message["event_type"], "illegal_state_detected")
        self.assertEqual(parsed_data["message"], "Board state is ambiguous.")
        self.assertEqual(parsed_data["error_code"], ErrorCode.AMBIGUOUS_SCAN)

    def test_json_round_trip(self):
        move = Move(
            player=Player.BLACK,
            from_square=Coordinate(2, 1),
            to_square=Coordinate(3, 2)
        )

        message = build_candidate_move_message(
            move=move,
            game_id="game-123",
            session_id="session-123",
            source="BBG-BoardA"
        )

        json_text = message_to_json(message)
        rebuilt_message = message_from_json(json_text)

        self.assertEqual(rebuilt_message["event_type"], "candidate_move")
        self.assertEqual(rebuilt_message["game_id"], "game-123")
        self.assertEqual(rebuilt_message["source"], "BBG-BoardA")


class TestBoardClient(unittest.TestCase):
    def test_build_candidate_move_json(self):
        client = BoardClient(
            board_id="BBG-BoardA",
            game_id="game-123",
            session_id="session-123"
        )

        move = Move(
            player=Player.BLACK,
            from_square=Coordinate(2, 1),
            to_square=Coordinate(3, 2)
        )

        json_text = client.build_candidate_move_json(move)
        message = message_from_json(json_text)

        self.assertEqual(message["event_type"], "candidate_move")
        self.assertEqual(message["game_id"], "game-123")
        self.assertEqual(message["session_id"], "session-123")
        self.assertEqual(message["source"], "BBG-BoardA")

    def test_handle_state_sync_updates_cache(self):
        client = BoardClient(board_id="BBG-BoardA")

        state = GameState.initial()
        state.game_id = "game-123"
        state.session_id = "session-123"
        state.version = 5

        message = build_state_sync_message(
            state=state,
            game_id=state.game_id,
            session_id=state.session_id,
            source="server"
        )

        result = client.handle_incoming_message(message)

        self.assertTrue(result["state_updated"])
        self.assertTrue(client.has_state())
        self.assertEqual(client.get_state_version(), 5)
        self.assertEqual(client.game_id, "game-123")
        self.assertEqual(client.session_id, "session-123")

    def test_handle_stale_state_sync_is_ignored(self):
        client = BoardClient(board_id="BBG-BoardA")

        newer_state = GameState.initial()
        newer_state.game_id = "game-123"
        newer_state.session_id = "session-123"
        newer_state.version = 5

        older_state = GameState.initial()
        older_state.game_id = "game-123"
        older_state.session_id = "session-123"
        older_state.version = 3

        first_message = build_state_sync_message(
            state=newer_state,
            game_id=newer_state.game_id,
            session_id=newer_state.session_id,
            source="server"
        )

        second_message = build_state_sync_message(
            state=older_state,
            game_id=older_state.game_id,
            session_id=older_state.session_id,
            source="server"
        )

        first_result = client.handle_incoming_message(first_message)
        second_result = client.handle_incoming_message(second_message)

        self.assertTrue(first_result["state_updated"])
        self.assertFalse(second_result["state_updated"])
        self.assertEqual(client.get_state_version(), 5)

    def test_handle_error_message_stores_last_error(self):
        client = BoardClient(board_id="BBG-BoardA")

        message = build_error_message(
            message_text="Must capture.",
            error_code=ErrorCode.MUST_CAPTURE,
            game_id="game-123",
            session_id="session-123",
            source="server"
        )

        result = client.handle_incoming_message(message)

        self.assertEqual(result["event_type"].value, "error")
        self.assertEqual(client.last_error["message"], "Must capture.")
        self.assertEqual(client.last_error["error_code"], ErrorCode.MUST_CAPTURE)

    def test_handle_heartbeat_message_stores_status(self):
        client = BoardClient(board_id="BBG-BoardA")

        message = build_heartbeat_message(
            game_id="game-123",
            session_id="session-123",
            source="server"
        )

        result = client.handle_incoming_message(message)

        self.assertEqual(result["event_type"].value, "heartbeat")
        self.assertEqual(client.last_heartbeat_status, "ok")

    def test_handle_desync_detected_message_stores_payload(self):
        client = BoardClient(board_id="BBG-BoardA")

        message = build_desync_detected_message(
            message_text="State versions do not match.",
            game_id="game-123",
            session_id="session-123",
            source="server"
        )

        result = client.handle_incoming_message(message)

        self.assertEqual(result["event_type"].value, "desync_detected")
        self.assertEqual(client.last_desync["message"], "State versions do not match.")

    def test_handle_piece_removed_required_message_stores_squares(self):
        client = BoardClient(board_id="BBG-BoardA")

        squares_to_remove = [
            Coordinate(4, 3)
        ]

        message = build_piece_removed_required_message(
            squares_to_remove=squares_to_remove,
            game_id="game-123",
            session_id="session-123",
            source="server"
        )

        result = client.handle_incoming_message(message)

        self.assertEqual(result["event_type"].value, "piece_removed_required")
        self.assertEqual(client.last_piece_removed_required, squares_to_remove)

    def test_handle_illegal_state_detected_message_stores_payload(self):
        client = BoardClient(board_id="BBG-BoardA")

        message = build_illegal_state_detected_message(
            message_text="Ambiguous board scan.",
            error_code=ErrorCode.AMBIGUOUS_SCAN,
            game_id="game-123",
            session_id="session-123",
            source="server"
        )

        result = client.handle_incoming_message(message)

        self.assertEqual(result["event_type"].value, "illegal_state_detected")
        self.assertEqual(client.last_illegal_state["message"], "Ambiguous board scan.")
        self.assertEqual(
            client.last_illegal_state["error_code"],
            ErrorCode.AMBIGUOUS_SCAN
        )

    def test_handle_incoming_json(self):
        client = BoardClient(board_id="BBG-BoardA")

        state = GameState.initial()
        state.game_id = "game-123"
        state.session_id = "session-123"
        state.version = 2

        message = build_state_sync_message(
            state=state,
            game_id=state.game_id,
            session_id=state.session_id,
            source="server"
        )

        json_text = message_to_json(message)
        result = client.handle_incoming_json(json_text)

        self.assertTrue(result["state_updated"])
        self.assertEqual(client.get_state_version(), 2)


if __name__ == "__main__":
    unittest.main()
