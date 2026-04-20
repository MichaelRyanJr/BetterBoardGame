# server/event_protocol.py
#
# This file defines the message format used between the board and server.
#
# Important:
# - This file does NOT open sockets.
# - This file does NOT run a server.
# - This file ONLY builds and reads messages.
#
# Basically this file is the shared "language" used by the board and server.


from shared.constants import BOARD_SIZE, ErrorCode, EventType
from shared.serialization import (
    coordinate_from_dict,
    coordinate_to_dict,
    dict_to_json,
    game_state_from_dict,
    game_state_to_dict,
    json_to_dict,
    move_from_dict,
    move_to_dict,
)


def normalize_scan_matrix(scan_matrix):
    """
    Make sure the scan matrix is an 8x8 list of booleans.

    Why this exists:
    The board scan data should always have one value per square.
    This keeps the data format predictable before it gets sent.
    """

    if len(scan_matrix) != BOARD_SIZE:
        raise ValueError("scan_matrix must have exactly 8 rows.")

    normalized_matrix = []

    for row_index, row in enumerate(scan_matrix):
        if len(row) != BOARD_SIZE:
            raise ValueError(
                "scan_matrix row " + str(row_index) + " must have exactly 8 columns."
            )

        normalized_row = []

        for value in row:
            normalized_row.append(bool(value))

        normalized_matrix.append(normalized_row)

    return normalized_matrix


def build_message(event_type, payload, game_id=None, session_id=None, source=None):
    """
    Build the outer message format.

    Every message uses the same general structure:
    {
        "event_type": ...,
        "game_id": ...,
        "session_id": ...,
        "source": ...,
        "payload": ...
    }
    """

    return {
        "event_type": event_type.value,
        "game_id": game_id,
        "session_id": session_id,
        "source": source,
        "payload": payload
    }


def message_to_json(message):
    """
    Convert a Python dictionary message into JSON text.
    """
    return dict_to_json(message)


def message_from_json(json_text):
    """
    Convert JSON text back into a Python dictionary.
    """
    return json_to_dict(json_text)

def serialize_coordinate_list(squares):
    """
    Convert a list of Coordinate objects into plain dictionaries.
    """
    serialized_squares = []

    for square in squares:
        serialized_squares.append(coordinate_to_dict(square))

    return serialized_squares


def parse_coordinate_list(square_data_list):
    """
    Convert a list of coordinate dictionaries back into Coordinate objects.
    """
    squares = []

    for square_data in square_data_list:
        squares.append(coordinate_from_dict(square_data))

    return squares



def build_scan_snapshot_message(scan_matrix, game_id=None, session_id=None, source=None):
    """
    Build a raw scan snapshot message.

    This can be used when the board wants to report its current
    physical occupancy reading, even if that reading is not yet stable.
    """

    payload = {
        "scan_matrix": normalize_scan_matrix(scan_matrix)
    }

    return build_message(
        EventType.SCAN_SNAPSHOT,
        payload,
        game_id,
        session_id,
        source
    )


def parse_scan_snapshot_message(message):
    """
    Extract the scan matrix from a scan_snapshot message.
    """

    scan_matrix = message["payload"]["scan_matrix"]
    return normalize_scan_matrix(scan_matrix)


def build_stable_scan_message(scan_matrix, game_id=None, session_id=None, source=None):
    """
    Build a stable_scan message.

    This is used when the board believes the scan has settled and
    is no longer just a temporary change.
    """

    payload = {
        "scan_matrix": normalize_scan_matrix(scan_matrix)
    }

    return build_message(
        EventType.STABLE_SCAN,
        payload,
        game_id,
        session_id,
        source
    )


def parse_stable_scan_message(message):
    """
    Extract the scan matrix from a stable_scan message.
    """

    scan_matrix = message["payload"]["scan_matrix"]
    return normalize_scan_matrix(scan_matrix)


def build_candidate_move_message(move, game_id=None, session_id=None, source=None):
    """
    Build a message for a move the board THINKS the player made.

    This is called a candidate move because the board is not the final authority.
    The server still decides whether the move is actually legal.
    """

    payload = {
        "move": move_to_dict(move)
    }

    return build_message(
        EventType.CANDIDATE_MOVE,
        payload,
        game_id,
        session_id,
        source
    )


def parse_candidate_move_message(message):
    """
    Extract a Move object from a candidate_move message.
    """

    move_data = message["payload"]["move"]
    return move_from_dict(move_data)


def build_state_sync_message(state, game_id=None, session_id=None, source=None):
    """
    Build a message containing the server's official game state.

    This is the main message the server sends back so boards can update
    their local copy of the state.
    """

    payload = {
        "state": game_state_to_dict(state)
    }

    return build_message(
        EventType.STATE_SYNC,
        payload,
        game_id,
        session_id,
        source
    )


def parse_state_sync_message(message):
    """
    Extract a GameState object from a state_sync message.
    """

    state_data = message["payload"]["state"]
    return game_state_from_dict(state_data)


def build_error_message(message_text, error_code=None, game_id=None, session_id=None, source=None):
    """
    Build an error message.

    This is used when something goes wrong and the board or server
    needs to explain the problem.
    """

    if error_code is None:
        error_code_value = None
    else:
        error_code_value = error_code.value

    payload = {
        "message": message_text,
        "error_code": error_code_value
    }

    return build_message(
        EventType.ERROR,
        payload,
        game_id,
        session_id,
        source
    )


def parse_error_message(message):
    """
    Read the important information from an error message.

    Unlike the simpler version, this converts the error code string
    back into the real ErrorCode enum when possible.
    """

    payload = message["payload"]

    if payload.get("error_code") is None:
        error_code = None
    else:
        error_code = ErrorCode(payload["error_code"])

    return {
        "message": payload.get("message", ""),
        "error_code": error_code
    }


def build_heartbeat_message(game_id=None, session_id=None, source=None):
    """
    Build a heartbeat message.

    A heartbeat is just a small "I am still connected" message.
    """

    payload = {
        "status": "ok"
    }

    return build_message(
        EventType.HEARTBEAT,
        payload,
        game_id,
        session_id,
        source
    )


def parse_heartbeat_message(message):
    """
    Read a heartbeat message.
    """

    return message["payload"].get("status", "")


def build_desync_detected_message(message_text, game_id=None, session_id=None, source=None):
    """
    Build a desync_detected message.

    This is used when the board and server believe they are no longer
    looking at the same game situation.
    """

    payload = {
        "message": message_text
    }

    return build_message(
        EventType.DESYNC_DETECTED,
        payload,
        game_id,
        session_id,
        source
    )


def parse_desync_detected_message(message):
    """
    Read a desync_detected message.
    """

    return {
        "message": message["payload"].get("message", "")
    }


def build_piece_removed_required_message(
    squares_to_remove,
    replay_squares=None,
    game_id=None,
    session_id=None,
    source=None
):
    """
    Build a piece_removed_required message.

    This is useful after a capture when a physical piece still needs
    to be taken off the board by the player.
    """

    if replay_squares is None:
        replay_squares = []

    payload = {
        "squares_to_remove": serialize_coordinate_list(squares_to_remove),
        "replay_squares": serialize_coordinate_list(replay_squares)
    }

    return build_message(
        EventType.PIECE_REMOVED_REQUIRED,
        payload,
        game_id,
        session_id,
        source
    )


def parse_piece_removed_required_message(message):
    """
    Extract the list of squares that still need to be physically cleared.

    This older helper is preserved for compatibility with code that only
    cares about removal squares.
    """

    square_data_list = message["payload"].get("squares_to_remove", [])
    return parse_coordinate_list(square_data_list)


def parse_piece_removed_required_replay_squares_message(message):
    """
    Extract the replay path squares attached to a piece_removed_required message.
    """

    square_data_list = message["payload"].get("replay_squares", [])
    return parse_coordinate_list(square_data_list)


def parse_piece_removed_required_details_message(message):
    """
    Read the full piece_removed_required payload.
    """

    return {
        "squares_to_remove": parse_piece_removed_required_message(message),
        "replay_squares": parse_piece_removed_required_replay_squares_message(message)
    }


def build_illegal_state_detected_message(
    message_text,
    error_code=None,
    game_id=None,
    session_id=None,
    source=None
):
    """
    Build an illegal_state_detected message.

    This is meant for cases where the physical board state itself
    is not acceptable or cannot be interpreted correctly.
    """

    if error_code is None:
        error_code_value = None
    else:
        error_code_value = error_code.value

    payload = {
        "message": message_text,
        "error_code": error_code_value
    }

    return build_message(
        EventType.ILLEGAL_STATE_DETECTED,
        payload,
        game_id,
        session_id,
        source
    )


def parse_illegal_state_detected_message(message):
    """
    Read an illegal_state_detected message.
    """

    payload = message["payload"]

    if payload.get("error_code") is None:
        error_code = None
    else:
        error_code = ErrorCode(payload["error_code"])

    return {
        "message": payload.get("message", ""),
        "error_code": error_code
    }
