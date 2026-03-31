import json

from shared.constants import ErrorCode, Player, Winner
from shared.game_state import AppliedMove, Coordinate, GameState, Move, Piece
from shared.move_validation import ValidationResult


def dict_to_json(data):
    """ Convert a Python dictionary into a JSON string """
    return json.dumps(data)


def json_to_dict(json_text):
    """ Convert a JSON string into a Python dictionary """
    return json.loads(json_text)


def coordinate_to_dict(coordinate):
    """ Convert a Coordinate object into a dictionary """
    return coordinate.to_dict()


def coordinate_from_dict(data):
    """ Build a Coordinate object from dictionary data """
    return Coordinate.from_dict(data)


def coordinate_to_json(coordinate):
    """ Convert a Coordinate object directly into a JSON string """
    return dict_to_json(coordinate_to_dict(coordinate))


def coordinate_from_json(json_text):
    """ Build a Coordinate object directly from a JSON string """
    data = json_to_dict(json_text)
    return coordinate_from_dict(data)


def piece_to_dict(piece):
    """ Convert a Piece object into a dictionary """
    return piece.to_dict()


def piece_from_dict(data):
    """ Build a Piece object from dictionary data """
    return Piece.from_dict(data)


def piece_to_json(piece):
    """ Convert a Piece object directly into a JSON string """
    return dict_to_json(piece_to_dict(piece))


def piece_from_json(json_text):
    """ Build a Piece object directly from a JSON string """
    data = json_to_dict(json_text)
    return piece_from_dict(data)


def move_to_dict(move):
    """ Convert a Move object into a dictionary """
    return move.to_dict()


def move_from_dict(data):
    """ Build a Move object from dictionary data """
    return Move.from_dict(data)


def move_to_json(move):
    """ Convert a Move object directly into a JSON string """
    return dict_to_json(move_to_dict(move))


def move_from_json(json_text):
    """Build a Move object directly from a JSON string """
    data = json_to_dict(json_text)
    return move_from_dict(data)


def game_state_to_dict(state):
    """Convert a GameState object into a dictionary """
    return state.to_dict()


def game_state_from_dict(data):
    """ Build a GameState object from dictionary data """
    return GameState.from_dict(data)


def game_state_to_json(state):
    """ Convert a GameState object directly into a JSON string """
    return dict_to_json(game_state_to_dict(state))


def game_state_from_json(json_text):
    """ Build a GameState object directly from a JSON string """
    data = json_to_dict(json_text)
    return game_state_from_dict(data)


def applied_move_to_dict(applied_move):
    """
    Convert an AppliedMove object into a dictionary.

    AppliedMove does not currently have its own to_dict() function,
    so serialization is defined here instead.
    """

    captured_list = []
    for square in applied_move.captured_squares:
        captured_list.append(square.to_dict())

    if applied_move.next_player is None:
        next_player_value = None
    else:
        next_player_value = applied_move.next_player.value

    if applied_move.winner is None:
        winner_value = None
    else:
        winner_value = applied_move.winner.value

    if applied_move.continuation_square is None:
        continuation_value = None
    else:
        continuation_value = applied_move.continuation_square.to_dict()

    return {
        "move": applied_move.move.to_dict(),
        "captured_squares": captured_list,
        "promoted": applied_move.promoted,
        "next_player": next_player_value,
        "winner": winner_value,
        "requires_continuation": applied_move.requires_continuation,
        "continuation_square": continuation_value
    }


def applied_move_from_dict(data):
    """Build an AppliedMove object from dictionary data """

    captured_list = []
    for square in data.get("captured_squares", []):
        captured_list.append(Coordinate.from_dict(square))

    if data.get("next_player") is None:
        next_player_value = None
    else:
        next_player_value = Player(data["next_player"])

    if data.get("winner") is None:
        winner_value = None
    else:
        winner_value = Winner(data["winner"])

    if data.get("continuation_square") is None:
        continuation_value = None
    else:
        continuation_value = Coordinate.from_dict(data["continuation_square"])

    return AppliedMove(
        move=Move.from_dict(data["move"]),
        captured_squares=captured_list,
        promoted=bool(data.get("promoted", False)),
        next_player=next_player_value,
        winner=winner_value,
        requires_continuation=bool(data.get("requires_continuation", False)),
        continuation_square=continuation_value
    )


def applied_move_to_json(applied_move):
    """ Convert an AppliedMove object directly into a JSON string """
    return dict_to_json(applied_move_to_dict(applied_move))


def applied_move_from_json(json_text):
    """ Build an AppliedMove object directly from a JSON string """
    data = json_to_dict(json_text)
    return applied_move_from_dict(data)


def validation_result_to_dict(result):
    """
    Convert a ValidationResult object into a dictionary.

    ValidationResult also does not have its own to_dict() function,
    so serialization is defined here instead.
    """

    captured_list = []
    for square in result.captured_squares:
        captured_list.append(square.to_dict())

    if result.error_code is None:
        error_code_value = None
    else:
        error_code_value = result.error_code.value

    if result.continuation_square is None:
        continuation_value = None
    else:
        continuation_value = result.continuation_square.to_dict()

    return {
        "is_legal": result.is_legal,
        "error_code": error_code_value,
        "message": result.message,
        "captured_squares": captured_list,
        "promoted": result.promoted,
        "continuation_square": continuation_value
    }


def validation_result_from_dict(data):
    """ Build a ValidationResult object from dictionary data """

    captured_list = []
    for square in data.get("captured_squares", []):
        captured_list.append(Coordinate.from_dict(square))

    if data.get("error_code") is None:
        error_code_value = None
    else:
        error_code_value = ErrorCode(data["error_code"])

    if data.get("continuation_square") is None:
        continuation_value = None
    else:
        continuation_value = Coordinate.from_dict(data["continuation_square"])

    return ValidationResult(
        is_legal=bool(data["is_legal"]),
        error_code=error_code_value,
        message=data.get("message", ""),
        captured_squares=captured_list,
        promoted=bool(data.get("promoted", False)),
        continuation_square=continuation_value
    )


def validation_result_to_json(result):
    """Convert a ValidationResult object directly into a JSON string """
    return dict_to_json(validation_result_to_dict(result))


def validation_result_from_json(json_text):
    """Build a ValidationResult object directly from a JSON string """
    data = json_to_dict(json_text)
    return validation_result_from_dict(data)
