# BetterBoardGame
BetterBoardGame is a physical checkers system built using Raspberry Pi controllers, an 8×8 diode-isolated contact matrix, and MAX7219-controlled LEDs. The software translates physical piece positions into logical game states, validates moves, provides LED guidance, and supports both single-player games against a minimax AI and multiplayer games synchronized over WebSockets.

The hardware interfaces are separated from the game logic through mockable scanner and LED drivers, allowing most of the system to be tested without access to the physical boards.

flowchart TD
    P["Physical checker pieces"] --> S["TokenScanner"]
    S --> C["Board controller or single-player runtime"]
    C --> R["Game state and rules"]
    C --> L["LEDDriver"]
    L --> H["MAX7219 LED matrix"]
    A["Minimax AI"] --> C
    C <--> N["BoardClient"]
    N <--> W["WebSocket server"]
    W --> G["GameService"]
