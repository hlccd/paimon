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
#   last_good_commit    上次启动成功并稳定运行的 commit hash
#                       （首次启动 watchdog 时若不存在用 HEAD 初始化；webui 升级前预写；
#                        paimon 启动 60s 后再覆盖一次确认稳定）
#   restart_fail_count  连续异常退出计数（每次 RC≠0/100 +1，重启成功清零）
#   last_rollback       触发回退时写入元数据（5 行：ts/before/after/fail_count/kind）。
#                       paimon 启动后 push_archive 通知用户；webui /selfcheck 警示条
#                       展示并提供「我知道了」按钮删除该文件

set -u

PORT="${1:-80}"
PAIMON_HOME="${PAIMON_HOME:-.paimon}"
LAST_GOOD_FILE="$PAIMON_HOME/last_good_commit"
FAIL_COUNT_FILE="$PAIMON_HOME/restart_fail_count"
ROLLBACK_FILE="$PAIMON_HOME/last_rollback"
MAX_FAIL_BEFORE_ROLLBACK=3

mkdir -p "$PAIMON_HOME"

# #B 主改进：watchdog 启动时若 last_good_commit 不存在 → 用当前 HEAD 初始化
# 防御「首次部署后用户立刻点升级、paimon 60s 内 _write_last_good_commit_after 还没跑」
# 的窗口期里就出现 broken commit；watchdog 可以从这个 HEAD 兜底回退
if [ ! -s "$LAST_GOOD_FILE" ]; then
    INITIAL_HEAD=$(git rev-parse HEAD 2>/dev/null)
    if [ -n "$INITIAL_HEAD" ]; then
        echo "$INITIAL_HEAD" > "$LAST_GOOD_FILE"
        echo "[watchdog] 初始化 last_good_commit=$INITIAL_HEAD"
    fi
fi

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
                BEFORE_HEAD=$(git rev-parse HEAD 2>/dev/null || echo unknown)
                NOW_TS=$(date +%s)

                # 自挑刺 #2：HEAD 已等于 last_good 时回退是 no-op，多半 last_good 本身就 broken
                # → 不再 reset，写 NEEDS_MANUAL 标记给用户看，然后 sleep 久一点防 CPU 烧
                if [ "$BEFORE_HEAD" = "$TARGET" ]; then
                    echo "[watchdog] ⚠ HEAD 已等于 last_good_commit ($TARGET)，回退无效；可能 last_good 本身有问题，请人工介入"
                    cat > "$ROLLBACK_FILE" << EOF
$NOW_TS
$BEFORE_HEAD
$TARGET
$FAIL
NEEDS_MANUAL
EOF
                    sleep 30
                    continue
                fi

                # #C 主改进：写 last_rollback 元数据（5 行）让 webui + paimon 启动通知能读到
                echo "[watchdog] 连续异常 $FAIL 次，自动 git reset --hard $TARGET 回退"
                if git reset --hard "$TARGET"; then
                    echo "[watchdog] 回退成功，重置失败计数"
                    echo 0 > "$FAIL_COUNT_FILE"
                    cat > "$ROLLBACK_FILE" << EOF
$NOW_TS
$BEFORE_HEAD
$TARGET
$FAIL
ROLLED_BACK
EOF
                else
                    echo "[watchdog] 回退失败，5 秒后重试启动（请人工介入）"
                fi
            fi
            sleep 5
            ;;
    esac
done
