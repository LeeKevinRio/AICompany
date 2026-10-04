欄位：on=命中日數；trans=命中狀態翻轉次數；quick=距上次翻轉≤5日的翻轉數；max20=任一20交易日內最多翻轉數；eps=命中段數；short_eps=≤3日的命中段；short_gaps=命中段之間≤3日的空檔數；missed=基準命中而此設計未命中日數；missed_eps=整段基準命中被完全略過的段數；extra=此設計命中但目前回撤未深於門檻的日數（explanation『已深於』字面不成立）；delay_mean=基準命中段起點到此設計首次命中的平均延遲（交易日）；gap=規則已不命中但失效條件尚未達成的日數；clusters=基準命中段以≤10日空檔合併後的『事件』數；missed_cl=此設計整個事件都未命中的事件數；cl_delay=事件起點到此設計首次命中的平均延遲。
## A. demo 合成日線（point-in-time，540 日窗）

#### 2330 / drawdown_protection / 全期（含區間不足日，口徑與線上不同）（評估 519 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 129 | 14 | 7 | 6 | 7 | 2 | 4 | 0 | 0 | 2 | 0 | 0 | 0.00 | 47 |
| A1_band_exit+5pp | 164 | 2 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 2 | 0 | 35 | 0.00 | 12 |
| A2_exit_at_invalidation | 176 | 2 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 2 | 0 | 47 | 0.00 | 0 |
| B1_confirm3_exit0 | 116 | 12 | 4 | 4 | 6 | 1 | 3 | 13 | 1 | 2 | 0 | 0 | 2.00 | 58 |
| B2_confirm3_both | 133 | 6 | 2 | 4 | 3 | 1 | 0 | 6 | 0 | 2 | 0 | 10 | 0.86 | 41 |
| C_any_below_last10 | 155 | 4 | 1 | 2 | 2 | 0 | 1 | 0 | 0 | 2 | 0 | 26 | 0.00 | 21 |

#### 2330 / drawdown_protection / 完整區間（自 2026-03-31）（評估 134 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 4 | 3 | 2 | 3 | 2 | 2 | 1 | 0 | 0 | 1 | 0 | 0 | 0.00 | 28 |
| A1_band_exit+5pp | 20 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 16 | 0.00 | 12 |
| A2_exit_at_invalidation | 32 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 28 | 0.00 | 0 |
| B1_confirm3_exit0 | 3 | 1 | 0 | 1 | 1 | 1 | 0 | 1 | 1 | 1 | 0 | 0 | 0.00 | 29 |
| B2_confirm3_both | 7 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 3 | 0.00 | 25 |
| C_any_below_last10 | 14 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 10 | 0.00 | 18 |

#### 2330 / deep_drawdown_stop / 全期（含區間不足日，口徑與線上不同）（評估 519 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| A1_band_exit+5pp | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| A2_exit_at_invalidation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| B1_confirm3_exit0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| B2_confirm3_both | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| C_any_below_last10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |

#### 2330 / deep_drawdown_stop / 完整區間（自 2026-03-31）（評估 134 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| A1_band_exit+5pp | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| A2_exit_at_invalidation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| B1_confirm3_exit0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| B2_confirm3_both | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| C_any_below_last10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |

#### 0050 / drawdown_protection / 全期（含區間不足日，口徑與線上不同）（評估 519 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 96 | 28 | 18 | 8 | 14 | 7 | 10 | 0 | 0 | 3 | 0 | 0 | 0.00 | 68 |
| A1_band_exit+5pp | 162 | 3 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 3 | 0 | 66 | 0.00 | 2 |
| A2_exit_at_invalidation | 164 | 3 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 3 | 0 | 68 | 0.00 | 0 |
| B1_confirm3_exit0 | 72 | 16 | 5 | 4 | 8 | 2 | 1 | 24 | 6 | 3 | 0 | 0 | 2.00 | 88 |
| B2_confirm3_both | 102 | 12 | 4 | 4 | 6 | 0 | 0 | 14 | 2 | 3 | 0 | 20 | 1.00 | 58 |
| C_any_below_last10 | 147 | 7 | 2 | 2 | 4 | 0 | 1 | 0 | 0 | 3 | 0 | 51 | 0.00 | 17 |

#### 0050 / drawdown_protection / 完整區間（自 2026-03-31）（評估 134 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 30 | 2 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0.00 | 8 |
| A1_band_exit+5pp | 38 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 8 | 0.00 | 0 |
| A2_exit_at_invalidation | 38 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 8 | 0.00 | 0 |
| B1_confirm3_exit0 | 28 | 2 | 0 | 1 | 1 | 0 | 0 | 2 | 0 | 1 | 0 | 0 | 2.00 | 8 |
| B2_confirm3_both | 30 | 2 | 0 | 1 | 1 | 0 | 0 | 2 | 0 | 1 | 0 | 2 | 2.00 | 6 |
| C_any_below_last10 | 38 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 8 | 0.00 | 0 |

#### 0050 / deep_drawdown_stop / 全期（含區間不足日，口徑與線上不同）（評估 519 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| A1_band_exit+5pp | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| A2_exit_at_invalidation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| B1_confirm3_exit0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| B2_confirm3_both | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| C_any_below_last10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |

#### 0050 / deep_drawdown_stop / 完整區間（自 2026-03-31）（評估 134 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| A1_band_exit+5pp | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| A2_exit_at_invalidation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| B1_confirm3_exit0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| B2_confirm3_both | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| C_any_below_last10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |

#### 00631L / drawdown_protection / 全期（含區間不足日，口徑與線上不同）（評估 519 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 214 | 13 | 9 | 5 | 7 | 3 | 5 | 0 | 0 | 2 | 0 | 0 | 0.00 | 14 |
| A1_band_exit+5pp | 224 | 3 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 2 | 0 | 10 | 0.00 | 4 |
| A2_exit_at_invalidation | 228 | 3 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 2 | 0 | 14 | 0.00 | 0 |
| B1_confirm3_exit0 | 203 | 7 | 3 | 3 | 4 | 1 | 2 | 11 | 3 | 2 | 0 | 0 | 2.00 | 15 |
| B2_confirm3_both | 213 | 3 | 0 | 1 | 2 | 0 | 0 | 6 | 2 | 2 | 0 | 5 | 0.80 | 5 |
| C_any_below_last10 | 230 | 3 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 2 | 0 | 16 | 0.00 | 0 |

#### 00631L / drawdown_protection / 完整區間（自 2026-03-31）（評估 134 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 50 | 3 | 2 | 3 | 2 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0.00 | 1 |
| A1_band_exit+5pp | 51 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 0.00 | 0 |
| A2_exit_at_invalidation | 51 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 0.00 | 0 |
| B1_confirm3_exit0 | 46 | 3 | 2 | 3 | 2 | 1 | 1 | 4 | 0 | 1 | 0 | 0 | 2.00 | 3 |
| B2_confirm3_both | 49 | 1 | 0 | 1 | 1 | 0 | 0 | 2 | 0 | 1 | 0 | 1 | 1.00 | 0 |
| C_any_below_last10 | 51 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 0.00 | 0 |

#### 00631L / deep_drawdown_stop / 全期（含區間不足日，口徑與線上不同）（評估 519 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 165 | 6 | 2 | 3 | 3 | 1 | 1 | 0 | 0 | 2 | 0 | 0 | 0.00 | 6 |
| A1_band_exit+5pp | 169 | 3 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 2 | 0 | 4 | 0.00 | 2 |
| A2_exit_at_invalidation | 171 | 3 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 2 | 0 | 6 | 0.00 | 0 |
| B1_confirm3_exit0 | 159 | 4 | 0 | 1 | 2 | 0 | 0 | 6 | 1 | 2 | 0 | 0 | 2.00 | 8 |
| B2_confirm3_both | 165 | 3 | 0 | 1 | 2 | 0 | 0 | 4 | 0 | 2 | 0 | 4 | 1.33 | 2 |
| C_any_below_last10 | 176 | 3 | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 2 | 0 | 11 | 0.00 | 9 |

#### 00631L / deep_drawdown_stop / 完整區間（自 2026-03-31）（評估 134 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 38 | 4 | 2 | 3 | 2 | 1 | 1 | 0 | 0 | 1 | 0 | 0 | 0.00 | 2 |
| A1_band_exit+5pp | 40 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 2 | 0.00 | 0 |
| A2_exit_at_invalidation | 40 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 2 | 0.00 | 0 |
| B1_confirm3_exit0 | 34 | 2 | 0 | 1 | 1 | 0 | 0 | 4 | 1 | 1 | 0 | 0 | 2.00 | 4 |
| B2_confirm3_both | 38 | 1 | 0 | 1 | 1 | 0 | 0 | 2 | 0 | 1 | 0 | 2 | 1.00 | 0 |
| C_any_below_last10 | 40 | 1 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 2 | 0.00 | 0 |

## B. 手工路徑（前置 60 日平盤 100，供 MA60）

#### H1 −20% 附近 ±1.2% 震盪 40 日後回升到 −5% / drawdown_protection / 全路徑（評估 145 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 16 | 16 | 14 | 13 | 8 | 7 | 6 | 0 | 0 | 1 | 0 | 0 | 0.00 | 30 |
| A1_band_exit+5pp | 39 | 2 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 23 | 0.00 | 7 |
| A2_exit_at_invalidation | 46 | 2 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 30 | 0.00 | 0 |
| B1_confirm3_exit0 | 3 | 4 | 2 | 4 | 2 | 2 | 0 | 13 | 6 | 1 | 0 | 0 | 2.00 | 41 |
| B2_confirm3_both | 22 | 2 | 0 | 1 | 1 | 0 | 0 | 3 | 1 | 1 | 0 | 9 | 0.29 | 22 |
| C_any_below_last10 | 41 | 2 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 25 | 0.00 | 5 |

#### H1 −20% 附近 ±1.2% 震盪 40 日後回升到 −5% / deep_drawdown_stop / 全路徑（評估 145 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| A1_band_exit+5pp | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| A2_exit_at_invalidation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| B1_confirm3_exit0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| B2_confirm3_both | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| C_any_below_last10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |

#### H2 停在 −19%，單日刺穿 −20.5% / drawdown_protection / 全路徑（評估 120 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 1 | 2 | 1 | 2 | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0.00 | 18 |
| A1_band_exit+5pp | 14 | 2 | 0 | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 13 | 0.00 | 5 |
| A2_exit_at_invalidation | 19 | 2 | 0 | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 18 | 0.00 | 0 |
| B1_confirm3_exit0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 1 | 0 | nan | 0 |
| B2_confirm3_both | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 1 | 0 | nan | 0 |
| C_any_below_last10 | 10 | 2 | 0 | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 9 | 0.00 | 9 |

#### H2 停在 −19%，單日刺穿 −20.5% / deep_drawdown_stop / 全路徑（評估 120 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| A1_band_exit+5pp | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| A2_exit_at_invalidation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| B1_confirm3_exit0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| B2_confirm3_both | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |
| C_any_below_last10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | nan | 0 |

#### H3 跌到 −35% 後反彈至 −15% 附近 ±1.5% 震盪 30 日，再到 −9% / drawdown_protection / 全路徑（評估 160 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 23 | 2 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0.00 | 44 |
| A1_band_exit+5pp | 28 | 2 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 5 | 0.00 | 39 |
| A2_exit_at_invalidation | 67 | 2 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 44 | 0.00 | 0 |
| B1_confirm3_exit0 | 21 | 2 | 0 | 1 | 1 | 0 | 0 | 2 | 0 | 1 | 0 | 0 | 2.00 | 44 |
| B2_confirm3_both | 23 | 2 | 0 | 1 | 1 | 0 | 0 | 2 | 0 | 1 | 0 | 2 | 2.00 | 42 |
| C_any_below_last10 | 32 | 2 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 9 | 0.00 | 35 |

#### H3 跌到 −35% 後反彈至 −15% 附近 ±1.5% 震盪 30 日，再到 −9% / deep_drawdown_stop / 全路徑（評估 160 日）

| design | on | trans | quick | max20 | eps | short_eps | short_gaps | missed | missed_eps | clusters | missed_cl | extra | delay_mean | gap |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 8 | 2 | 0 | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0.00 | 17 |
| A1_band_exit+5pp | 12 | 2 | 0 | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 4 | 0.00 | 13 |
| A2_exit_at_invalidation | 25 | 2 | 0 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 17 | 0.00 | 0 |
| B1_confirm3_exit0 | 6 | 2 | 0 | 2 | 1 | 0 | 0 | 2 | 0 | 1 | 0 | 0 | 2.00 | 17 |
| B2_confirm3_both | 8 | 2 | 0 | 2 | 1 | 0 | 0 | 2 | 0 | 1 | 0 | 2 | 2.00 | 15 |
| C_any_below_last10 | 17 | 2 | 0 | 2 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 9 | 0.00 | 8 |

## C. GBM 蒙地卡羅（模型，不是資料）：每組 400 條、每條 10 年（252 日/年）評估、窗 370 根
| sigma | rule | design | on_per_yr | trans_per_yr | quick_share | eps_per_yr | short_eps_share | p95_max20 | missed_per_yr | missed_eps_share | extra_per_yr | delay_mean | clusters_per_yr | missed_cl_share | cl_delay | gap_per_yr |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.2 | drawdown_protection | base | 65.1 | 4.80 | 58% | 2.42 | 51% | 10 | 0.0 | 0% | 0.0 | 0.00 | 0.85 | 0.0% | 0.00 | 29.8 |
| 0.2 | drawdown_protection | A1_band_exit+5pp | 79.9 | 1.24 | 1% | 0.65 | 0% | 3 | 0.0 | 0% | 14.8 | 0.00 | 0.85 | 0.0% | 0.00 | 15.1 |
| 0.2 | drawdown_protection | A2_exit_at_invalidation | 95.1 | 0.82 | 0% | 0.45 | 0% | 2 | 0.0 | 0% | 30.0 | 0.00 | 0.85 | 0.0% | 0.00 | 0.0 |
| 0.2 | drawdown_protection | B1_confirm3_exit0 | 61.0 | 2.73 | 34% | 1.39 | 30% | 6 | 4.1 | 43% | 0.0 | 1.95 | 0.85 | 19.9% | 3.59 | 28.9 |
| 0.2 | drawdown_protection | B2_confirm3_both | 65.0 | 1.98 | 17% | 1.01 | 9% | 4 | 3.0 | 32% | 2.8 | 1.24 | 0.85 | 19.9% | 3.58 | 25.0 |
| 0.2 | drawdown_protection | C_any_below_last10 | 77.1 | 1.71 | 8% | 0.89 | 0% | 3 | 0.0 | 0% | 12.0 | 0.00 | 0.85 | 0.0% | 0.00 | 17.9 |
| 0.2 | deep_drawdown_stop | base | 21.5 | 2.14 | 59% | 1.08 | 52% | 10 | 0.0 | 0% | 0.0 | 0.00 | 0.38 | 0.0% | 0.00 | 14.9 |
| 0.2 | deep_drawdown_stop | A1_band_exit+5pp | 28.9 | 0.53 | 0% | 0.28 | 0% | 2 | 0.0 | 0% | 7.4 | 0.00 | 0.38 | 0.0% | 0.00 | 7.6 |
| 0.2 | deep_drawdown_stop | A2_exit_at_invalidation | 36.5 | 0.38 | 0% | 0.20 | 0% | 1 | 0.0 | 0% | 15.0 | 0.00 | 0.38 | 0.0% | 0.00 | 0.0 |
| 0.2 | deep_drawdown_stop | B1_confirm3_exit0 | 19.7 | 1.20 | 36% | 0.61 | 33% | 6 | 1.8 | 44% | 0.0 | 1.96 | 0.38 | 19.2% | 3.53 | 14.6 |
| 0.2 | deep_drawdown_stop | B2_confirm3_both | 21.4 | 0.88 | 17% | 0.45 | 8% | 4 | 1.3 | 32% | 1.3 | 1.30 | 0.38 | 19.2% | 3.52 | 12.9 |
| 0.2 | deep_drawdown_stop | C_any_below_last10 | 26.8 | 0.77 | 7% | 0.39 | 0% | 3 | 0.0 | 0% | 5.3 | 0.00 | 0.38 | 0.0% | 0.00 | 9.7 |
| 0.35 | drawdown_protection | base | 142.4 | 7.39 | 59% | 3.75 | 51% | 12 | 0.0 | 0% | 0.0 | 0.00 | 1.24 | 0.0% | 0.00 | 25.0 |
| 0.35 | drawdown_protection | A1_band_exit+5pp | 155.1 | 2.49 | 9% | 1.31 | 4% | 4 | 0.0 | 0% | 12.7 | 0.00 | 1.24 | 0.0% | 0.00 | 12.4 |
| 0.35 | drawdown_protection | A2_exit_at_invalidation | 167.6 | 1.57 | 1% | 0.85 | 0% | 3 | 0.0 | 0% | 25.2 | 0.00 | 1.24 | 0.0% | 0.00 | 0.0 |
| 0.35 | drawdown_protection | B1_confirm3_exit0 | 136.2 | 4.18 | 35% | 2.15 | 30% | 6 | 6.3 | 43% | 0.0 | 1.94 | 1.24 | 18.5% | 3.51 | 25.7 |
| 0.35 | drawdown_protection | B2_confirm3_both | 142.3 | 2.97 | 17% | 1.54 | 8% | 5 | 4.5 | 31% | 4.4 | 1.16 | 1.24 | 18.5% | 3.51 | 19.6 |
| 0.35 | drawdown_protection | C_any_below_last10 | 160.2 | 2.46 | 9% | 1.30 | 0% | 4 | 0.0 | 0% | 17.8 | 0.00 | 1.24 | 0.0% | 0.00 | 8.9 |
| 0.35 | deep_drawdown_stop | base | 94.0 | 5.59 | 58% | 2.83 | 50% | 11 | 0.0 | 0% | 0.0 | 0.00 | 0.96 | 0.0% | 0.00 | 21.6 |
| 0.35 | deep_drawdown_stop | A1_band_exit+5pp | 104.9 | 1.80 | 6% | 0.94 | 2% | 4 | 0.0 | 0% | 10.9 | 0.00 | 0.96 | 0.0% | 0.00 | 10.7 |
| 0.35 | deep_drawdown_stop | A2_exit_at_invalidation | 115.7 | 1.17 | 0% | 0.63 | 0% | 2 | 0.0 | 0% | 21.7 | 0.00 | 0.96 | 0.0% | 0.00 | 0.0 |
| 0.35 | deep_drawdown_stop | B1_confirm3_exit0 | 89.3 | 3.19 | 34% | 1.63 | 30% | 7 | 4.8 | 42% | 0.0 | 1.95 | 0.96 | 18.1% | 3.56 | 21.8 |
| 0.35 | deep_drawdown_stop | B2_confirm3_both | 93.9 | 2.29 | 17% | 1.18 | 8% | 5 | 3.4 | 30% | 3.3 | 1.19 | 0.96 | 18.1% | 3.55 | 17.1 |
| 0.35 | deep_drawdown_stop | C_any_below_last10 | 107.7 | 1.92 | 8% | 1.00 | 0% | 4 | 0.0 | 0% | 13.7 | 0.00 | 0.96 | 0.0% | 0.00 | 8.7 |
| 0.6 | drawdown_protection | base | 199.3 | 6.88 | 59% | 3.52 | 49% | 11 | 0.0 | 0% | 0.0 | 0.00 | 1.11 | 0.0% | 0.00 | 13.3 |
| 0.6 | drawdown_protection | A1_band_exit+5pp | 206.2 | 3.12 | 24% | 1.64 | 13% | 5 | 0.0 | 0% | 6.8 | 0.00 | 1.11 | 0.0% | 0.00 | 6.5 |
| 0.6 | drawdown_protection | A2_exit_at_invalidation | 212.6 | 1.99 | 7% | 1.08 | 2% | 4 | 0.0 | 0% | 13.3 | 0.00 | 1.11 | 0.0% | 0.00 | 0.0 |
| 0.6 | drawdown_protection | B1_confirm3_exit0 | 193.5 | 3.97 | 35% | 2.06 | 28% | 7 | 5.9 | 41% | 0.0 | 1.91 | 1.11 | 17.4% | 3.47 | 14.3 |
| 0.6 | drawdown_protection | B2_confirm3_both | 199.3 | 2.76 | 17% | 1.46 | 7% | 5 | 4.1 | 29% | 4.1 | 1.12 | 1.11 | 17.4% | 3.46 | 8.6 |
| 0.6 | drawdown_protection | C_any_below_last10 | 215.4 | 2.16 | 10% | 1.16 | 0% | 4 | 0.0 | 0% | 16.1 | 0.00 | 1.11 | 0.0% | 0.00 | 2.3 |
| 0.6 | deep_drawdown_stop | base | 169.1 | 6.81 | 59% | 3.48 | 49% | 11 | 0.0 | 0% | 0.0 | 0.00 | 1.13 | 0.0% | 0.00 | 15.4 |
| 0.6 | deep_drawdown_stop | A1_band_exit+5pp | 176.9 | 2.91 | 20% | 1.52 | 10% | 5 | 0.0 | 0% | 7.8 | 0.00 | 1.13 | 0.0% | 0.00 | 7.7 |
| 0.6 | deep_drawdown_stop | A2_exit_at_invalidation | 184.6 | 1.85 | 3% | 1.00 | 1% | 3 | 0.0 | 0% | 15.5 | 0.00 | 1.13 | 0.0% | 0.00 | 0.0 |
| 0.6 | deep_drawdown_stop | B1_confirm3_exit0 | 163.3 | 3.91 | 34% | 2.02 | 28% | 7 | 5.8 | 42% | 0.0 | 1.93 | 1.13 | 18.5% | 3.46 | 16.0 |
| 0.6 | deep_drawdown_stop | B2_confirm3_both | 169.1 | 2.74 | 17% | 1.44 | 7% | 5 | 4.1 | 30% | 4.0 | 1.14 | 1.13 | 18.5% | 3.45 | 10.3 |
| 0.6 | deep_drawdown_stop | C_any_below_last10 | 185.4 | 2.24 | 9% | 1.19 | 0% | 4 | 0.0 | 0% | 16.2 | 0.00 | 1.13 | 0.0% | 0.00 | 3.2 |
