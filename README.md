# BetterBoardGame
A physical checkers board capable of online multiplayer and single player vs an AI (minimax)


To run multiplayer mode:

  1st: on the server open the terminal and run
  
    cd ~/BetterBoardGame
    python3 -m server.server_main

  2nd: on both boards run the following commands
  
    cd ~/BetterBoardGame
    python3 -m board.main


To run singleplayer:

  simply run the following commands with the wanted difficulty:

For Easy:

    cd ~/BetterBoardGame
    python3 -m board.run_single_player --difficulty easy

For Medium:

    cd ~/BetterBoardGame
    python3 -m board.run_single_player --difficulty medium

For Hard:

    cd ~/BetterBoardGame
    python3 -m board.run_single_player --difficulty hard
