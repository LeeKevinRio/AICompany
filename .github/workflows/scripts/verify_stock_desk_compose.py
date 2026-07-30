"""Compose guard for stock-desk: backend and scheduler must share one database.

Reads ``docker compose config --format json`` from stdin (the *resolved*
configuration, not the raw YAML — text grepping the YAML would miss anchors,
env interpolation and defaults) and asserts the invariants whose absence
caused a real defect: without a shared named volume and an identical
``STOCK_DESK_DB_PATH``, the scheduler writes a database the API never reads,
and user data lives in a container layer that ``docker compose down`` deletes.

Exit code 0 with a one-line pass message, or 1 with a Traditional-Chinese
explanation of exactly which invariant broke.
"""

from __future__ import annotations

import json
import sys

SERVICES = ("backend", "scheduler")
ENV_KEY = "STOCK_DESK_DB_PATH"


def fail(message: str) -> None:
    print(f"[compose-guard] 失敗:{message}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    try:
        config = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"stdin 不是合法的 compose config JSON({exc})。")

    services = config.get("services", {})
    for name in SERVICES:
        if name not in services:
            fail(f"compose 設定裡找不到 service「{name}」。")

    mounts: dict[str, tuple[str, str]] = {}
    db_paths: dict[str, str] = {}

    for name in SERVICES:
        svc = services[name]

        volume_mounts = [
            v for v in svc.get("volumes", []) or [] if v.get("type") == "volume"
        ]
        if not volume_mounts:
            fail(
                f"service「{name}」沒有掛載任何 named volume——"
                "資料會寫進容器可寫層,docker compose down 即消失。"
            )
        if len(volume_mounts) > 1:
            fail(f"service「{name}」掛了多個 named volume,無法判定資料庫位置。")
        mount = volume_mounts[0]
        mounts[name] = (mount.get("source", ""), mount.get("target", ""))

        env = svc.get("environment", {}) or {}
        value = env.get(ENV_KEY)
        if not value:
            fail(
                f"service「{name}」未設定 {ENV_KEY}——"
                "兩個 process 必須顯式指向同一個檔案,不得依賴相對路徑預設值。"
            )
        db_paths[name] = value

    backend_mount, scheduler_mount = mounts["backend"], mounts["scheduler"]
    if backend_mount[0] != scheduler_mount[0]:
        fail(
            "backend 與 scheduler 掛的不是同一個 volume"
            f"(backend=「{backend_mount[0]}」, scheduler=「{scheduler_mount[0]}」)"
            "——排程寫入的資料 API 永遠讀不到。"
        )
    if backend_mount[1] != scheduler_mount[1]:
        fail(
            "backend 與 scheduler 的 volume 掛載路徑不同"
            f"(backend=「{backend_mount[1]}」, scheduler=「{scheduler_mount[1]}」)。"
        )
    if db_paths["backend"] != db_paths["scheduler"]:
        fail(
            f"兩個 service 的 {ENV_KEY} 數值不同"
            f"(backend=「{db_paths['backend']}」, scheduler=「{db_paths['scheduler']}」)"
            "——即使共用同一個 volume,路徑字串不同兩邊仍各寫各的檔案。"
        )
    if not db_paths["backend"].startswith(backend_mount[1].rstrip("/") + "/"):
        fail(
            f"{ENV_KEY}=「{db_paths['backend']}」不在 volume 掛載路徑"
            f"「{backend_mount[1]}」之內——資料庫沒有真正落在持久化區。"
        )

    print(
        f"[compose-guard] 通過:backend 與 scheduler 共用 volume「{backend_mount[0]}」"
        f"掛載於「{backend_mount[1]}」,且 {ENV_KEY}=「{db_paths['backend']}」一致。"
    )


if __name__ == "__main__":
    main()
