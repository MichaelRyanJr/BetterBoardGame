"""Board evaluation helpers for the single-player AI."""

from shared.constants import Player, Winner
from shared.move_validation import legal_moves_for_player

WIN_SCORE = 100000
MAN_VALUE = 100
KING_VALUE = 175
MOBILITY_VALUE = 5


def winner_for_player(player):
    if player == Player.RED:
        return Winner.RED
    return Winner.BLACK


def evaluate_material(state, ai_player):
    score = 0

    for row in state.board:
        for piece in row:
            if piece is None:
                continue

            if piece.is_king:
                piece_value = KING_VALUE
            else:
                piece_value = MAN_VALUE

            if piece.owner == ai_player:
                score += piece_value
            else:
                score -= piece_value

    return score


def evaluate_mobility(state, ai_player):
    temp_for_ai = state.clone()
    temp_for_ai.current_player = ai_player
    if ai_player != state.current_player:
        temp_for_ai.pending_multi_jump = None
    ai_moves = legal_moves_for_player(temp_for_ai, ai_player)

    opponent = ai_player.get_opponent()
    temp_for_opponent = state.clone()
    temp_for_opponent.current_player = opponent
    if opponent != state.current_player:
        temp_for_opponent.pending_multi_jump = None
    opponent_moves = legal_moves_for_player(temp_for_opponent, opponent)

    return (len(ai_moves) - len(opponent_moves)) * MOBILITY_VALUE


def evaluate_state(state, ai_player):
    """
    Return a numeric score from the AI player's perspective.

    Positive values are good for the AI player.
    Negative values are good for the opponent.
    """

    if state.winner is not None:
        if state.winner == winner_for_player(ai_player):
            return WIN_SCORE
        return -WIN_SCORE

    material_score = evaluate_material(state, ai_player)
    mobility_score = evaluate_mobility(state, ai_player)

    return material_score + mobility_score
