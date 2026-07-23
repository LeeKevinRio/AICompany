# Stock Desk Backend

Stock Desk 產品的後端服務（Phase 1 骨架）。技術棧：Python 3.12 + FastAPI，依賴以 `uv` 管理。

## 需求

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

## 安裝依賴

```bash
uv sync
```

此指令會依 `uv.lock` 建立 `.venv` 並安裝正式與 dev 依賴。

## 啟動 dev server

```bash
uv run uvicorn app.main:app --reload --port 8000
```

健康檢查：`GET http://127.0.0.1:8000/health`，回傳範例：

```json
{"status": "ok", "service": "backend", "as_of": "2026-07-23T00:00:00+00:00"}
```

## 測試

```bash
uv run pytest
```

## Lint 與型別檢查

```bash
uv run ruff check .
uv run mypy app tests
```
