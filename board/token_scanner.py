from time import sleep

from shared.constants import BOARD_SIZE, is_dark_square

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


# Columns are listed left to right.
DEFAULT_COLUMN_PINS = [4, 17, 27, 22, 5, 6, 13, 19]

# Rows are listed top to bottom.
DEFAULT_ROW_PINS = [21, 20, 16, 12, 25, 24, 23, 18]

DEFAULT_SETTLE_DELAY_SECONDS = 0.0005


def empty_scan_matrix():
    """Build a blank 8x8 occupancy matrix."""
    matrix = []

    for _ in range(BOARD_SIZE):
        row = []
        for _ in range(BOARD_SIZE):
            row.append(False)
        matrix.append(row)

    return matrix


def clone_scan_matrix(scan_matrix):
    """Return a deep copy of an 8x8 occupancy matrix."""
    cloned_matrix = []

    for row in scan_matrix:
        cloned_row = []

        for value in row:
            cloned_row.append(bool(value))

        cloned_matrix.append(cloned_row)

    return cloned_matrix


def normalize_scan_matrix(scan_matrix):
    """Validate and normalize scan data into an 8x8 boolean matrix."""
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


class TokenScanner:
    """
    Read board occupancy as an 8x8 boolean matrix.

    mock mode:
    - returns stored mock matrices

    gpio mode:
    - scans the physical row/column matrix using Raspberry Pi GPIO

    Hardware assumptions:
    - columns use the board's external pull-up resistors
    - one row is selected at a time by driving it LOW
    - all non-selected rows are left as inputs
    - a LOW column reading on the selected row means a piece is present
    - only playable dark squares can ever report occupied
    """

    def __init__(
        self,
        mode="gpio",
        stable_reads_required=2,
        initial_scan_matrix=None,
        row_pins=None,
        column_pins=None,
        settle_delay_seconds=DEFAULT_SETTLE_DELAY_SECONDS
    ):
        if stable_reads_required < 1:
            raise ValueError("stable_reads_required must be at least 1.")

        self.mode = mode
        self.stable_reads_required = stable_reads_required
        self.settle_delay_seconds = float(settle_delay_seconds)

        if self.settle_delay_seconds < 0:
            raise ValueError("settle_delay_seconds cannot be negative.")

        if row_pins is None:
            self.row_pins = list(DEFAULT_ROW_PINS)
        else:
            self.row_pins = list(row_pins)

        if column_pins is None:
            self.column_pins = list(DEFAULT_COLUMN_PINS)
        else:
            self.column_pins = list(column_pins)

        self._validate_pin_lists()

        if initial_scan_matrix is None:
            self.mock_scan_matrix = empty_scan_matrix()
        else:
            self.mock_scan_matrix = normalize_scan_matrix(initial_scan_matrix)

        self.mock_scan_sequence = []
        self.mock_sequence_index = 0

        self.latest_scan_matrix = None
        self.previous_scan_matrix = None
        self.matching_scan_count = 0

        self.gpio_initialized = False

        if self.mode == "gpio":
            self._setup_gpio()

    def _validate_pin_lists(self):
        """Make sure the row and column pin lists are usable."""
        if len(self.row_pins) != BOARD_SIZE:
            raise ValueError("row_pins must contain exactly 8 GPIO pins.")

        if len(self.column_pins) != BOARD_SIZE:
            raise ValueError("column_pins must contain exactly 8 GPIO pins.")

        for pin in self.row_pins:
            if not isinstance(pin, int):
                raise ValueError("Each row pin must be an integer GPIO number.")

        for pin in self.column_pins:
            if not isinstance(pin, int):
                raise ValueError("Each column pin must be an integer GPIO number.")

        used_pins = set()

        for pin in self.row_pins:
            if pin in used_pins:
                raise ValueError("row_pins contains a duplicate GPIO pin.")
            used_pins.add(pin)

        for pin in self.column_pins:
            if pin in used_pins:
                raise ValueError(
                    "A GPIO pin cannot appear in both row_pins and column_pins."
                )
            used_pins.add(pin)

    def set_mock_scan_matrix(self, scan_matrix):
        """Replace the current mock scan matrix."""
        self.mock_scan_matrix = normalize_scan_matrix(scan_matrix)
        self.mock_scan_sequence = []
        self.mock_sequence_index = 0

    def set_mock_scan_sequence(self, scan_sequence):
        """
        Load a sequence of mock scans.

        Each call to read_scan_matrix() will move forward in the sequence.
        Once the end is reached, the last matrix will keep repeating.
        """
        if len(scan_sequence) == 0:
            raise ValueError("scan_sequence must contain at least one matrix.")

        normalized_sequence = []

        for scan_matrix in scan_sequence:
            normalized_sequence.append(normalize_scan_matrix(scan_matrix))

        self.mock_scan_sequence = normalized_sequence
        self.mock_sequence_index = 0

    def reset_stability_tracking(self):
        """Forget the previous scan history used for stability checks."""
        self.previous_scan_matrix = None
        self.matching_scan_count = 0

    def _read_mock_scan_matrix(self):
        """Return the next mock scan matrix."""
        if len(self.mock_scan_sequence) > 0:
            current_matrix = self.mock_scan_sequence[self.mock_sequence_index]

            if self.mock_sequence_index < len(self.mock_scan_sequence) - 1:
                self.mock_sequence_index += 1

            return clone_scan_matrix(current_matrix)

        return clone_scan_matrix(self.mock_scan_matrix)

    def _setup_gpio(self):
        """Initialize Raspberry Pi GPIO for matrix scanning."""
        if GPIO is None:
            raise ImportError(
                "GPIO scanner mode requires the 'RPi.GPIO' package. "
                "Run this on a Raspberry Pi with RPi.GPIO installed."
            )

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        self._configure_columns()
        self._set_all_rows_inactive()

        self.gpio_initialized = True

    def _configure_columns(self):
        """
        Configure all column pins as inputs.

        The board already provides external pull-ups, so internal pulls are off.
        """
        for pin in self.column_pins:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_OFF)

    def _set_all_rows_inactive(self):
        """
        Put every row pin into input mode.

        This leaves non-selected rows effectively high-impedance while
        another row is being scanned.
        """
        for pin in self.row_pins:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_OFF)

    def _select_row(self, row_index):
        """Activate exactly one row by driving it LOW."""
        selected_pin = self.row_pins[row_index]

        self._set_all_rows_inactive()
        GPIO.setup(selected_pin, GPIO.OUT)
        GPIO.output(selected_pin, GPIO.LOW)

    def _read_gpio_scan_matrix(self):
        """
        Scan the physical row/column matrix and return an 8x8 occupancy matrix.
        """
        if not self.gpio_initialized:
            self._setup_gpio()

        scan_matrix = empty_scan_matrix()
        self._configure_columns()

        for row_index in range(BOARD_SIZE):
            self._select_row(row_index)

            if self.settle_delay_seconds > 0:
                sleep(self.settle_delay_seconds)

            for col_index in range(BOARD_SIZE):
                if not is_dark_square(row_index, col_index):
                    scan_matrix[row_index][col_index] = False
                    continue

                column_pin = self.column_pins[col_index]
                column_value = GPIO.input(column_pin)

                # External pull-up keeps idle columns HIGH.
                # A closed path on the selected row pulls the column LOW.
                scan_matrix[row_index][col_index] = (column_value == GPIO.LOW)

        self._set_all_rows_inactive()

        return scan_matrix

    def _read_raw_scan_matrix(self):
        """Read one raw scan from the active scanner mode."""
        if self.mode == "mock":
            return self._read_mock_scan_matrix()

        if self.mode == "gpio":
            return self._read_gpio_scan_matrix()

        raise ValueError("Unsupported scanner mode: " + str(self.mode))

    def read_scan_matrix(self):
        """
        Read one scan and return it as an 8x8 boolean matrix.

        This always returns the latest raw reading, even if the scan
        is not stable yet.
        """
        current_scan = self._read_raw_scan_matrix()
        current_scan = normalize_scan_matrix(current_scan)

        if self.previous_scan_matrix is None:
            self.matching_scan_count = 1
        elif current_scan == self.previous_scan_matrix:
            self.matching_scan_count += 1
        else:
            self.matching_scan_count = 1

        self.previous_scan_matrix = clone_scan_matrix(current_scan)
        self.latest_scan_matrix = clone_scan_matrix(current_scan)

        return clone_scan_matrix(current_scan)

    def read_stable_scan_matrix(self):
        """
        Read one scan and return it only if it is stable.

        A scan is considered stable when the same matrix has been read
        stable_reads_required times in a row.
        """
        current_scan = self.read_scan_matrix()

        if self.matching_scan_count >= self.stable_reads_required:
            return clone_scan_matrix(current_scan)

        return None

    def get_latest_scan_matrix(self):
        """Return the latest scan that was read, or None if no scan exists yet."""
        if self.latest_scan_matrix is None:
            return None

        return clone_scan_matrix(self.latest_scan_matrix)

    def get_matching_scan_count(self):
        """Return how many times the current scan has repeated in a row."""
        return self.matching_scan_count

    def is_current_scan_stable(self):
        """Return True if the latest scan is currently considered stable."""
        if self.latest_scan_matrix is None:
            return False

        return self.matching_scan_count >= self.stable_reads_required

    def shutdown(self):
        """
        Clean up scanner resources.
        """
        if self.mode == "gpio" and GPIO is not None and self.gpio_initialized:
            try:
                self._set_all_rows_inactive()

                for pin in self.row_pins:
                    GPIO.cleanup(pin)

                for pin in self.column_pins:
                    GPIO.cleanup(pin)
            finally:
                self.gpio_initialized = False
