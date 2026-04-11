from shared.constants import BOARD_SIZE, LED_OFF, LED_ON


def empty_led_matrix():
    """Build a blank 8x8 LED matrix."""
    matrix = []

    for _ in range(BOARD_SIZE):
        row = []
        for _ in range(BOARD_SIZE):
            row.append(LED_OFF)
        matrix.append(row)

    return matrix


def clone_led_matrix(led_matrix):
    """Return a deep copy of an 8x8 LED matrix."""
    cloned_matrix = []

    for row in led_matrix:
        cloned_row = []

        for value in row:
            cloned_row.append(int(value))

        cloned_matrix.append(cloned_row)

    return cloned_matrix


def normalize_led_value(value):
    """Convert a value into a valid LED state."""
    if bool(value):
        return LED_ON

    return LED_OFF


def normalize_led_matrix(led_matrix):
    """Validate and normalize LED data into an 8x8 matrix."""
    if len(led_matrix) != BOARD_SIZE:
        raise ValueError("led_matrix must have exactly 8 rows.")

    normalized_matrix = []

    for row_index, row in enumerate(led_matrix):
        if len(row) != BOARD_SIZE:
            raise ValueError(
                "led_matrix row " + str(row_index) + " must have exactly 8 columns."
            )

        normalized_row = []

        for value in row:
            normalized_row.append(normalize_led_value(value))

        normalized_matrix.append(normalized_row)

    return normalized_matrix


def build_piece_led_matrix_for_player(state, player):
    """
    Build an LED matrix that lights every square occupied by one player.
    """
    matrix = empty_led_matrix()

    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            piece = state.board[row][col]

            if piece is None:
                continue

            if piece.owner != player:
                continue

            matrix[row][col] = LED_ON

    return matrix


def build_opponent_led_matrix(state, local_player):
    """
    Build an LED matrix showing the opponent's pieces.

    This matches the project direction where each board lights the
    opponent's positions rather than the local player's own pieces.
    """
    opponent = local_player.get_opponent()
    return build_piece_led_matrix_for_player(state, opponent)


class LEDDriver:
    """
    Control the 8x8 board LED output.

    For now this runs in mock mode and simply stores the current LED matrix.
    Later, the real MAX7219/SPI implementation can replace the internal
    output logic without changing the rest of the board-side API.
    """

    def __init__(self, mode="mock", initial_led_matrix=None):
        self.mode = mode

        if initial_led_matrix is None:
            self.led_matrix = empty_led_matrix()
        else:
            self.led_matrix = normalize_led_matrix(initial_led_matrix)

    def _apply_mock_led_matrix(self, led_matrix):
        """Store the LED matrix in mock mode."""
        self.led_matrix = clone_led_matrix(led_matrix)

    def _apply_hardware_led_matrix(self, led_matrix):
        """
        Placeholder for the future real hardware implementation.

        Later, the MAX7219/SPI output code can go here.
        """
        raise NotImplementedError(
            "Hardware LED output has not been implemented yet."
        )

    def _apply_led_matrix(self, led_matrix):
        """Send one LED matrix to the active driver mode."""
        if self.mode == "mock":
            self._apply_mock_led_matrix(led_matrix)
            return

        if self.mode == "hardware":
            self._apply_hardware_led_matrix(led_matrix)
            return

        raise ValueError("Unsupported LED driver mode: " + str(self.mode))

    def set_led_matrix(self, led_matrix):
        """
        Replace the full 8x8 LED matrix.
        """
        normalized_matrix = normalize_led_matrix(led_matrix)
        self._apply_led_matrix(normalized_matrix)

    def get_led_matrix(self):
        """Return a copy of the currently displayed LED matrix."""
        return clone_led_matrix(self.led_matrix)

    def clear(self):
        """Turn off every LED."""
        self.set_led_matrix(empty_led_matrix())

    def set_square(self, row, col, state):
        """Set one LED square on or off."""
        if row < 0 or row >= BOARD_SIZE:
            raise ValueError("row is outside the board.")

        if col < 0 or col >= BOARD_SIZE:
            raise ValueError("col is outside the board.")

        updated_matrix = self.get_led_matrix()
        updated_matrix[row][col] = normalize_led_value(state)
        self.set_led_matrix(updated_matrix)

    def set_square_from_coordinate(self, square, state):
        """Set one LED square on or off using a Coordinate object."""
        self.set_square(square.row, square.col, state)

    def set_squares(self, squares, state=LED_ON):
        """Set multiple LED squares to the same state."""
        updated_matrix = self.get_led_matrix()
        normalized_state = normalize_led_value(state)

        for square in squares:
            if square.row < 0 or square.row >= BOARD_SIZE:
                raise ValueError("square row is outside the board.")

            if square.col < 0 or square.col >= BOARD_SIZE:
                raise ValueError("square col is outside the board.")

            updated_matrix[square.row][square.col] = normalized_state

        self.set_led_matrix(updated_matrix)

    def display_player_pieces(self, state, player):
        """Light every square occupied by the given player."""
        led_matrix = build_piece_led_matrix_for_player(state, player)
        self.set_led_matrix(led_matrix)

    def display_opponent_pieces(self, state, local_player):
        """Light every square occupied by the local player's opponent."""
        led_matrix = build_opponent_led_matrix(state, local_player)
        self.set_led_matrix(led_matrix)

    def display_capture_removal_squares(self, squares_to_remove):
        """
        Light squares where captured physical pieces still need removal.

        For now this simply lights the listed squares.
        Later, the real hardware version could blink these or use a
        different display pattern if needed.
        """
        led_matrix = empty_led_matrix()

        for square in squares_to_remove:
            if square.row < 0 or square.row >= BOARD_SIZE:
                raise ValueError("square row is outside the board.")

            if square.col < 0 or square.col >= BOARD_SIZE:
                raise ValueError("square col is outside the board.")

            led_matrix[square.row][square.col] = LED_ON

        self.set_led_matrix(led_matrix)

    def shutdown(self):
        """
        Clean up LED driver resources.

        This does not need to do anything in mock mode, but keeping the
        method now makes later hardware cleanup easier.
        """
        return
