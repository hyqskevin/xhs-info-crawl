#!/bin/bash
# 本地一次性操作:把老 Application Support/com.xhs-info-crawl.local/ 顶层内容
# 重组为 base-dir 模式 (data/ 子目录)。
#
# 关联背景:
# - 2026-08-24 用户反馈 "我这里删掉，是不是走默认了" → launcher 陈旧 fallback spec
# - v0.7.0+6 时代 DATA_DIR 是 Application Support 顶层
# - v0.7.0+9 之后 base-dir 模式要求 DATA_DIR 是 Application Support/com.xhs-info-crawl.local/data
# - 此脚本帮你从老布局迁到新布局
#
# 警告:
# - 涉及生产数据移动 (1.7GB+),运行前请确认 ~/Library/Application Support/com.xhs-info-crawl.local/.env 里的 DATA_DIR 已经是 /data 结尾
# - 执行后 .app/.env 的 DATA_DIR 必须指向 Application Support/com.xhs-info-crawl.local/data,否则 launcher 会写到 .app 内部
# - 不要再启老 v0.7.0+6 之前的 .app,会读到老 layout
#
# 用法: bash scripts/dev/local-realign-data-dir-to-base-dir.sh

set -e

DATA_HOME="/Users/hanamaki_mac_mini/Library/Application Support/com.xhs-info-crawl.local"
DATA_DIR="$DATA_HOME/data"

if [ ! -d "$DATA_HOME" ]; then
    echo "错误: $DATA_HOME 不存在,无需迁移"
    exit 1
fi

if [ -d "$DATA_DIR" ] && [ -n "$(ls -A "$DATA_DIR" 2>/dev/null)" ]; then
    echo "错误: $DATA_DIR 已存在且非空,可能已经迁过。手动检查后再决定"
    ls -la "$DATA_DIR"
    exit 1
fi
# data 目录是空目录(如 mkdir -p 预创建的)时,直接复用,无需先删
if [ ! -d "$DATA_DIR" ]; then
    : # 下面统一 mkdir
fi

# 校验 .env 里 DATA_DIR 已指向 data 结尾
ENV_FILE="$DATA_HOME/.env"
if [ -f "$ENV_FILE" ]; then
    CURRENT_DATA_DIR=$(grep -E "^DATA_DIR=" "$ENV_FILE" | head -1 | cut -d= -f2)
    EXPECTED="$DATA_DIR"
    if [ "$CURRENT_DATA_DIR" != "$EXPECTED" ]; then
        echo "警告: .env 的 DATA_DIR=$CURRENT_DATA_DIR 不是预期的 $EXPECTED"
        echo "  本脚本假设你已经手动改了 DATA_DIR 到 $DATA_DIR"
        echo "  如果不确定,Ctrl-C 退出,先改 .env 再重跑"
        read -p "继续吗? (y/N) " yn
        if [ "$yn" != "y" ]; then
            exit 1
        fi
    fi
fi

echo "=== 创建 $DATA_DIR ==="
mkdir -p "$DATA_DIR"

echo "=== 移动子目录到 $DATA_DIR ==="
# base-dir 派生子目录,平移
for sub in images archive celery chrome-pool exports paddlex run tmp; do
    if [ -e "$DATA_HOME/$sub" ]; then
        echo "  mv $sub → data/$sub"
        mv "$DATA_HOME/$sub" "$DATA_DIR/$sub"
    fi
done

# app.db 是 base-dir 模式下 database_url 派生位置
if [ -f "$DATA_HOME/app.db" ]; then
    echo "  mv app.db → data/app.db"
    mv "$DATA_HOME/app.db" "$DATA_DIR/app.db"
fi

# 备份文件跟随
if [ -f "$DATA_HOME/app.db.backup-pre-dev" ]; then
    echo "  mv app.db.backup-pre-dev → data/app.db.backup-pre-dev"
    mv "$DATA_HOME/app.db.backup-pre-dev" "$DATA_DIR/app.db.backup-pre-dev"
fi

echo ""
echo "=== 迁移完成 ==="
echo "迁移后 layout:"
ls -la "$DATA_HOME"
echo ""
echo "data/ 子目录:"
ls -la "$DATA_DIR"