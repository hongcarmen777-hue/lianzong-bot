# 小苹果 v0.2 🍎

这是一个刻意限缩后的 QQ 主群机器人：**恋综档案馆 + 选本/身份牌聊天搭子**。

不再负责心动信、心愿墙、小群、个人群、NPC、公告、随机嘉宾等跑团自动化。固定的一表格式、群公告、关键词回复等更适合交给 QQ 群管家。

## 它现在做什么

### 1. 骰主把整辆恋综直接“说给它听”

先私聊认主：

`认主 <CLAIM_TOKEN>`

然后在目标主群：

`@小苹果 设为主群`

开始录入：

`@小苹果 录入恋综 P1`

随后把恋综正文分成一条或多条消息，每一条都需要 `@小苹果`（QQ 官方机器人只能收到群里的 @ 事件）。最后：

`@小苹果 录入完成`

小苹果会保存：

- 每一段原始消息
- 拼接后的完整原文
- 系列名 / P编号 / 标题 / TAG
- 一表、二表、正式日程
- D0、D1……日程
- 01、02……身份牌的原始段落
- AI 提取的身份牌关系、关键词、概况（用于推荐检索）

原文不交给 AI 改写；AI 只负责做结构化索引。

### 2. 同编号再次录入 = 覆盖升级

再次发送：

`@小苹果 录入恋综 P1`

重新给新版全文并 `录入完成`，会覆盖 P1 当前内容，并把版本从 v1 升到 v2。数据库里保存的是最新版正式档案。

### 3. 自然聊天和推荐

任何非管理命令都进入聊天：

- `@小苹果 我想玩女强男弱，但不想男方太废，推荐一个。`
- `@小苹果 我在P1和P3之间纠结，你先问我几个问题。`
- `@小苹果 有没有事业线重、感情不太狗血的身份牌？`

小苹果会读取真实档案。偏好不够明确时，它可以先反问 1～2 个有区分度的问题，再推荐。

硬规则：**不能编造不存在的恋综、P编号和身份牌。**

## 数据表

v0.2 使用这些清晰表名：

- `xp_admins`：骰主
- `xp_settings`：主群等设置
- `xp_shows`：恋综正式档案，含原文和结构化索引
- `xp_ingest_drafts`：正在录入、尚未提交的草稿
- `xp_ai_history`：主群近期 AI 对话上下文

如果使用 CloudBase MySQL，可以直接通过腾讯云 DMC 数据库管理界面查看、编辑和导出这些表，不是黑箱。

## 重要：正式使用前请接持久数据库

如果不配置数据库，程序会暂时使用：

`sqlite:////tmp/xiaopingguo-v02.db`

它只适合测试。CloudBase 容器重新部署或重启后可能丢失。

v0.2 同时支持 MySQL 和 PostgreSQL。推荐在 CloudBase MySQL 开启直连后，把下面参数加入云托管环境变量：

- `MYSQL_HOST`
- `MYSQL_PORT`（通常 3306）
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`

也可以直接使用 `DATABASE_URL`。

## 环境变量

必填：

- `QQ_APP_ID`
- `QQ_APP_SECRET`
- `DEEPSEEK_API_KEY`
- `CLAIM_TOKEN`

建议：

- `DEEPSEEK_MODEL=deepseek-flash`
- `PORT=8080`
- `AI_HISTORY_LIMIT=20`

## 从 v0.1 升级

CloudBase 已经开启 GitHub 自动部署的话，把本包同名文件覆盖到仓库 `main` 分支即可自动重新构建。

需要覆盖：

- `main.py`
- `requirements.txt`
- `Dockerfile`
- `README.md`
- `xiaopingguo/__init__.py`
- `xiaopingguo/config.py`
- `xiaopingguo/db.py`
- `xiaopingguo/parser.py`（新增）
- `xiaopingguo/ai.py`
- `xiaopingguo/commands.py`
- `xiaopingguo/bot.py`

旧的 v0.1 数据表即使还在 SQLite / SQL 数据库中也不会被 v0.2 使用。
