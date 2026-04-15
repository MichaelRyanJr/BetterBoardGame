import unittest

from server.server_main import ServerMain
from shared.constants import EventType, Player
from server.event_protocol import (
    build_candidate_move_message,
    build_piece_removed_required_message,
)
from shared.game_state import Coordinate, Move


class FakeWebSocket:
    def __init__(self, name):
        self.name = name
        self.sent_messages = []

    def send(self, message_text):
        self.sent_messages.append(message_text)


class TestServerMain(unittest.TestCase):
    def test_prepare_outgoing_message_removes_target_board_id(self):
        server = ServerMain()

        message = build_piece_removed_required_message(
            squares_to_remove=[Coordinate(3, 2)],
            game_id="game-123",
            session_id="session-123",
            source="server"
        )
        message["target_board_id"] = "bbg-boardb"

        prepared_message = server.prepare_outgoing_message(message)

        self.assertNotIn("target_board_id", prepared_message)
        self.assertIn("target_board_id", message)

    def test_register_connection_board_id_normalizes_board_name(self):
        server = ServerMain()
        websocket = FakeWebSocket("A")

        server.register_connection(websocket)
        server.register_connection_board_id(websocket, "BBG-BoardA")

        self.assertEqual(server.board_id_by_connection[websocket], "bbg-boarda")
        self.assertIs(server.connection_by_board_id["bbg-boarda"], websocket)

    def test_learn_sender_identity_from_message_registers_source(self):
        server = ServerMain()
        websocket = FakeWebSocket("A")

        move = Move(
            player=Player.BLACK,
            from_square=Coordinate(2, 1),
            to_square=Coordinate(3, 0)
        )

        message = build_candidate_move_message(
            move=move,
            game_id="game-123",
            session_id="session-123",
            source="BBG-BoardA"
        )
        json_text = server.game_service.encode_message(message)

        server.register_connection(websocket)
        server.learn_sender_identity_from_message(websocket, json_text)

        self.assertEqual(server.board_id_by_connection[websocket], "bbg-boarda")

    def test_split_response_messages_routes_targeted_piece_removed_message(self):
        server = ServerMain()

        direct_message = server.game_service.build_error_message("problem")
        broadcast_message = server.game_service.build_state_sync_message()

        routed_message = build_piece_removed_required_message(
            squares_to_remove=[Coordinate(3, 2)],
            game_id=server.game_service.state.game_id,
            session_id=server.game_service.state.session_id,
            source="server"
        )
        routed_message["target_board_id"] = "bbg-boardb"

        direct_messages, broadcast_messages, routed_messages = server.split_response_messages(
            [direct_message, broadcast_message, routed_message]
        )

        self.assertEqual(len(direct_messages), 1)
        self.assertEqual(direct_messages[0]["event_type"], EventType.ERROR.value)

        self.assertEqual(len(broadcast_messages), 1)
        self.assertEqual(broadcast_messages[0]["event_type"], EventType.STATE_SYNC.value)

        self.assertEqual(len(routed_messages), 1)
        self.assertEqual(
            routed_messages[0]["event_type"],
            EventType.PIECE_REMOVED_REQUIRED.value
        )

    def test_route_messages_sends_only_to_target_board(self):
        server = ServerMain()
        websocket_a = FakeWebSocket("A")
        websocket_b = FakeWebSocket("B")

        server.register_connection(websocket_a)
        server.register_connection(websocket_b)
        server.register_connection_board_id(websocket_a, "BBG-BoardA")
        server.register_connection_board_id(websocket_b, "BBG-BoardB")

        routed_message = build_piece_removed_required_message(
            squares_to_remove=[Coordinate(3, 2)],
            game_id=server.game_service.state.game_id,
            session_id=server.game_service.state.session_id,
            source="server"
        )
        routed_message["target_board_id"] = "bbg-boardb"

        server.route_messages([routed_message])

        self.assertEqual(len(websocket_a.sent_messages), 0)
        self.assertEqual(len(websocket_b.sent_messages), 1)
        self.assertNotIn("target_board_id", websocket_b.sent_messages[0])


if __name__ == "__main__":
    unittest.main()
