
# Gmail Auto-Reply (Python 3.9+)

一个本地运行的 Gmail 自动回复工具：每天读取当天邮件，根据关键词匹配模板并自动回复。支持多账号、每账号独立规则/模板、独立 token/state。

## 快速开始

1. **克隆/解压本项目**，确保 Python 3.9+ 环境可用。建议创建虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate   # Windows 使用: .venv\Scripts\activate
pip install -r requirements.txt
```

2. **在 Google Cloud Console 启用 Gmail API 并下载凭据**：
   - 打开 https://console.cloud.google.com/
   - 创建或选择项目 → 「API 与服务」→「库」→ 启用 **Gmail API**
   - 「API 与服务」→「OAuth 同意屏幕」按指引完成
   - 「凭据」→「创建凭据」→「OAuth 客户端 ID」→ 类型选“桌面应用”→ 下载 `credentials.json`
   - 将文件放到项目根目录（与本 README 同级）

3. **可选：配置 `.env`**（设置时区、是否跳过特定发件人等）：
   - 复制一份 `.env.example` 为 `.env`，按需修改

4. **首次授权（本地运行一次）**：

```bash
python src/main.py --init-auth
# 多账号授权（会分别生成 token_*.json）
python src/main.py --init-auth --accounts first@example.com,second@example.com
```

浏览器会弹出 OAuth 授权；成功后会在项目根目录生成 `token.json`（勿泄露）。

5. **运行自动回复（手动执行）**：

```bash
python3.9 src/main.py --run
python3.9 src/main.py --dry-run
# 多账号运行（也可通过 .env: ACCOUNTS=...）
python3.9 src/main.py --run --accounts first@example.com,second@example.com

python3.9 src/main.py --run --accounts photogridapp.feedback@gmail.com
# 演练模式（不真正发信）
python3.9 src/main.py --run --accounts photogridapp.feedback@gmail.com --dry-run

```

6. **定时执行**：
   - macOS/Linux: `crontab -e` 添加（每天 09:00 运行）：
     ```
     0 9 * * * /full/path/to/python /full/path/to/gmail_autoreply_python/src/main.py --run >> /full/path/to/gmail_autoreply_python/logs/cron.log 2>&1
     ```
   - Windows: 使用「任务计划程序」创建每日触发的任务，程序/脚本填写 Python 路径，参数填写 `src\main.py --run`，起始位置填写项目路径。

## 关键词与模板

- 规则文件：`data/rules.json`
- 支持按账号覆盖：存在 `data/rules_{email_sanitized}.json` 时会优先加载（其中 `{email_sanitized}` 是把邮箱里的 `@` 替换为 `_` 且过滤非法字符，比如 `user@gmail.com` → `user_gmail_com`）
- 模板目录：`templates/`
- 匹配逻辑：对 **主题+正文** 进行不区分大小写的包含判断（支持多关键词中任意命中 / 全部命中，见 `match_mode`）
- 回复主题：默认 `Re: <原主题>`，可在规则中叠加 `subject_prefix`

## 避免重复回复

- 程序会为已自动回复的线程添加标签 **AutoReplied** 并记录到 `data/state.json`（多账号对应 `data/state_{email_sanitized}.json`），防止重复回复。
- 可通过 `.env` 中 `SKIP_SENDERS` 跳过特定发件人（逗号分隔）。

## 开发/调试

- 开启干跑（不真正发送，仅打印）：`--dry-run`
- 指定日期运行（读取指定日期的邮件，格式 YYYY-MM-DD）：`--date 2025-09-24`

## 目录结构

```
gmail_autoreply_python/
  ├─ src/
  │  ├─ main.py                 # 入口：参数解析、调度
  │  ├─ gmail_service.py        # Gmail API 封装（认证/查询/发送/打标签）
  │  └─ utils/
  │     ├─ email_parser.py      # 解析 MIME、取纯文本/HTML、提取头
  │     └─ rules_engine.py      # 简单规则引擎与渲染
  ├─ templates/                 # 回复模板（Jinja2）
  ├─ data/
  │  ├─ rules.json              # 关键词→模板映射
  │  └─ state.json              # 已处理线程/消息记录
  ├─ logs/
  ├─ requirements.txt
  ├─ .env.example
  └─ README.md
```

## 注意

- 首次运行需手动完成 OAuth 授权。
- 本工具不会对垃圾邮件箱操作，仅处理收件箱（INBOX）。
- 请保护好 `credentials.json` 与 `token*.json`，避免泄露。

