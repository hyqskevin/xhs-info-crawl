# 爬虫设计

## 爬虫工具

- **工具**：OpenCLI (`jackwener/OpenCLI`)
- **核心命令**：
  - `opencli xiaohongshu search --keyword "{keyword}" --limit {n}`
  - `opencli xiaohongshu note --url "{note_url}"`
  - `opencli xiaohongshu download "{note_url}" --output ./images`
- **登录态**：复用 Chrome 已登录 session，通过 CDP 连接

## 本地验证环境

### 启动 Chrome 并开启 CDP

**macOS：**

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/chrome-debug-profile" \
  --remote-allow-origins="*"
```

**Linux：**

```bash
google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/chrome-debug-profile" \
  --remote-allow-origins="*"
```

启动后，在 Chrome 中登录小红书。

### 设置环境变量并测试

```bash
export OPENCLI_CDP_ENDPOINT="http://localhost:9222"
opencli doctor
opencli xiaohongshu search --keyword "上海 周末活动" --limit 10 -f json
```

## 抓取流程

```python
def run_keyword_crawl(task_id: int, city_code: str, keyword: str):
    # 1. 调用 OpenCLI 搜索
    result = opencli.run(
        "xiaohongshu", "search",
        f"--keyword", f"{city_name} {keyword}",
        f"--limit", str(SEARCH_LIMIT),
        "-f", "json"
    )
    
    # 2. 解析搜索结果
    notes = parse_search_result(result)
    
    # 3. 过滤近 7 天笔记
    notes = filter_recent_notes(notes, days=7)
    
    # 4. 保存到 notes 表（待处理状态）
    save_notes(task_id, notes, city_code, keyword)
    
    # 5. 间隔 10-15 秒
    time.sleep(random.randint(10, 15))
```

## 笔记详情下载

```python
def download_note_details(note_id: int, note_url: str):
    # 1. 调用 OpenCLI 获取笔记详情
    detail = opencli.run("xiaohongshu", "note", "--url", note_url, "-f", "json")
    
    # 2. 保存标题、正文、互动数据
    update_note(note_id, detail)
    
    # 3. 通过统一 Storage 接口保存图片
    images = opencli.run("xiaohongshu", "download", note_url, "--output", tmp_dir)
    for img_path in images:
        storage_key = storage.save(img_path)
        save_note_image(note_id, storage_key, original_url=...)
```

## 错误处理

| 错误码 | 含义 | 处理策略 |
|--------|------|----------|
| 0 | 成功 | 继续 |
| 66 | 结果为空 | 记录并跳过 |
| 69 | Browser Bridge 未连接 | 检查 Chrome/CDP，重试 |
| 75 | 超时 | 重试，最多 3 次 |
| 77 | 需要认证 | 暂停任务，发送告警 |
| 78 | 配置错误 | 记录错误，人工检查 |
| 130 | 用户中断 | 记录任务中断 |

## 反爬策略

- 关键词搜索间隔：10-15 秒
- 单账号每周搜索总量不超过 500 次（可配置）
- 使用 OpenCLI 的真实浏览器行为，避免低级别 HTTP 请求
- 遇到验证码或登录失效，立即暂停并告警
- 不抓取评论、私信等敏感内容
