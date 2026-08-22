# C5 K4b 後續三 commit — qa-reviewer 批審紀錄

- **日期**:2026-08-22
- **審查對象**:`ea2923c`(守門補強)、`f43dbc5`((g-overridden)+六格表)、`6d564cc`(第八輪定稿落地與六格表收斂)
- **審查依據**:批審檔第七/八輪(條件 51-70、覆核 E1-E3)、條件46裁決附註、`code-review-checklist` skill
- **結論**:**PASS**,`BLOCKING_ISSUES=false`(1982 測試、mypy、ruff 綠)

## 核對摘要

1. **ea2923c**:傳遞閉包守門(app/advice 全套對 kelly store/attempts 不可達)+limits 零 import 雙重白盒+清冊斷言+正向釘 models+plain-import teeth;qa 實際植入 `import app.kelly.store` 抽驗兩斷言轉紅後還原,working tree 乾淨。
2. **f43dbc5**:(g-overridden) 字元級相符;六格表+反向斷言;alerts/scheduler call-site 對稱;xfail 佔位為風控允許的過渡(由 6d564cc 結案)。
3. **6d564cc**:欄位 11 E1-E4+五則、任務 7/8、(g-4-overridden) 全部逐字相符(含全形標點、段序條件 59、E4 刪第二分句、never_synced 括號條件 69);條件 62 查證 backtest.py diff 0 行、零 import 拼接;覆核 **E1**(反向斷言型非拔標)/**E2**(顯式 raise+雙重不可達驗證)/**E3**(裁決六格為鍵+第七組合不可達雙斷言)全數確實落地。
4. **dev 兩回送項技術面查證屬實**:①白名單 +3 非 +6——E2/E4 為條件 60 要求的共用常數,計數以定義處為準(條件 56),kelly_wording 5→8 與 dict 相等測試一致;②條件 61 掃描面限縮——全檔掃會誤傷三處既有核可((b) 句 K_observed 語境的低估/高估、backtest 側報酬率語境、playbook「本頁面」),限縮於組裝後五則正確。措辭面歸屬留風控(已併下輪)。
5. 「開頭相符」守門放寬為 siblings 邏輯,仍擋開頭相符內容漂移的變體。
6. 全跑一次 `test_positions_store.py` 同型 SQLite 併發 flake(單跑過)——即 D9 列管項的另一暴露面,與本批無關。

## 第二意見(Codex)

CLI 不可用,依慣例降級(逐檔審+紅燈植入實測+全套測試/mypy/ruff)。

## 協調人補記

風控第八輪工程閘門清單仍列「PortfolioContext 來源欄位(條件 19)」——**此項實際已由 68c12c9 落地**(KellyInputs.source 存在、(e)/(e-manual) 三來源互斥窮盡有 property test、qa K4b 補審已核),條件 19 應視為已結,將於下輪風控回報時提請正式銷項。
