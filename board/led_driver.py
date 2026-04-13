from shared.constants import BOARD_SIZE, LED_OFF, LED_ON

try:
    import spidev
except ImportError:
    spidev = None


# MAX7219 register addresses
MAX7219_REG_NOOP = 0x00
MAX7219_REG_DIGIT0 = 0x01
MAX7219_REG_DIGIT1 = 0x02
MAX7219_REG_DIGIT2 = 0x03
MAX7219_REG_DIGIT3 = 0x04
MAX7219_REG_DIGIT4 = 0x05
MAX7219_REG_DIGIT5 = 0x06
MAX7219_REG_DIGIT6 = 0x07
MAX7219_REG_DIGIT7 = 0x08
MAX7219_REG_DECODE_MODE = 0x09
MAX7219_REG_INTENSITY = 0x0A
MAX7219_REG_SCAN_LIMIT = 0x0B
MAX7219_REG_SHUTDOWN = 0x0C
MAX7219_REG_DISPLAY_TEST = 0x0F

DEFAULT_SPI_BUS = 0
DEFAULT_SPI_DEVICE = 0
DEFAULT_SPI_SPEED_HZ = 1000000
DEFAULT_BRIGHTNESS = 3


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

    mock mode:
    - stores the current matrix only

    hardware mode:
    - sends the matrix to a MAX7219 over SPI

    Hardware mapping used here:
    - software row 0 (top) -> DIG7
    - software row 7 (bottom) -> DIG0
    - software col 0 (left) -> SEG A
    - software col 7 (right) -> SEG DP
    """

    def __init__(
        self,
        mode="mock",
        initial_led_matrix=None,
        spi_bus=DEFAULT_SPI_BUS,
        spi_device=DEFAULT_SPI_DEVICE,
        spi_speed_hz=DEFAULT_SPI_SPEED_HZ,
        brightness=DEFAULT_BRIGHTNESS
    ):
        self.mode = mode
        self.spi_bus = spi_bus
        self.spi_device = spi_device
        self.spi_speed_hz = int(spi_speed_hz)
        self.brightness = self._normalize_brightness(brightness)

        self.spi = None

        if initial_led_matrix is None:
            self.led_matrix = empty_led_matrix()
        else:
            self.led_matrix = normalize_led_matrix(initial_led_matrix)

        if self.mode == "mock":
            return

        if self.mode == "hardware":
            self._open_spi()
            self._initialize_max7219()
            self._write_led_matrix_to_hardware(self.led_matrix)
            return

        raise ValueError("Unsupported LED driver mode: " + str(self.mode))

    def _normalize_brightness(self, brightness):
        """Validate the MAX7219 intensity value."""
        brightness = int(brightness)

        if brightness < 0 or brightness > 15:
            raise ValueError("brightness must be between 0 and 15.")

        return brightness

    def _open_spi(self):
        """Open the SPI device used by the MAX7219."""
        if spidev is None:
            raise ImportError(
                "Hardware LED mode requires the 'spidev' package. "
                "Install it in your virtual environment first."
            )

        try:
            self.spi = spidev.SpiDev()
            self.spi.open(self.spi_bus, self.spi_device)
            self.spi.max_speed_hz = self.spi_speed_hz
            self.spi.mode = 0
        except Exception as exc:
            raise RuntimeError(
                "Could not open SPI for the MAX7219. "
                "Make sure SPI is enabled and the bus/device values are correct."
            ) from exc

    def _write_register(self, register_address, register_value):
        """Write one register/value pair to the MAX7219."""
        if self.spi is None:
            raise RuntimeError("SPI device is not open.")

        self.spi.xfer2([int(register_address), int(register_value)])

    def _initialize_max7219(self):
        """Configure the MAX7219 for an 8x8 raw LED matrix."""
        self._write_register(MAX7219_REG_DISPLAY_TEST, 0)
        self._write_register(MAX7219_REG_DECODE_MODE, 0)
        self._write_register(MAX7219_REG_SCAN_LIMIT, 7)
        self._write_register(MAX7219_REG_INTENSITY, self.brightness)
        self._write_register(MAX7219_REG_SHUTDOWN, 1)
        self._write_clear_to_hardware()

    def _write_clear_to_hardware(self):
        """Turn off all eight MAX7219 digit rows."""
        for register_address in range(MAX7219_REG_DIGIT0, MAX7219_REG_DIGIT7 + 1):
            self._write_register(register_address, 0)

    def _software_row_to_digit_register(self, row):
        """
        Convert a software row index into the correct MAX7219 digit register.

        software row 0 -> DIG7 register
        software row 7 -> DIG0 register
        """
        digit_index = (BOARD_SIZE - 1) - row
        return MAX7219_REG_DIGIT0 + digit_index

    def _build_row_byte(self, led_row):
        """
        Convert one 8-element LED row into the segment bit pattern.

        Bit 0 -> SEG A  -> software col 0
        Bit 7 -> SEG DP -> software col 7
        """
        row_value = 0

        for col in range(BOARD_SIZE):
            if led_row[col] == LED_ON:
                row_value = row_value | (1 << col)

        return row_value

    def _write_led_matrix_to_hardware(self, led_matrix):
        """Send the full 8x8 matrix to the MAX7219."""
        for row in range(BOARD_SIZE):
            register_address = self._software_row_to_digit_register(row)
            row_value = self._build_row_byte(led_matrix[row])
            self._write_register(register_address, row_value)

    def _apply_mock_led_matrix(self, led_matrix):
        """Store the LED matrix in mock mode."""
        return

    def _apply_hardware_led_matrix(self, led_matrix):
        """Send the LED matrix to the MAX7219."""
        self._write_led_matrix_to_hardware(led_matrix)

    def _apply_led_matrix(self, led_matrix):
        """Send one LED matrix to the active driver mode."""
        if self.mode == "mock":
            self._apply_mock_led_matrix(led_matrix)
            self.led_matrix = clone_led_matrix(led_matrix)
            return

        if self.mode == "hardware":
            self._apply_hardware_led_matrix(led_matrix)
            self.led_matrix = clone_led_matrix(led_matrix)
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

    def set_brightness(self, brightness):
        """Change MAX7219 brightness in hardware mode."""
        normalized_brightness = self._normalize_brightness(brightness)
        self.brightness = normalized_brightness

        if self.mode == "hardware":
            self._write_register(MAX7219_REG_INTENSITY, self.brightness)

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
        """
        if self.mode == "hardware" and self.spi is not None:
            try:
                self._write_clear_to_hardware()
                self._write_register(MAX7219_REG_SHUTDOWN, 0)
            finally:
                self.spi.close()
                self.spi = None

        self.led_matrix = empty_led_matrix()
