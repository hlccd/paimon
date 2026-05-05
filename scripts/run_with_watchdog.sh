#!/bin/bash
# Paimon 守护脚本：升级/崩溃自动重启 + broken commit 失败 N 次自动 git reset 回退。
#
# 用法（云端首次部署 / 改造）：
#   1. ssh 到服务器
#   2. 杀掉旧的 nohup paimon: pkill -f 'paimon 80' 或类似
#   3. cd 到项目根目录
#   4. nohup ./scripts/run_with_watchdog.sh 80 > /dev/null 2>&1 &
#   5. 以后所有更新走 webui /selfcheck → 「检查更新 / 升级」按钮，不再 ssh
#
# 退出码约定（paimon 进程返回值）：
#   0   正常退出（用户主动 stop）→ watchdog 退出
#   100 升级请求（webui 按钮触发 git pull 后）→ watchdog 立即重启
#   其他 异常退出 → 累计失败 +1，达 3 次自动 git reset 回退到 last_good_commit
#
# 状态文件（都在 .paimon/）：
#   last_good_commit    上次启动成功并稳定运行的 commit hash（webui 启动 60s 后写入）
#   restart_fail_count  连续异常退出计数（每次 RC≠0/100 +1，重启成功清零）

set -u

PORT="${1:-80}"
PAIMON_HOME="${PAIMON_HOME:-.paimon}"
LAST_GOOD_FILE="$PAIMON_HOME/last_good_commit"
FAIL_COUNT_FILE="$PAIMON_HOME/restart_fail_count"
MAX_FAIL_BEFORE_ROLLBACK=3

mkdir -p "$PAIMON_HOME"

while true; do
    echo "[watchdog $(date '+%H:%M:%S')] 启动 paimon $PORT (HEAD=$(git rev-parse --short HEAD 2>/dev/null || echo unknown))"
    paimon "$PORT"
    RC=$?
    echo "[watchdog $(date '+%H:%M:%S')] paimon 退出 RC=$RC"

    case "$RC" in
        0)
            echo "[watchdog] 正常退出，watchdog 一并停止"
            exit 0
            ;;
        100)
            echo "[watchdog] 升级请求，立即重启加载新代码"
            echo 0 > "$FAIL_COUNT_FILE"
            continue
            ;;
        *)
            FAIL=$(cat "$FAIL_COUNT_FILE" 2>/dev/null || echo 0)
            FAIL=$((FAIL + 1))
            echo "$FAIL" > "$FAIL_COUNT_FILE"
            echo "[watchdog] 异常退出 RC=$RC，累计失败 $FAIL/$MAX_FAIL_BEFORE_ROLLBACK"

            if [ "$FAIL" -ge "$MAX_FAIL_BEFORE_ROLLBACK" ] && [ -s "$LAST_GOOD_FILE" ]; then
                TARGET=$(cat "$LAST_GOOD_FILE")
                echo "[watchdog] 连续异常 $FAIL 次，自动 git reset --hard $TARGET 回退"
                if git reset --hard "$TARGET"; then
                    echo "[watchdog] 回退成功，重置失败计数"
                    echo 0 > "$FAIL_COUNT_FILE"
                else
                    echo "[watchdog] 回退失败，5 秒后重试启动（请人工介入）"
                fi
            fi
            sleep 5
            ;;
    esac
done
