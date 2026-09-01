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
    for key,fn in [('concepts','concepts.json'),('tactics','tactics.json'),('strategy_graph','strategy_graph.json'),('safety_rules','safety_rules.json'),('opening_knowledge','opening_knowledge.json')]:
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

def opening_intent_for_position(opening_name, board, is_user_white, knowledge=None):
    """Retourne un contexte d'ouverture exploitable pedagogiquement.

    L'ouverture donne un cadre (structure, developpement, plans), mais ne
    remplace jamais la verification concrete de la position par Stockfish.
    """
    name = (opening_name or "").strip()
    if not name:
        return {}
    entries = (knowledge or {}).get('opening_knowledge', {}).get('openings', [])
    low = name.lower().replace("’", "'")
    chosen = None
    for entry in entries:
        for key in entry.get('keys', []):
            if key.lower().replace("’", "'") in low:
                chosen = entry
                break
        if chosen:
            break
    if not chosen:
        return {'name': name, 'relevant': False}
    return {
        'name': chosen.get('name', name),
        'relevant': True,
        'summary': chosen.get('summary', ''),
        'plans': chosen.get('plans', []),
        'watch': chosen.get('watch', []),
    }

def _ray_between(board, a, b):
    af, ar = chess.square_file(a), chess.square_rank(a)
    bf, br = chess.square_file(b), chess.square_rank(b)
    df, dr = bf-af, br-ar
    if df == 0 and dr != 0: step=(0, 1 if dr>0 else -1)
    elif dr == 0 and df != 0: step=(1 if df>0 else -1, 0)
    elif abs(df)==abs(dr): step=(1 if df>0 else -1, 1 if dr>0 else -1)
    else: return []
    out=[]; f,r=af+step[0], ar+step[1]
    while (f,r)!=(bf,br):
        out.append(chess.square(f,r)); f+=step[0]; r+=step[1]
    return out

def skewer(board_before, move):
    """Detecte une enfilade creee par le coup: cible de grande valeur devant une autre."""
    if not board_before.is_legal(move): return None
    mover=board_before.piece_at(move.from_square)
    if mover is None or mover.piece_type not in (chess.BISHOP,chess.ROOK,chess.QUEEN): return None
    after=board_before.copy(); after.push(move)
    enemy=not mover.color
    origin=move.to_square
    directions=((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,-1),(1,-1),(-1,1))
    for df,dr in directions:
        f,r=chess.square_file(origin)+df,chess.square_rank(origin)+dr
        first=None; first_sq=None
        while 0<=f<8 and 0<=r<8:
            sq=chess.square(f,r); p=after.piece_at(sq)
            if p:
                if first is None:
                    if p.color==enemy: first,first_sq=p,sq
                    else: break
                else:
                    if p.color==enemy and p.piece_type not in (chess.PAWN,chess.KING):
                        # Une cible de tete doit etre au moins aussi precieuse que celle derriere.
                        if _piece_value(first) >= _piece_value(p) and after.is_attacked_by(mover.color, first_sq):
                            return {'id':'skewer','theme':'Enfilade','front':(first_sq,first),'back':(sq,p),'attacker':origin}
                    break
            f+=df; r+=dr
    return None

def trapped_piece(board_after, user_color):
    """Signale une piece mineure avec tres peu de sorties utiles."""
    candidates=[]
    for sq,p in board_after.piece_map().items():
        if p.color!=user_color or p.piece_type not in (chess.BISHOP,chess.KNIGHT): continue
        legal=[m for m in board_after.legal_moves if m.from_square==sq]
        # Pour un diagnostic robuste, on cherche surtout une piece qui n'a qu'une sortie
        # ou aucune sortie et dont les cases sont occupées/contrôlées par l'adversaire.
        useful=0
        for m in legal:
            dest=board_after.piece_at(m.to_square)
            if dest is None or dest.color!=user_color:
                if not board_after.is_attacked_by(not user_color,m.to_square): useful+=1
        if useful<=1:
            candidates.append((useful,sq,p))
    if not candidates: return None
    useful,sq,p=min(candidates,key=lambda x:x[0])
    return {'id':'trapped_piece','theme':'Pièce enfermée','square':sq,'piece':p,'useful_exits':useful}

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
    for fn in (royal_fork,skewer,fork,discovered_attack,pin):
        x=fn(board_before,move)
        if x: findings.append(x)
    after=board_before.copy(); after.push(move)
    # Concrete hanging piece: attacked + no defender, only if the position changed into that state.
    for x in new_piece_status(board_before,after,move,user_color):
        if x['status']=='non_defendue' and _piece_value(x['piece'])>=3:
            findings.append({'id':'hanging_piece','theme':'Pièce laissée en prise',**x})
    priority={'royal_fork':1,'skewer':2,'double_attack':3,'hanging_piece':4,'pin':5,'discovered_attack':6,'trapped_piece':7}
    trapped=trapped_piece(after,user_color)
    if trapped: findings.append(trapped)
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

def pedagogical_layer(board_before, board_after, move, best_move_san, best_reply_san, loss, is_user_white, knowledge=None, opening=""):
    user_color=chess.WHITE if is_user_white else chess.BLACK
    findings=detect_tactics(board_before,move,user_color)
    opening_ctx=opening_intent_for_position(opening, board_before, is_user_white, knowledge=knowledge)
    played=board_before.san(move)
    same_as_best = bool(best_move_san and best_move_san != "-" and played == best_move_san)

    if findings:
        f=findings[0]
        if f['id']=='royal_fork':
            reason=f"{played} donne échec tout en attaquant la dame : c'est une fourchette royale. L'échec force la réponse du roi, ce qui laisse la deuxième cible exposée."
        elif f['id']=='skewer':
            fs,fp=f['front']; bs,bp=f['back']
            reason=f"{played} crée une enfilade : le {fp.symbol()} en {chess.square_name(fs)} est la cible de tête et le {bp.symbol()} en {chess.square_name(bs)} se trouve derrière. Si la première cible doit se déplacer, la seconde devient exposée."
        elif f['id']=='hanging_piece':
            reason=f"{played} laisse le {f['piece'].symbol()} en {chess.square_name(f['square'])} attaqué sans défense effective."
        elif f['id']=='trapped_piece':
            reason=f"{played} laisse le {f['piece'].symbol()} en {chess.square_name(f['square'])} avec très peu de sorties utiles : la pièce risque de rester hors jeu."
        else:
            reason=f"{played} crée le motif tactique « {f['theme']} » ; la conséquence concrète est prioritaire sur les principes généraux."
    elif same_as_best or loss <= 0.20:
        if opening_ctx.get('relevant') and opening_ctx.get('plans'):
            plan=opening_ctx['plans'][0]
            reason=f"{played} est un très bon choix ici. Dans la {opening_ctx['name']}, il sert directement l'idée suivante : {plan}. Ce n'est pas seulement un coup bien noté par le moteur : il va dans le sens du projet de la position."
        else:
            reason=f"{played} est un très bon choix : le coup joué correspond au meilleur choix du moteur et produit une amélioration concrète sans perte significative."
    else:
        reason=f"{played} est inférieur à {best_move_san}. Le diagnostic doit être fondé sur une conséquence concrète de la variante et non sur une formule générale."
    return {'played':played,'best_move':best_move_san,'best_reply':best_reply_san,'loss':0.0 if same_as_best else loss,'findings':findings,'dominant_concept':findings[0].get('id') if findings else None,'human_reason':reason,'opening_context':opening_ctx}

