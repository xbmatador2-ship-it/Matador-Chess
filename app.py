# ============================================================
# COACH CHESS 1500 V2
# PARTIE 1/6
# Imports + configuration + récupération des parties
# ============================================================

import io
import json
import re
from collections import Counter, defaultdict

import chess
import chess.pgn
import chess.svg
import pandas as pd
import plotly.express as px
import requests
import streamlit as st


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Coach Chess 1500",
    page_icon="♟️",
    layout="wide",
)

st.title("♟️ Coach Chess 1500")

st.caption(
    "Ton coach personnel pour comprendre tes erreurs, "
    "identifier tes habitudes et progresser vers 1500 Elo."
)


# Nombre de parties utilisées pour le diagnostic
NB_PARTIES = 10

# API Stockfish utilisée dans cette version
STOCKFISH_API_URL = "https://chess-api.com/v1"


# ============================================================
# OUTILS HTTP
# ============================================================

def safe_get(url, headers=None, params=None, timeout=20):
    """
    Requête GET sécurisée.

    Retourne la réponse si elle est correcte.
    Retourne None en cas d'erreur.
    """

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=timeout,
        )

        if response.status_code == 200:
            return response

    except requests.RequestException:
        pass

    return None


# ============================================================
# CHESS.COM
# ============================================================

def get_chesscom_games(username):
    """
    Récupère les NB_PARTIES parties les plus récentes
    d'un joueur Chess.com.

    IMPORTANT :
    Les archives Chess.com sont chronologiques.
    On commence donc par la dernière archive et on remonte
    vers les archives précédentes.

    Dans chaque archive, on parcourt également les parties
    de la fin vers le début.

    Cela évite le problème rencontré précédemment :
    récupérer les 10 parties les plus anciennes au lieu
    des 10 dernières.
    """

    username = username.strip()

    if not username:
        return None

    headers = {
        "User-Agent": "ChessCoach1500/1.0"
    }

    archives_url = (
        f"https://api.chess.com/pub/player/"
        f"{username}/games/archives"
    )

    response = safe_get(
        archives_url,
        headers=headers,
    )

    if not response:
        return None

    try:
        archives = response.json().get(
            "archives",
            [],
        )
    except Exception:
        return None

    if not archives:
        return None

    collected_games = []

    # ========================================================
    # PLUS RÉCENT → PLUS ANCIEN
    # ========================================================

    for archive_url in reversed(archives):

        archive_response = safe_get(
            archive_url,
            headers=headers,
        )

        if not archive_response:
            continue

        try:
            games = archive_response.json().get(
                "games",
                [],
            )
        except Exception:
            continue

        # Les parties sont parcourues de la plus récente
        # vers la plus ancienne.
        for game in reversed(games):

            collected_games.append(game)

            if len(collected_games) >= NB_PARTIES:
                return (
                    "chesscom",
                    collected_games[:NB_PARTIES],
                )

    return (
        "chesscom",
        collected_games[:NB_PARTIES],
    )


# ============================================================
# LICHESS
# ============================================================

def get_lichess_games(username):
    """
    Récupère les NB_PARTIES dernières parties Lichess.

    L'API Lichess renvoie les parties les plus récentes
    lorsque max=NB_PARTIES est utilisé.
    """

    username = username.strip()

    if not username:
        return None

    url = (
        f"https://lichess.org/api/games/user/"
        f"{username}"
    )

    params = {
        "max": NB_PARTIES,
        "opening": "true",
        "clocks": "true",
        "evals": "true",
        "literate": "false",
    }

    headers = {
        "Accept": "application/x-chess-pgn",
        "User-Agent": "ChessCoach1500/1.0",
    }

    response = safe_get(
        url,
        headers=headers,
        params=params,
        timeout=30,
    )

    if not response:
        return None

    pgn_text = response.text.strip()

    if not pgn_text:
        return None

    # ========================================================
    # SÉPARATION DES PARTIES PGN
    # ========================================================

    chunks = re.split(
        r"(?=\[Event )",
        pgn_text,
    )

    games = []

    for chunk in chunks:

        chunk = chunk.strip()

        if not chunk:
            continue

        games.append({
            "pgn": chunk,
        })

    return (
        "lichess",
        games[:NB_PARTIES],
    )


# ============================================================
# CONVERSION DU RÉSULTAT
# ============================================================

def convert_chesscom_result(result):
    """
    Convertit le résultat spécifique Chess.com
    vers notre format pédagogique.
    """

    if result == "win":
        return "Victoire"

    if result in {
        "agreed",
        "repetition",
        "stalemate",
        "insufficient",
        "50move",
        "timevsinsufficient",
    }:
        return "Nul"

    return "Défaite"


def convert_pgn_result(result, is_user_white):
    """
    Convertit un résultat PGN en fonction de la couleur
    du joueur analysé.
    """

    if result == "1/2-1/2":
        return "Nul"

    if result == "*":
        return "Inconnue"

    user_won = (
        (result == "1-0" and is_user_white)
        or
        (result == "0-1" and not is_user_white)
    )

    if user_won:
        return "Victoire"

    return "Défaite"


# ============================================================
# TRAITEMENT CHESS.COM
# ============================================================

def process_chesscom_games(games, username):
    """
    Transforme les données Chess.com en DataFrame.

    On ne conserve que les parties dans lesquelles
    le joueur demandé participe réellement.
    """

    rows = []

    target = username.strip().lower()

    for index, game in enumerate(games):

        white = game.get(
            "white",
            {},
        )

        black = game.get(
            "black",
            {},
        )

        white_username = white.get(
            "username",
            "",
        )

        black_username = black.get(
            "username",
            "",
        )

        white_lower = white_username.lower()
        black_lower = black_username.lower()

        if white_lower == target:

            is_white = True
            player = white
            opponent = black

        elif black_lower == target:

            is_white = False
            player = black
            opponent = white

        else:
            continue

        result = convert_chesscom_result(
            player.get(
                "result",
                "",
            )
        )

        # ====================================================
        # OUVERTURE
        # ====================================================

        eco_url = game.get(
            "eco",
            "",
        )

        if eco_url:

            opening = (
                eco_url
                .rstrip("/")
                .split("/")[-1]
                .replace("-", " ")
                .title()
            )

        else:

            opening = "Inconnue"

        # ====================================================
        # DATE
        # ====================================================

        date_value = game.get(
            "end_time",
            game.get(
                "start_time",
                "",
            ),
        )

        rows.append({
            "ID": index,
            "Couleur": (
                "Blancs"
                if is_white
                else "Noirs"
            ),
            "Résultat": result,
            "Adversaire": opponent.get(
                "username",
                "Inconnu",
            ),
            "Elo Adversaire": opponent.get(
                "rating",
                0,
            ),
            "Ouverture": opening,
            "Date": date_value,
            "PGN": game.get(
                "pgn",
                "",
            ),
            "Plateforme": "Chess.com",
        })

    return pd.DataFrame(rows)


# ============================================================
# TRAITEMENT LICHESS
# ============================================================

def process_lichess_games(games, username):
    """
    Transforme les parties Lichess en DataFrame.
    """

    rows = []

    target = username.strip().lower()

    for index, item in enumerate(games):

        pgn_text = item.get(
            "pgn",
            "",
        )

        if not pgn_text:
            continue

        try:

            game = chess.pgn.read_game(
                io.StringIO(pgn_text)
            )

        except Exception:
            continue

        if not game:
            continue

        headers = game.headers

        white = headers.get(
            "White",
            "",
        )

        black = headers.get(
            "Black",
            "",
        )

        white_lower = white.lower()
        black_lower = black.lower()

        # ====================================================
        # IDENTIFICATION DU JOUEUR
        # ====================================================

        if white_lower == target:

            is_white = True
            opponent = black

        elif black_lower == target:

            is_white = False
            opponent = white

        else:
            continue

        # ====================================================
        # RÉSULTAT
        # ====================================================

        result = convert_pgn_result(
            headers.get(
                "Result",
                "*",
            ),
            is_white,
        )

        # ====================================================
        # ELO ADVERSAIRE
        # ====================================================

        if is_white:

            opponent_elo = headers.get(
                "BlackElo",
                "0",
            )

        else:

            opponent_elo = headers.get(
                "WhiteElo",
                "0",
            )

        try:
            opponent_elo = int(
                opponent_elo
            )
        except Exception:
            opponent_elo = 0

        # ====================================================
        # OUVERTURE
        # ====================================================

        opening = (
            headers.get(
                "Opening"
            )
            or
            headers.get(
                "ECO"
            )
            or
            "Inconnue"
        )

        rows.append({
            "ID": index,
            "Couleur": (
                "Blancs"
                if is_white
                else "Noirs"
            ),
            "Résultat": result,
            "Adversaire": (
                opponent
                or "Inconnu"
            ),
            "Elo Adversaire": opponent_elo,
            "Ouverture": opening,
            "Date": headers.get(
                "UTCDate",
                "",
            ),
            "PGN": pgn_text,
            "Plateforme": "Lichess",
        })

    return pd.DataFrame(rows)


# ============================================================
# FONCTION GÉNÉRALE DE TRAITEMENT
# ============================================================

def process_games(platform, games, username):
    """
    Fonction commune Chess.com / Lichess.
    """

    if platform == "chesscom":

        df = process_chesscom_games(
            games,
            username,
        )

    elif platform == "lichess":

        df = process_lichess_games(
            games,
            username,
        )

    else:

        return pd.DataFrame()

    if df.empty:
        return df

    # ========================================================
    # NORMALISATION
    # ========================================================

    df = df.copy()

    df["Elo Adversaire"] = pd.to_numeric(
        df["Elo Adversaire"],
        errors="coerce",
    ).fillna(0).astype(int)

    # ========================================================
    # SÉCURITÉ :
    # ON NE GARDE JAMAIS PLUS DE 10 PARTIES
    # ========================================================

    df = df.head(
        NB_PARTIES
    ).reset_index(
        drop=True
    )

    return df


# ============================================================
# INTERFACE DE CHARGEMENT
# ============================================================

st.markdown("---")

st.subheader(
    "👤 Charger tes parties"
)

col_platform, col_username, col_button = st.columns(
    [1, 2, 1]
)

with col_platform:

    platform_label = st.radio(
        "Plateforme",
        [
            "Chess.com",
            "Lichess",
        ],
        horizontal=True,
    )

with col_username:

    username = st.text_input(
        "Pseudonyme",
        placeholder="Ex : ton_pseudo",
    )

with col_button:

    st.write("")

    st.write("")

    load_games = st.button(
        "🔍 Charger",
        type="primary",
        use_container_width=True,
    )


# ============================================================
# CHARGEMENT
# ============================================================

if load_games:

    if not username.strip():

        st.warning(
            "Entre ton pseudonyme."
        )

    else:

        with st.spinner(
            "Recherche des 10 parties les plus récentes..."
        ):

            if platform_label == "Chess.com":

                raw_data = get_chesscom_games(
                    username
                )

            else:

                raw_data = get_lichess_games(
                    username
                )

        if not raw_data:

            st.error(
                "Impossible de récupérer les parties. "
                "Vérifie le pseudonyme et la plateforme."
            )

        else:

            platform_type, games = raw_data

            df = process_games(
                platform_type,
                games,
                username,
            )

            if df.empty:

                st.error(
                    "Aucune partie de ce joueur n'a été trouvée."
                )

            else:

                st.session_state[
                    "games_df"
                ] = df

                st.session_state[
                    "coach_username"
                ] = username

                st.session_state[
                    "coach_platform"
                ] = platform_label

                st.session_state[
                    "game_analyses"
                ] = {}

                st.success(
                    f"✅ {len(df)} partie(s) récente(s) "
                    f"chargée(s)."
                )


# ============================================================
# AFFICHAGE DES PARTIES
# ============================================================

if (
    "games_df" in st.session_state
    and not st.session_state["games_df"].empty
):

    games_df = st.session_state[
        "games_df"
    ]

    st.markdown("---")

    st.subheader(
        "📋 Parties sélectionnées"
    )

    st.caption(
        "Le coach travaille sur les 10 parties les plus récentes "
        "disponibles pour ce joueur."
    )

    st.dataframe(
        games_df[
            [
                "ID",
                "Date",
                "Couleur",
                "Résultat",
                "Adversaire",
                "Elo Adversaire",
                "Ouverture",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.info(
        "La récupération des parties est maintenant séparée "
        "du moteur d'analyse. Nous ajouterons Stockfish et le "
        "nouveau moteur pédagogique dans les parties suivantes."
    )
  # ============================================================
# COACH CHESS 1500 V2
# PARTIE 2/6
# Moteur Stockfish + analyse objective des coups
# ============================================================


# ============================================================
# CONFIGURATION STOCKFISH
# ============================================================

@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def stockfish_analyse(fen, depth=12):
    """
    Analyse une position avec Stockfish via chess-api.com.

    Retourne :
        eval       = évaluation en pions
        best_move  = meilleur coup en SAN
        mate       = indication de mat éventuel
    """

    payload = {
        "fen": fen,
        "depth": depth,
    }

    try:

        response = requests.post(
            STOCKFISH_API_URL,
            json=payload,
            timeout=10,
        )

        if response.status_code != 200:
            return {
                "eval": 0.0,
                "best_move": "-",
                "mate": None,
            }

        data = response.json()

        # ----------------------------------------------------
        # ÉVALUATION
        # ----------------------------------------------------

        evaluation = data.get(
            "eval"
        )

        mate = data.get(
            "mate"
        )

        if evaluation is None:

            if mate is not None:

                if mate > 0:
                    evaluation = 100.0
                else:
                    evaluation = -100.0

            else:

                evaluation = 0.0

        try:
            evaluation = float(
                evaluation
            )
        except Exception:
            evaluation = 0.0

        # ----------------------------------------------------
        # MEILLEUR COUP
        # ----------------------------------------------------

        best_move = data.get(
            "san",
            "-"
        )

        if not best_move:
            best_move = "-"

        return {
            "eval": evaluation,
            "best_move": best_move,
            "mate": mate,
        }

    except (
        requests.RequestException,
        ValueError,
        TypeError,
    ):

        return {
            "eval": 0.0,
            "best_move": "-",
            "mate": None,
        }


# ============================================================
# NORMALISATION DE L'ÉVALUATION
# ============================================================

def evaluation_for_player(
    evaluation,
    is_user_white,
):
    """
    Convertit l'évaluation Stockfish du point de vue
    Blancs/Noirs vers le point de vue du joueur.

    Exemple :

        Stockfish = +1.5
        joueur = Blancs

        => +1.5

           Stockfish = +1.5
        joueur = Noirs

        => -1.5
    """

    if is_user_white:
        return evaluation

    return -evaluation


# ============================================================
# PERTE D'ÉVALUATION
# ============================================================

def calculate_move_loss(
    evaluation_before,
    evaluation_after,
    player_was_white,
):
    """
    Calcule la perte d'évaluation causée par le coup.

    IMPORTANT :

    On ne juge que le coup du joueur.

    Si le joueur est Blanc :

        avant - après

    Si le joueur est Noir :

        après - avant

    Une perte négative devient 0.

    Exemple Blanc :

        avant = +0.4
        après = -1.2

        perte = 1.6

    Exemple Noir :

        avant = -0.4
        après = +1.2

        perte = 1.6
    """

    if player_was_white:

        loss = (
            evaluation_before
            - evaluation_after
        )

    else:

        loss = (
            evaluation_after
            - evaluation_before
        )

    return max(
        0.0,
        round(loss, 3),
    )


# ============================================================
# CLASSIFICATION DU COUP
# ============================================================

def classify_move_loss(loss):
    """
    Classe un coup selon la perte d'évaluation.

    Ces catégories servent de signal.

    Elles ne constituent PAS encore le diagnostic pédagogique.

    Le moteur pédagogique de la PARTIE 3 décidera ensuite
    pourquoi le coup est mauvais.
    """

    if loss <= 0.20:

        return {
            "category": "Excellent",
            "icon": "🟢",
            "color": "#2ecc71",
            "severity": 0,
        }

    if loss <= 0.50:

        return {
            "category": "Bon coup",
            "icon": "🔵",
            "color": "#3498db",
            "severity": 1,
        }

    if loss <= 1.00:

        return {
            "category": "Inexactitude",
            "icon": "🟡",
            "color": "#f1c40f",
            "severity": 2,
        }

    if loss <= 2.00:

        return {
            "category": "Erreur",
            "icon": "🟠",
            "color": "#e67e22",
            "severity": 3,
        }

    return {
        "category": "Gaffe",
        "icon": "🔴",
        "color": "#e74c3c",
        "severity": 4,
    }


# ============================================================
# PHASE DE LA PARTIE
# ============================================================

def determine_game_phase(board):
    """
    Détermine approximativement la phase de jeu.

    Cette fonction est volontairement prudente.

    Elle ne doit PAS appliquer les mêmes principes à toute
    la partie.

    Ouverture :
        développement / centre / roi / tempi

    Milieu :
        tactique / activité / structure / plans

    Finale :
        roi / pions / activité / conversion
    """

    move_number = board.fullmove_number

    pieces = list(
        board.piece_map().values()
    )

    non_pawn_pieces = [
        piece
        for piece in pieces
        if piece.piece_type
        not in (
            chess.PAWN,
            chess.KING,
        )
    ]

    piece_count = len(
        non_pawn_pieces
    )

    # --------------------------------------------------------
    # OUVERTURE
    # --------------------------------------------------------

    if move_number <= 12:

        return "Ouverture"

    # --------------------------------------------------------
    # FINALE
    # --------------------------------------------------------

    if piece_count <= 4:

        return "Finale"

    if move_number >= 45:

        return "Finale"

    # --------------------------------------------------------
    # MILIEU
    # --------------------------------------------------------

    return "Milieu de partie"


# ============================================================
# MATÉRIEL
# ============================================================

PIECE_VALUES = {
    chess.PAWN: 1.0,
    chess.KNIGHT: 3.0,
    chess.BISHOP: 3.0,
    chess.ROOK: 5.0,
    chess.QUEEN: 9.0,
    chess.KING: 0.0,
}


def calculate_material(board):
    """
    Calcule le matériel de chaque camp.
    """

    white_material = 0.0
    black_material = 0.0

    for piece in board.piece_map().values():

        value = PIECE_VALUES.get(
            piece.piece_type,
            0.0,
        )

        if piece.color == chess.WHITE:

            white_material += value

        else:

            black_material += value

    return {
        "white": round(
            white_material,
            1,
        ),
        "black": round(
            black_material,
            1,
        ),
    }


def material_balance_for_player(
    board,
    is_user_white,
):
    """
    Matériel du point de vue du joueur.
    """

    material = calculate_material(
        board
    )

    if is_user_white:

        return round(
            material["white"]
            - material["black"],
            1,
        )

    return round(
        material["black"]
        - material["white"],
        1,
    )


# ============================================================
# SÉCURITÉ DU ROI
# ============================================================

def king_safety_info(
    board,
    color,
):
    """
    Produit quelques informations simples sur la sécurité
    du roi.

    Ce n'est PAS encore une évaluation complète.

    Le but est de fournir du contexte au moteur pédagogique.
    """

    king_square = board.king(
        color
    )

    if king_square is None:

        return {
            "castled": False,
            "king_square": None,
            "pawn_shield": 0,
            "under_attack": False,
        }

    rank = chess.square_rank(
        king_square
    )

    file_index = chess.square_file(
        king_square
    )

    # --------------------------------------------------------
    # ROQUE
    # --------------------------------------------------------

    castled = False

    if color == chess.WHITE:

        if king_square in (
            chess.G1,
            chess.C1,
        ):

            castled = True

    else:

        if king_square in (
            chess.G8,
            chess.C8,
        ):

            castled = True

    # --------------------------------------------------------
    # BOUCLIER DE PIONS
    # --------------------------------------------------------

    pawn_shield = 0

    for file_offset in (
        -1,
        0,
        1,
    ):

        target_file = (
            file_index
            + file_offset
        )

        if not 0 <= target_file <= 7:
            continue

        # Les pions devant le roi.
        if color == chess.WHITE:

            target_rank = rank + 1

        else:

            target_rank = rank - 1

        if not 0 <= target_rank <= 7:
            continue

        square = chess.square(
            target_file,
            target_rank,
        )

        piece = board.piece_at(
            square
        )

        if (
            piece is not None
            and piece.color == color
            and piece.piece_type == chess.PAWN
        ):

            pawn_shield += 1

    under_attack = board.is_attacked_by(
        not color,
        king_square,
    )

    return {
        "castled": castled,
        "king_square": king_square,
        "pawn_shield": pawn_shield,
        "under_attack": under_attack,
    }


# ============================================================
# STRUCTURE DE PIONS
# ============================================================

def pawn_structure_info(
    board,
    color,
):
    """
    Analyse très simplement la structure de pions.

    On recherche :

        pions doublés
        pions isolés
        pions passés

    Ces données seront utilisées par le coach stratégique.
    """

    pawn_files = defaultdict(
        list
    )

    opponent_pawns = []

    for square, piece in board.piece_map().items():

        if piece.piece_type != chess.PAWN:
            continue

        file_index = chess.square_file(
            square
        )

        if piece.color == color:

            pawn_files[
                file_index
            ].append(square)

        else:

            opponent_pawns.append(
                square
            )

    doubled = 0
    isolated = 0
    passed = 0

    # --------------------------------------------------------
    # PIONS DOUBLÉS
    # --------------------------------------------------------

    for file_index, squares in pawn_files.items():

        if len(squares) > 1:

            doubled += (
                len(squares) - 1
            )

    # --------------------------------------------------------
    # PIONS ISOLÉS
    # --------------------------------------------------------

    own_files = set(
        pawn_files.keys()
    )

    for file_index in own_files:

        has_left = (
            file_index - 1
            in own_files
        )

        has_right = (
            file_index + 1
            in own_files
        )

        if not has_left and not has_right:

            isolated += len(
                pawn_files[
                    file_index
                ]
            )

    # --------------------------------------------------------
    # PIONS PASSÉS
    # --------------------------------------------------------

    for file_index, squares in pawn_files.items():

        for square in squares:

            rank = chess.square_rank(
                square
            )

            blocked_by_enemy = False

            for enemy_square in opponent_pawns:

                enemy_file = chess.square_file(
                    enemy_square
                )

                enemy_rank = chess.square_rank(
                    enemy_square
                )

                if abs(
                    enemy_file
                    - file_index
                ) > 1:

                    continue

                if color == chess.WHITE:

                    if enemy_rank > rank:
                        blocked_by_enemy = True
                        break

                else:

                    if enemy_rank < rank:
                        blocked_by_enemy = True
                        break

            if not blocked_by_enemy:

                passed += 1

    return {
        "doubled": doubled,
        "isolated": isolated,
        "passed": passed,
    }


# ============================================================
# DÉVELOPPEMENT
# ============================================================

def development_info(
    board,
    color,
):
    """
    Mesure approximativement le développement des pièces
    mineures.

    On ne considère PAS le développement comme une faute
    automatique : le contexte de la position sera examiné
    par le moteur pédagogique.
    """

    starting_squares = {
        chess.WHITE: {
            chess.B1,
            chess.C1,
            chess.F1,
            chess.G1,
        },
        chess.BLACK: {
            chess.B8,
            chess.C8,
            chess.F8,
            chess.G8,
        },
    }

    undeveloped = 0
    developed = 0

    for square in starting_squares[color]:

        piece = board.piece_at(
            square
        )

        if piece is None:

            developed += 1

        elif piece.color != color:

            developed += 1

        else:

            undeveloped += 1

    return {
        "developed_minor": developed,
        "undeveloped_minor": undeveloped,
    }


# ============================================================
# CENTRE
# ============================================================

CENTER_SQUARES = {
    chess.D4,
    chess.E4,
    chess.D5,
    chess.E5,
}


def center_control_info(
    board,
    color,
):
    """
    Mesure le contrôle des quatre cases centrales.
    """

    controlled = 0

    for square in CENTER_SQUARES:

        if board.is_attacked_by(
            color,
            square,
        ):

            controlled += 1

    return controlled


# ============================================================
# OUVERTURE DES LIGNES
# ============================================================

def open_file_info(board):
    """
    Détecte les colonnes ouvertes ou semi-ouvertes.

    Utilisé pour éviter les diagnostics simplistes du type :

        "Tu as ouvert une ligne = mauvais"

    Une colonne ouverte peut être excellente si elle active
    une tour ou permet d'attaquer une faiblesse.

    Le moteur pédagogique utilisera donc cette information
    avec le contexte.
    """

    open_files = []
    semi_open_white = []
    semi_open_black = []

    for file_index in range(8):

        white_pawn = False
        black_pawn = False

        for rank in range(8):

            square = chess.square(
                file_index,
                rank,
            )

            piece = board.piece_at(
                square
            )

            if not piece:
                continue

            if piece.piece_type != chess.PAWN:
                continue

            if piece.color == chess.WHITE:
                white_pawn = True

            else:
                black_pawn = True

        if (
            not white_pawn
            and not black_pawn
        ):

            open_files.append(
                file_index
            )

        elif not white_pawn:

            semi_open_black.append(
                file_index
            )

        elif not black_pawn:

            semi_open_white.append(
                file_index
            )

    return {
        "open_files": open_files,
        "semi_open_white": semi_open_white,
        "semi_open_black": semi_open_black,
    }


# ============================================================
# CONTEXTE COMPLET D'UNE POSITION
# ============================================================

def build_position_context(
    board,
    is_user_white,
):
    """
    Construit le contexte nécessaire au futur coach.

    Cette fonction est volontairement descriptive.

    Elle ne dit PAS :

        "ce coup est mauvais parce que..."

    Elle fournit les faits.

    Le moteur pédagogique de la PARTIE 3 interprétera ensuite
    ces faits.
    """

    user_color = (
        chess.WHITE
        if is_user_white
        else chess.BLACK
    )

    opponent_color = not user_color

    material = calculate_material(
        board
    )

    user_king = king_safety_info(
        board,
        user_color,
    )

    opponent_king = king_safety_info(
        board,
        opponent_color,
    )

    user_pawns = pawn_structure_info(
        board,
        user_color,
    )

    opponent_pawns = pawn_structure_info(
        board,
        opponent_color,
    )

    user_development = development_info(
        board,
        user_color,
    )

    opponent_development = development_info(
        board,
        opponent_color,
    )

    return {
        "phase": determine_game_phase(
            board
        ),

        "move_number": board.fullmove_number,

        "side_to_move": (
            "Blancs"
            if board.turn == chess.WHITE
            else "Noirs"
        ),

        "material": material,

        "material_for_user": (
            material["white"]
            - material["black"]
            if is_user_white
            else
            material["black"]
            - material["white"]
        ),

        "user_king": user_king,

        "opponent_king": opponent_king,

        "user_pawns": user_pawns,

        "opponent_pawns": opponent_pawns,

        "user_development": user_development,

        "opponent_development": opponent_development,

        "user_center_control": center_control_info(
            board,
            user_color,
        ),

        "opponent_center_control": center_control_info(
            board,
            opponent_color,
        ),

        "open_lines": open_file_info(
            board
        ),

        "legal_moves": board.legal_moves.count(),

        "in_check": board.is_check(),
    }


# ============================================================
# ANALYSE D'UNE PARTIE
# ============================================================

def analyze_game_with_engine(
    pgn_text,
    is_user_white,
):
    """
    Analyse toute la partie.

    IMPORTANT :

    Cette fonction analyse les positions des deux camps,
    mais les statistiques de qualité et les erreurs sont
    enregistrées uniquement pour le joueur.

    Les coups adverses serviront ensuite au moteur pédagogique
    uniquement comme contexte de menace et de réponse.
    """

    try:

        game = chess.pgn.read_game(
            io.StringIO(
                pgn_text
            )
        )

    except Exception:

        return None

    if not game:
        return None

    board = game.board()

    moves = list(
        game.mainline_moves()
    )

    history = []

    user_stats = {
        "coups": 0,
        "total_loss": 0.0,
        "gaffes": 0,
        "erreurs": 0,
        "inexactitudes": 0,
        "bons_coups": 0,
        "phases": Counter(),
    }

    # --------------------------------------------------------
    # ANALYSE DES COUPS
    # --------------------------------------------------------

    for ply, move in enumerate(moves):

        # ----------------------------------------------------
        # Position AVANT le coup
        # ----------------------------------------------------

        board_before = board.copy()

        player_was_white = (
            board_before.turn
            == chess.WHITE
        )

        is_user_turn = (
            player_was_white
            == is_user_white
        )

        fen_before = board_before.fen()

        context_before = (
            build_position_context(
                board_before,
                is_user_white,
            )
        )

        sf_before = stockfish_analyse(
            fen_before
        )

        evaluation_before = sf_before[
            "eval"
        ]

        best_move = sf_before[
            "best_move"
        ]

        # ----------------------------------------------------
        # COUP JOUÉ
        # ----------------------------------------------------

        san = board_before.san(
            move
        )

        from_square = move.from_square
        to_square = move.to_square

        # ----------------------------------------------------
        # Position APRÈS
        # ----------------------------------------------------

        board.push(move)

        board_after = board.copy()

        fen_after = board_after.fen()

        context_after = (
            build_position_context(
                board_after,
                is_user_white,
            )
        )

        sf_after = stockfish_analyse(
            fen_after
        )

        evaluation_after = sf_after[
            "eval"
        ]

        # ----------------------------------------------------
        # PERTE
        # ----------------------------------------------------

        loss = calculate_move_loss(
            evaluation_before,
            evaluation_after,
            player_was_white,
        )

        classification = (
            classify_move_loss(
                loss
            )
        )

        # ----------------------------------------------------
        # STATISTIQUES DU JOUEUR
        # ----------------------------------------------------

        if is_user_turn:

            user_stats["coups"] += 1

            user_stats[
                "total_loss"
            ] += loss

            user_stats[
                "phases"
            ][
                context_before[
                    "phase"
                ]
            ] += 1

            severity = classification[
                "severity"
            ]

            if severity == 4:

                user_stats[
                    "gaffes"
                ] += 1

            elif severity == 3:

                user_stats[
                    "erreurs"
                ] += 1

            elif severity == 2:

                user_stats[
                    "inexactitudes"
                ] += 1

            else:

                user_stats[
                    "bons_coups"
                ] += 1

        # ----------------------------------------------------
        # HISTORIQUE
        # ----------------------------------------------------

        history.append({

            "ply": ply + 1,

            "coup_num": (
                ply // 2
                + 1
            ),

            "joueur": (
                "Vous"
                if is_user_turn
                else "Adversaire"
            ),

            "is_user_turn": (
                is_user_turn
            ),

            "san": san,

            "from_sq": (
                from_square
            ),

            "to_sq": (
                to_square
            ),

            "fen_before": (
                fen_before
            ),

            "fen_after": (
                fen_after
            ),

            "eval_before": (
                evaluation_before
            ),

            "eval_after": (
                evaluation_after
            ),

            "eval_before_player": (
                evaluation_for_player(
                    evaluation_before,
                    is_user_white,
                )
            ),

            "eval_after_player": (
                evaluation_for_player(
                    evaluation_after,
                    is_user_white,
                )
            ),

            "eval_perspective": (
                evaluation_for_player(
                    evaluation_after,
                    is_user_white,
                )
            ),

            "loss": loss,

            "delta": loss,

            "best_move": best_move,

            "category": classification[
                "category"
            ],

            "icon": classification[
                "icon"
            ],

            "arrow_color": classification[
                "color"
            ],

            "severity": classification[
                "severity"
            ],

            "phase": context_before[
                "phase"
            ],

            "context_before": (
                context_before
            ),

            "context_after": (
                context_after
            ),
        })

    # ========================================================
    # STATISTIQUES FINALES
    # ========================================================

    user_count = max(
        1,
        user_stats["coups"],
    )

    acpl = (
        user_stats["total_loss"]
        / user_count
    )

    user_stats["acpl"] = round(
        acpl,
        2,
    )

    # Cette précision est une approximation pédagogique.
    # Elle n'est pas présentée comme une précision officielle
    # Chess.com ou Lichess.
    user_stats["precision"] = round(
        max(
            0,
            min(
                100,
                100
                - (
                    acpl
                    * 25
                ),
            ),
        ),
        1,
    )

    return {

        "history": history,

        "user_stats": user_stats,

        "total_plies": len(
            moves
        ),

        "total_moves": len(
            moves
        ),

    }


# ============================================================
# FIN PARTIE 2
# ============================================================

st.markdown("---")

st.caption(
    "⚙️ Moteur objectif chargé. "
    "Le diagnostic pédagogique sera ajouté dans la PARTIE 3."
)
# ============================================================
# COACH CHESS 1500 V2
# PARTIE 3/6
# MOTEUR PÉDAGOGIQUE
# ============================================================


# ============================================================
# OBJECTIF
# ============================================================
#
# Stockfish répond principalement :
#
#     "Quel coup est meilleur ?"
#
# Le coach doit répondre :
#
#     "Pourquoi ?"
#     "Quelle était la menace ?"
#     "Qu'est-ce que mon coup permet ?"
#     "Quelles conséquences ?"
#     "Quelle idée derrière le meilleur coup ?"
#     "Que peut-on faire ensuite ?"
#
# IMPORTANT :
#
# Les règles ci-dessous sont volontairement prudentes.
# Le coach préfère dire "aucun thème clair détecté"
# plutôt que d'inventer une explication.
#
# ============================================================


# ============================================================
# NOMS DES CASES
# ============================================================

def square_name(square):
    """
    Convertit un index python-chess en notation algébrique.
    """

    if square is None:
        return "case inconnue"

    return chess.square_name(square)


def piece_name(piece):
    """
    Nom pédagogique d'une pièce.
    """

    if piece is None:
        return "pièce"

    names = {
        chess.PAWN: "pion",
        chess.KNIGHT: "cavalier",
        chess.BISHOP: "fou",
        chess.ROOK: "tour",
        chess.QUEEN: "dame",
        chess.KING: "roi",
    }

    return names.get(
        piece.piece_type,
        "pièce",
    )


def piece_name_upper(piece):
    """
    Nom avec majuscule pour les textes.
    """

    name = piece_name(piece)

    if not name:
        return "Pièce"

    return name[0].upper() + name[1:]


# ============================================================
# UTILITAIRES DE POSITION
# ============================================================

def get_move_piece(
    board,
    move,
):
    """
    Retourne la pièce qui joue le coup.
    """

    return board.piece_at(
        move.from_square
    )


def is_capture_move(
    board,
    move,
):
    """
    Détermine si le coup capture une pièce.

    Gère également les prises en passant.
    """

    return board.is_capture(
        move
    )


def is_castling_move(
    board,
    move,
):
    """
    Détermine si le coup est un roque.
    """

    return board.is_castling(
        move
    )


def is_pawn_move(
    board,
    move,
):
    piece = board.piece_at(
        move.from_square
    )

    return (
        piece is not None
        and piece.piece_type
        == chess.PAWN
    )


def is_piece_move(
    board,
    move,
):
    piece = board.piece_at(
        move.from_square
    )

    return (
        piece is not None
        and piece.piece_type
        not in (
            chess.PAWN,
            chess.KING,
        )
    )


# ============================================================
# MOBILITÉ / ACTIVITÉ
# ============================================================

def piece_attack_count(
    board,
    square,
    color,
):
    """
    Nombre approximatif de cases contrôlées
    par une pièce.
    """

    if square is None:
        return 0

    attacks = board.attacks(
        square
    )

    count = 0

    for target in attacks:

        piece = board.piece_at(
            target
        )

        if piece is None:
            count += 1

        elif piece.color != color:
            count += 1

    return count


def attacked_pieces(
    board,
    color,
):
    """
    Retourne les pièces du camp indiqué
    qui sont attaquées.
    """

    result = []

    opponent = not color

    for square, piece in board.piece_map().items():

        if piece.color != color:
            continue

        if piece.piece_type == chess.KING:
            continue

        if board.is_attacked_by(
            opponent,
            square,
        ):

            result.append({
                "square": square,
                "piece": piece,
                "value": PIECE_VALUES.get(
                    piece.piece_type,
                    0,
                ),
            })

    return result


def undefended_pieces(
    board,
    color,
):
    """
    Détecte les pièces réellement sans protection.

    Une pièce n'est considérée comme non défendue que si
    aucune autre pièce du même camp ne contrôle sa case.

    Une pièce simplement attaquée par l'adversaire n'est donc
    PAS considérée comme non défendue si elle possède un
    défenseur.
    """

    result = []

    for square, piece in board.piece_map().items():

        if piece.color != color:
            continue

        if piece.piece_type == chess.KING:
            continue

        defenders = board.attackers(
            color,
            square,
        )

        # On retire la pièce elle-même si nécessaire.
        real_defenders = [
            defender_square
            for defender_square in defenders
            if defender_square != square
        ]

        if not real_defenders:

            result.append({
                "square": square,
                "piece": piece,
                "value": PIECE_VALUES.get(
                    piece.piece_type,
                    0,
                ),
            })

    return result

# ============================================================
# PIÈCES NON DÉFENDUES
# ============================================================

def undefended_pieces(
    board,
    color,
):
    """
    Détecte les pièces qui ne sont pas défendues.

    C'est une information pédagogique importante
    pour les joueurs autour de 1000 Elo.

    Attention :
    une pièce non défendue n'est PAS automatiquement
    une erreur.
    """

    result = []

    for square, piece in board.piece_map().items():

        if piece.color != color:
            continue

        if piece.piece_type == chess.KING:
            continue

        defenders = board.attackers(
            color,
            square,
        )

        if not defenders:

            result.append({
                "square": square,
                "piece": piece,
                "value": PIECE_VALUES.get(
                    piece.piece_type,
                    0,
                ),
            })

    return result


# ============================================================
# MENACES IMMÉDIATES
# ============================================================

def detect_check(
    board,
):
    """
    Vérifie si le camp au trait est en échec.
    """

    return board.is_check()


def detect_attacked_queen(
    board,
    color,
):
    """
    Vérifie si la dame du camp est attaquée.
    """

    result = []

    for square, piece in board.piece_map().items():

        if (
            piece.color == color
            and piece.piece_type
            == chess.QUEEN
        ):

            if board.is_attacked_by(
                not color,
                square,
            ):

                result.append(
                    square
                )

    return result


def detect_attacked_rooks(
    board,
    color,
):
    """
    Retourne les tours attaquées.
    """

    result = []

    for square, piece in board.piece_map().items():

        if (
            piece.color == color
            and piece.piece_type
            == chess.ROOK
        ):

            if board.is_attacked_by(
                not color,
                square,
            ):

                result.append(
                    square
                )

    return result


def immediate_threats(
    board,
    color,
):
    """
    Cherche quelques menaces concrètes.

    Ce n'est pas une recherche tactique exhaustive.
    Stockfish reste responsable de l'évaluation.

    Cette fonction sert à construire un langage pédagogique.
    """

    threats = []

    opponent = not color

    # --------------------------------------------------------
    # ÉCHEC
    # --------------------------------------------------------

    king_square = board.king(
        color
    )

    if (
        king_square is not None
        and board.is_attacked_by(
            opponent,
            king_square,
        )
    ):

        threats.append(
            "échec"
        )

    # --------------------------------------------------------
    # DAME ATTAQUÉE
    # --------------------------------------------------------

    if detect_attacked_queen(
        board,
        color,
    ):

        threats.append(
            "dame attaquée"
        )

    # --------------------------------------------------------
    # TOURS ATTAQUÉES
    # --------------------------------------------------------

    if detect_attacked_rooks(
        board,
        color,
    ):

        threats.append(
            "tour attaquée"
        )

    # --------------------------------------------------------
    # PIÈCES NON DÉFENDUES
    # --------------------------------------------------------

    undefended = (
        undefended_pieces(
            board,
            color,
        )
    )

    valuable_undefended = [
        item
        for item in undefended
        if item["value"] >= 3
    ]

    if valuable_undefended:

        threats.append(
            "pièce importante non défendue"
        )

    return threats


# ============================================================
# DÉTECTION DE MENACE AVANT LE COUP
# ============================================================

# ============================================================
# DÉTECTION DE MENACE AVANT LE COUP
# ============================================================

def identify_opponent_threat(
    board_before,
    is_user_white,
):
    """
    Identifie uniquement les menaces réellement pertinentes
    avant le coup du joueur.

    IMPORTANT :
    Une pièce attaquée n'est PAS automatiquement une pièce
    en danger.

    Le coach distingue :
        - pièce attaquée mais correctement défendue ;
        - pièce sous pression supérieure à sa défense ;
        - pièce réellement non défendue ;
        - roi sous attaque.

    Objectif :
        éviter les faux diagnostics du type
        "fou attaqué en f5" lorsque le fou est parfaitement
        protégé.
    """

    user_color = (
        chess.WHITE
        if is_user_white
        else chess.BLACK
    )

    opponent_color = not user_color

    threats = []

    # ========================================================
    # MENACES CONCRÈTES DE L'ADVERSAIRE
    # ========================================================

    immediate = immediate_threats(
        board_before,
        opponent_color,
    )

    for threat in immediate:

        if threat not in threats:

            threats.append(
                threat
            )

    # ========================================================
    # PIÈCES ATTAQUÉES
    # ========================================================

    for square, piece in board_before.piece_map().items():

        # On ne regarde que les pièces du joueur.
        if piece.color != user_color:
            continue

        # Le roi est traité séparément.
        if piece.piece_type == chess.KING:
            continue

        # La pièce doit réellement être attaquée.
        if not board_before.is_attacked_by(
            opponent_color,
            square,
        ):
            continue

        piece_value = PIECE_VALUES.get(
            piece.piece_type,
            0,
        )

        # On ignore les pions pour éviter le bruit.
        if piece_value < 3:
            continue

        # ====================================================
        # ATTAQUANTS
        # ====================================================

        attackers = board_before.attackers(
            opponent_color,
            square,
        )

        # ====================================================
        # DÉFENSEURS
        # ====================================================

        defenders = board_before.attackers(
            user_color,
            square,
        )

        attacker_count = len(
            attackers
        )

        defender_count = len(
            defenders
        )

        name = piece_name(
            piece
        )

        square_text = square_name(
            square
        )

        # ====================================================
        # PIÈCE SANS DÉFENSE
        # ====================================================

        if defender_count == 0:

            threats.append(
                f"{name} réellement vulnérable "
                f"en {square_text} : aucune défense directe"
            )

        # ====================================================
        # PLUS D'ATTAQUANTS QUE DE DÉFENSEURS
        # ====================================================

        elif attacker_count > defender_count:

            threats.append(
                f"{name} en {square_text} est sous "
                "une pression supérieure à sa défense"
            )

        # ====================================================
        # PIÈCE ATTAQUÉE ET CORRECTEMENT DÉFENDUE
        # ====================================================

        else:

            # NE PAS SIGNALER LA PIÈCE.
            #
            # Une pièce attaquée mais suffisamment défendue
            # n'est pas automatiquement une menace.
            #
            # Exemple :
            # Fou f5 attaqué par une pièce adverse
            # mais défendu par une tour ou un pion.
            #
            # Aucun message n'est ajouté.

            pass

    # ========================================================
    # ROI
    # ========================================================

    king_square = board_before.king(
        user_color
    )

    if (
        king_square is not None
        and board_before.is_attacked_by(
            opponent_color,
            king_square,
        )
    ):

        threats.append(
            "ton roi est sous pression"
        )

    # ========================================================
    # SUPPRESSION DES DOUBLONS
    # ========================================================

    unique = []

    for threat in threats:

        if threat not in unique:

            unique.append(
                threat
            )

    return unique[:5]

# ============================================================
# TACTIQUES — FOURCHETTE
# ============================================================

def detect_fork_after_move(
    board_before,
    move,
):
    """
    Recherche si le coup joué crée une fourchette.

    Une fourchette est retenue si la pièce arrivée
    sur sa nouvelle case attaque au moins deux pièces
    adverses significatives.

    On exclut le roi comme cible.
    """

    piece = board_before.piece_at(
        move.from_square
    )

    if piece is None:
        return None

    board_after = board_before.copy()

    try:
        board_after.push(
            move
        )
    except Exception:
        return None

    color = piece.color
    target_square = move.to_square

    attacked_targets = []

    for square in board_after.attacks(
        target_square
    ):

        target = board_after.piece_at(
            square
        )

        if target is None:
            continue

        if target.color == color:
            continue

        if target.piece_type == chess.KING:
            continue

        value = PIECE_VALUES.get(
            target.piece_type,
            0,
        )

        if value >= 3:

            attacked_targets.append({
                "square": square,
                "piece": target,
                "value": value,
            })

    if len(
        attacked_targets
    ) >= 2:

        return {
            "theme": "Fourchette",
            "targets": attacked_targets[:3],
            "square": target_square,
        }

    return None


# ============================================================
# TACTIQUES — CLOUAGE
# ============================================================

def detect_pin_after_move(
    board_before,
    move,
):
    """
    Détecte quelques situations de clouage après le coup.

    Le test reste volontairement simple :
    une pièce adverse entre dans une ligne entre une pièce
    importante et le roi.
    """

    board_after = board_before.copy()

    try:
        board_after.push(
            move
        )
    except Exception:
        return None

    attacking_color = not board_after.turn
    defending_color = board_after.turn

    king_square = board_after.king(
        defending_color
    )

    if king_square is None:
        return None

    king_file = chess.square_file(
        king_square
    )

    king_rank = chess.square_rank(
        king_square
    )

    directions = [
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
        (1, 1),
        (-1, -1),
        (1, -1),
        (-1, 1),
    ]

    for df, dr in directions:

        file_index = king_file + df
        rank_index = king_rank + dr

        first_piece = None
        first_square = None

        while (
            0 <= file_index <= 7
            and 0 <= rank_index <= 7
        ):

            square = chess.square(
                file_index,
                rank_index,
            )

            piece = board_after.piece_at(
                square
            )

            if piece is not None:

                if first_piece is None:

                    first_piece = piece
                    first_square = square

                else:

                    if (
                        first_piece.color
                        == defending_color
                        and piece.color
                        == attacking_color
                    ):

                        if piece.piece_type in (
                            chess.ROOK,
                            chess.QUEEN,
                            chess.BISHOP,
                        ):

                            if first_piece.piece_type != chess.KING:

                                return {
                                    "theme": "Clouage",
                                    "square": first_square,
                                    "king_square": king_square,
                                }

                    break

            file_index += df
            rank_index += dr

    return None


# ============================================================
# TACTIQUES — ATTACK DOUBLE
# ============================================================

def detect_double_attack(
    board_before,
    move,
):
    """
    Détecte une attaque double simple.

    Différence pédagogique avec la fourchette :
    une fourchette implique typiquement une même pièce
    attaquant plusieurs cibles.

    Ici on cherche plus largement une création de deux
    menaces après le coup.
    """

    board_after = board_before.copy()

    try:
        board_after.push(
            move
        )
    except Exception:
        return None

    color = not board_after.turn
    opponent = board_after.turn

    threats = []

    # Échec
    king_square = board_after.king(
        opponent
    )

    if (
        king_square is not None
        and board_after.is_attacked_by(
            color,
            king_square,
        )
    ):

        threats.append(
            "échec"
        )

    # Pièces importantes attaquées
    for square, piece in board_after.piece_map().items():

        if piece.color != opponent:
            continue

        if piece.piece_type == chess.KING:
            continue

        if PIECE_VALUES.get(
            piece.piece_type,
            0,
        ) < 3:

            continue

        if board_after.is_attacked_by(
            color,
            square,
        ):

            threats.append(
                piece_name(
                    piece
                )
            )

    if len(threats) >= 2:

        return {
            "theme": "Attaque double",
            "threats": threats[:3],
        }

    return None


# ============================================================
# TACTIQUES — DÉCOUVERTE
# ============================================================

def detect_discovered_attack(
    board_before,
    move,
):
    """
    Détecte grossièrement une attaque découverte.

    On vérifie si le déplacement de la pièce libère une ligne
    d'un fou, d'une tour ou de la dame vers une cible.
    """

    moving_piece = board_before.piece_at(
        move.from_square
    )

    if moving_piece is None:
        return None

    board_after = board_before.copy()

    try:
        board_after.push(
            move
        )
    except Exception:
        return None

    color = moving_piece.color

    for square, piece in board_after.piece_map().items():

        if piece.color != color:
            continue

        if piece.piece_type not in (
            chess.BISHOP,
            chess.ROOK,
            chess.QUEEN,
        ):
            continue

        for target_square in board_after.attacks(
            square
        ):

            target = board_after.piece_at(
                target_square
            )

            if target is None:
                continue

            if target.color == color:
                continue

            if target.piece_type == chess.KING:
                continue

            # Une pièce importante ciblée peut indiquer
            # une attaque découverte.
            if PIECE_VALUES.get(
                target.piece_type,
                0,
            ) >= 3:

                # On ne confirme que si la pièce déplacée
                # n'est pas elle-même celle qui attaque.
                if square != move.to_square:

                    return {
                        "theme": "Attaque à la découverte",
                        "attacker": square,
                        "target": target_square,
                    }

    return None


# ============================================================
# TACTIQUES — PIÈCE EN PRISE
# ============================================================

def detect_hanging_piece(
    board_before,
    board_after,
    move,
    is_user_white,
):
    """
    Détecte si le coup joué laisse une pièce importante
    directement attaquable sans compensation évidente.

    Ce n'est qu'un signal.

    Le moteur ne conclut pas automatiquement à une gaffe.
    """

    user_color = (
        chess.WHITE
        if is_user_white
        else chess.BLACK
    )

    pieces = undefended_pieces(
        board_after,
        user_color,
    )

    valuable = [
        item
        for item in pieces
        if item["value"] >= 3
    ]

    if not valuable:
        return None

    # Vérification supplémentaire :
    # la pièce doit être effectivement attaquée.
    for item in valuable:

        square = item[
            "square"
        ]

        if board_after.is_attacked_by(
            not user_color,
            square,
        ):

            return {
                "theme": "Pièce en prise",
                "square": square,
                "piece": item["piece"],
            }

    return None


# ============================================================
# DÉTECTION TACTIQUE GLOBALE
# ============================================================

def detect_tactical_themes(
    board_before,
    board_after,
    move,
    is_user_white,
):
    """
    Retourne les thèmes tactiques réellement détectés.

    Plusieurs thèmes peuvent coexister.
    """

    themes = []

    fork = detect_fork_after_move(
        board_before,
        move,
    )

    if fork:
        themes.append(
            fork
        )

    pin = detect_pin_after_move(
        board_before,
        move,
    )

    if pin:
        themes.append(
            pin
        )

    double_attack = (
        detect_double_attack(
            board_before,
            move,
        )
    )

    if double_attack:
        themes.append(
            double_attack
        )

    discovered = (
        detect_discovered_attack(
            board_before,
            move,
        )
    )

    if discovered:
        themes.append(
            discovered
        )

    hanging = (
        detect_hanging_piece(
            board_before,
            board_after,
            move,
            is_user_white,
        )
    )

    if hanging:
        themes.append(
            hanging
        )

    return themes


# ============================================================
# ROQUE — ANALYSE CONTEXTUELLE
# ============================================================

def evaluate_castling_context(
    board_before,
    board_after,
    move,
    is_user_white,
):
    """
    Analyse spécifiquement le roque.

    C'est une fonction importante car le coach ne doit jamais
    dire automatiquement :

        "Évite d'ouvrir des lignes"

    après un roque.

    Le roque peut simultanément :

        - sécuriser le roi ;
        - activer une tour ;
        - connecter les tours ;
        - terminer le développement ;
        - préparer un plan central.

    Le diagnostic dépend donc du contexte.
    """

    if not is_castling_move(
        board_before,
        move,
    ):

        return None

    user_color = (
        chess.WHITE
        if is_user_white
        else chess.BLACK
    )

    king_before = board_before.king(
        user_color
    )

    king_after = board_after.king(
        user_color
    )

    king_info_before = king_safety_info(
        board_before,
        user_color,
    )

    king_info_after = king_safety_info(
        board_after,
        user_color,
    )

    development_before = development_info(
        board_before,
        user_color,
    )

    development_after = development_info(
        board_after,
        user_color,
    )

    context = {
        "was_castling": True,
        "king_before": king_before,
        "king_after": king_after,
        "castled_before": king_info_before[
            "castled"
        ],
        "castled_after": king_info_after[
            "castled"
        ],
        "pawn_shield": king_info_after[
            "pawn_shield"
        ],
        "under_attack_after": king_info_after[
            "under_attack"
        ],
        "undeveloped_before": development_before[
            "undeveloped_minor"
        ],
        "undeveloped_after": development_after[
            "undeveloped_minor"
        ],
        "phase": determine_game_phase(
            board_before
        ),
    }

    # --------------------------------------------------------
    # ROQUE COHÉRENT
    # --------------------------------------------------------

    if (
        context["castled_after"]
        and not context["under_attack_after"]
        and context["pawn_shield"] >= 2
    ):

        context[
            "assessment"
        ] = "cohérent"

    else:

        context[
            "assessment"
        ] = "à examiner"

    return context


# ============================================================
# PRINCIPES STRATÉGIQUES
# ============================================================

def strategic_principles_for_position(
    board,
    is_user_white,
):
    """
    Génère une liste de principes potentiellement pertinents.

    IMPORTANT :
    Ce sont des principes candidats.

    Ils ne sont pas présentés automatiquement comme
    des erreurs du joueur.
    """

    user_color = (
        chess.WHITE
        if is_user_white
        else chess.BLACK
    )

    context = build_position_context(
        board,
        is_user_white,
    )

    principles = []

    phase = context[
        "phase"
    ]

    # --------------------------------------------------------
    # OUVERTURE
    # --------------------------------------------------------

    if phase == "Ouverture":

        undeveloped = context[
            "user_development"
        ][
            "undeveloped_minor"
        ]

        if undeveloped >= 2:

            principles.append(
                "Développer les pièces avant de multiplier "
                "les coups de pions ou les déplacements d'une "
                "même pièce."
            )

        if context[
            "user_king"
        ]["castled"] is False:

            principles.append(
                "Chercher à mettre le roi en sécurité lorsque "
                "la position le permet."
            )

        if (
            context[
                "user_center_control"
            ]
            < context[
                "opponent_center_control"
            ]
        ):

            principles.append(
                "Surveiller le contrôle du centre et chercher "
                "à contester les cases centrales importantes."
            )

    # --------------------------------------------------------
    # MILIEU DE PARTIE
    # --------------------------------------------------------

    elif phase == "Milieu de partie":

        principles.extend([
            "Identifier le plan de l'adversaire avant "
            "de commencer son propre plan.",
            "Chercher à améliorer la pièce la moins active.",
            "Comparer les échanges avant de simplifier.",
        ])

        if context[
            "material_for_user"
        ] > 1:

            principles.append(
                "Avec un avantage matériel, penser à la "
                "simplification et à la conversion sans "
                "abandonner l'activité."
            )

    # --------------------------------------------------------
    # FINALE
    # --------------------------------------------------------

    elif phase == "Finale":

        principles.extend([
            "En finale, l'activité du roi devient souvent "
            "un facteur central.",
            "Avant de pousser un pion, vérifier les cases "
            "d'entrée du roi adverse.",
            "L'activité de la tour compte souvent davantage "
            "que la simple conservation d'un pion.",
        ])

    return principles[:5]


# ============================================================
# PLAN À 2–3 COUPS
# ============================================================

def generate_plan_ideas(
    board,
    best_move_san,
    is_user_white,
):
    """
    Propose une direction de plan.

    Cette fonction n'invente pas une variante Stockfish.
    Elle explique l'idée générale du meilleur coup.

    Une véritable variante calculée pourra être ajoutée
    ultérieurement avec plusieurs profondeurs Stockfish.
    """

    if not best_move_san or best_move_san == "-":

        return []

    context = build_position_context(
        board,
        is_user_white,
    )

    phase = context[
        "phase"
    ]

    ideas = []

    # --------------------------------------------------------
    # OUVERTURE
    # --------------------------------------------------------

    if phase == "Ouverture":

        development = context[
            "user_development"
        ]

        if development[
            "undeveloped_minor"
        ] > 0:

            ideas.append(
                "Continuer le développement des pièces mineures."
            )

        if not context[
            "user_king"
        ]["castled"]:

            ideas.append(
                "Préparer la mise en sécurité du roi."
            )

        ideas.append(
            "Chercher ensuite à connecter les tours."
        )

    # --------------------------------------------------------
    # MILIEU
    # --------------------------------------------------------

    elif phase == "Milieu de partie":

        undefended = undefended_pieces(
            board,
            chess.WHITE
            if is_user_white
            else chess.BLACK,
        )

        if undefended:

            ideas.append(
                "Après le meilleur coup, vérifier les pièces "
                "qui restent insuffisamment défendues."
            )

        ideas.append(
            "Rechercher la prochaine menace concrète "
            "plutôt que jouer automatiquement un coup d'attente."
        )

        ideas.append(
            "Comparer l'activité des pièces avant de décider "
            "d'un échange ou d'une poussée de pion."
        )

    # --------------------------------------------------------
    # FINALE
    # --------------------------------------------------------

    else:

        ideas.append(
            "Améliorer l'activité du roi."
        )

        ideas.append(
            "Chercher un pion passé ou une faiblesse cible."
        )

        ideas.append(
            "Éviter de pousser un pion sans vérifier "
            "la réponse du roi adverse."
        )

    return ideas[:3]


# ============================================================
# EXPLICATION DU MEILLEUR COUP
# ============================================================

def explain_best_move(
    board_before,
    board_after,
    move,
    best_move_san,
    loss,
    is_user_white,
):
    """
    Construit l'explication du meilleur choix.

    Le texte reste honnête :
    si le moteur ne fournit pas suffisamment d'information,
    on ne prétend pas connaître une intention précise.
    """

    if not best_move_san or best_move_san == "-":

        return (
            "Stockfish n'a pas fourni de meilleur coup exploitable."
        )

    phase = determine_game_phase(
        board_before
    )

    move_piece = get_move_piece(
        board_before,
        move,
    )

    piece_text = piece_name(
        move_piece
    )

    if loss <= 0.20:

        return (
            f"{best_move_san} est une excellente référence dans "
            f"cette position. Ton coup avec le {piece_text} ne "
            "semble pas créer de problème significatif."
        )

    # --------------------------------------------------------
    # PRINCIPES DE BASE
    # --------------------------------------------------------

    if phase == "Ouverture":

        context = build_position_context(
            board_before,
            is_user_white,
        )

        undeveloped = context[
            "user_development"
        ][
            "undeveloped_minor"
        ]

        if undeveloped >= 2:

            return (
                f"{best_move_san} est préférable car il améliore "
                "davantage la coordination et le développement. "
                "Dans cette phase, le but n'est pas seulement de "
                "gagner un tempo local : il faut préparer une "
                "position où les pièces travaillent ensemble et "
                "où le roi peut être sécurisé."
            )

        return (
            f"{best_move_san} donne une meilleure coordination "
            "aux pièces et répond plus précisément aux exigences "
            "de la position. L'intérêt du coup est surtout "
            "positionnel : il prépare les décisions suivantes "
            "au lieu de résoudre uniquement un problème local."
        )

    if phase == "Finale":

        return (
            f"{best_move_san} est préférable parce qu'en finale "
            "l'activité des pièces et du roi devient prioritaire. "
            "Le bon coup cherche généralement à créer une cible, "
            "un pion passé ou une amélioration concrète de l'activité "
            "plutôt qu'un simple gain de tempo."
        )

    # --------------------------------------------------------
    # MILIEU DE PARTIE
    # --------------------------------------------------------

    return (
        f"{best_move_san} est préférable parce qu'il répond "
        "mieux aux exigences concrètes de la position. "
        "Il ne s'agit pas seulement d'une différence de "
        "quelques centipawns : le meilleur choix conserve "
        "davantage de possibilités et réduit les réponses "
        "favorables à l'adversaire."
    )


# ============================================================
# EXPLICATION DU COUP JOUÉ
# ============================================================

def explain_move_problem(
    board_before,
    board_after,
    move,
    best_move_san,
    loss,
    is_user_white,
):
    """
    Produit une première explication du problème.

    L'explication est basée sur les faits détectables.

    Elle ne prétend pas connaître exactement l'intention
    psychologique du joueur.
    """

    phase = determine_game_phase(
        board_before
    )

    piece = get_move_piece(
        board_before,
        move,
    )

    piece_text = piece_name(
        piece
    )

    # --------------------------------------------------------
    # COUP TRÈS BON
    # --------------------------------------------------------

    if loss <= 0.20:

        return (
            f"Ton coup {board_before.san(move)} "
            "ne présente pas de perte significative selon "
            "l'analyse moteur."
        )

    # --------------------------------------------------------
    # ROQUE
    # --------------------------------------------------------

    castling_context = (
        evaluate_castling_context(
            board_before,
            board_after,
            move,
            is_user_white,
        )
    )

    if castling_context:

        if (
            castling_context[
                "assessment"
            ]
            == "cohérent"
        ):

            return (
                "Ton roque est cohérent dans cette position. "
                "Il sécurise le roi et améliore immédiatement "
                "la coordination de la tour. Le fait qu'une "
                "ligne puisse devenir plus accessible ne suffit "
                "pas à rendre le roque mauvais : il faut regarder "
                "si le roi devient réellement vulnérable et si "
                "l'adversaire possède une façon concrète "
                "d'exploiter cette ouverture."
            )

        return (
            "Le roque mérite ici une analyse contextuelle. "
            "La sécurité du roi, le bouclier de pions et "
            "l'activité des pièces doivent être comparés "
            "aux possibilités concrètes de l'adversaire."
        )

    # --------------------------------------------------------
    # PIÈCE EN PRISE
    # --------------------------------------------------------

    hanging = detect_hanging_piece(
        board_before,
        board_after,
        move,
        is_user_white,
    )

    if hanging:

        square = square_name(
            hanging["square"]
        )

        target_piece = piece_name(
            hanging["piece"]
        )

        return (
            f"Le problème concret est que ton {target_piece} "
            f"en {square} devient vulnérable. "
            "Avant de chercher un plan actif, il fallait "
            "vérifier quelles pièces seraient laissées "
            "sans protection après ton coup."
        )

    # --------------------------------------------------------
    # MENACE ADVERSE
    # --------------------------------------------------------

    threats = identify_opponent_threat(
        board_before,
        is_user_white,
    )

    if threats:

        return (
            "Le point important de cette position est la "
            "menace adverse : "
            + ", ".join(threats[:3])
            + ". "
            "Ton coup ne traite pas suffisamment cette "
            "contrainte, ce qui permet à l'adversaire de "
            "poursuivre son idée avec davantage de liberté."
        )

    # --------------------------------------------------------
    # OUVERTURE
    # --------------------------------------------------------

    if phase == "Ouverture":

        context = build_position_context(
            board_before,
            is_user_white,
        )

        undeveloped = context[
            "user_development"
        ][
            "undeveloped_minor"
        ]

        if (
            undeveloped >= 2
            and piece is not None
            and piece.piece_type == chess.PAWN
        ):

            return (
                f"Ton coup de pion {board_before.san(move)} "
                "n'est pas nécessairement mauvais en lui-même, "
                "mais il faut le comparer au développement. "
                "Plusieurs pièces restent encore à développer, "
                "donc un coup qui améliore directement une pièce "
                "peut avoir une valeur plus importante."
            )

    # --------------------------------------------------------
    # MILIEU
    # --------------------------------------------------------

    if phase == "Milieu de partie":

        return (
            f"Le {piece_text} déplacé ne répond pas au mieux "
            "aux besoins de la position. Le problème n'est pas "
            "simplement que Stockfish préfère un autre coup : "
            "le coup choisi donne à l'adversaire une position "
            "plus facile à jouer ou lui permet d'améliorer "
            "une pièce avec tempo."
        )

    # --------------------------------------------------------
    # FINALE
    # --------------------------------------------------------

    if phase == "Finale":

        return (
            f"En finale, ton coup avec le {piece_text} ne semble "
            "pas exploiter suffisamment les facteurs essentiels "
            "de la position : activité du roi, pions faibles, "
            "pion passé et activité des pièces."
        )

    return (
        f"Ton {piece_text} pouvait être utilisé plus efficacement. "
        "Le moteur indique une meilleure possibilité, mais "
        "l'explication exacte doit être reliée aux menaces et "
        "aux caractéristiques concrètes de la position."
    )


# ============================================================
# CONSÉQUENCES DU COUP
# ============================================================

def explain_consequences(
    board_before,
    board_after,
    move,
    is_user_white,
):
    """
    Cherche les conséquences concrètes du coup.

    Une pièce attaquée mais correctement défendue
    n'est pas considérée comme une menace matérielle.
    """

    consequences = []

    user_color = (
        chess.WHITE
        if is_user_white
        else chess.BLACK
    )

    opponent_color = not user_color

    # --------------------------------------------------------
    # ROI
    # --------------------------------------------------------

    user_king = board_after.king(
        user_color
    )

    if (
        user_king is not None
        and board_after.is_attacked_by(
            opponent_color,
            user_king,
        )
    ):
        consequences.append(
            "ton roi est directement sous pression"
        )

    # --------------------------------------------------------
    # PIÈCES ATTAQUÉES
    # --------------------------------------------------------

    attacked = attacked_pieces(
        board_after,
        user_color,
    )

    important = [
        item
        for item in attacked
        if item["value"] >= 3
    ]

    for item in important[:3]:

        square = item["square"]

        defenders = board_after.attackers(
            user_color,
            square,
        )

        # Une pièce attaquée et défendue
        # n'est pas automatiquement vulnérable.

        if not defenders:

            consequences.append(
                f"ton {piece_name(item['piece'])} "
                f"en {square_name(square)} "
                "est attaqué et non défendu"
            )

        else:

            enemy_attackers = board_after.attackers(
                opponent_color,
                square,
            )

            # La pièce est sous pression seulement
            # si elle possède moins de défenseurs
            # que l'adversaire n'a d'attaquants.

            if len(enemy_attackers) > len(defenders):

                consequences.append(
                    f"ton {piece_name(item['piece'])} "
                    f"en {square_name(square)} "
                    "est sous une pression supérieure à sa défense"
                )

    # --------------------------------------------------------
    # PIÈCES NON DÉFENDUES
    # --------------------------------------------------------

    undefended = undefended_pieces(
        board_after,
        user_color,
    )

    valuable_undefended = [
        item
        for item in undefended
        if item["value"] >= 3
    ]

    for item in valuable_undefended[:2]:

        square = item["square"]

        # On ne signale ici que les pièces
        # qui sont réellement attaquées.

        if board_after.is_attacked_by(
            opponent_color,
            square,
        ):

            # Évite un doublon avec le bloc précédent.

            already_reported = any(
                square_name(square) in consequence
                for consequence in consequences
            )

            if not already_reported:

                consequences.append(
                    f"ton {piece_name(item['piece'])} "
                    f"en {square_name(square)} "
                    "est réellement vulnérable"
                )

    # --------------------------------------------------------
    # MENACES CONTRE L'ADVERSAIRE
    # --------------------------------------------------------

    opponent_king = board_after.king(
        opponent_color
    )

    if (
        opponent_king is not None
        and board_after.is_attacked_by(
            user_color,
            opponent_king,
        )
    ):

        consequences.append(
            "tu crées une pression directe sur le roi adverse"
        )

    # --------------------------------------------------------
    # SI AUCUNE CONSÉQUENCE CONCRÈTE
    # --------------------------------------------------------

    if not consequences:

        consequences.append(
            "aucune conséquence matérielle directe : "
            "les pièces attaquées restent correctement protégées"
        )

    return consequences[:4]
# ============================================================
# INTENTION POSSIBLE DU JOUEUR
# ============================================================

def infer_player_intention(
    board_before,
    move,
    is_user_white,
):
    """
    Estime l'idée évidente du coup.

    ATTENTION :
    On ne prétend pas connaître les pensées du joueur.

    On parle d'"intention probable" uniquement lorsque
    le déplacement permet de l'inférer raisonnablement.
    """

    piece = get_move_piece(
        board_before,
        move,
    )

    if piece is None:

        return "Intention non déterminée."

    san = board_before.san(
        move
    )

    # --------------------------------------------------------
    # ROQUE
    # --------------------------------------------------------

    if board_before.is_castling(
        move
    ):

        return (
            "Intention probable : mettre le roi en sécurité "
            "tout en activant la tour."
        )

    # --------------------------------------------------------
    # CAPTURE
    # --------------------------------------------------------

    if board_before.is_capture(
        move
    ):

        return (
            f"Intention probable : utiliser le {piece_name(piece)} "
            "pour gagner ou éliminer du matériel, modifier la "
            "structure ou supprimer une pièce active."
        )

    # --------------------------------------------------------
    # PAWN
    # --------------------------------------------------------

    if piece.piece_type == chess.PAWN:

        return (
            "Intention probable : gagner de l'espace, "
            "préparer une rupture ou soutenir une pièce."
        )

    # --------------------------------------------------------
    # PIÈCES MINEURES
    # --------------------------------------------------------

    if piece.piece_type == chess.KNIGHT:

        return (
            "Intention probable : améliorer le cavalier, "
            "contrôler de nouvelles cases ou préparer une menace."
        )

    if piece.piece_type == chess.BISHOP:

        return (
            "Intention probable : améliorer la diagonale du fou "
            "ou exercer une pression sur une cible."
        )

    # --------------------------------------------------------
    # TOURS
    # --------------------------------------------------------

    if piece.piece_type == chess.ROOK:

        return (
            "Intention probable : améliorer l'activité de la tour, "
            "contrôler une colonne ou soutenir une poussée."
        )

    # --------------------------------------------------------
    # DAME
    # --------------------------------------------------------

    if piece.piece_type == chess.QUEEN:

        return (
            "Intention probable : créer une menace ou améliorer "
            "la coordination des pièces."
        )

    return (
        "Intention probable non déterminée avec suffisamment "
        "de certitude."
    )


# ============================================================
# LEÇON À RETENIR
# ============================================================

def generate_lesson(
    board_before,
    board_after,
    move,
    best_move_san,
    loss,
    themes,
    is_user_white,
):
    """
    Génère une leçon courte et réutilisable.

    Le but est que le joueur puisse appliquer la leçon
    dans une autre partie.
    """

    # --------------------------------------------------------
    # TACTIQUE
    # --------------------------------------------------------

    if themes:

        theme_names = [
            item["theme"]
            for item in themes
        ]

        if "Fourchette" in theme_names:

            return (
                "Avant chaque coup, vérifie si une de tes pièces "
                "attaque plusieurs cibles et si l'adversaire peut "
                "faire la même chose."
            )

        if "Clouage" in theme_names:

            return (
                "Regarde toujours les pièces placées devant le roi "
                "ou une pièce de grande valeur : elles peuvent être "
                "clouées et perdre leur mobilité."
            )

        if "Attaque à la découverte" in theme_names:

            return (
                "Quand une pièce quitte une ligne, vérifie ce qu'elle "
                "libère derrière elle : une tour, un fou ou une dame "
                "peut soudainement créer une menace."
            )

        if "Pièce en prise" in theme_names:

            return (
                "Avant de jouer, fais le contrôle : "
                "Échecs → Captures → Menaces. "
                "Vérifie ensuite que tes propres pièces restent protégées."
            )

    # --------------------------------------------------------
    # ROQUE
    # --------------------------------------------------------

    if board_before.is_castling(
        move
    ):

        return (
            "Le roque doit être jugé par la sécurité réelle du roi, "
            "pas par une règle automatique. Cherche à comprendre "
            "si le roi est mieux protégé et si la tour devient plus active."
        )

    # --------------------------------------------------------
    # OUVERTURE
    # --------------------------------------------------------

    phase = determine_game_phase(
        board_before
    )

    if phase == "Ouverture":

        context = build_position_context(
            board_before,
            is_user_white,
        )

        if context[
            "user_development"
        ][
            "undeveloped_minor"
        ] >= 2:

            return (
                "En ouverture, cherche d'abord à développer, "
                "contrôler le centre et mettre ton roi en sécurité. "
                "Chaque coup doit idéalement améliorer au moins "
                "un de ces trois éléments."
            )

    # --------------------------------------------------------
    # FINALE
    # --------------------------------------------------------

    if phase == "Finale":

        return (
            "En finale, demande-toi avant chaque coup : "
            "mon roi peut-il devenir plus actif ? "
            "Puis-je créer ou attaquer une faiblesse ? "
            "Puis-je créer un pion passé ?"
        )

    # --------------------------------------------------------
    # MILIEU
    # --------------------------------------------------------

    return (
        "Avant de jouer ton plan, pose-toi systématiquement "
        "la question : « Que veut faire mon adversaire au prochain "
        "coup ? » Ensuite seulement, compare tes coups candidats."
    )


# ============================================================
# RAPPORT PÉDAGOGIQUE D'UN COUP
# ============================================================

def build_move_coaching(
    board_before,
    board_after,
    move,
    move_data,
    is_user_white,
):
    """
    Produit le rapport complet d'un coup du joueur.

    Structure :

        1. Diagnostic
        2. Intention probable
        3. Menace adverse
        4. Pourquoi le coup pose problème
        5. Conséquences
        6. Meilleur coup
        7. Pourquoi il est meilleur
        8. Plan 2–3 coups
        9. Thèmes
        10. Principe
        11. Leçon
    """

    loss = move_data[
        "loss"
    ]

    best_move = move_data[
        "best_move"
    ]

    # --------------------------------------------------------
    # THÈMES
    # --------------------------------------------------------

    themes = detect_tactical_themes(
        board_before,
        board_after,
        move,
        is_user_white,
    )

    # --------------------------------------------------------
    # MENACE
    # --------------------------------------------------------

    opponent_threats = (
        identify_opponent_threat(
            board_before,
            is_user_white,
        )
    )

    # --------------------------------------------------------
    # INTENTION
    # --------------------------------------------------------

    intention = infer_player_intention(
        board_before,
        move,
        is_user_white,
    )

    # --------------------------------------------------------
    # EXPLICATION
    # --------------------------------------------------------

    problem = explain_move_problem(
        board_before,
        board_after,
        move,
        best_move,
        loss,
        is_user_white,
    )

    # --------------------------------------------------------
    # CONSÉQUENCES
    # --------------------------------------------------------

    consequences = explain_consequences(
        board_before,
        board_after,
        move,
        is_user_white,
    )

    # --------------------------------------------------------
    # MEILLEUR COUP
    # --------------------------------------------------------

    best_explanation = (
        explain_best_move(
            board_before,
            board_after,
            move,
            best_move,
            loss,
            is_user_white,
        )
    )

    # --------------------------------------------------------
    # PLAN
    # --------------------------------------------------------

    plan = generate_plan_ideas(
        board_before,
        best_move,
        is_user_white,
    )

    # --------------------------------------------------------
    # PRINCIPES
    # --------------------------------------------------------

    principles = (
        strategic_principles_for_position(
            board_before,
            is_user_white,
        )
    )

    # --------------------------------------------------------
    # LEÇON
    # --------------------------------------------------------

    lesson = generate_lesson(
        board_before,
        board_after,
        move,
        best_move,
        loss,
        themes,
        is_user_white,
    )

    # --------------------------------------------------------
    # CONFIANCE
    # --------------------------------------------------------

    if themes:

        confidence = "Élevée"

    elif loss >= 1.0:

        confidence = "Moyenne"

    else:

        confidence = "Faible à moyenne"

    return {

        "loss": loss,

        "category": move_data[
            "category"
        ],

        "icon": move_data[
            "icon"
        ],

        "phase": move_data[
            "phase"
        ],

        "san": move_data[
            "san"
        ],

        "best_move": best_move,

        "intention": intention,

        "opponent_threats": (
            opponent_threats
        ),

        "problem": problem,

        "consequences": consequences,

        "best_explanation": (
            best_explanation
        ),

        "plan": plan,

        "themes": themes,

        "principles": principles,

        "lesson": lesson,

        "confidence": confidence,
    }


# ============================================================
# SÉLECTION DES COUPS VRAIMENT IMPORTANTS
# ============================================================

def select_critical_user_moves(
    analysis,
    max_moves=8,
):
    """
    Sélectionne les coups du joueur qui méritent une
    explication pédagogique.

    On ne montre pas 25 coups "bons" ou "mauvais".

    On cherche les moments importants.
    """

    history = analysis[
        "history"
    ]

    candidates = []

    for index, move_data in enumerate(
        history
    ):

        if not move_data[
            "is_user_turn"
        ]:

            continue

        loss = move_data[
            "loss"
        ]

        # ----------------------------------------------------
        # Critères
        # ----------------------------------------------------

        score = 0.0

        score += loss * 10

        if move_data[
            "severity"
        ] >= 3:

            score += 10

        if move_data[
            "phase"
        ] == "Milieu de partie":

            score += 1

        candidates.append(
            (
                score,
                index,
            )
        )

    # --------------------------------------------------------
    # PLUS IMPORTANT → MOINS IMPORTANT
    # --------------------------------------------------------

    candidates.sort(
        reverse=True
    )

    selected = [
        index
        for _, index
        in candidates[
            :max_moves
        ]
    ]

    selected.sort()

    return selected


# ============================================================
# ENRICHISSEMENT DE L'ANALYSE
# ============================================================

def enrich_analysis_with_coaching(
    analysis,
    is_user_white,
):
    """
    Ajoute le coaching uniquement sur les coups importants.

    Cela évite d'envoyer / d'afficher des dizaines
    d'explications inutiles.
    """

    if not analysis:

        return analysis

    critical_indexes = (
        select_critical_user_moves(
            analysis
        )
    )

    coaching = {}

    history = analysis[
        "history"
    ]

    for index in critical_indexes:

        move_data = history[
            index
        ]

        try:

            board_before = chess.Board(
                move_data[
                    "fen_before"
                ]
            )

            board_after = chess.Board(
                move_data[
                    "fen_after"
                ]
            )

            move = chess.Move(
                move_data[
                    "from_sq"
                ],
                move_data[
                    "to_sq"
                ],
            )

            report = build_move_coaching(
                board_before,
                board_after,
                move,
                move_data,
                is_user_white,
            )

            coaching[
                index
            ] = report

        except Exception:

            continue

    analysis[
        "coaching"
    ] = coaching

    analysis[
        "critical_indexes"
    ] = critical_indexes

    return analysis


# ============================================================
# DIAGNOSTIC GLOBAL D'UNE PARTIE
# ============================================================

def build_game_diagnosis(
    analysis,
):
    """
    Résume la partie sans simplement répéter l'ACPL.

    Le diagnostic cherche :

        - erreurs critiques ;
        - thèmes tactiques ;
        - phases problématiques ;
        - habitudes potentielles.
    """

    if not analysis:

        return {}

    stats = analysis[
        "user_stats"
    ]

    coaching = analysis.get(
        "coaching",
        {},
    )

    theme_counter = Counter()
    phase_counter = Counter()
    habit_counter = Counter()

    for report in coaching.values():

        phase = report.get(
            "phase"
        )

        if phase:

            phase_counter[
                phase
            ] += 1

        for theme in report.get(
            "themes",
            [],
        ):

            name = theme.get(
                "theme"
            )

            if name:

                theme_counter[
                    name
                ] += 1

        threats = report.get(
            "opponent_threats",
            [],
        )

        if threats:

            habit_counter[
                "Vérification des menaces"
            ] += 1

    # --------------------------------------------------------
    # DIAGNOSTIC
    # --------------------------------------------------------

    diagnosis = []

    if stats[
        "gaffes"
    ] > 0:

        diagnosis.append(
            "La priorité est de réduire les grosses pertes "
            "causées par les erreurs tactiques."
        )

    if theme_counter:

        most_common = (
            theme_counter.most_common(
                2
            )
        )

        for theme, count in most_common:

            diagnosis.append(
                f"Thème récurrent : {theme} "
                f"({count} occurrence(s))."
            )

    if habit_counter[
        "Vérification des menaces"
    ] >= 2:

        diagnosis.append(
            "Une habitude à travailler est la vérification "
            "de la menace adverse avant de lancer ton propre plan."
        )

    if not diagnosis:

        diagnosis.append(
            "Aucun défaut dominant suffisamment clair "
            "n'a été détecté dans cette partie."
        )

    return {

        "diagnosis": diagnosis,

        "themes": dict(
            theme_counter
        ),

        "phases": dict(
            phase_counter
        ),

        "habits": dict(
            habit_counter
        ),
    }


# ============================================================
# APPLICATION DU COACH À UNE ANALYSE
# ============================================================

def finalize_game_analysis(
    analysis,
    is_user_white,
):
    """
    Pipeline final :

        Stockfish
            ↓
        contexte
            ↓
        coups critiques
            ↓
        coaching
            ↓
        diagnostic
    """

    if not analysis:

        return None

    analysis = (
        enrich_analysis_with_coaching(
            analysis,
            is_user_white,
        )
    )

    analysis[
        "game_diagnosis"
    ] = build_game_diagnosis(
        analysis
    )

    return analysis


# ============================================================
# FIN PARTIE 3
# ============================================================

st.markdown("---")

st.caption(
    "🧠 Moteur pédagogique chargé : "
    "menaces, tactiques, contexte, conséquences et principes."
)
# ============================================================
# COACH CHESS 1500 V2
# PARTIE 4/6
# COACH GLOBAL — 10 DERNIÈRES PARTIES
# ============================================================


# ============================================================
# OBJECTIF DE CETTE PARTIE
# ============================================================
#
# Une partie isolée peut être trompeuse.
#
# Le coach doit rechercher des tendances :
#
#     Partie 1 ─┐
#     Partie 2  │
#     Partie 3  │
#       ...     ├──> PROFIL DU JOUEUR
#     Partie 10 ┘
#
# Le but n'est PAS de dire :
#
#     "Tu as fait une fourchette."
#
# mais :
#
#     "Sur tes 10 dernières parties, les erreurs liées
#      aux pièces non défendues apparaissent régulièrement.
#      C'est actuellement une priorité."
#
# ============================================================


# ============================================================
# CONSTANTES DU COACH
# ============================================================

COACH_TARGET_ELO = 1500

COACH_MIN_THEME_OCCURRENCES = 2

COACH_MAX_PRIORITIES = 3


# ============================================================
# STRUCTURE VIDE
# ============================================================

def empty_coach_profile():
    """
    Profil initial du joueur.
    """

    return {
        "games_analyzed": 0,

        "user_moves": 0,

        "wins": 0,
        "losses": 0,
        "draws": 0,

        "total_loss": 0.0,

        "gaffes": 0,
        "erreurs": 0,
        "inexactitudes": 0,

        "phases": Counter(),

        "themes": Counter(),

        "habits": Counter(),

        "strengths": [],
        "weaknesses": [],

        "priorities": [],

        "training_plan": [],

        "progression": {},
    }


# ============================================================
# AJOUTER UNE PARTIE AU PROFIL
# ============================================================

def add_game_to_coach_profile(
    profile,
    analysis,
    game_result,
):
    """
    Ajoute les informations d'une partie au profil global.

    Seules les données concernant le joueur sont agrégées.

    Le résultat de la partie est utilisé uniquement comme
    contexte global.
    """

    if not analysis:
        return profile

    profile[
        "games_analyzed"
    ] += 1

    # --------------------------------------------------------
    # RÉSULTAT
    # --------------------------------------------------------

    if game_result == "Victoire":

        profile[
            "wins"
        ] += 1

    elif game_result == "Défaite":

        profile[
            "losses"
        ] += 1

    elif game_result == "Nul":

        profile[
            "draws"
        ] += 1

    # --------------------------------------------------------
    # STATISTIQUES JOUEUR
    # --------------------------------------------------------

    stats = analysis.get(
        "user_stats",
        {},
    )

    profile[
        "user_moves"
    ] += stats.get(
        "coups",
        0,
    )

    profile[
        "total_loss"
    ] += stats.get(
        "total_loss",
        0.0,
    )

    profile[
        "gaffes"
    ] += stats.get(
        "gaffes",
        0,
    )

    profile[
        "erreurs"
    ] += stats.get(
        "erreurs",
        0,
    )

    profile[
        "inexactitudes"
    ] += stats.get(
        "inexactitudes",
        0,
    )

    # --------------------------------------------------------
    # PHASES
    # --------------------------------------------------------

    for phase, count in stats.get(
        "phases",
        {},
    ).items():

        profile[
            "phases"
        ][phase] += count

    # --------------------------------------------------------
    # DONNÉES DU COACHING
    # --------------------------------------------------------

    coaching = analysis.get(
        "coaching",
        {},
    )

    for report in coaching.values():

        # ====================================================
        # THÈMES TACTIQUES
        # ====================================================

        for theme in report.get(
            "themes",
            [],
        ):

            name = theme.get(
                "theme"
            )

            if name:

                profile[
                    "themes"
                ][name] += 1

        # ====================================================
        # MENACES
        # ====================================================

        threats = report.get(
            "opponent_threats",
            [],
        )

        if threats:

            profile[
                "habits"
            ][
                "Ne vérifie pas toujours la menace adverse"
            ] += 1

        # ====================================================
        # GROSSE ERREUR
        # ====================================================

        if report.get(
            "loss",
            0,
        ) >= 2.0:

            profile[
                "habits"
            ][
                "Décisions à très forte perte"
            ] += 1

        # ====================================================
        # PIÈCES EN PRISE
        # ====================================================

        for theme in report.get(
            "themes",
            [],
        ):

            if theme.get(
                "theme"
            ) == "Pièce en prise":

                profile[
                    "habits"
                ][
                    "Pièces insuffisamment protégées"
                ] += 1

    return profile


# ============================================================
# CALCULS STATISTIQUES
# ============================================================

def finalize_coach_statistics(
    profile,
):
    """
    Calcule les statistiques globales.
    """

    games = max(
        1,
        profile[
            "games_analyzed"
        ],
    )

    moves = max(
        1,
        profile[
            "user_moves"
        ],
    )

    # --------------------------------------------------------
    # ACPL MOYEN
    # --------------------------------------------------------

    profile[
        "average_acpl"
    ] = round(
        profile[
            "total_loss"
        ]
        / moves,
        2,
    )

    # --------------------------------------------------------
    # GAFFES / PARTIE
    # --------------------------------------------------------

    profile[
        "gaffes_per_game"
    ] = round(
        profile[
            "gaffes"
        ]
        / games,
        2,
    )

    profile[
        "errors_per_game"
    ] = round(
        profile[
            "erreurs"
        ]
        / games,
        2,
    )

    profile[
        "inaccuracies_per_game"
    ] = round(
        profile[
            "inexactitudes"
        ]
        / games,
        2,
    )

    # --------------------------------------------------------
    # TAUX DE VICTOIRE
    # --------------------------------------------------------

    profile[
        "winrate"
    ] = round(
        (
            profile[
                "wins"
            ]
            / games
        )
        * 100,
        1,
    )

    # --------------------------------------------------------
    # FRÉQUENCE DES THÈMES
    # --------------------------------------------------------

    profile[
        "theme_frequency"
    ] = {}

    for theme, count in profile[
        "themes"
    ].items():

        profile[
            "theme_frequency"
        ][theme] = round(
            count / games,
            2,
        )

    return profile


# ============================================================
# SCORE DE GRAVITÉ DES THÈMES
# ============================================================

THEME_WEIGHTS = {

    # Tactiques fondamentales
    "Pièce en prise": 10,
    "Fourchette": 8,
    "Attaque double": 8,
    "Clouage": 7,
    "Attaque à la découverte": 7,

    # Habitudes
    "Ne vérifie pas toujours la menace adverse": 10,
    "Pièces insuffisamment protégées": 10,
    "Décisions à très forte perte": 12,
}


def calculate_theme_priority(
    profile,
):
    """
    Calcule quelles difficultés méritent le plus
    d'attention.

    On combine :

        fréquence
        gravité
        répétition
    """

    priorities = []

    # --------------------------------------------------------
    # THÈMES TACTIQUES
    # --------------------------------------------------------

    for theme, count in profile[
        "themes"
    ].items():

        if count < COACH_MIN_THEME_OCCURRENCES:
            continue

        weight = THEME_WEIGHTS.get(
            theme,
            5,
        )

        score = (
            count
            * weight
        )

        priorities.append({
            "name": theme,
            "score": score,
            "count": count,
            "type": "Tactique",
        })

    # --------------------------------------------------------
    # HABITUDES
    # --------------------------------------------------------

    for habit, count in profile[
        "habits"
    ].items():

        weight = THEME_WEIGHTS.get(
            habit,
            6,
        )

        score = (
            count
            * weight
        )

        priorities.append({
            "name": habit,
            "score": score,
            "count": count,
            "type": "Habitude",
        })

    priorities.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    return priorities


# ============================================================
# PHASES PROBLÉMATIQUES
# ============================================================

def calculate_phase_problems(
    profile,
):
    """
    Cherche dans quelle phase les problèmes apparaissent
    le plus souvent.

    Important :
    on ne dit pas simplement "tu es mauvais en finale".

    On regarde où les coups critiques du joueur ont été
    enregistrés.
    """

    phase_scores = Counter()

    # Les statistiques de phase présentes dans profile
    # correspondent au volume de coups.
    #
    # Pour le diagnostic, on préfère utiliser les coups
    # critiques et leur phase.

    return phase_scores


def aggregate_critical_phases(
    profile,
    analyses,
):
    """
    Ajoute les phases des erreurs importantes.
    """

    critical_phases = Counter()

    for analysis in analyses:

        if not analysis:
            continue

        coaching = analysis.get(
            "coaching",
            {},
        )

        for report in coaching.values():

            loss = report.get(
                "loss",
                0,
            )

            if loss < 1.0:
                continue

            phase = report.get(
                "phase",
                "Inconnue",
            )

            critical_phases[
                phase
            ] += 1

    profile[
        "critical_phases"
    ] = critical_phases

    return profile


# ============================================================
# DÉTECTION DES FORCES
# ============================================================

def identify_strengths(
    profile,
):
    """
    Identifie les domaines relativement solides.

    Le coach ne dit pas "tu es excellent" avec peu de données.

    Il cherche plutôt :

        "dans cet échantillon, ce domaine semble moins
         problématique que les autres."
    """

    strengths = []

    games = profile[
        "games_analyzed"
    ]

    if games <= 0:
        return strengths

    # --------------------------------------------------------
    # GAFFES
    # --------------------------------------------------------

    if (
        profile[
            "gaffes_per_game"
        ] <= 0.5
    ):

        strengths.append({
            "name": "Contrôle des grosses gaffes",
            "description": (
                "Le nombre de gaffes très importantes reste "
                "relativement limité sur l'échantillon analysé."
            ),
        })

    # --------------------------------------------------------
    # TACTIQUE
    # --------------------------------------------------------

    tactical_count = sum(
        profile[
            "themes"
        ].get(
            theme,
            0,
        )
        for theme in [
            "Fourchette",
            "Clouage",
            "Attaque double",
            "Attaque à la découverte",
        ]
    )

    if tactical_count <= games:

        strengths.append({
            "name": "Détection tactique",
            "description": (
                "Peu de motifs tactiques récurrents ont été "
                "détectés dans les coups critiques analysés."
            ),
        })

    # --------------------------------------------------------
    # ROQUE / ROI
    # --------------------------------------------------------

    castling_problems = (
        profile[
            "habits"
        ].get(
            "Roques problématiques",
            0,
        )
    )

    if castling_problems == 0:

        strengths.append({
            "name": "Sécurité du roi",
            "description": (
                "Aucun problème récurrent spécifique au roque "
                "n'a été identifié dans l'échantillon."
            ),
        })

    return strengths


# ============================================================
# DÉTECTION DES FAIBLESSES
# ============================================================

def identify_weaknesses(
    profile,
    priorities,
):
    """
    Transforme les données en faiblesses pédagogiques.

    Le but est d'éviter une liste interminable.
    """

    weaknesses = []

    # --------------------------------------------------------
    # GAFFES
    # --------------------------------------------------------

    if (
        profile[
            "gaffes_per_game"
        ] >= 1
    ):

        weaknesses.append({
            "name": "Gaffes tactiques",
            "severity": "Élevée",
            "description": (
                "Des pertes importantes apparaissent "
                "régulièrement. La priorité est de ralentir "
                "dans les positions critiques et de vérifier "
                "Échecs → Captures → Menaces."
            ),
        })

    # --------------------------------------------------------
    # MENACES
    # --------------------------------------------------------

    threat_habit = profile[
        "habits"
    ].get(
        "Ne vérifie pas toujours la menace adverse",
        0,
    )

    if threat_habit >= 2:

        weaknesses.append({
            "name": "Calcul défensif",
            "severity": "Élevée",
            "description": (
                "Plusieurs décisions critiques apparaissent "
                "sans réponse claire à la menace adverse. "
                "Il faut apprendre à identifier le coup "
                "que l'adversaire aimerait jouer ensuite."
            ),
        })

    # --------------------------------------------------------
    # PIÈCES
    # --------------------------------------------------------

    hanging = profile[
        "habits"
    ].get(
        "Pièces insuffisamment protégées",
        0,
    )

    if hanging >= 2:

        weaknesses.append({
            "name": "Pièces non défendues",
            "severity": "Élevée",
            "description": (
                "Des pièces importantes deviennent vulnérables "
                "après tes décisions. Le contrôle des pièces "
                "en prise doit devenir une routine."
            ),
        })

    # --------------------------------------------------------
    # THÈMES
    # --------------------------------------------------------

    for item in priorities:

        name = item[
            "name"
        ]

        if name in {
            "Pièce en prise",
            "Fourchette",
            "Clouage",
            "Attaque double",
            "Attaque à la découverte",
        }:

            weaknesses.append({
                "name": name,
                "severity": (
                    "Moyenne"
                    if item["count"] < 3
                    else "Élevée"
                ),
                "description": (
                    f"Le motif {name.lower()} apparaît "
                    f"{item['count']} fois dans les positions "
                    "critiques de l'échantillon."
                ),
            })

    return weaknesses


# ============================================================
# PRIORITÉ PRINCIPALE
# ============================================================

def choose_main_priority(
    profile,
    weaknesses,
):
    """
    Le coach choisit UNE priorité principale.

    C'est essentiel pédagogiquement.

    À 1000 Elo, travailler 10 faiblesses simultanément
    est généralement moins efficace que travailler
    un problème dominant.
    """

    if not weaknesses:

        return {
            "name": "Calcul et vérification",
            "reason": (
                "Aucun défaut dominant n'est suffisamment "
                "établi. Le meilleur axe général est de "
                "renforcer la routine Échecs → Captures → Menaces."
            ),
        }

    # --------------------------------------------------------
    # ORDRE DE PRIORITÉ
    # --------------------------------------------------------

    ranking = {
        "Gaffes tactiques": 100,
        "Calcul défensif": 95,
        "Pièces non défendues": 90,
        "Pièce en prise": 88,
        "Fourchette": 75,
        "Attaque double": 72,
        "Clouage": 68,
        "Attaque à la découverte": 65,
    }

    selected = sorted(
        weaknesses,
        key=lambda item: ranking.get(
            item["name"],
            50,
        ),
        reverse=True,
    )[0]

    reasons = {
        "Gaffes tactiques": (
            "Réduire les grosses erreurs donne généralement "
            "un gain immédiat de stabilité."
        ),

        "Calcul défensif": (
            "Savoir ce que l'adversaire menace avant de jouer "
            "son propre plan est une compétence fondamentale."
        ),

        "Pièces non défendues": (
            "La protection des pièces évite une grande partie "
            "des pertes tactiques simples."
        ),

        "Pièce en prise": (
            "La détection des pièces attaquées constitue "
            "une base essentielle avant le calcul."
        ),
    }

    return {
        "name": selected[
            "name"
        ],
        "reason": reasons.get(
            selected["name"],
            selected["description"],
        ),
    }


# ============================================================
# PLAN D'ENTRAÎNEMENT
# ============================================================

def build_training_plan(
    main_priority,
    profile,
):
    """
    Produit un plan concret.

    Le plan est orienté vers la compréhension et non
    simplement vers l'accumulation de puzzles.
    """

    priority = main_priority[
        "name"
    ]

    # --------------------------------------------------------
    # GAFFES
    # --------------------------------------------------------

    if priority == "Gaffes tactiques":

        return [
            {
                "jour": "Chaque partie",
                "travail": (
                    "Avant chaque coup critique : "
                    "Échecs → Captures → Menaces."
                ),
            },
            {
                "jour": "10 min",
                "travail": (
                    "Résoudre 5 exercices tactiques simples "
                    "sans bouger les pièces."
                ),
            },
            {
                "jour": "Après une partie",
                "travail": (
                    "Rejouer uniquement les 3 plus grosses erreurs "
                    "et trouver un coup candidat avant de regarder "
                    "Stockfish."
                ),
            },
        ]

    # --------------------------------------------------------
    # CALCUL DÉFENSIF
    # --------------------------------------------------------

    if priority == "Calcul défensif":

        return [
            {
                "jour": "Chaque partie",
                "travail": (
                    "Avant ton plan : demande-toi "
                    "« Quelle est la menace de mon adversaire ? »"
                ),
            },
            {
                "jour": "10 min",
                "travail": (
                    "Sur une position, trouver la menace adverse "
                    "avant de chercher ton meilleur coup."
                ),
            },
            {
                "jour": "Après une partie",
                "travail": (
                    "Reprendre chaque erreur et écrire : "
                    "« Ce que l'adversaire voulait faire »."
                ),
            },
        ]

    # --------------------------------------------------------
    # PIÈCES EN PRISE
    # --------------------------------------------------------

    if priority in {
        "Pièces non défendues",
        "Pièce en prise",
    }:

        return [
            {
                "jour": "Chaque coup",
                "travail": (
                    "Vérifier les pièces adverses attaquées "
                    "et tes propres pièces attaquées."
                ),
            },
            {
                "jour": "10 min",
                "travail": (
                    "Exercices de pièces en prise et attaques doubles."
                ),
            },
            {
                "jour": "Après une partie",
                "travail": (
                    "Repérer les moments où une pièce est devenue "
                    "non défendue."
                ),
            },
        ]

    # --------------------------------------------------------
    # FOURCHETTES
    # --------------------------------------------------------

    if priority == "Fourchette":

        return [
            {
                "jour": "10 min",
                "travail": (
                    "Exercices de fourchettes de cavalier."
                ),
            },
            {
                "jour": "Chaque partie",
                "travail": (
                    "Chercher les cases où un cavalier pourrait "
                    "attaquer roi + dame ou deux pièces."
                ),
            },
            {
                "jour": "Après une partie",
                "travail": (
                    "Identifier les occasions de fourchette "
                    "manquées par les deux camps."
                ),
            },
        ]

    # --------------------------------------------------------
    # CLOUAGE
    # --------------------------------------------------------

    if priority == "Clouage":

        return [
            {
                "jour": "10 min",
                "travail": (
                    "Exercices de clouages absolus et relatifs."
                ),
            },
            {
                "jour": "Chaque partie",
                "travail": (
                    "Chercher les pièces placées devant le roi "
                    "ou une pièce de grande valeur."
                ),
            },
        ]

    # --------------------------------------------------------
    # PLAN GÉNÉRAL
    # --------------------------------------------------------

    return [
        {
            "jour": "Chaque partie",
            "travail": (
                "Avant ton coup, identifier la menace adverse."
            ),
        },
        {
            "jour": "10 min",
            "travail": (
                "Faire quelques exercices tactiques "
                "sans déplacer les pièces."
            ),
        },
        {
            "jour": "Après une partie",
            "travail": (
                "Analyser les moments critiques avant de "
                "consulter le moteur."
            ),
        },
    ]


# ============================================================
# RAPPORT GLOBAL
# ============================================================

def build_coach_report(
    analyses,
    games_df,
):
    """
    Construit le rapport du Coach 1500 sur l'ensemble
    des parties analysées.
    """

    profile = empty_coach_profile()

    # --------------------------------------------------------
    # AGRÉGATION
    # --------------------------------------------------------

    for index, analysis in enumerate(
        analyses
    ):

        if analysis is None:
            continue

        if index < len(
            games_df
        ):

            result = games_df.iloc[
                index
            ][
                "Résultat"
            ]

        else:

            result = "Inconnue"

        profile = add_game_to_coach_profile(
            profile,
            analysis,
            result,
        )

    profile = finalize_coach_statistics(
        profile
    )

    profile = aggregate_critical_phases(
        profile,
        analyses,
    )

    # --------------------------------------------------------
    # PRIORITÉS
    # --------------------------------------------------------

    priorities = calculate_theme_priority(
        profile
    )

    profile[
        "priority_scores"
    ] = priorities

    strengths = identify_strengths(
        profile
    )

    weaknesses = identify_weaknesses(
        profile,
        priorities,
    )

    profile[
        "strengths"
    ] = strengths

    profile[
        "weaknesses"
    ] = weaknesses

    main_priority = choose_main_priority(
        profile,
        weaknesses,
    )

    profile[
        "main_priority"
    ] = main_priority

    profile[
        "training_plan"
    ] = build_training_plan(
        main_priority,
        profile,
    )

    return profile


# ============================================================
# SCORE DE STABILITÉ
# ============================================================

def calculate_stability_score(
    profile,
):
    """
    Score pédagogique de stabilité.

    Ce n'est PAS un Elo.
    Il sert uniquement à suivre l'évolution interne
    du joueur dans l'application.
    """

    score = 100.0

    score -= (
        profile[
            "gaffes_per_game"
        ]
        * 15
    )

    score -= (
        profile[
            "errors_per_game"
        ]
        * 6
    )

    score -= (
        profile[
            "inaccuracies_per_game"
        ]
        * 2
    )

    return round(
        max(
            0,
            min(
                100,
                score,
            ),
        ),
        1,
    )


# ============================================================
# MESSAGE DU COACH
# ============================================================

def generate_coach_message(
    profile,
):
    """
    Génère le message principal du coach.

    Le message doit rester concret.
    """

    games = profile[
        "games_analyzed"
    ]

    if games == 0:

        return (
            "Pas encore assez de parties analysées."
        )

    priority = profile[
        "main_priority"
    ][
        "name"
    ]

    reason = profile[
        "main_priority"
    ][
        "reason"
    ]

    if priority == "Gaffes tactiques":

        opening = (
            "Ta priorité actuelle est la sécurité tactique. "
        )

    elif priority == "Calcul défensif":

        opening = (
            "Ta priorité actuelle est le calcul défensif. "
        )

    elif priority in {
        "Pièces non défendues",
        "Pièce en prise",
    }:

        opening = (
            "Ta priorité actuelle est la protection "
            "de tes pièces. "
        )

    else:

        opening = (
            f"Ta priorité actuelle est : {priority}. "
        )

    return (
        f"Après l'analyse de {games} parties, "
        f"{opening}{reason}"
    )


# ============================================================
# COMPARAISON DE DEUX GROUPES DE PARTIES
# ============================================================

def compare_coach_profiles(
    recent_profile,
    previous_profile,
):
    """
    Compare deux périodes.

    Exemple :

        10 dernières parties
        VS
        10 précédentes

    Cette fonction prépare la mémoire du coach.
    """

    if not previous_profile:

        return {
            "available": False
        }

    comparison = {}

    # --------------------------------------------------------
    # GAFFES
    # --------------------------------------------------------

    comparison[
        "gaffes_per_game"
    ] = round(
        recent_profile[
            "gaffes_per_game"
        ]
        - previous_profile[
            "gaffes_per_game"
        ],
        2,
    )

    # --------------------------------------------------------
    # ERREURS
    # --------------------------------------------------------

    comparison[
        "errors_per_game"
    ] = round(
        recent_profile[
            "errors_per_game"
        ]
        - previous_profile[
            "errors_per_game"
        ],
        2,
    )

    # --------------------------------------------------------
    # ACPL
    # --------------------------------------------------------

    comparison[
        "acpl"
    ] = round(
        recent_profile[
            "average_acpl"
        ]
        - previous_profile[
            "average_acpl"
        ],
        2,
    )

    # --------------------------------------------------------
    # STABILITÉ
    # --------------------------------------------------------

    recent_stability = (
        calculate_stability_score(
            recent_profile
        )
    )

    previous_stability = (
        calculate_stability_score(
            previous_profile
        )
    )

    comparison[
        "stability"
    ] = round(
        recent_stability
        - previous_stability,
        1,
    )

    # --------------------------------------------------------
    # INTERPRÉTATION
    # --------------------------------------------------------

    messages = []

    if comparison[
        "gaffes_per_game"
    ] < 0:

        messages.append(
            "Tu fais moins de grosses gaffes."
        )

    elif comparison[
        "gaffes_per_game"
    ] > 0:

        messages.append(
            "Le nombre de grosses gaffes augmente."
        )

    if comparison[
        "acpl"
    ] < 0:

        messages.append(
            "La perte moyenne par coup diminue."
        )

    elif comparison[
        "acpl"
    ] > 0:

        messages.append(
            "La perte moyenne par coup augmente."
        )

    if comparison[
        "stability"
    ] > 0:

        messages.append(
            "Ta stabilité globale progresse."
        )

    elif comparison[
        "stability"
    ] < 0:

        messages.append(
            "Ta stabilité globale recule."
        )

    if not messages:

        messages.append(
            "La tendance générale est relativement stable."
        )

    comparison[
        "messages"
    ] = messages

    comparison[
        "available"
    ] = True

    return comparison


# ============================================================
# AFFICHAGE DU PROFIL
# ============================================================

def display_coach_profile(
    profile,
):
    """
    Affiche le tableau de bord du Coach 1500.
    """

    st.markdown("---")

    st.subheader(
        "🧠 Coach personnel"
    )

    # --------------------------------------------------------
    # MESSAGE
    # --------------------------------------------------------

    st.info(
        generate_coach_message(
            profile
        )
    )

    # --------------------------------------------------------
    # INDICATEURS
    # --------------------------------------------------------

    c1, c2, c3, c4, c5 = st.columns(
        5
    )

    c1.metric(
        "Parties",
        profile[
            "games_analyzed"
        ],
    )

    c2.metric(
        "ACPL moyen",
        profile[
            "average_acpl"
        ],
    )

    c3.metric(
        "Gaffes / partie",
        profile[
            "gaffes_per_game"
        ],
    )

    c4.metric(
        "Erreurs / partie",
        profile[
            "errors_per_game"
        ],
    )

    c5.metric(
        "Stabilité",
        f"{calculate_stability_score(profile)}%",
    )

    # --------------------------------------------------------
    # PRIORITÉ
    # --------------------------------------------------------

    st.markdown(
        "### 🎯 Priorité actuelle"
    )

    priority = profile[
        "main_priority"
    ]

    st.warning(
        f"**{priority['name']}**\n\n"
        f"{priority['reason']}"
    )

    # --------------------------------------------------------
    # FORCES / FAIBLESSES
    # --------------------------------------------------------

    col_strengths, col_weaknesses = st.columns(
        2
    )

    with col_strengths:

        st.markdown(
            "### 🟢 Points forts"
        )

        if profile[
            "strengths"
        ]:

            for strength in profile[
                "strengths"
            ]:

                st.success(
                    f"**{strength['name']}** — "
                    f"{strength['description']}"
                )

        else:

            st.write(
                "Pas encore suffisamment de données."
            )

    with col_weaknesses:

        st.markdown(
            "### 🔴 Points faibles"
        )

        if profile[
            "weaknesses"
        ]:

            for weakness in profile[
                "weaknesses"
            ]:

                st.error(
                    f"**{weakness['name']}** "
                    f"({weakness['severity']}) — "
                    f"{weakness['description']}"
                )

        else:

            st.write(
                "Aucune faiblesse dominante détectée."
            )

    # --------------------------------------------------------
    # THÈMES
    # --------------------------------------------------------

    st.markdown(
        "### ♟️ Thèmes rencontrés"
    )

    if profile[
        "themes"
    ]:

        theme_df = pd.DataFrame(
            [
                {
                    "Thème": theme,
                    "Occurrences": count,
                }
                for theme, count
                in profile[
                    "themes"
                ].most_common()
            ]
        )

        st.dataframe(
            theme_df,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.write(
            "Aucun thème tactique récurrent détecté."
        )

    # --------------------------------------------------------
    # PHASES
    # --------------------------------------------------------

    if profile.get(
        "critical_phases"
    ):

        st.markdown(
            "### 📚 Phases où apparaissent les erreurs critiques"
        )

        phase_df = pd.DataFrame(
            [
                {
                    "Phase": phase,
                    "Erreurs critiques": count,
                }
                for phase, count
                in profile[
                    "critical_phases"
                ].most_common()
            ]
        )

        st.dataframe(
            phase_df,
            use_container_width=True,
            hide_index=True,
        )

    # --------------------------------------------------------
    # PLAN
    # --------------------------------------------------------

    st.markdown(
        "### 🏋️ Plan d'entraînement"
    )

    for item in profile[
        "training_plan"
    ]:

        st.markdown(
            f"**{item['jour']}** → "
            f"{item['travail']}"
        )


# ============================================================
# FIN PARTIE 4
# ============================================================

st.markdown("---")

st.caption(
    "🎯 Profil Coach 1500 prêt : "
    "forces, faiblesses, priorités et entraînement."
)
# ============================================================
# COACH CHESS 1500 V2
# PARTIE 5/6
# INTERFACE D'ANALYSE
# ============================================================


# ============================================================
# CACHE DES ANALYSES
# ============================================================

def get_game_analysis(
    games_df,
    selected_index,
):
    """
    Analyse une partie et conserve le résultat dans
    st.session_state.

    Ainsi, déplacer le slider ne relance pas Stockfish.
    """

    if selected_index < 0:
        return None

    if selected_index >= len(games_df):
        return None

    row = games_df.iloc[
        selected_index
    ]

    cache = st.session_state.setdefault(
        "game_analyses",
        {},
    )

    game_id = (
        f"{row['Plateforme']}_"
        f"{row['ID']}_"
        f"{row['Adversaire']}"
    )

    # --------------------------------------------------------
    # ANALYSE DÉJÀ DISPONIBLE
    # --------------------------------------------------------

    if game_id in cache:
        return cache[
            game_id
        ]

    pgn = row.get(
        "PGN",
        "",
    )

    if not pgn:
        return None

    is_user_white = (
        row[
            "Couleur"
        ]
        == "Blancs"
    )

    # --------------------------------------------------------
    # ANALYSE STOCKFISH
    # --------------------------------------------------------

    with st.spinner(
        "♟️ Analyse de la partie avec Stockfish..."
    ):

        analysis = analyze_game_with_engine(
            pgn,
            is_user_white,
        )

    if not analysis:
        return None

    # --------------------------------------------------------
    # COACHING PÉDAGOGIQUE
    # --------------------------------------------------------

    with st.spinner(
        "🧠 Construction du diagnostic pédagogique..."
    ):

        analysis = finalize_game_analysis(
            analysis,
            is_user_white,
        )

    cache[
        game_id
    ] = analysis

    return analysis


# ============================================================
# AFFICHAGE D'UNE JAUGE DE QUALITÉ
# ============================================================

def display_move_quality(
    move_data,
):
    """
    Affiche une synthèse visuelle de la qualité du coup.
    """

    category = move_data.get(
        "category",
        "Inconnue",
    )

    icon = move_data.get(
        "icon",
        "⚪",
    )

    loss = move_data.get(
        "loss",
        0,
    )

    st.markdown(
        f"### {icon} {category}"
    )

    if loss <= 0.20:

        st.success(
            "Perte d'évaluation négligeable."
        )

    elif loss <= 0.50:

        st.info(
            f"Perte estimée : **{loss:.2f} pion**."
        )

    elif loss <= 1.00:

        st.warning(
            f"Perte estimée : **{loss:.2f} pion**. "
            "Le coup mérite d'être compris."
        )

    elif loss <= 2.00:

        st.warning(
            f"Perte estimée : **{loss:.2f} pions**. "
            "C'est une erreur importante."
        )

    else:

        st.error(
            f"Perte estimée : **{loss:.2f} pions**. "
            "Moment critique de la partie."
        )


# ============================================================
# AFFICHAGE DES MENACES
# ============================================================

def display_threats(
    threats,
):
    """
    Affiche les menaces identifiées avant le coup.
    """

    st.markdown(
        "### ⚠️ Ce que l'adversaire menaçait"
    )

    if not threats:

        st.write(
            "Aucune menace immédiate suffisamment claire "
            "n'a été détectée."
        )

        return

    for threat in threats:

        st.markdown(
            f"- ⚠️ {threat}"
        )


# ============================================================
# AFFICHAGE DES CONSÉQUENCES
# ============================================================

def display_consequences(
    consequences,
):
    """
    Affiche les conséquences concrètes du coup.
    """

    st.markdown(
        "### 🔎 Conséquences de ton coup"
    )

    if not consequences:

        st.write(
            "Aucune conséquence concrète supplémentaire "
            "n'a été identifiée."
        )

        return

    for consequence in consequences:

        st.markdown(
            f"- {consequence}"
        )


# ============================================================
# AFFICHAGE DES THÈMES TACTIQUES
# ============================================================

def display_tactical_themes(
    themes,
):
    """
    Affiche les thèmes tactiques détectés.
    """

    st.markdown(
        "### ♟️ Thèmes tactiques"
    )

    if not themes:

        st.write(
            "Aucun thème tactique suffisamment clair "
            "n'a été détecté sur ce coup."
        )

        return

    for theme in themes:

        name = theme.get(
            "theme",
            "Thème inconnu",
        )

        if name == "Fourchette":

            targets = theme.get(
                "targets",
                [],
            )

            target_names = []

            for target in targets:

                target_names.append(
                    f"{piece_name(target['piece'])} "
                    f"en {square_name(target['square'])}"
                )

            description = (
                "Une même pièce attaque plusieurs cibles."
            )

            if target_names:

                description += (
                    " Cibles : "
                    + ", ".join(
                        target_names
                    )
                )

        elif name == "Clouage":

            description = (
                "Une pièce adverse est limitée dans son "
                "déplacement car elle protège une pièce "
                "plus importante ou le roi."
            )

        elif name == "Attaque double":

            threats = theme.get(
                "threats",
                [],
            )

            description = (
                "Le coup crée simultanément plusieurs menaces."
            )

            if threats:

                description += (
                    " Menaces : "
                    + ", ".join(
                        threats
                    )
                )

        elif name == "Attaque à la découverte":

            description = (
                "Le déplacement d'une pièce libère une ligne "
                "d'attaque d'une autre pièce."
            )

        elif name == "Pièce en prise":

            square = square_name(
                theme.get(
                    "square"
                )
            )

            piece = theme.get(
                "piece"
            )

            description = (
                f"Le {piece_name(piece)} en {square} "
                "devient vulnérable."
            )

        else:

            description = (
                "Motif tactique détecté."
            )

        st.warning(
            f"**{name}** — {description}"
        )


# ============================================================
# AFFICHAGE DES PRINCIPES
# ============================================================

def display_principles(
    principles,
):
    """
    Affiche les principes stratégiques pertinents.
    """

    if not principles:
        return

    st.markdown(
        "### 📚 Principes à retenir"
    )

    for principle in principles:

        st.markdown(
            f"- 💡 {principle}"
        )


# ============================================================
# AFFICHAGE DU PLAN
# ============================================================

def display_plan(
    plan,
):
    """
    Affiche les idées de plan après le meilleur coup.
    """

    st.markdown(
        "### 🧭 Et après ?"
    )

    if not plan:

        st.write(
            "Aucun plan suffisamment fiable n'a été déduit."
        )

        return

    for index, idea in enumerate(
        plan,
        1,
    ):

        st.markdown(
            f"**{index}.** {idea}"
        )


# ============================================================
# AFFICHAGE DU RAPPORT COACH
# ============================================================

def display_coaching_report(
    report,
):
    """
    Affiche le rapport pédagogique complet d'un coup.
    """

    if not report:
        return

    # --------------------------------------------------------
    # CONFIANCE
    # --------------------------------------------------------

    confidence = report.get(
        "confidence",
        "Inconnue",
    )

    st.caption(
        f"Fiabilité du diagnostic automatique : **{confidence}**"
    )

    # --------------------------------------------------------
    # INTENTION
    # --------------------------------------------------------

    st.markdown(
        "### 🎯 Ton intention probable"
    )

    st.info(
        report.get(
            "intention",
            "Intention non déterminée.",
        )
    )

    # --------------------------------------------------------
    # MENACES
    # --------------------------------------------------------

    display_threats(
        report.get(
            "opponent_threats",
            [],
        )
    )

    # --------------------------------------------------------
    # PROBLÈME
    # --------------------------------------------------------

    st.markdown(
        "### ❓ Pourquoi ce coup pose problème"
    )

    st.error(
        report.get(
            "problem",
            "Aucune explication disponible.",
        )
    )

    # --------------------------------------------------------
    # CONSÉQUENCES
    # --------------------------------------------------------

    display_consequences(
        report.get(
            "consequences",
            [],
        )
    )

    # --------------------------------------------------------
    # MEILLEUR COUP
    # --------------------------------------------------------

    best_move = report.get(
        "best_move",
        "-",
    )

    st.markdown(
        "### 💡 Meilleur choix"
    )

    st.success(
        f"**{best_move}**"
    )

    st.write(
        report.get(
            "best_explanation",
            "Explication indisponible.",
        )
    )

    # --------------------------------------------------------
    # PLAN
    # --------------------------------------------------------

    display_plan(
        report.get(
            "plan",
            [],
        )
    )

    # --------------------------------------------------------
    # TACTIQUE
    # --------------------------------------------------------

    display_tactical_themes(
        report.get(
            "themes",
            [],
        )
    )

    # --------------------------------------------------------
    # STRATÉGIE
    # --------------------------------------------------------

    display_principles(
        report.get(
            "principles",
            [],
        )
    )

    # --------------------------------------------------------
    # LEÇON
    # --------------------------------------------------------

    st.markdown(
        "### 🧠 La leçon à retenir"
    )

    st.success(
        report.get(
            "lesson",
            "Aucune leçon disponible.",
        )
    )


# ============================================================
# AFFICHAGE DU PLATEAU
# ============================================================

def build_board_for_ply(
    analysis,
    current_ply,
):
    """
    Construit la position correspondant au slider.

    Retourne :

        board
        move_data
    """

    if current_ply <= 0:

        return (
            chess.Board(
                chess.STARTING_FEN
            ),
            None,
        )

    history = analysis[
        "history"
    ]

    if current_ply > len(history):

        current_ply = len(history)

    move_data = history[
        current_ply - 1
    ]

    board = chess.Board(
        move_data[
            "fen_after"
        ]
    )

    return (
        board,
        move_data,
    )


# ============================================================
# FLÈCHES DU PLATEAU
# ============================================================

def build_board_arrows(
    analysis,
    current_ply,
):
    """
    Construit les flèches :

        🔵 / 🟠 / 🔴 = coup joué
        🟢 = meilleur coup Stockfish
    """

    arrows = []

    if current_ply <= 0:

        return arrows

    history = analysis[
        "history"
    ]

    if current_ply > len(history):

        return arrows

    move_data = history[
        current_ply - 1
    ]

    # --------------------------------------------------------
    # COUP JOUÉ
    # --------------------------------------------------------

    arrows.append(
        chess.svg.Arrow(
            move_data[
                "from_sq"
            ],
            move_data[
                "to_sq"
            ],
            color=move_data.get(
                "arrow_color",
                "#3498db",
            ),
        )
    )

    # --------------------------------------------------------
    # MEILLEUR COUP
    # --------------------------------------------------------

    best_move = move_data.get(
        "best_move",
        "-",
    )

    if best_move and best_move != "-":

        try:

            previous_board = chess.Board(
                move_data[
                    "fen_before"
                ]
            )

            best_move_obj = (
                previous_board.parse_san(
                    best_move
                )
            )

            arrows.append(
                chess.svg.Arrow(
                    best_move_obj.from_square,
                    best_move_obj.to_square,
                    color="#2ecc71",
                )
            )

        except Exception:

            pass

    return arrows


# ============================================================
# NAVIGATION
# ============================================================

def set_current_ply(
    key,
    value,
):
    """
    Callback pour positionner le slider.
    """

    st.session_state[
        key
    ] = value


def change_current_ply(
    key,
    delta,
    maximum,
):
    """
    Callback précédent / suivant.
    """

    current = st.session_state.get(
        key,
        0,
    )

    st.session_state[
        key
    ] = max(
        0,
        min(
            maximum,
            current + delta,
        ),
    )


# ============================================================
# AFFICHAGE DE L'ANALYSE D'UNE PARTIE
# ============================================================

def display_game_analysis(
    games_df,
    selected_index,
):
    """
    Interface complète d'une partie.
    """

    if selected_index < 0:
        return

    if selected_index >= len(
        games_df
    ):
        return

    game_row = games_df.iloc[
        selected_index
    ]

    # --------------------------------------------------------
    # INFORMATIONS PARTIE
    # --------------------------------------------------------

    st.markdown("---")

    st.subheader(
        "♟️ Analyse détaillée"
    )

    info1, info2, info3, info4 = st.columns(
        4
    )

    info1.metric(
        "Résultat",
        game_row[
            "Résultat"
        ],
    )

    info2.metric(
        "Couleur",
        game_row[
            "Couleur"
        ],
    )

    info3.metric(
        "Adversaire",
        str(
            game_row[
                "Adversaire"
            ]
        ),
    )

    info4.metric(
        "Elo adverse",
        str(
            game_row[
                "Elo Adversaire"
            ]
        ),
    )

    st.caption(
        f"Ouverture : {game_row['Ouverture']} "
        f"| Plateforme : {game_row['Plateforme']}"
    )

    # --------------------------------------------------------
    # ANALYSE
    # --------------------------------------------------------

    analysis = get_game_analysis(
        games_df,
        selected_index,
    )

    if not analysis:

        st.error(
            "Impossible d'analyser cette partie."
        )

        return

    # --------------------------------------------------------
    # STATISTIQUES
    # --------------------------------------------------------

    stats = analysis[
        "user_stats"
    ]

    st.markdown(
        "### 📊 Performance dans cette partie"
    )

    m1, m2, m3, m4, m5 = st.columns(
        5
    )

    m1.metric(
        "Précision estimée",
        f"{stats.get('precision', 0):.1f}%",
    )

    m2.metric(
        "ACPL",
        f"{stats.get('acpl', 0):.2f}",
    )

    m3.metric(
        "🔴 Gaffes",
        stats.get(
            "gaffes",
            0,
        ),
    )

    m4.metric(
        "🟠 Erreurs",
        stats.get(
            "erreurs",
            0,
        ),
    )

    m5.metric(
        "🟡 Inexactitudes",
        stats.get(
            "inexactitudes",
            0,
        ),
    )

    # --------------------------------------------------------
    # DIAGNOSTIC DE PARTIE
    # --------------------------------------------------------

    diagnosis = analysis.get(
        "game_diagnosis",
        {},
    )

    if diagnosis:

        st.markdown(
            "### 🔍 Diagnostic de la partie"
        )

        messages = diagnosis.get(
            "diagnosis",
            [],
        )

        for message in messages:

            st.write(
                f"• {message}"
            )

    # --------------------------------------------------------
    # LAYOUT PLATEAU / COACH
    # --------------------------------------------------------

    col_board, col_coach = st.columns(
        [1.1, 1.4]
    )

    move_key = (
        f"current_ply_"
        f"{game_row['Plateforme']}_"
        f"{game_row['ID']}"
    )

    maximum = analysis[
        "total_plies"
    ]

    if move_key not in st.session_state:

        st.session_state[
            move_key
        ] = 0

    # ========================================================
    # PLATEAU
    # ========================================================

    with col_board:

        st.markdown(
            "### ♟️ Échiquier"
        )

        # ----------------------------------------------------
        # BOUTONS
        # ----------------------------------------------------

        b1, b2, b3, b4 = st.columns(
            4
        )

        with b1:

            st.button(
                "⏮️",
                key=f"start_{move_key}",
                use_container_width=True,
                on_click=set_current_ply,
                args=(
                    move_key,
                    0,
                ),
            )

        with b2:

            st.button(
                "◀️",
                key=f"prev_{move_key}",
                use_container_width=True,
                on_click=change_current_ply,
                args=(
                    move_key,
                    -1,
                    maximum,
                ),
            )

        with b3:

            st.button(
                "▶️",
                key=f"next_{move_key}",
                use_container_width=True,
                on_click=change_current_ply,
                args=(
                    move_key,
                    1,
                    maximum,
                ),
            )

        with b4:

            st.button(
                "⏭️",
                key=f"end_{move_key}",
                use_container_width=True,
                on_click=set_current_ply,
                args=(
                    move_key,
                    maximum,
                ),
            )

        # ----------------------------------------------------
        # SLIDER
        # ----------------------------------------------------

        current_ply = st.slider(
            "Coup par coup",
            min_value=0,
            max_value=maximum,
            key=move_key,
        )

        # ----------------------------------------------------
        # POSITION
        # ----------------------------------------------------

        board, move_data = (
            build_board_for_ply(
                analysis,
                current_ply,
            )
        )

        arrows = build_board_arrows(
            analysis,
            current_ply,
        )

        orientation = (
            chess.WHITE
            if game_row[
                "Couleur"
            ]
            == "Blancs"
            else chess.BLACK
        )

        svg_board = chess.svg.board(
            board=board,
            orientation=orientation,
            arrows=arrows,
            size=500,
        )

        st.image(
            svg_board,
            use_container_width=False,
        )

        st.caption(
            "🟢 Meilleur coup Stockfish"
            " | 🔵 Bon coup"
            " | 🟡 Inexactitude"
            " | 🟠 Erreur"
            " | 🔴 Gaffe"
        )

        # ----------------------------------------------------
        # POSITION
        # ----------------------------------------------------

        if current_ply == 0:

            st.info(
                "Position initiale de la partie."
            )

        else:

            st.caption(
                f"Demi-coup {current_ply} / "
                f"{maximum}"
            )

    # ========================================================
    # COACH
    # ========================================================

    with col_coach:

        st.markdown(
            "### 🧠 Ton coach"
        )

        if current_ply == 0:

            st.info(
                "Commence la partie avec ▶️ pour "
                "voir les décisions critiques."
            )

        elif move_data is None:

            st.info(
                "Aucune donnée disponible."
            )

        elif not move_data[
            "is_user_turn"
        ]:

            # ------------------------------------------------
            # COUP ADVERSAIRE
            # ------------------------------------------------

            st.markdown(
                f"**Coup de l'adversaire :** "
                f"`{move_data['san']}`"
            )

            st.info(
                "Le coach ne note pas le coup de l'adversaire. "
                "Il l'utilise uniquement pour comprendre "
                "la menace et expliquer ta décision suivante."
            )

            st.markdown(
                "### 👀 À surveiller"
            )

            context = move_data.get(
                "context_before",
                {},
            )

            user_color = (
                chess.WHITE
                if game_row[
                    "Couleur"
                ]
                == "Blancs"
                else chess.BLACK
            )

            board_after = chess.Board(
                move_data[
                    "fen_after"
                ]
            )

            threats = immediate_threats(
                board_after,
                not board_after.turn,
            )

            if threats:

                for threat in threats[:4]:

                    st.write(
                        f"⚠️ {threat}"
                    )

            else:

                st.write(
                    "Aucune menace immédiate clairement "
                    "identifiée."
                )

            st.caption(
                "Passe au coup suivant pour voir comment "
                "le coach évalue ta réponse."
            )

        else:

            # ------------------------------------------------
            # COUP DU JOUEUR
            # ------------------------------------------------

            st.markdown(
                f"**Ton coup :** "
                f"`{move_data['san']}`"
            )

            st.caption(
                f"Phase : **{move_data['phase']}**"
            )

            display_move_quality(
                move_data
            )

            # ------------------------------------------------
            # RAPPORT
            # ------------------------------------------------

            history_index = (
                current_ply - 1
            )

            report = analysis.get(
                "coaching",
                {},
            ).get(
                history_index
            )

            if report:

                display_coaching_report(
                    report
                )

            else:

                st.success(
                    "Aucune erreur importante détectée "
                    "sur ce coup."
                )

                st.write(
                    "Le moteur considère ce coup comme suffisamment "
                    "bon pour ne pas nécessiter un diagnostic "
                    "pédagogique détaillé."
                )

            # ------------------------------------------------
            # ÉVALUATION
            # ------------------------------------------------

            st.markdown(
                "### 📈 Évaluation"
            )

            eval_before = (
                move_data.get(
                    "eval_before_player",
                    0,
                )
            )

            eval_after = (
                move_data.get(
                    "eval_after_player",
                    0,
                )
            )

            e1, e2 = st.columns(
                2
            )

            e1.metric(
                "Avant",
                f"{eval_before:+.2f}",
            )

            e2.metric(
                "Après",
                f"{eval_after:+.2f}",
            )

    # ========================================================
    # COURBE
    # ========================================================

    st.markdown("---")

    st.subheader(
        "📈 Évolution de la position"
    )

    history_df = pd.DataFrame(
        analysis[
            "history"
        ]
    )

    if not history_df.empty:

        fig = px.line(
            history_df,
            x="ply",
            y="eval_perspective",
            labels={
                "ply": "Demi-coup",
                "eval_perspective":
                    "Évaluation du point de vue du joueur",
            },
            markers=True,
        )

        fig.add_hline(
            y=0,
            line_dash="dash",
        )

        fig.update_layout(
            height=400,
            margin=dict(
                l=20,
                r=20,
                t=40,
                b=20,
            ),
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )


# FIN PARTIE 5
# ============================================================

st.markdown("---")

st.caption(
    "♟️ Analyse interactive prête. "
    "Le bilan longitudinal et la progression vers 1500 Elo "
    "seront ajoutés dans la PARTIE 6."
)
# ============================================================
# COACH CHESS 1500 V2
# PARTIE 6/6
# TABLEAU DE BORD — OBJECTIF 1500
# ============================================================


# ============================================================
# INITIALISATION DU PROFIL PERSISTANT
# ============================================================

def initialize_coach_memory():
    """
    Initialise la mémoire du coach dans session_state.

    Cette mémoire permet de conserver :
        - l'objectif Elo
        - le profil courant
        - l'ancien profil
        - la priorité précédente
        - l'historique des diagnostics
    """

    if "coach_memory" not in st.session_state:

        st.session_state[
            "coach_memory"
        ] = {
            "target_elo": 1500,
            "current_profile": None,
            "previous_profile": None,
            "previous_priority": None,
            "history": [],
        }


initialize_coach_memory()


# ============================================================
# OBJECTIF DU JOUEUR
# ============================================================

def display_coach_goal():
    """
    Permet de définir l'objectif Elo.
    """

    memory = st.session_state[
        "coach_memory"
    ]

    st.markdown("---")

    st.subheader(
        "🎯 Ton objectif"
    )

    col1, col2 = st.columns(
        [1, 2]
    )

    with col1:

        target_elo = st.number_input(
            "Elo objectif",
            min_value=800,
            max_value=2500,
            value=int(
                memory.get(
                    "target_elo",
                    1500,
                )
            ),
            step=50,
        )

        memory[
            "target_elo"
        ] = target_elo

    with col2:

        st.info(
            f"Le coach est actuellement configuré pour "
            f"t'accompagner vers **{target_elo} Elo**."
        )

    return target_elo


# ============================================================
# CONVERSION DES DONNÉES EN PROFIL COACH
# ============================================================

def build_current_coach_profile(
    games_df,
):
    """
    Analyse toutes les parties actuellement disponibles
    et construit le profil global du joueur.
    """

    analyses = []

    cache = st.session_state.get(
        "game_analyses",
        {},
    )

    # --------------------------------------------------------
    # RÉCUPÉRATION DES ANALYSES EXISTANTES
    # --------------------------------------------------------

    for index in range(
        len(games_df)
    ):

        row = games_df.iloc[
            index
        ]

        game_id = (
            f"{row['Plateforme']}_"
            f"{row['ID']}_"
            f"{row['Adversaire']}"
        )

        analysis = cache.get(
            game_id
        )

        if analysis:

            analyses.append(
                analysis
            )

        else:

            analyses.append(
                None
            )

    # --------------------------------------------------------
    # CONSTRUCTION DU PROFIL
    # --------------------------------------------------------

    profile = build_coach_report(
        analyses,
        games_df,
    )

    return profile


# ============================================================
# NOMBRE D'ANALYSES DISPONIBLES
# ============================================================

def count_available_analyses(
    games_df,
):
    """
    Compte les parties réellement analysées.
    """

    cache = st.session_state.get(
        "game_analyses",
        {},
    )

    count = 0

    for index in range(
        len(games_df)
    ):

        row = games_df.iloc[
            index
        ]

        game_id = (
            f"{row['Plateforme']}_"
            f"{row['ID']}_"
            f"{row['Adversaire']}"
        )

        if game_id in cache:
            count += 1

    return count


# ============================================================
# PROGRESSION VERS L'OBJECTIF
# ============================================================

def display_goal_progress(
    target_elo,
    current_elo,
):
    """
    Affiche la progression Elo.

    L'Elo n'est jamais inventé par le coach.
    Si la plateforme ne fournit pas l'Elo du joueur,
    l'interface indique simplement que cette donnée
    n'est pas disponible.
    """

    st.markdown(
        "### 📈 Progression vers l'objectif"
    )

    if current_elo is None:

        st.warning(
            "L'Elo actuel du joueur n'est pas disponible "
            "dans les données chargées."
        )

        st.caption(
            f"Objectif enregistré : {target_elo} Elo."
        )

        return

    try:

        current_elo = int(
            current_elo
        )

    except Exception:

        st.warning(
            "Impossible de déterminer l'Elo actuel."
        )

        return

    difference = (
        target_elo
        - current_elo
    )

    if target_elo <= current_elo:

        st.success(
            f"🎯 Objectif de {target_elo} Elo atteint "
            f"ou dépassé."
        )

        progress = 1.0

    else:

        # ----------------------------------------------------
        # BASE DE PROGRESSION
        # ----------------------------------------------------

        # On utilise 800 Elo comme référence basse
        # uniquement pour construire une jauge visuelle.

        base = 800

        progress = (
            current_elo - base
        ) / (
            target_elo - base
        )

        progress = max(
            0.0,
            min(
                1.0,
                progress,
            ),
        )

        st.write(
            f"**{current_elo} → {target_elo} Elo**"
        )

        st.progress(
            progress
        )

        st.caption(
            f"Il reste environ {difference} Elo "
            "pour atteindre l'objectif."
        )


# ============================================================
# RÉCUPÉRATION DE L'ELO
# ============================================================

def get_current_player_elo(
    games_df,
):
    """
    Cherche l'Elo du joueur dans les données.

    On utilise les colonnes disponibles sans inventer
    de valeur.
    """

    possible_columns = [
        "Elo",
        "Elo Joueur",
        "Rating",
        "Elo actuel",
    ]

    for column in possible_columns:

        if column in games_df.columns:

            values = (
                games_df[column]
                .dropna()
                .tolist()
            )

            if values:

                try:

                    return int(
                        values[-1]
                    )

                except Exception:

                    pass

    return None


# ============================================================
# PRIORITÉ ET PROGRESSION
# ============================================================

def display_priority_evolution(
    profile,
):
    """
    Affiche la priorité actuelle et compare avec
    la priorité précédente si disponible.
    """

    current_priority = profile.get(
        "main_priority",
        {},
    ).get(
        "name",
        "Calcul et vérification",
    )

    previous = st.session_state[
        "coach_memory"
    ].get(
        "previous_priority"
    )

    st.markdown(
        "### 🧠 Évolution du coaching"
    )

    if previous:

        if previous == current_priority:

            st.info(
                f"Le problème prioritaire reste "
                f"**{current_priority}**."
            )

            st.write(
                "Cela signifie que le coach considère "
                "que cette compétence mérite encore "
                "un travail spécifique."
            )

        else:

            st.success(
                f"🔄 La priorité a changé : "
                f"**{previous}** → **{current_priority}**."
            )

            st.write(
                "C'est un signal intéressant : le coach "
                "considère que le problème précédent est "
                "moins prioritaire ou qu'un autre problème "
                "est désormais plus important."
            )

    else:

        st.info(
            f"Première priorité enregistrée : "
            f"**{current_priority}**."
        )


# ============================================================
# COMPARAISON AVEC LE PROFIL PRÉCÉDENT
# ============================================================

def display_longitudinal_comparison(
    current_profile,
):
    """
    Compare le profil actuel avec le profil précédent.
    """

    previous_profile = (
        st.session_state[
            "coach_memory"
        ].get(
            "previous_profile"
        )
    )

    if not previous_profile:

        st.markdown(
            "### 📊 Évolution"
        )

        st.info(
            "Le coach vient de créer son premier profil. "
            "Une seconde analyse permettra de mesurer "
            "la progression dans le temps."
        )

        return

    comparison = compare_coach_profiles(
        current_profile,
        previous_profile,
    )

    if not comparison.get(
        "available",
        False,
    ):

        return

    st.markdown(
        "### 📊 Évolution depuis le précédent bilan"
    )

    c1, c2, c3, c4 = st.columns(
        4
    )

    # --------------------------------------------------------
    # GAFFES
    # --------------------------------------------------------

    gaffes_change = comparison[
        "gaffes_per_game"
    ]

    c1.metric(
        "Gaffes / partie",
        current_profile[
            "gaffes_per_game"
        ],
        delta=f"{gaffes_change:+.2f}",
        delta_color="inverse",
    )

    # --------------------------------------------------------
    # ERREURS
    # --------------------------------------------------------

    errors_change = comparison[
        "errors_per_game"
    ]

    c2.metric(
        "Erreurs / partie",
        current_profile[
            "errors_per_game"
        ],
        delta=f"{errors_change:+.2f}",
        delta_color="inverse",
    )

    # --------------------------------------------------------
    # ACPL
    # --------------------------------------------------------

    acpl_change = comparison[
        "acpl"
    ]

    c3.metric(
        "ACPL",
        current_profile[
            "average_acpl"
        ],
        delta=f"{acpl_change:+.2f}",
        delta_color="inverse",
    )

    # --------------------------------------------------------
    # STABILITÉ
    # --------------------------------------------------------

    stability_change = comparison[
        "stability"
    ]

    c4.metric(
        "Stabilité",
        f"{calculate_stability_score(current_profile):.1f}%",
        delta=f"{stability_change:+.1f}",
    )

    # --------------------------------------------------------
    # MESSAGES
    # --------------------------------------------------------

    for message in comparison[
        "messages"
    ]:

        st.write(
            f"• {message}"
        )


# ============================================================
# MÉMOIRE DU COACH
# ============================================================

def save_coach_profile(
    profile,
):
    """
    Enregistre le profil courant comme ancienne référence
    avant de créer le prochain bilan.

    Attention :
    cette mémoire est conservée dans la session Streamlit.
    """

    memory = st.session_state[
        "coach_memory"
    ]

    current = memory.get(
        "current_profile"
    )

    if current:

        memory[
            "previous_profile"
        ] = current

        memory[
            "previous_priority"
        ] = current.get(
            "main_priority",
            {},
        ).get(
            "name"
        )

    memory[
        "current_profile"
    ] = profile

    memory[
        "history"
    ].append(
        {
            "games": profile.get(
                "games_analyzed",
                0,
            ),
            "acpl": profile.get(
                "average_acpl",
                0,
            ),
            "gaffes": profile.get(
                "gaffes_per_game",
                0,
            ),
            "priority": profile.get(
                "main_priority",
                {},
            ).get(
                "name",
                "",
            ),
        }
    )


# ============================================================
# PLAN D'ENTRAÎNEMENT DÉTAILLÉ
# ============================================================

def display_detailed_training_plan(
    profile,
):
    """
    Affiche le programme d'entraînement personnalisé.
    """

    st.markdown(
        "### 🏋️ Ton programme de travail"
    )

    priority = profile.get(
        "main_priority",
        {},
    )

    st.write(
        f"**Priorité : {priority.get('name', 'Calcul et vérification')}**"
    )

    st.caption(
        priority.get(
            "reason",
            "",
        )
    )

    plan = profile.get(
        "training_plan",
        [],
    )

    if not plan:

        st.write(
            "Aucun programme spécifique disponible."
        )

        return

    for number, item in enumerate(
        plan,
        1,
    ):

        with st.expander(
            f"{number}. {item['jour']}"
        ):

            st.write(
                item[
                    "travail"
                ]
            )


# ============================================================
# CONSEIL SELON LE NIVEAU
# ============================================================

def level_based_advice(
    target_elo,
    current_elo,
):
    """
    Ajoute un cadre pédagogique général.

    Le coach ne prétend pas qu'une seule méthode
    fonctionne pour tout le monde.
    """

    if current_elo is None:

        return (
            "Le coach va prioriser les erreurs observées "
            "dans tes parties plutôt que de supposer ton niveau."
        )

    if current_elo < 1000:

        return (
            "À ce niveau, la priorité est généralement "
            "la sécurité tactique : pièces en prise, "
            "menaces immédiates et mats simples."
        )

    if current_elo < 1200:

        return (
            "La priorité est généralement de réduire les "
            "grosses erreurs tout en améliorant le calcul "
            "des menaces adverses."
        )

    if current_elo < 1400:

        return (
            "Le passage vers 1500 demande surtout de rendre "
            "les décisions critiques plus fiables : "
            "calcul, activité des pièces et conversion "
            "des avantages."
        )

    if current_elo < 1500:

        return (
            "Tu approches de l'objectif : le travail doit "
            "être ciblé sur les erreurs qui continuent "
            "à apparaître régulièrement."
        )

    return (
        "Ton objectif de 1500 est atteint ou dépassé. "
        "Le coach peut maintenant chercher un nouvel objectif."
    )


# ============================================================
# TABLEAU DE BORD COMPLET
# ============================================================

def display_coach_dashboard(
    games_df,
):
    """
    Affiche le tableau de bord global du Coach 1500.
    """

    if games_df is None:

        return

    if games_df.empty:

        return

    # --------------------------------------------------------
    # OBJECTIF
    # --------------------------------------------------------

    target_elo = display_coach_goal()

    # --------------------------------------------------------
    # NOMBRE D'ANALYSES
    # --------------------------------------------------------

    analyzed = count_available_analyses(
        games_df
    )

    total = len(
        games_df
    )

    st.markdown(
        "---"
    )

    st.subheader(
        "🧠 Coach 1500 — Tableau de bord"
    )

    st.write(
        f"Analyses disponibles : "
        f"**{analyzed}/{total}**"
    )

    if analyzed == 0:

        st.info(
            "Analyse au moins une partie pour construire "
            "le profil du coach."
        )

        return

    # --------------------------------------------------------
    # PROFIL
    # --------------------------------------------------------

    profile = build_current_coach_profile(
        games_df
    )

    # --------------------------------------------------------
    # ELO
    # --------------------------------------------------------

    current_elo = get_current_player_elo(
        games_df
    )

    display_goal_progress(
        target_elo,
        current_elo,
    )

    st.info(
        level_based_advice(
            target_elo,
            current_elo,
        )
    )

    # --------------------------------------------------------
    # PROFIL
    # --------------------------------------------------------

    display_coach_profile(
        profile
    )

    # --------------------------------------------------------
    # ÉVOLUTION
    # --------------------------------------------------------

    display_priority_evolution(
        profile
    )

    display_longitudinal_comparison(
        profile
    )

    # --------------------------------------------------------
    # PROGRAMME
    # --------------------------------------------------------

    display_detailed_training_plan(
        profile
    )

    # --------------------------------------------------------
    # SAUVEGARDE
    # --------------------------------------------------------

    if st.button(
        "💾 Enregistrer ce bilan comme référence",
        use_container_width=True,
    ):

        save_coach_profile(
            profile
        )

        st.success(
            "Bilan enregistré. "
            "Le prochain bilan pourra être comparé à celui-ci."
        )


# ============================================================
# ONGLETS PRINCIPAUX
# ============================================================

def display_main_tabs(
    games_df,
):
    """
    Organisation finale de l'application.
    """

    tab_analysis, tab_coach, tab_games = st.tabs(
        [
            "♟️ Analyse",
            "🧠 Coach 1500",
            "📋 Parties",
        ]
    )

        # --------------------------------------------------------
    # ANALYSE
    # --------------------------------------------------------

    with tab_analysis:

        st.subheader(
            "♟️ Analyse d'une partie"
        )

        if games_df is not None and not games_df.empty:

            game_options = list(
                range(
                    len(games_df)
                )
            )

            def local_game_label(index):

                row = games_df.iloc[index]

                return (
                    f"#{index + 1} — "
                    f"vs {row['Adversaire']} — "
                    f"{row['Résultat']} — "
                    f"{row['Ouverture']}"
                )

            selected = st.selectbox(
                "Choisis une partie",
                game_options,
                format_func=local_game_label,
                key="main_analysis_game_selector",
            )

            # IMPORTANT :
            # Une seule instance de l'analyse est affichée ici.
            display_game_analysis(
                games_df,
                selected,
            )

        else:

            st.info(
                "Aucune partie chargée."
            )
    # --------------------------------------------------------
    # COACH
    # --------------------------------------------------------

    with tab_coach:

        display_coach_dashboard(
            games_df
        )

    # --------------------------------------------------------
    # LISTE DES PARTIES
    # --------------------------------------------------------

    with tab_games:

        st.subheader(
            "📋 Parties analysables"
        )

        st.dataframe(
            games_df,
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# LANCEMENT DU TABLEAU DE BORD
# ============================================================

if (
    "games_df"
    in st.session_state
):

    final_games_df = st.session_state[
        "games_df"
    ]

    if (
        final_games_df is not None
        and not final_games_df.empty
    ):

        display_main_tabs(
            final_games_df
        )

else:

    st.info(
        "👤 Charge tes parties pour lancer le Coach 1500."
    )


# ============================================================
# FIN DU PROJET
# ============================================================

st.markdown(
    "---"
)

st.caption(
    "♟️ Coach Chess 1500 — "
    "Analyse → Diagnostic → Priorité → Entraînement → Progression"
)
