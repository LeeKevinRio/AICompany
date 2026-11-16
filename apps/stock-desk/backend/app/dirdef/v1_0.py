"""The ``dirdef-v1.0`` object (ADR-0030 D-6 CG-2; freeze pack G7, CEO #145 (3)).

The values are the freeze pack G7 table word for word (v0.31 values,
RC-133 / RC-134 / RC-142 wording); the two C-8 provenance fields point at the
C-8 decision record, whose sha256 is that of its git blob (RC-152 point 1:
``git cat-file blob <commit>:<path>``). It is registered in
``app/dirdef/registry.py``; this object and its two registered hashes are never
to be modified (risk R-4). Only the market h3 / h5 forward claims use it.
"""

from __future__ import annotations

from typing import Final

from app.dirdef.definition import DirectionDefinition

DIRDEF_V1_0: Final = DirectionDefinition(
    definition_version="dirdef-v1.0",
    description=(
        "方向判斷定義 dirdef-v1.0：只供大盤 h3、h5 前瞻 claim 使用"
        "（ADR-0030 D-1、D-6 CG-2）；常數依事先宣告 v0.32。"
    ),
    K3=0.43,
    K5=0.43,
    EPS=1e-12,
    SIGMA_WINDOW=60,
    SIGMA_MIN_VALID=55,
    SIGMA_FLOOR=0.001,
    B2_WINDOW=250,
    B2_MIN_REALIZED=120,
    MAJORITY_TIE_ORDER=("range", "bullish", "bearish"),
    NEFF_BLOCK_LEN3=3,
    NEFF_BLOCK_LEN5=5,
    SEASON_MONTHS=(6, 7, 8, 9),
    MARKET_PRICE_INDEX_DEVIATION=(
        "大盤（臺灣加權股價指數）的標籤與特徵以價格指數點數計算，不含股利，不是還原價；"
        "此項偏離 PV-7「價格基準：還原價」，經風控 R-1（2026-10-16）附條件核可，只限大盤。"
        "除息旺季（6～9 月）標籤與特徵都會偏空，見事先宣告 §1.1 偏誤揭露。"
    ),
    f2_variant="F2-B",
    c8_decision_ref="work/dispatch/2026-11-15-C8決策紀錄-F2B.md",
    c8_decision_sha256="c942642c1958e6259545c4f64b4202fbafecf585f1f2cbe513961190af0ea54f",
    EXIT_DEADLINE_N_MARKET_SYMBOL=150,
    EXIT_DEADLINE_N_SECTOR=250,
    CHECKPOINTS_MARKET_SYMBOL=(30, 60, 100, 150, 250, 500),
    CHECKPOINTS_SECTOR=(150, 250, 500),
    REPLAY_CHECKPOINT_COUNT=1,
    ALPHA_FAMILY=0.05,
    M_EFF_FLOOR=8,
    MIN_MEAN_RECALL=1 / 3,
    MIN_COVERAGE=0.80,
    VOID_RATE_W_THRESHOLD=0.05,
    BOOTSTRAP_RESAMPLES=10000,
    BOOTSTRAP_BLOCK_LEN=4,
    BOOTSTRAP_BLOCK_LEN_ALTERNATIVES=(2, 8),
    BASKET_EXCLUSION_REASON_ORDER=(
        "dividend_factor_unusable",
        "split_or_reduction_suspected",
        "t_plus_h_bar_unavailable",
    ),
    SPLIT_SUSPECT_ABS_RETURN=0.11,
    BASKET_MIN_MEMBER_WEIGHT=0.90,
)
