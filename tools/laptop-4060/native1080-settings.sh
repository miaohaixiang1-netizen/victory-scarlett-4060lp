#!/bin/bash
# launch_scarlett_8gb.sh - 综合版启动（bash 版，绕过 PowerShell ExecutionPolicy）
# victory-scarlett-3070 scarlett-fox + RENDER_SCALE + 修脸三件套
cd "D:/gta/重编译资料/repos/victory-scarlett-3070"

export VICTORY_GAME_DIR="D:/gta/GTA6.v1.0.2.1-CYBERLEEK（游戏本体）"
export VICTORY_CACHE_DIR="D:/gta/重编译资料/ab/cache_scarlett_8gb"
export VICTORY_DATA_DIR="D:/gta/重编译资料/ab/data_cool_fox_8gb"
export VICTORY_PIPELINE_BOOK=1
export VICTORY_CARD_SPANS=1
export VICTORY_LOG=info
export VICTORY_FRAME_INTERVAL_MS=16.667

# 实验：原生 1080p，完全不设 hooks（RENDER_SCALE 会 patch 标题二进制，scale=1.0 时崩溃）
# 不设 NO_WATCHDOG/RENDER_SCALE/OWN_UPSCALER → hooks 代码路径不触发，走游戏原生 Series S 1080p
# 保留 THIN=1 + RAM_CAPS=0 + MIP_DROP=1 等所有 CPU/显存优化

# 修脸三件套（-Quality 档，有脸）
export VICTORY_RELAY=1
export VICTORY_CARD_STEPS=0
export VICTORY_TEXTURE_NO_WAIT=0

# 8GB VRAM budget + Scarlett page pool
export VICTORY_DYNAMIC_SLOTS=524288
export VICTORY_MAX_PRELUDES=32
export VICTORY_CARD_BUFFERS_MB=1024
export VICTORY_CARD_WINDOWS_MB=512
export VICTORY_TEXTURE_MIP_DROP=1
export VICTORY_TEXTURE_ROOM_PERCENT=94
export VICTORY_CARD_ROOM_FOR_TARGETS_MB=1536
# 无损解：关掉多余的 host-RAM soft cap（保留 critical OOM 保护），纹理上传快 3 倍
export VICTORY_TEXTURE_RAM_CAPS=0
export VICTORY_READ_KEEP_MB=64
export VICTORY_SECTION_MB=2
export VICTORY_PAGE_POOL=1
export VICTORY_STAGING_PACK=1
export VICTORY_LEVELS_ON_DEMAND=0

# Scarlett CPU submit & upload wins
export VICTORY_WAIT_RESIDENT=0
export VICTORY_JOIN_COPIES=0
export VICTORY_REFRESH_ONCE=1
export VICTORY_CARD_REHASH_RUNS=1
export VICTORY_BACK_OWN_VIEW=1
export VICTORY_WIDE_MERGE=1
export VICTORY_MIRROR_FAST=1
export VICTORY_PIPELINE_WAIT_MS=20
export VICTORY_ASYNC_SUBMIT=1
# 实验变量：THIN=1 用 8 线程并行翻译 list calls（CPU 提交优化）
# 注意：scarlett-fox 作者标注在 7900XTX/64GB 上 no gain + 2x long frames，
# 但本机 8GB/31GB 瓶颈在 CPU，值得 A/B 验证（单变量实验）
export VICTORY_THIN=1
export VICTORY_WAVE_PAIRS_FIRST=1
export VICTORY_QUEUE2=1
export VICTORY_INDIRECT_WINDOW=1
export VICTORY_COPY_PLAIN=1
export VICTORY_WIDE_TEXTURES=1
export VICTORY_INDIRECT_GATHER=1
export VICTORY_LATE_WAIT_LISTS=1024
export VICTORY_CARD_FILLS_BATCH=0
export VICTORY_GATHER_DISPATCH=0
export VICTORY_WIDE_BACK=1
export VICTORY_RELAY_COPY=1
export VICTORY_INDIRECT_BATCH=2
export VICTORY_MAP_THREADS=1
export VICTORY_CARD_AWAKE=0
export VICTORY_SHOW_AFTER=1
export VICTORY_JOIN_PARTS=8
export VICTORY_UPLOAD_AHEAD=1
export VICTORY_CARD_BUFFERS_MIN_KB=64
export VICTORY_POOL_DISCARD=1
export VICTORY_FILL_TITLE=1
export VICTORY_PARTIAL_DELTA=1
export VICTORY_BAKE_DELTA=1
export VICTORY_MAP_LOCK_FINE=1
export VICTORY_POOL_CAP=1
export VICTORY_TABLE_MEMO=1
export VICTORY_LIST_ALIAS_EXACT=1
export VICTORY_LIST_HOLD=1
export VICTORY_EARLY_TEXTURES_MS=40
export VICTORY_BAKE_TEXTURES_MS=10000
export VICTORY_HEAP_PASS_MAX=0
export VICTORY_HEAP_CHANGED_MAX=0
export VICTORY_LEAVE_OUT=02384a60fda6f2d0
export VICTORY_WC_NO_BACK=1
export VICTORY_WC_NO_BACK_MIN_KB=1024
export VICTORY_SYNC_IN_PLACE=1
export VICTORY_SPANS_QUICK=1
export VICTORY_SYNC_FINE=1
export VICTORY_HEAP_SYNC_FIRST=1
export VICTORY_HEAP_SYNC_AT_SUBMIT=1
export VICTORY_SOFT_VIEWS=copies
export VICTORY_SAMPLERS_MADE=1
export VICTORY_TABLE_NAMED_ONLY=1
export VICTORY_QUEUE_MARKS=1
export VICTORY_PORT_CONSTANTS=0
export VICTORY_EARLY_DEPTH=1

# 自动过场（基于 draws/frame 的按键脚本，自动点过账户进世界）
export VICTORY_AUTO_INPUT='d>=15,rep(A,1,d>=10)'

# 环境光（无光追时）
export VICTORY_AMBIENT=0.8
export VICTORY_AMBIENT_AIR=1.5

echo "=== victory-scarlett-3070 综合版 (RTX 4060 8GB, 有脸+540p, scarlett-fox 优化) ==="
echo "RENDER_SCALE=0.5 + OWN_UPSCALER + 修脸三件套 + PAGE_POOL + SECTION_MB + DescriptorSync5 + TEXBACK_ASYNC"
echo "Log: D:/gta/重编译资料/ab/scarlett_8gb.log"
echo ""

GAME="D:/gta/GTA6.v1.0.2.1-CYBERLEEK（游戏本体）/game_scarlett_master.exe"
LOG="D:/gta/重编译资料/ab/scarlett_8gb_native1080.log"

# HUD 随游戏一起启动（不传 pid，hud.py 自动 find_game()）
HUD_PY="C:/Users/20708/.workbuddy/binaries/python/versions/3.13.12/python.exe"
HUD_SCRIPT="D:/gta/重编译资料/hud.py"
"$HUD_PY" "$HUD_SCRIPT" "$LOG" &
HUD_PID=$!
trap 'kill $HUD_PID 2>/dev/null' EXIT

./target/release/victory.exe run "$GAME" --execute --console series-s 2>&1 | tee "$LOG"

# 游戏退出后自动增量预热新增管线（AUTO_WARM=0 可跳过）
if [ "${AUTO_WARM:-1}" = "1" ]; then
    ./target/release/victory.exe warm --jobs 16 2>&1 | tail -5
fi
