import io, sys
import chess
import chess.pgn
sys.path.insert(0, '/mnt/data')
import coach_brain

PGN='''1. e3 c6 2. b3 d5 3. Bb2 Bf5 4. Qf3 e6 5. g3 Nf6 6. Bh3 Be4 7. Qe2 Bxh1 8. f3 Be7 9. Bxf6 Bxf6 10. c3 O-O 11. Qf1 Nd7 12. Ne2 Bxf3 13. Qxf3 Ne5 14. Qf2 Nd3+ 15. Kf1 Nxf2 16. Kxf2 c5 17. Na3 b6 18. Rd1 Bh4 19. gxh4 Qxh4+ 20. Kg2 Rac8 21. Nb5 c4 22. Nxa7 Ra8 23. Nb5 Rxa2 24. bxc4 dxc4 25. Nbd4 Qh5 26. Kf1 e5 27. Nf3 Qxh3+ 28. Kf2 e4 29. Nfg1 Qxh2+ 30. Kf1 Rd8 31. d4 cxd3 32. Nc1 Qf2# 0-1'''

game=chess.pgn.read_game(io.StringIO('[Event "test"]\n\n'+PGN))
board=game.board()
for ply, move in enumerate(game.mainline_moves(), 1):
    if ply == 28:
        result=coach_brain.pedagogical_layer(board, board.copy(), move, 'Nd3+', 'Nxf2', 0.0, False, coach_brain.load_knowledge('/mnt/data/coach_1500_master_kb_v0_3'))
        assert result['dominant_concept']=='royal_fork', result
        assert result['findings'][0]['theme']=='Fourchette royale', result
        print('PLY 28:', result['human_reason'])
        break
    board.push(move)
else:
    raise AssertionError('ply 28 not reached')

# Regression: bishop f5 is attacked by g4 but defended by e6.
b=chess.Board('rnbqkbnr/pp2pppp/2pp4/5b2/6P1/8/PPPPPP1P/RNBQKBNR b KQkq - 0 1')
status=coach_brain.attacked_and_defended(b, chess.F5)
assert status['attacked'] and status['defenders'], status
print('F5: attacked + defended => NOT hanging')
print('ALL COACH-BRAIN TESTS PASSED')
