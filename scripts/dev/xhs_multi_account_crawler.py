"""
多账号主备抓取脚本（demo）。

按顺序尝试每个账号；第一个成功的就用第一个的结果；全失败才报错。
生产环境应在 OpenCLIAdapter 里实现，这里只验证多账号切换可行性。
"""
import json
import subprocess
import sys
import time

KEYWORD = sys.argv[1] if len(sys.argv) > 1 else "户外露营"
LIMIT = 5

# 多账号配置：按 priority 降序（数字越小越优先）
ACCOUNTS = [
    {"alias": "xhs1", "priority": 1, "session": "sess-xhs1"},
    {"alias": "xhs2", "priority": 2, "session": "sess-xhs2"},
]


def search_one(account, keyword, limit=5):
    cmd = [
        "opencli",
        "--profile", account["alias"],
        "xiaohongshu", "search", keyword,
        "--limit", str(limit),
        "-f", "json",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return None, "timeout"

    if proc.returncode != 0:
        return None, f"exit={proc.returncode} stderr={proc.stderr[:200]}"

    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as e:
        return None, f"json decode error: {e}"


def fetch_note(account, note_url):
    """抓单条笔记详情"""
    cmd = [
        "opencli",
        "--profile", account["alias"],
        "xiaohongshu", "note", note_url,
        "-f", "json",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    if proc.returncode != 0:
        return None, f"exit={proc.returncode} stderr={proc.stderr[:200]}"
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as e:
        return None, f"json decode error: {e}"


def main():
    print(f"=== 搜索主题: {KEYWORD}, 每账号 {LIMIT} 条 ===")
    # 按 priority 排序
    sorted_accounts = sorted(ACCOUNTS, key=lambda a: a["priority"])

    # 主备搜索
    primary_result, primary_account = None, None
    for acct in sorted_accounts:
        print(f"\n--- 尝试账号 {acct['alias']} ---")
        result, err = search_one(acct, KEYWORD, LIMIT)
        if err:
            print(f"  失败: {err}")
            continue
        print(f"  成功: {len(result)} 条")
        primary_result, primary_account = result, acct
        break

    if not primary_result:
        print("\n所有账号都失败")
        sys.exit(1)

    # 抓前 2 条笔记详情（验证详情抓取）
    print(f"\n=== 抓 {primary_account['alias']} 搜到的前 2 条详情 ===")
    for i, note in enumerate(primary_result[:2]):
        url = note.get("url", "")
        if not url:
            continue
        print(f"\n--- [{i+1}] {note.get('title', '')[:30]} ---")
        detail, err = fetch_note(primary_account, url)
        if err:
            print(f"  抓详情失败: {err}")
            continue
        # detail 是 [{field, value}, ...]
        fields = {x["field"]: x["value"] for x in detail}
        print(f"  title: {fields.get('title', '?')[:50]}")
        print(f"  likes={fields.get('likes', '?')}, "
              f"collects={fields.get('collects', '?')}, "
              f"comments={fields.get('comments', '?')}")
        print(f"  tags: {fields.get('tags', '?')[:80]}...")


if __name__ == "__main__":
    main()
