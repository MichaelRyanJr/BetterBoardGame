from time import sleep

from shared.constants import BOARD_SIZE, is_dark_square

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None


# Columns are listed left to right on the real hardware.
DEFAULT_COLUMN_PINS = [26, 17, 27, 22, 5, 6, 13, 19]

# Rows are listed top to bottom on the real hardware.
DEFAULT_ROW_PINS = [17, 20, 16, 12, 25, 24, 23, 18]

DEFAULT_SETTLE_DELAY_SECONDS = 0.0005

# Confirmed inverse-remap values based on the working LED mapping.
DEFAULT_EVEN_ROW_SLOT_SHIFT = -1
DEFAULT_ODD_ROW_SLOT_SHIFT = 0
DEFAULT_COL_SHIFT_AFTER_CW = -1
DEFAULT_EVEN_COL_SLOT_SHIFT = 1
DEFAULT_ODD_COL_SLOT_SHIFT = 0

# Remaining scanner-only row correction observed after the existing
# inverse remap logic is applied. This is intentionally kept local to
# the scanner layer so the rest of the software can stay on the clean
# canonical 8x8 board coordinates.
DEFAULT_POST_REMAP_ROW_MAP = [6, 5, 4, 3, 2, 1, 0, 7]


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


def build_hardware_safe_scan_matrix(scan_matrix):
    """
    Force all non-playable squares to False.

    The physical checkers board only has valid piece locations on the
    dark squares, so light squares should never report occupied in the
    logical matrix that higher layers receive.
    """
    normalized_matrix = normalize_scan_matrix(scan_matrix)
    safe_matrix = empty_scan_matrix()

    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            if not is_dark_square(row, col):
                safe_matrix[row][col] = False
            else:
                safe_matrix[row][col] = normalized_matrix[row][col]

    return safe_matrix


def get_playable_cols_for_row(row):
    """
    Return the playable columns in left-to-right order for one row.
    """
    playable_cols = []

    for col in range(BOARD_SIZE):
        if is_dark_square(row, col):
            playable_cols.append(col)

    return playable_cols


def remap_playable_col_in_row(
    row,
    logical_col,
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Apply the confirmed pre-rotation row correction.

    This is the same correction used on the LED side before rotation:
    - even rows need a playable-slot shift of -1
    - odd rows need no shift
    """
    if not is_dark_square(row, logical_col):
        raise ValueError(
            "logical_col must be a playable dark-square column for this row."
        )

    playable_cols = get_playable_cols_for_row(row)
    logical_index = None

    for index in range(len(playable_cols)):
        if playable_cols[index] == logical_col:
            logical_index = index
            break

    if logical_index is None:
        raise ValueError(
            "Could not find logical_col in the row's playable columns."
        )

    if (row % 2) == 0:
        slot_shift = even_row_slot_shift
    else:
        slot_shift = odd_row_slot_shift

    mapped_index = (logical_index + slot_shift) % len(playable_cols)
    return playable_cols[mapped_index]


def inverse_remap_playable_col_in_row(
    row,
    baseline_col,
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Undo the confirmed pre-rotation row correction.

    This is used on the scanner side because the hardware gives us the
    physical/baseline column and we need to recover the logical column.
    """
    if not is_dark_square(row, baseline_col):
        raise ValueError(
            "baseline_col must be a playable dark-square column for this row."
        )

    playable_cols = get_playable_cols_for_row(row)
    baseline_index = None

    for index in range(len(playable_cols)):
        if playable_cols[index] == baseline_col:
            baseline_index = index
            break

    if baseline_index is None:
        raise ValueError(
            "Could not find baseline_col in the row's playable columns."
        )

    if (row % 2) == 0:
        slot_shift = even_row_slot_shift
    else:
        slot_shift = odd_row_slot_shift

    logical_index = (baseline_index - slot_shift) % len(playable_cols)
    return playable_cols[logical_index]


def map_logical_to_baseline_physical(
    logical_row,
    logical_col,
    even_row_slot_shift,
    odd_row_slot_shift
):
    """
    Apply only the known-good non-rotated mapping.

    This helper is kept here mainly so the inverse mapping logic is easy
    to understand alongside the LED side.
    """
    baseline_row = logical_row
    baseline_col = remap_playable_col_in_row(
        logical_row,
        logical_col,
        even_row_slot_shift,
        odd_row_slot_shift
    )

    return baseline_row, baseline_col


def rotate_coordinate_cw(row, col):
    """
    Apply a pure 90 degree clockwise rotation.

    (row, col) -> (col, 7 - row)
    """
    rotated_row = col
    rotated_col = BOARD_SIZE - 1 - row
    return rotated_row, rotated_col


def inverse_rotate_coordinate_cw(rotated_row, rotated_col):
    """
    Undo a 90 degree clockwise rotation.

    If CW rotation is:
        (row, col) -> (col, 7 - row)

    then the inverse is:
        (rotated_row, rotated_col) -> (7 - rotated_col, rotated_row)
    """
    original_row = BOARD_SIZE - 1 - rotated_col
    original_col = rotated_row
    return original_row, original_col


def get_playable_rows_for_col(col):
    """
    Return the playable rows in top-to-bottom order for one column.
    """
    playable_rows = []

    for row in range(BOARD_SIZE):
        if is_dark_square(row, col):
            playable_rows.append(row)

    return playable_rows


def remap_playable_row_in_col(
    col,
    logical_row,
    even_col_slot_shift,
    odd_col_slot_shift
):
    """
    Apply the confirmed post-rotation column correction.

    On the LED side this fixed the remaining wrap inside rotated columns:
    - even columns need a playable-slot shift of +1
    - odd columns need no shift
    """
    if not is_dark_square(logical_row, col):
        raise ValueError(
            "logical_row must be a playable dark-square row for this column."
        )

    playable_rows = get_playable_rows_for_col(col)
    logical_index = None

    for index in range(len(playable_rows)):
        if playable_rows[index] == logical_row:
            logical_index = index
            break

    if logical_index is None:
        raise ValueError(
            "Could not find logical_row in the column's playable rows."
        )

    if (col % 2) == 0:
        slot_shift = even_col_slot_shift
    else:
        slot_shift = odd_col_slot_shift

    mapped_index = (logical_index + slot_shift) % len(playable_rows)
    return playable_rows[mapped_index]


def inverse_remap_playable_row_in_col(
    col,
    physical_row,
    even_col_slot_shift,
    odd_col_slot_shift
):
    """
    Undo the confirmed post-rotation column correction.

    This is used on the scanner side because the hardware gives us the
    physical row inside the rotated column and we need to recover the
    rotated/logical row before undoing the rest of the mapping.
    """
    if not is_dark_square(physical_row, col):
        raise ValueError(
            "physical_row must be a playable dark-square row for this column."
        )

    playable_rows = get_playable_rows_for_col(col)
    physical_index = None

    for index in range(len(playable_rows)):
        if playable_rows[index] == physical_row:
            physical_index = index
            break

    if physical_index is None:
        raise ValueError(
            "Could not find physical_row in the column's playable rows."
        )

    if (col % 2) == 0:
        slot_shift = even_col_slot_shift
    else:
        slot_shift = odd_col_slot_shift

    logical_index = (physical_index - slot_shift) % len(playable_rows)
    return playable_rows[logical_index]


def map_logical_scan_coordinate_to_physical(
    logical_row,
    logical_col,
    col_shift_after_cw=DEFAULT_COL_SHIFT_AFTER_CW,
    even_row_slot_shift=DEFAULT_EVEN_ROW_SLOT_SHIFT,
    odd_row_slot_shift=DEFAULT_ODD_ROW_SLOT_SHIFT,
    even_col_slot_shift=DEFAULT_EVEN_COL_SLOT_SHIFT,
    odd_col_slot_shift=DEFAULT_ODD_COL_SLOT_SHIFT
):
    """
    Map one logical square onto the corrected physical board layout.

    This matches the now-confirmed LED mapping exactly.
    """
    if not is_dark_square(logical_row, logical_col):
        raise ValueError("Only playable dark squares can be mapped.")

    baseline_row, baseline_col = map_logical_to_baseline_physical(
        logical_row,
        logical_col,
        even_row_slot_shift,
        odd_row_slot_shift
    )

    rotated_row, rotated_col = rotate_coordinate_cw(
        baseline_row,
        baseline_col
    )

    physical_col = (rotated_col + col_shift_after_cw) % BOARD_SIZE
    physical_row = rotated_row

    physical_row = remap_playable_row_in_col(
        physical_col,
        physical_row,
        even_col_slot_shift,
        odd_col_slot_shift
    )

    return physical_row, physical_col


def map_physical_scan_coordinate_to_logical(
    physical_row,
    physical_col,
    col_shift_after_cw=DEFAULT_COL_SHIFT_AFTER_CW,
    even_row_slot_shift=DEFAULT_EVEN_ROW_SLOT_SHIFT,
    odd_row_slot_shift=DEFAULT_ODD_ROW_SLOT_SHIFT,
    even_col_slot_shift=DEFAULT_EVEN_COL_SLOT_SHIFT,
    odd_col_slot_shift=DEFAULT_ODD_COL_SLOT_SHIFT
):
    """
    Convert one physical hardware scan coordinate back into a logical
    board coordinate.

    This is the inverse of the confirmed LED mapping.

    Reverse order:
    1. undo the even-column row correction
    2. undo the global column shift
    3. undo the 90 degree clockwise rotation
    4. undo the pre-rotation row-order correction
    """
    if not is_dark_square(physical_row, physical_col):
        raise ValueError("Only playable dark squares can be mapped.")

    rotated_row = inverse_remap_playable_row_in_col(
        physical_col,
        physical_row,
        even_col_slot_shift,
        odd_col_slot_shift
    )

    rotated_col = (physical_col - col_shift_after_cw) % BOARD_SIZE

    baseline_row, baseline_col = inverse_rotate_coordinate_cw(
        rotated_row,
        rotated_col
    )

    logical_row = baseline_row
    logical_col = inverse_remap_playable_col_in_row(
        baseline_row,
        baseline_col,
        even_row_slot_shift,
        odd_row_slot_shift
    )

    logical_row = apply_post_remap_logical_row_correction(logical_row)

    if not is_dark_square(logical_row, logical_col):
        raise ValueError(
            "Final logical scan coordinate landed on a non-playable tile: "
            + "physical=(" + str(physical_row) + "," + str(physical_col) + ") "
            + "-> logical=(" + str(logical_row) + "," + str(logical_col) + ")"
        )

    return logical_row, logical_col


def apply_post_remap_logical_row_correction(logical_row, row_map=None):
    """
    Apply the final row-only correction after the normal inverse remap.

    The currently observed scanner output still returns logical rows as:
        0 -> 6
        1 -> 5
        2 -> 4
        3 -> 3
        4 -> 2
        5 -> 1
        6 -> 0
        7 -> 7

    Applying this correction after the existing remap logic fixes the
    row numbering without disturbing the already-correct column mapping.
    """
    if row_map is None:
        row_map = DEFAULT_POST_REMAP_ROW_MAP

    if len(row_map) != BOARD_SIZE:
        raise ValueError("row_map must contain exactly 8 row indices.")

    if logical_row < 0 or logical_row >= BOARD_SIZE:
        raise ValueError("logical_row must be between 0 and 7.")

    corrected_row = row_map[logical_row]

    if corrected_row < 0 or corrected_row >= BOARD_SIZE:
        raise ValueError("row_map contains an invalid row index.")

    return corrected_row


def build_logical_scan_matrix_from_physical(
    physical_scan_matrix,
    col_shift_after_cw=DEFAULT_COL_SHIFT_AFTER_CW,
    even_row_slot_shift=DEFAULT_EVEN_ROW_SLOT_SHIFT,
    odd_row_slot_shift=DEFAULT_ODD_ROW_SLOT_SHIFT,
    even_col_slot_shift=DEFAULT_EVEN_COL_SLOT_SHIFT,
    odd_col_slot_shift=DEFAULT_ODD_COL_SLOT_SHIFT
):
    """
    Convert a physical hardware scan matrix into the logical board matrix
    used by the rest of the software.
    """
    safe_physical_matrix = build_hardware_safe_scan_matrix(physical_scan_matrix)
    logical_matrix = empty_scan_matrix()

    for physical_row in range(BOARD_SIZE):
        for physical_col in range(BOARD_SIZE):
            if not is_dark_square(physical_row, physical_col):
                continue

            logical_row, logical_col = map_physical_scan_coordinate_to_logical(
                physical_row,
                physical_col,
                col_shift_after_cw,
                even_row_slot_shift,
                odd_row_slot_shift,
                even_col_slot_shift,
                odd_col_slot_shift
            )

            logical_matrix[logical_row][logical_col] = safe_physical_matrix[physical_row][physical_col]

    return logical_matrix


class TokenScanner:
    """
    Read board occupancy as an 8x8 boolean matrix.

    mock mode:
    - returns stored mock matrices
    - mock matrices are assumed to already be in logical board coordinates

    gpio mode:
    - scans the physical row/column matrix using Raspberry Pi GPIO
    - then remaps the physical hardware layout back into logical board
      coordinates before returning the result

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
        settle_delay_seconds=DEFAULT_SETTLE_DELAY_SECONDS,
        col_shift_after_cw=DEFAULT_COL_SHIFT_AFTER_CW,
        even_row_slot_shift=DEFAULT_EVEN_ROW_SLOT_SHIFT,
        odd_row_slot_shift=DEFAULT_ODD_ROW_SLOT_SHIFT,
        even_col_slot_shift=DEFAULT_EVEN_COL_SLOT_SHIFT,
        odd_col_slot_shift=DEFAULT_ODD_COL_SLOT_SHIFT
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

        self.col_shift_after_cw = int(col_shift_after_cw)
        self.even_row_slot_shift = int(even_row_slot_shift)
        self.odd_row_slot_shift = int(odd_row_slot_shift)
        self.even_col_slot_shift = int(even_col_slot_shift)
        self.odd_col_slot_shift = int(odd_col_slot_shift)

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

        Mock matrices are expected to already be in logical coordinates.
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

    def _read_gpio_physical_scan_matrix(self):
        """
        Scan the real physical row/column matrix and return the raw physical
        occupancy matrix in physical hardware coordinates.
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

    def _read_gpio_scan_matrix(self):
        """
        Read the real physical hardware matrix, then convert it into the
        logical board matrix expected by the rest of the software.
        """
        physical_scan_matrix = self._read_gpio_physical_scan_matrix()

        logical_scan_matrix = build_logical_scan_matrix_from_physical(
            physical_scan_matrix,
            self.col_shift_after_cw,
            self.even_row_slot_shift,
            self.odd_row_slot_shift,
            self.even_col_slot_shift,
            self.odd_col_slot_shift
        )

        return logical_scan_matrix

    def _read_raw_scan_matrix(self):
        """Read one raw scan from the active scanner mode."""
        if self.mode == "mock":
            return self._read_mock_scan_matrix()

        if self.mode == "gpio":
            return self._read_gpio_scan_matrix()

        raise ValueError("Unsupported scanner mode: " + str(self.mode))

    def read_scan_matrix(self):
        """
        Read one scan and return it as an 8x8 logical boolean matrix.

        This always returns the latest raw reading, even if the scan
        is not stable yet.
        """
        current_scan = self._read_raw_scan_matrix()
        current_scan = normalize_scan_matrix(current_scan)
        current_scan = build_hardware_safe_scan_matrix(current_scan)

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
        """Return the latest logical scan that was read, or None if no scan exists yet."""
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
