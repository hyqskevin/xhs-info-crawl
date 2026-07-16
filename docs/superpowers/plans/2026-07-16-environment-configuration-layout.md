# Environment Configuration Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对本地环境变量进行中文注释和分类，同时保持配置行为不变。

**Architecture:** 仅调整 `.env` 与 `.env.example` 的可读性。变量名称和值仍由现有 FastAPI、Celery 和 Vite 配置入口读取。

**Tech Stack:** dotenv、FastAPI、Celery、Vite

## Global Constraints

- 不新增、删除或重命名环境变量。
- `.env` 的当前值不得改变。
- 敏感值不得复制到 `.env.example`。

---

### Task 1: 整理环境变量文件

**Files:**
- Modify: `.env`
- Modify: `.env.example`

**Interfaces:**
- Consumes: 现有 dotenv 键值配置。
- Produces: 与原配置等价、按功能分类并逐项附中文说明的 dotenv 文件。

- [ ] **Step 1: 记录整理前的变量名和值摘要**

运行安全的键名和值哈希比较脚本，不输出敏感原值。

- [ ] **Step 2: 按设计分类并添加逐项注释**

保持每一行 `KEY=value` 的键和值不变，只调整顺序并添加注释。

- [ ] **Step 3: 验证变量集合和值未改变**

比较修改前后的键集合和值哈希；预期完全一致。

- [ ] **Step 4: 验证配置仍可加载**

运行后端配置测试和前端构建；预期命令退出码为 0。

