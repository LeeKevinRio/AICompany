#!/usr/bin/env bash
# Idempotent installer for OpenAI Codex CLI, used by qa-reviewer's /review
# command for cross-vendor code review second opinions.
#
# Safe to re-run: skips installation if `codex` is already on PATH.
# Never writes secrets to disk; only checks for OPENAI_API_KEY in the
# environment and prints a reminder if it is missing.
set -euo pipefail

CODEX_PACKAGE="@openai/codex"

echo "== Codex CLI 安裝腳本 =="

if command -v codex >/dev/null 2>&1; then
  INSTALLED_VERSION="$(codex --version 2>/dev/null || echo '未知版本')"
  echo "偵測到已安裝的 Codex CLI（${INSTALLED_VERSION}），略過安裝。"
else
  echo "未偵測到 Codex CLI，開始安裝 ${CODEX_PACKAGE}..."

  # Retry npm install up to 2 times; on TLS failure, point npm at the
  # pre-configured proxy CA bundle (see /root/.ccr/README.md) and retry.
  ATTEMPT=1
  MAX_ATTEMPTS=3
  until npm install -g "${CODEX_PACKAGE}"; do
    if [ "${ATTEMPT}" -ge "${MAX_ATTEMPTS}" ]; then
      echo "安裝失敗：已重試 ${ATTEMPT} 次仍失敗，請檢查網路或 proxy 設定後手動處理。" >&2
      exit 1
    fi
    echo "npm install 失敗（第 ${ATTEMPT} 次），嘗試設定 CA bundle 後重試..."
    if [ -f "/root/.ccr/ca-bundle.crt" ]; then
      npm config set cafile /root/.ccr/ca-bundle.crt
    fi
    ATTEMPT=$((ATTEMPT + 1))
  done

  echo "安裝完成。"
fi

if command -v codex >/dev/null 2>&1; then
  echo "版本確認：$(codex --version)"
else
  echo "警告：安裝流程結束但仍找不到 codex 指令，請手動檢查。" >&2
  exit 1
fi

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo ""
  echo "提醒：目前環境變數 OPENAI_API_KEY 未設定。"
  echo "需要 CEO 在環境設定中提供 OPENAI_API_KEY，祕密絕不寫進檔案。"
  echo "（若改用 ChatGPT 帳號登入，請改跑 'codex login'，不需要此環境變數。）"
fi

echo "== 完成 =="
