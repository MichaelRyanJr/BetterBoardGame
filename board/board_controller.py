from board.board_client import BoardClient, DEFAULT_SERVER_HOST, DEFAULT_SERVER_PORT
from board.led_driver import LEDDriver
from board.token_scanner import TokenScanner, clone_scan_matrix
from shared.constants import EventType


class BoardController:
    """
    Coordinate board-side scanning, protocol handling, and LED output.

    This class does not open sockets and does not run the WebSocket runtime.
    Instead, it sits between:
    - TokenScanner for board input
    - BoardClient for protocol/state handling
    - LEDDriver for board output

    For now this controller focuses on scan-based messages and LED updates.
    Candidate move inference can be added later without changing the overall
    board-side structure.
    """

    def __init__(
        self,
        board_id,
        local_player=None,
        game_id=None,
        session_id=None,
        server_host=DEFAULT_SERVER_HOST,
        server_port=DEFAULT_SERVER_PORT,
        scanner=None,
        led_driver=None,
        client=None,
        scanner_mode="mock",
        scanner_stable_reads_required=2,
        led_mode="mock"
    ):
        self.board_id = board_id
        self.local_player = local_player

        if client is None:
            self.client = BoardClient(
                board_id=board_id,
                game_id=game_id,
                session_id=session_id,
                server_host=server_host,
                server_port=server_port
            )
        else:
            self.client = client

        if scanner is None:
            self.scanner = TokenScanner(
                mode=scanner_mode,
                stable_reads_required=scanner_stable_reads_required
            )
        else:
            self.scanner = scanner

        if led_driver is None:
            self.led_driver = LEDDriver(mode=led_mode)
        else:
            self.led_driver = led_driver

        self.latest_raw_scan_matrix = None
        self.latest_stable_scan_matrix = None
        self.last_stable_scan_sent = None

        # These are squares where the server says a captured piece still needs
        # to be physically removed from the board.
        self.pending_capture_removal_squares = []

    def set_local_player(self, local_player):
        """Store which side this physical board belongs to."""
        self.local_player = local_player
        self.refresh_led_display()

    def set_game_context(self, game_id=None, session_id=None):
        """Update the board's current game/session context."""
        self.client.set_game_context(game_id=game_id, session_id=session_id)

    def has_state(self):
        """Return True if the board has a cached canonical state."""
        return self.client.has_state()

    def get_state(self):
        """Return a clone of the cached canonical state."""
        return self.client.get_state()

    def get_state_version(self):
        """Return the cached state's version number."""
        return self.client.get_state_version()

    def get_led_matrix(self):
        """Return the LED matrix currently being displayed."""
        return self.led_driver.get_led_matrix()

    def get_latest_scan_matrix(self):
        """Return the latest raw scan that was read."""
        if self.latest_raw_scan_matrix is None:
            return None

        return clone_scan_matrix(self.latest_raw_scan_matrix)

    def get_latest_stable_scan_matrix(self):
        """Return the latest stable scan that was observed."""
        if self.latest_stable_scan_matrix is None:
            return None

        return clone_scan_matrix(self.latest_stable_scan_matrix)

    def has_pending_capture_removal(self):
        """Return True if captured pieces still need physical removal."""
        return len(self.pending_capture_removal_squares) > 0

    def clear_pending_capture_removal(self):
        """Clear the current capture-removal requirement."""
        self.pending_capture_removal_squares = []
        self.refresh_led_display()

    def capture_removal_is_complete(self, scan_matrix):
        """
        Return True if all required captured-piece squares are now empty.

        scan_matrix[row][col] should be True when a physical piece is present
        and False when the square is empty.
        """
        if not self.has_pending_capture_removal():
            return False

        for square in self.pending_capture_removal_squares:
            if scan_matrix[square.row][square.col]:
                return False

        return True

    def refresh_led_display(self):
        """
        Update the LEDs based on the current board-side situation.

        Priority:
        1. show required captured-piece removals
        2. otherwise show the opponent's current positions
        3. otherwise clear the LEDs
        """
        if self.has_pending_capture_removal():
            self.led_driver.display_capture_removal_squares(
                self.pending_capture_removal_squares
            )
            return

        state = self.client.get_state()

        if state is None:
            self.led_driver.clear()
            return

        if self.local_player is None:
            self.led_driver.clear()
            return

        self.led_driver.display_opponent_pieces(state, self.local_player)

    def read_scan_matrix(self):
        """
        Read one raw scan from the scanner.

        This updates the controller's stored latest scan and also checks
        whether a pending capture-removal requirement has now been satisfied.
        """
        scan_matrix = self.scanner.read_scan_matrix()
        self.latest_raw_scan_matrix = clone_scan_matrix(scan_matrix)

        if self.scanner.is_current_scan_stable():
            self.latest_stable_scan_matrix = clone_scan_matrix(scan_matrix)

            if self.capture_removal_is_complete(scan_matrix):
                self.pending_capture_removal_squares = []
                self.refresh_led_display()

        return clone_scan_matrix(scan_matrix)

    def read_stable_scan_matrix(self):
        """
        Read one scan and return it only if it is stable right now.
        """
        scan_matrix = self.read_scan_matrix()

        if self.scanner.is_current_scan_stable():
            return clone_scan_matrix(scan_matrix)

        return None

    def poll_scanner_and_build_outgoing_messages(self):
        """
        Read the scanner and build any outbound protocol messages.

        Current behavior:
        - always build one scan_snapshot
        - build stable_scan only when a new stable matrix appears
        """
        scan_matrix = self.read_scan_matrix()

        outbound_messages = [
            self.client.build_scan_snapshot_message(scan_matrix)
        ]

        if self.scanner.is_current_scan_stable():
            should_send_stable = False

            if self.last_stable_scan_sent is None:
                should_send_stable = True
            elif scan_matrix != self.last_stable_scan_sent:
                should_send_stable = True

            if should_send_stable:
                stable_message = self.client.build_stable_scan_message(scan_matrix)
                outbound_messages.append(stable_message)

            self.last_stable_scan_sent = clone_scan_matrix(scan_matrix)
        else:
            self.last_stable_scan_sent = None

        return outbound_messages

    def poll_scanner_and_build_outgoing_json(self):
        """
        Read the scanner and return outbound messages as JSON strings.
        """
        outbound_messages = self.poll_scanner_and_build_outgoing_messages()
        outbound_json = []

        for message in outbound_messages:
            outbound_json.append(self.client.encode_message(message))

        return outbound_json

    def handle_incoming_message(self, message):
        """
        Process one incoming protocol message and update board output.
        """
        result = self.client.handle_incoming_message(message)
        event_type = result["event_type"]

        if event_type == EventType.STATE_SYNC:
            self.refresh_led_display()
            return result

        if event_type == EventType.PIECE_REMOVED_REQUIRED:
            squares_to_remove = result.get("squares_to_remove", [])
            self.pending_capture_removal_squares = list(squares_to_remove)
            self.refresh_led_display()
            return result

        return result

    def handle_incoming_json(self, json_text):
        """
        Process one incoming JSON protocol message and update board output.
        """
        message = self.client.decode_message(json_text)
        return self.handle_incoming_message(message)

    def shutdown(self):
        """Clean up controller-owned board resources."""
        self.scanner.shutdown()
        self.led_driver.shutdown()
