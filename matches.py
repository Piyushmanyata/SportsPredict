"""
Match parameter registry for 2026 World Cup R32 sessions.
Populate lam_a/lam_b from devig.py after anchor fetch.
Player props finalized after lineup confirmation (~T-75 min).

Usage:
    from matches import MATCHES, get_match
    m = get_match("FRA vs SWE")
    from engine import compute_all_markets
    results = compute_all_markets(m)
"""
from engine import Match

# ── R32 matches — parameters to be updated with fresh odds each session ────────
# λ estimates below are FALLBACK-LOW (no fresh anchor).
# Replace lam_a, lam_b, sot_a, sot_b from devigged odds before submitting.
# Stage weight 2× for all R32 matches.

MATCHES = {

    "CIV vs NOR": Match(
        name="CIV vs NOR", stage="r32",
        match_id="b1772d21-e69c-4f9b-8f57-03f3b34a49c1",
        # Norway: moderate favourite. T~2.4 knockout-cagey.
        lam_a=1.05, lam_b=1.35,  # A=CIV, B=NOR
        sot_a=4.5,  sot_b=5.5,
        corners_a=4.5, corners_b=5.0,
        cards_lam=3.5, offside_lam=3.5,
        player_a1_name="Amad Diallo", player_a1_goal_share=0.15,
        player_a1_sot_share=0.22, player_a1_involvement=0.20,
        player_b1_name="Erling Haaland", player_b1_goal_share=0.35,
        player_b1_sot_share=0.30, player_b1_involvement=0.35,
        player_a2_name="Martin Ødegaard", player_a2_goal_share=0.12,
        player_a2_sot_share=0.16, player_a2_involvement=0.30, player_a2_sot_k=2,
        player_b2_name="Alexander Sørloth", player_b2_goal_share=0.12,
        player_b2_sot_share=0.17, player_b2_sot_k=2,
        confidence="LOW",
    ),

    "FRA vs SWE": Match(
        name="FRA vs SWE", stage="r32",
        match_id="a07006f4-3304-4406-819d-0921767cb4f5",
        # France strong favourite. T~2.8.
        lam_a=1.80, lam_b=1.00,  # A=FRA, B=SWE
        sot_a=7.0,  sot_b=4.5,
        corners_a=6.5, corners_b=4.0,
        cards_lam=3.5, offside_lam=4.5,
        player_a1_name="Kylian Mbappé", player_a1_goal_share=0.30,
        player_a1_sot_share=0.30, player_a1_involvement=0.40,
        player_a2_name="Ousmane Dembélé", player_a2_goal_share=0.15,
        player_a2_sot_share=0.18, player_a2_involvement=0.25, player_a2_sot_k=2,
        player_b1_name="Viktor Gyökeres", player_b1_goal_share=0.45,
        player_b1_sot_share=0.30, player_b1_involvement=0.45,
        player_b2_name="Alexander Isak", player_b2_goal_share=0.25,
        player_b2_sot_share=0.22, player_b2_sot_k=2,
        confidence="LOW",
    ),

    "MEX vs ECU": Match(
        name="MEX vs ECU", stage="r32",
        match_id="de713985-da7b-4d96-9445-d2352339dc90",
        # Mexico host + altitude advantage at Azteca (2,240m). T~2.5.
        # Altitude overlay: −2 to −4 on ECU attacking λ (§5.12).
        lam_a=1.40, lam_b=1.10,  # A=MEX, B=ECU; altitude adj applied to B
        sot_a=5.5,  sot_b=4.0,
        corners_a=5.0, corners_b=4.5,
        cards_lam=3.7, offside_lam=3.5,
        player_a1_name="Raúl Jiménez", player_a1_goal_share=0.30,
        player_a1_sot_share=0.25, player_a1_involvement=0.30,
        player_b2_name="Gonzalo Plata", player_b2_goal_share=0.15,
        player_b2_sot_share=0.18, player_b2_sot_k=1,
        altitude_adj=-3.0, confidence="LOW",
    ),

    "ENG vs COD": Match(
        name="ENG vs COD", stage="r32",
        match_id="56218a5e-0156-4c5c-bba9-b7c5da02bf10",
        # England heavy favourite vs DR Congo. T~3.0+.
        # L15: crowd may spread too much mass to DR Congo — STRONG opportunity on England.
        lam_a=2.10, lam_b=0.80,  # A=ENG, B=COD
        sot_a=7.5,  sot_b=3.5,
        corners_a=7.5, corners_b=3.0,
        cards_lam=3.5, offside_lam=4.0,
        player_a1_name="Harry Kane", player_a1_goal_share=0.35,
        player_a1_sot_share=0.30, player_a1_involvement=0.40,
        player_a2_name="Jude Bellingham", player_a2_goal_share=0.15,
        player_a2_sot_share=0.22, player_a2_involvement=0.30, player_a2_sot_k=2,
        player_b1_name="Yoane Wissa", player_b1_goal_share=0.30,
        player_b1_sot_share=0.25, player_b1_involvement=0.30,
        confidence="LOW",
    ),

    "BEL vs SEN": Match(
        name="BEL vs SEN", stage="r32",
        match_id="373353ee-5a7b-4a24-afe1-cd9336f03ca3",
        # Belgium moderate favourite. T~2.6.
        lam_a=1.55, lam_b=1.05,  # A=BEL, B=SEN
        sot_a=6.0,  sot_b=4.5,
        corners_a=6.0, corners_b=4.0,
        cards_lam=3.5, offside_lam=3.5,
        player_a1_name="Leandro Trossard", player_a1_goal_share=0.20,
        player_a1_sot_share=0.20, player_a1_involvement=0.25,
        player_a2_name="Kevin De Bruyne", player_a2_goal_share=0.12,
        player_a2_sot_share=0.15, player_a2_involvement=0.35, player_a2_sot_k=2,
        player_b1_name="Ismaïla Sarr", player_b1_goal_share=0.20,
        player_b1_sot_share=0.22, player_b1_involvement=0.25,
        player_b2_name="Sadio Mané", player_b2_goal_share=0.28,
        player_b2_sot_share=0.25, player_b2_sot_k=2,
        confidence="LOW",
    ),

    "USA vs BIH": Match(
        name="USA vs BIH", stage="r32",
        match_id="b2c86c3b-8060-4173-8321-fb68699210f4",
        # USA moderate favourite at home. T~2.6.
        lam_a=1.50, lam_b=1.10,  # A=USA, B=BIH
        sot_a=6.0,  sot_b=4.5,
        corners_a=6.0, corners_b=4.0,
        cards_lam=3.7, offside_lam=3.8,
        player_a1_name="Folarin Balogun", player_a1_goal_share=0.30,
        player_a1_sot_share=0.25, player_a1_involvement=0.30,
        player_b1_name="Ermedin Demirović", player_b1_goal_share=0.30,
        player_b1_sot_share=0.25, player_b1_involvement=0.30,
        confidence="LOW",
    ),



    "ESP vs AUT": Match(
        name="ESP vs AUT", stage="r32",
        match_id="11bcf2a2-6564-4ade-9cf7-43ee2ecbedd1",
        # Spain heavy favourite (Goldman top pick). T~2.8. L15 applies.
        lam_a=1.90, lam_b=0.90,  # A=ESP, B=AUT
        sot_a=7.5,  sot_b=4.0,
        corners_a=7.0, corners_b=3.5,
        cards_lam=3.5, offside_lam=4.5,
        player_a1_name="Mikel Oyarzabal", player_a1_goal_share=0.22,
        player_a1_sot_share=0.22, player_a1_involvement=0.28,
        player_a2_name="Lamine Yamal", player_a2_goal_share=0.12,
        player_a2_sot_share=0.25, player_a2_involvement=0.30, player_a2_sot_k=2,
        player_b1_name="Marcel Sabitzer", player_b1_goal_share=0.18,
        player_b1_sot_share=0.22, player_b1_involvement=0.28,
        confidence="LOW",
    ),

    "POR vs CRO": Match(
        name="POR vs CRO", stage="r32",
        match_id="b6287c24-0362-4169-ad1d-3aa4116a8bce",
        # Portugal moderate favourite vs Croatia. T~2.7.
        lam_a=1.60, lam_b=1.10,  # A=POR, B=CRO
        sot_a=6.5,  sot_b=4.5,
        corners_a=6.0, corners_b=4.5,
        cards_lam=3.7, offside_lam=3.5,
        player_a1_name="Cristiano Ronaldo", player_a1_goal_share=0.35,
        player_a1_sot_share=0.35, player_a1_involvement=0.40,
        player_a2_name="Bruno Fernandes", player_a2_goal_share=0.18,
        player_a2_sot_share=0.25, player_a2_involvement=0.35, player_a2_sot_k=2,
        player_b1_name="Luka Modrić", player_b1_goal_share=0.10,
        player_b1_sot_share=0.15, player_b1_involvement=0.30,
        confidence="LOW",
    ),

    "SUI vs ALG": Match(
        name="SUI vs ALG", stage="r32",
        match_id="66a5b1e2-aff3-435f-835b-2ca80de5e571",
        # Switzerland slight favourite. T~2.4 (tight/cagey).
        lam_a=1.35, lam_b=1.05,  # A=SUI, B=ALG
        sot_a=5.0,  sot_b=4.0,
        corners_a=5.0, corners_b=4.0,
        cards_lam=3.5, offside_lam=3.0,
        player_a1_name="Breel Embolo", player_a1_goal_share=0.30,
        player_a1_sot_share=0.25, player_a1_involvement=0.30,
        player_a2_name="Rubén Vargas", player_a2_goal_share=0.15,
        player_a2_sot_share=0.22, player_a2_involvement=0.25, player_a2_sot_k=2,
        player_b1_name="Riyad Mahrez", player_b1_goal_share=0.18,
        player_b1_sot_share=0.22, player_b1_involvement=0.30,
        player_b2_name="Amine Gouiri", player_b2_goal_share=0.22,
        player_b2_sot_share=0.25, player_b2_involvement=0.28, player_b2_sot_k=2,
        confidence="LOW",
    ),

    "AUS vs EGY": Match(
        name="AUS vs EGY", stage="r32",
        match_id="0bc25d75-319a-493e-86b2-96f84ea9ad55",
        # Near-even matchup. T~2.3.
        lam_a=1.20, lam_b=1.10,  # A=AUS, B=EGY
        sot_a=4.5,  sot_b=4.0,
        corners_a=4.5, corners_b=4.5,
        cards_lam=3.5, offside_lam=3.0,
        player_a1_name="Nestory Irankunda", player_a1_goal_share=0.15,
        player_a1_sot_share=0.22, player_a1_involvement=0.25,
        player_b1_name="Mahmoud Trezeguet", player_b1_goal_share=0.22,
        player_b1_sot_share=0.25, player_b1_involvement=0.25,
        confidence="LOW",
    ),

    "ARG vs CPV": Match(
        name="ARG vs CPV", stage="r32",
        match_id="9abe28c5-f74a-492f-a6f9-96d9bc03ecec",
        # Argentina heavy favourite vs Cape Verde. T~3.0+.
        # Winner's slump overlay: −1 to −2 on ARG (§5.12, soft, logged).
        lam_a=2.10, lam_b=0.75,  # A=ARG, B=CPV
        sot_a=7.5,  sot_b=3.0,
        corners_a=7.0, corners_b=3.0,
        cards_lam=3.5, offside_lam=4.5,
        player_a1_name="Lautaro Martínez", player_a1_goal_share=0.30,
        player_a1_sot_share=0.28, player_a1_involvement=0.30,
        player_a2_name="Julián Álvarez", player_a2_goal_share=0.20,
        player_a2_sot_share=0.22, player_a2_involvement=0.28, player_a2_sot_k=2,
        confidence="LOW",
    ),

    "COL vs GHA": Match(
        name="COL vs GHA", stage="r32",
        match_id="f4efe654-74c0-4f84-9aa0-6f34dacdd45f",
        # Colombia moderate favourite. T~2.6.
        lam_a=1.55, lam_b=1.05,  # A=COL, B=GHA
        sot_a=6.0,  sot_b=4.0,
        corners_a=5.5, corners_b=4.0,
        cards_lam=3.7, offside_lam=3.5,
        player_a1_name="Luis Díaz", player_a1_goal_share=0.28,
        player_a1_sot_share=0.25, player_a1_involvement=0.30,
        player_a2_name="James Rodríguez", player_a2_goal_share=0.12,
        player_a2_sot_share=0.18, player_a2_involvement=0.35, player_a2_sot_k=2,
        player_b1_name="Jordan Ayew", player_b1_goal_share=0.22,
        player_b1_sot_share=0.25, player_b1_involvement=0.28,
        player_b2_name="Antoine Semenyo", player_b2_goal_share=0.15,
        player_b2_sot_share=0.22, player_b2_involvement=0.25, player_b2_sot_k=2,
        confidence="LOW",
    ),
}


def get_match(name: str) -> Match:
    return MATCHES[name]


def all_match_names() -> list:
    return list(MATCHES.keys())
