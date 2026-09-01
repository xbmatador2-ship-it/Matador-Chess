import json, os
from collections import Counter
import chess

PIECE_VALUES={chess.PAWN:1,chess.KNIGHT:3,chess.BISHOP:3,chess.ROOK:5,chess.QUEEN:9,chess.KING:100}

_DEFAULT={
 'concepts':[], 'tactics':[], 'strategy_graph':{}, 'safety_rules':{}
}

def load_knowledge(base_dir=None):
    base_dir = base_dir or os.path.join(os.path.dirname(__file__), 'knowledge')
    data=dict(_DEFAULT)
    for key,fn in [('concepts','concepts.json'),('tactics','tactics.json'),('strategy_graph','strategy_graph.json'),('safety_rules','safety_rules.json')]:
        p=os.path.join(base_dir,fn)
        if os.path.exists(p):
            with open(p,encoding='utf-8') as f: data[key]=json.load(f)
    data['concept_by_id']={x['id']:x for x in data['concepts'] if isinstance(x,dict) and 'id' in x}
    data['tactic_by_id']={x['id']:x for x in data['tactics'] if isinstance(x,dict) and 'id' in x}
    return data

def _piece_value(piece): return PIECE_VALUES.get(piece.piece_type,0)

def effective_defenders(board, color, square):
    return [s for s in board.attackers(color,square) if board.piece_at(s) is not None and board.piece_at(s).color==color]

def attacked_and_defended(board, square):
    p=board.piece_at(square)
    if p is None: return None
    return {
      'attacked': bool(board.attackers(not p.color,square)),
      'defenders': effective_defenders(board,p.color,square),
      'attackers': [s for s in board.attackers(not p.color,square)],
    }

def royal_fork(board_before, move):
    if not board_before.is_legal(move): return None
    mover=board_before.piece_at(move.from_square)
    after=board_before.copy(); after.push(move)
    if mover is None: return None
    opp=not mover.color
    king=after.king(opp)
    if king is None or not after.is_attacked_by(mover.color,king): return None
    queen_squares=[s for s,p in after.piece_map().items() if p.color==opp and p.piece_type==chess.QUEEN and after.is_attacked_by(mover.color,s)]
    if queen_squares:
        return {'id':'royal_fork','theme':'Fourchette royale','king':king,'queen':queen_squares[0],'attacker':move.to_square}
    return None

def fork(board_before, move):
    if not board_before.is_legal(move): return None
    mover=board_before.piece_at(move.from_square); after=board_before.copy(); after.push(move)
    if mover is None: return None
    targets=[]
    for s in after.attacks(move.to_square):
        p=after.piece_at(s)
        if p and p.color!=mover.color and p.piece_type!=chess.KING and _piece_value(p)>=3:
            targets.append((s,p))
    if len(targets)>=2: return {'id':'double_attack','theme':'Fourchette','targets':targets[:3],'attacker':move.to_square}
    return None

def discovered_attack(board_before, move):
    mover=board_before.piece_at(move.from_square)
    if mover is None or mover.piece_type not in (chess.PAWN,chess.KNIGHT): return None
    before=board_before.copy(); after=board_before.copy(); after.push(move)
    for s,p in after.piece_map().items():
        if p.color!=mover.color or p.piece_type not in (chess.BISHOP,chess.ROOK,chess.QUEEN): continue
        targets=[]
        for t in after.attacks(s):
            q=after.piece_at(t)
            if q and q.color!=p.color and q.piece_type!=chess.KING and _piece_value(q)>=3: targets.append(t)
        if targets and not before.is_attacked_by(mover.color,targets[0]):
            return {'id':'discovered_attack','theme':'Attaque découverte','attacker':s,'target':targets[0]}
    return None

def pin(board_before, move):
    if not board_before.is_legal(move): return None
    after=board_before.copy(); after.push(move); attacking=not after.turn; defending=after.turn; king=after.king(defending)
    if king is None: return None
    kf,kr=chess.square_file(king),chess.square_rank(king)
    for df,dr in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,-1),(1,-1),(-1,1)):
        f,r=kf+df,kr+dr; first=None; fs=None
        while 0<=f<8 and 0<=r<8:
            s=chess.square(f,r); p=after.piece_at(s)
            if p:
                if first is None: first,fs=p,s
                else:
                    if first.color==defending and p.color==attacking and p.piece_type in (chess.BISHOP,chess.ROOK,chess.QUEEN):
                        return {'id':'pin','theme':'Clouage absolu','square':fs,'king':king}
                    break
            f+=df;r+=dr
    return None

def new_piece_status(board_before, board_after, move, user_color):
    out=[]
    for s,p in board_after.piece_map().items():
        if p.color!=user_color or p.piece_type==chess.KING: continue
        a=attacked_and_defended(board_after,s)
        if not a['attacked']: continue
        before=attacked_and_defended(board_before,s)
        # only flag newly attacked or newly undefended pieces
        if before is None or not before['attacked'] or (before['defenders'] and not a['defenders']):
            out.append({'square':s,'piece':p,'attackers':a['attackers'],'defenders':a['defenders'],'status':'non_defendue' if not a['defenders'] else 'attaquee_et_defendue'})
    return out

def detect_tactics(board_before, move, user_color):
    findings=[]
    for fn in (royal_fork,fork,discovered_attack,pin):
        x=fn(board_before,move)
        if x: findings.append(x)
    after=board_before.copy(); after.push(move)
    # Concrete hanging piece: attacked + no defender, only if the position changed into that state.
    for x in new_piece_status(board_before,after,move,user_color):
        if x['status']=='non_defendue' and _piece_value(x['piece'])>=3:
            findings.append({'id':'hanging_piece','theme':'Pièce laissée en prise',**x})
    priority={'royal_fork':1,'skewer':2,'double_attack':3,'hanging_piece':4,'pin':5,'discovered_attack':6}
    findings.sort(key=lambda x:priority.get(x.get('id'),99))
    return findings

def choose_concept(findings, context=None, knowledge=None):
    if findings:
        return findings[0].get('id')
    context=context or {}
    # conservative strategic hints; no invented diagnosis
    if context.get('opponent_threat'): return 'prophylaxis'
    if context.get('weak_square'): return 'weak_square'
    if context.get('passed_pawn'): return 'passed_pawn'
    if context.get('initiative'): return 'initiative'
    return None

def pedagogical_layer(board_before, board_after, move, best_move_san, best_reply_san, loss, is_user_white, knowledge=None):
    user_color=chess.WHITE if is_user_white else chess.BLACK
    findings=detect_tactics(board_before,move,user_color)
    concept=choose_concept(findings, knowledge=knowledge)
    played=board_before.san(move)
    if findings:
        f=findings[0]
        if f['id']=='royal_fork':
            reason=f"{played} donne échec tout en attaquant la dame : c'est une fourchette royale."
        elif f['id']=='hanging_piece':
            reason=f"{played} laisse le {f['piece'].symbol()} en {chess.square_name(f['square'])} attaqué sans défense effective."
        else:
            reason=f"{played} crée le motif tactique « {f['theme']} »."
    elif loss<=0.20:
        reason=f"{played} est un bon choix : aucune perte significative n'est détectée et aucune faiblesse tactique claire n'est créée."
    else:
        reason=f"{played} est inférieur à {best_move_san}. Aucune justification tactique fiable n'a été isolée automatiquement; la différence doit donc être lue dans la conséquence positionnelle et la variante moteur."
    return {'played':played,'best_move':best_move_san,'best_reply':best_reply_san,'loss':loss,'findings':findings,'dominant_concept':concept,'human_reason':reason}
