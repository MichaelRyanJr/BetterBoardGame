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

from shared.constants import ErrorCode, EventType, GameMode, Player
from shared.game_state import Coordinate, GameState, Move, Piece


def empty_scan_matrix():
    scan_matrix = []

    for _ in range(8):
        current_row = []

        for _ in range(8):
            current_row.append(False)

        scan_matrix.append(current_row)

    return scan_matrix


def build_scan_from_squares(occupied_squares):
    scan_matrix = empty_scan_matrix()

    for row, col in occupied_squares:
        scan_matrix[row][col] = True

    return scan_matrix


def build_scan_from_player_pieces(state, player):
    scan_matrix = empty_scan_matrix()

    for row in range(8):
        for col in range(8):
            square = Coordinate(row, col)
            piece = state.piece_at(square)

            if piece is None:
                continue

            if piece.owner != player:
                continue

            scan_matrix[row][col] = True

    return scan_matrix


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
        board = GameState.empty_board()
        board[2][1] = Piece(owner=Player.BLACK)

        state = GameState(
            board=board,
            current_player=Player.BLACK,
            mode=GameMode.MULTIPLAYER
        )

        service = GameService(initial_state=state)

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

    def test_capture_move_returns_state_sync_and_targeted_piece_removed_required(self):
        board = GameState.empty_board()
        board[2][1] = Piece(owner=Player.BLACK)
        board[3][2] = Piece(owner=Player.RED)
        board[5][0] = Piece(owner=Player.RED)

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

        self.assertIsNone(updated_state.winner)
        self.assertEqual(squares_to_remove, [Coordinate(3, 2)])
        self.assertEqual(response_messages[1]["target_board_id"], "bbg-boardb")
        self.assertEqual(
            service.pending_capture_removal_by_player[Player.RED],
            [Coordinate(3, 2)]
        )

    def test_multi_capture_accumulates_pending_piece_removals(self):
        board = GameState.empty_board()
        board[2][1] = Piece(owner=Player.BLACK)
        board[3][2] = Piece(owner=Player.RED)
        board[5][4] = Piece(owner=Player.RED)
        board[7][0] = Piece(owner=Player.RED)

        state = GameState(
            board=board,
            current_player=Player.BLACK,
            mode=GameMode.MULTIPLAYER
        )

        service = GameService(initial_state=state)

        first_move = Move(
            player=Player.BLACK,
            from_square=Coordinate(2, 1),
            to_square=Coordinate(4, 3)
        )

        first_message = build_candidate_move_message(
            move=first_move,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardA"
        )

        first_response_messages = service.handle_incoming_message(first_message)
        first_squares_to_remove = parse_piece_removed_required_message(
            first_response_messages[1]
        )

        self.assertEqual(first_squares_to_remove, [Coordinate(3, 2)])
        self.assertEqual(
            service.pending_capture_removal_by_player[Player.RED],
            [Coordinate(3, 2)]
        )

        second_move = Move(
            player=Player.BLACK,
            from_square=Coordinate(4, 3),
            to_square=Coordinate(6, 5)
        )

        second_message = build_candidate_move_message(
            move=second_move,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardA"
        )

        second_response_messages = service.handle_incoming_message(second_message)
        second_squares_to_remove = parse_piece_removed_required_message(
            second_response_messages[1]
        )

        self.assertEqual(
            second_squares_to_remove,
            [Coordinate(3, 2), Coordinate(5, 4)]
        )
        self.assertEqual(
            service.pending_capture_removal_by_player[Player.RED],
            [Coordinate(3, 2), Coordinate(5, 4)]
        )

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

    def test_scan_snapshot_is_stored_per_source(self):
        service = GameService()
        scan_matrix = build_scan_from_squares([(2, 1)])

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
        self.assertIn("bbg-boarda", service.last_scan_snapshot_by_source)
        self.assertTrue(service.last_scan_snapshot_by_source["bbg-boarda"][2][1])

    def test_stable_scan_matching_canonical_state_returns_no_messages(self):
        board = GameState.empty_board()
        board[2][1] = Piece(owner=Player.BLACK)
        board[5][0] = Piece(owner=Player.RED)

        state = GameState(
            board=board,
            current_player=Player.BLACK,
            mode=GameMode.MULTIPLAYER
        )

        service = GameService(initial_state=state)
        stable_scan = build_scan_from_player_pieces(service.state, Player.BLACK)

        message = build_stable_scan_message(
            scan_matrix=stable_scan,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardA"
        )

        response_messages = service.handle_incoming_message(message)

        self.assertEqual(response_messages, [])
        self.assertIsNotNone(service.last_stable_scan)
        self.assertIn("bbg-boarda", service.last_stable_scan_by_source)

    def test_stable_scan_can_infer_one_legal_move_and_return_state_sync(self):
        board = GameState.empty_board()
        board[2][1] = Piece(owner=Player.BLACK)
        board[5][0] = Piece(owner=Player.RED)

        state = GameState(
            board=board,
            current_player=Player.BLACK,
            mode=GameMode.MULTIPLAYER
        )

        service = GameService(initial_state=state)
        inferred_post_move_scan = build_scan_from_squares([(3, 0)])

        message = build_stable_scan_message(
            scan_matrix=inferred_post_move_scan,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardA"
        )

        response_messages = service.handle_incoming_message(message)

        self.assertEqual(len(response_messages), 1)
        self.assertEqual(response_messages[0]["event_type"], EventType.STATE_SYNC.value)

        updated_state = parse_state_sync_message(response_messages[0])
        self.assertIsNone(updated_state.piece_at(Coordinate(2, 1)))
        self.assertIsNotNone(updated_state.piece_at(Coordinate(3, 0)))
        self.assertEqual(updated_state.current_player, Player.RED)

    def test_stable_scan_from_unknown_source_returns_error_and_state_sync(self):
        service = GameService()
        stable_scan = build_scan_from_squares([(2, 1)])

        message = build_stable_scan_message(
            scan_matrix=stable_scan,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-UnknownBoard"
        )

        response_messages = service.handle_incoming_message(message)

        self.assertEqual(len(response_messages), 2)
        self.assertEqual(response_messages[0]["event_type"], EventType.ERROR.value)
        self.assertEqual(response_messages[1]["event_type"], EventType.STATE_SYNC.value)

        error_data = parse_error_message(response_messages[0])
        self.assertEqual(error_data["error_code"], ErrorCode.SERVER_REJECTED_STATE)

    def test_stable_scan_change_on_out_of_turn_board_returns_error_and_state_sync(self):
        board = GameState.empty_board()
        board[2][1] = Piece(owner=Player.BLACK)
        board[5][0] = Piece(owner=Player.RED)

        state = GameState(
            board=board,
            current_player=Player.BLACK,
            mode=GameMode.MULTIPLAYER
        )

        service = GameService(initial_state=state)
        changed_red_scan = build_scan_from_squares([(4, 1)])

        message = build_stable_scan_message(
            scan_matrix=changed_red_scan,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardB"
        )

        response_messages = service.handle_incoming_message(message)

        self.assertEqual(len(response_messages), 2)
        self.assertEqual(response_messages[0]["event_type"], EventType.ERROR.value)
        self.assertEqual(response_messages[1]["event_type"], EventType.STATE_SYNC.value)

        error_data = parse_error_message(response_messages[0])
        self.assertEqual(error_data["error_code"], ErrorCode.OUT_OF_TURN)

    def test_pending_capture_removal_returns_no_messages_until_square_is_cleared(self):
        board = GameState.empty_board()
        board[4][3] = Piece(owner=Player.BLACK)
        board[5][0] = Piece(owner=Player.RED)

        state = GameState(
            board=board,
            current_player=Player.RED,
            mode=GameMode.MULTIPLAYER
        )

        service = GameService(initial_state=state)
        service.pending_capture_removal_by_player[Player.RED] = [Coordinate(3, 2)]

        incomplete_scan = build_scan_from_squares([(3, 2), (5, 0)])

        message = build_stable_scan_message(
            scan_matrix=incomplete_scan,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardB"
        )

        response_messages = service.handle_incoming_message(message)

        self.assertEqual(response_messages, [])
        self.assertIn(Player.RED, service.pending_capture_removal_by_player)

    def test_pending_capture_removal_clears_when_required_square_becomes_empty(self):
        board = GameState.empty_board()
        board[4][3] = Piece(owner=Player.BLACK)
        board[5][0] = Piece(owner=Player.RED)

        state = GameState(
            board=board,
            current_player=Player.RED,
            mode=GameMode.MULTIPLAYER
        )

        service = GameService(initial_state=state)
        service.pending_capture_removal_by_player[Player.RED] = [Coordinate(3, 2)]

        complete_scan = build_scan_from_player_pieces(service.state, Player.RED)

        message = build_stable_scan_message(
            scan_matrix=complete_scan,
            game_id=service.state.game_id,
            session_id=service.state.session_id,
            source="BBG-BoardB"
        )

        response_messages = service.handle_incoming_message(message)

        self.assertEqual(response_messages, [])
        self.assertNotIn(Player.RED, service.pending_capture_removal_by_player)

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
