import unittest

from server.event_protocol import (
    build_candidate_move_message,
    build_desync_detected_message,
    build_heartbeat_message,
    build_illegal_state_detected_message,
    build_scan_snapshot_message,
    build_stable_scan_message,
    message_to_json,
    parse_error_message,
    parse_piece_removed_required_message,
    parse_state_sync_message,
)
from server.game_service import GameService

from shared.constants import ErrorCode, EventType, GameMode, Player, Winner
from shared.game_state import Coordinate, GameState, Move, Piece


class TestGameService(unittest.TestCase):
    def test_legal_candidate_move_returns_state_sync(self):
        service = GameService()

        move = Move(
            player=Player.BLACK,
            from_square=Coordinate(2, 1),
            to_square=Coordinate(3, 2)
        )

        message = build_candidate_move_message(
            move=move,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardA"
        )

        response_messages = service.handle_incoming_message(message)

        self.assertEqual(len(response_messages), 1)
        self.assertEqual(response_messages[0]["event_type"], EventType.STATE_SYNC.value)

        updated_state = parse_state_sync_message(response_messages[0])

        self.assertEqual(updated_state.version, 1)
        self.assertEqual(updated_state.move_number, 2)
        self.assertEqual(updated_state.current_player, Player.RED)
        self.assertIsNone(updated_state.piece_at(Coordinate(2, 1)))
        self.assertIsNotNone(updated_state.piece_at(Coordinate(3, 2)))

    def test_illegal_candidate_move_returns_error(self):
        service = GameService()
    
        # This is illegal because it is a horizontal move.
        move = Move(
            player=Player.BLACK,
            from_square=Coordinate(2, 1),
            to_square=Coordinate(2, 3)
        )
    
        message = build_candidate_move_message(
            move=move,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardA"
        )
    
        response_messages = service.handle_incoming_message(message)
    
        self.assertEqual(len(response_messages), 1)
        self.assertEqual(response_messages[0]["event_type"], EventType.ERROR.value)
    
        error_data = parse_error_message(response_messages[0])
    
        self.assertEqual(error_data["error_code"], ErrorCode.ILLEGAL_DIRECTION)
        self.assertEqual(error_data["message"], "Moves must be diagonal.")
        
    def test_capture_move_returns_state_sync_and_piece_removed_required(self):
        board = GameState.empty_board()
        board[2][1] = Piece(owner=Player.BLACK)
        board[3][2] = Piece(owner=Player.RED)

        state = GameState(
            board=board,
            current_player=Player.BLACK,
            mode=GameMode.MULTIPLAYER
        )

        service = GameService(initial_state=state)

        move = Move(
            player=Player.BLACK,
            from_square=Coordinate(2, 1),
            to_square=Coordinate(4, 3)
        )

        message = build_candidate_move_message(
            move=move,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardA"
        )

        response_messages = service.handle_incoming_message(message)

        self.assertEqual(len(response_messages), 2)
        self.assertEqual(response_messages[0]["event_type"], EventType.STATE_SYNC.value)
        self.assertEqual(
            response_messages[1]["event_type"],
            EventType.PIECE_REMOVED_REQUIRED.value
        )

        updated_state = parse_state_sync_message(response_messages[0])
        squares_to_remove = parse_piece_removed_required_message(response_messages[1])

        self.assertEqual(updated_state.winner, Winner.BLACK)
        self.assertEqual(squares_to_remove, [Coordinate(3, 2)])

    def test_heartbeat_returns_heartbeat_message(self):
        service = GameService()

        message = build_heartbeat_message(
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardA"
        )

        response_messages = service.handle_incoming_message(message)

        self.assertEqual(len(response_messages), 1)
        self.assertEqual(response_messages[0]["event_type"], EventType.HEARTBEAT.value)
        self.assertEqual(response_messages[0]["payload"]["status"], "ok")

    def test_scan_snapshot_is_stored(self):
        service = GameService()

        scan_matrix = []
        for row in range(8):
            current_row = []
            for col in range(8):
                current_row.append(False)
            scan_matrix.append(current_row)

        scan_matrix[2][1] = True

        message = build_scan_snapshot_message(
            scan_matrix=scan_matrix,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardA"
        )

        response_messages = service.handle_incoming_message(message)

        self.assertEqual(response_messages, [])
        self.assertIsNotNone(service.last_scan_snapshot)
        self.assertTrue(service.last_scan_snapshot[2][1])

    def test_stable_scan_is_stored(self):
        service = GameService()

        scan_matrix = []
        for row in range(8):
            current_row = []
            for col in range(8):
                current_row.append(False)
            scan_matrix.append(current_row)

        scan_matrix[5][0] = True

        message = build_stable_scan_message(
            scan_matrix=scan_matrix,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardA"
        )

        response_messages = service.handle_incoming_message(message)

        self.assertEqual(response_messages, [])
        self.assertIsNotNone(service.last_stable_scan)
        self.assertTrue(service.last_stable_scan[5][0])

    def test_desync_detected_returns_state_sync(self):
        service = GameService()

        message = build_desync_detected_message(
            message_text="State versions do not match.",
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardA"
        )

        response_messages = service.handle_incoming_message(message)

        self.assertEqual(len(response_messages), 1)
        self.assertEqual(response_messages[0]["event_type"], EventType.STATE_SYNC.value)
        self.assertEqual(
            service.last_desync_report["message"],
            "State versions do not match."
        )

    def test_illegal_state_detected_returns_state_sync(self):
        service = GameService()

        message = build_illegal_state_detected_message(
            message_text="Board state is ambiguous.",
            error_code=ErrorCode.AMBIGUOUS_SCAN,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardA"
        )

        response_messages = service.handle_incoming_message(message)

        self.assertEqual(len(response_messages), 1)
        self.assertEqual(response_messages[0]["event_type"], EventType.STATE_SYNC.value)
        self.assertEqual(
            service.last_illegal_state_report["message"],
            "Board state is ambiguous."
        )
        self.assertEqual(
            service.last_illegal_state_report["error_code"],
            ErrorCode.AMBIGUOUS_SCAN
        )

    def test_candidate_move_rejected_in_single_player_mode(self):
        state = GameState.initial(mode=GameMode.SINGLE_PLAYER)
        service = GameService(initial_state=state)

        move = Move(
            player=Player.BLACK,
            from_square=Coordinate(2, 1),
            to_square=Coordinate(3, 2)
        )

        message = build_candidate_move_message(
            move=move,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardA"
        )

        response_messages = service.handle_incoming_message(message)

        self.assertEqual(len(response_messages), 1)
        self.assertEqual(response_messages[0]["event_type"], EventType.ERROR.value)

        error_data = parse_error_message(response_messages[0])

        self.assertEqual(error_data["error_code"], ErrorCode.INVALID_MODE)
        self.assertEqual(error_data["message"], "Server is not in multiplayer mode.")

    def test_handle_incoming_json_and_encode_responses(self):
        service = GameService()

        move = Move(
            player=Player.BLACK,
            from_square=Coordinate(2, 1),
            to_square=Coordinate(3, 2)
        )

        message = build_candidate_move_message(
            move=move,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardA"
        )

        json_text = message_to_json(message)
        response_json_list = service.handle_incoming_json_and_encode_responses(json_text)

        self.assertEqual(len(response_json_list), 1)
        self.assertTrue(isinstance(response_json_list[0], str))


if __name__ == "__main__":
    unittest.main()
