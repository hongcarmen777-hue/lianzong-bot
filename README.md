# 小苹果 v0.2.4 🍎

这一版在 v0.2.3 的持久化数据库基础上，把**骰主档案后台彻底移到私聊**：私聊录入/覆盖，主群只负责查询、聊天和推荐。

小苹果的产品定位仍然保持极简：

- 骰主在**私聊**把历届恋综原文直接录给它；原文完整保存，同时整理出 P 编号、标题、TAG、日程、身份牌等结构化索引。
- 玩家在主群自然地问“我想玩什么”“P1 和 P3 怎么选”“有没有女强男弱但男方不废的”，小苹果从真实档案里检索、比较，必要时反问 1～2 个偏好问题。
- 固定 FAQ、一表格式、一表收集继续交给 QQ 群管家。

## 1. 一次性创建可见数据表

打开 CloudBase：`SQL 型数据库 → SQL 编辑器`，把仓库根目录的 `cloudbase_mysql_setup.sql` 全部粘贴进去执行一次。

执行后，“数据库表”里应该能看到：

- `xp_admins`
- `xp_settings`
- `xp_shows`
- `xp_ingest_drafts`
- `xp_ai_history`

这些就是小苹果真正的长期记忆，全部在腾讯云后台可见。

## 2. 创建服务端 API Key

CloudBase：`环境配置 / API Key 配置` → 创建 **服务端 API Key**。

服务端 Key 是长期管理员凭证，只放云托管环境变量，不能放 GitHub、群聊或截图里。

云托管更新版本时有两种配置方法，二选一：

### 方法 A：推荐

打开“API Key 设置”，选择你刚创建的服务端 Key。CloudBase 通常会自动注入：

`CLOUDBASE_APIKEY`

v0.2.4 会自动识别这个变量。

再手动新增：

`TCB_ENV_ID=<你的 CloudBase 环境 ID>`

### 方法 B：手动环境变量

直接填：

`TCB_ENV_ID=<你的 CloudBase 环境 ID>`

`TCB_API_KEY=<服务端 API Key>`

## 3. 不再需要这些 MySQL 直连配置

使用 HTTP API 后，不需要：

- VPC / 子网
- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`

MySQL 外网地址也可以继续关闭。

## 4. 其他环境变量

继续保留：

- `QQ_APP_ID`
- `QQ_APP_SECRET`
- `DEEPSEEK_API_KEY`
- `CLAIM_TOKEN`
- `PORT=8080`
- `AI_HISTORY_LIMIT=20`

DeepSeek 当前正式 Flash 模型 ID 使用：

`DEEPSEEK_MODEL=deepseek-v4-flash`

如果你的 CloudBase 里还写着旧的 `deepseek-flash`，v0.2.4 会自动转换成 `deepseek-v4-flash`，但建议以后直接改成正式 ID。

## 5. 怎么确认已经用上永久数据库

部署后私聊或主群 @小苹果发送：

`数据库状态`

正确结果应当是：

`小苹果 v0.2.4｜数据库：CloudBase MySQL HTTP API（持久化）`

如果显示 `SQLite 临时数据库`，说明 `TCB_ENV_ID` 或 API Key 没注入成功。

## 6. 第一次迁移说明

之前 P1、认主状态和主群设置存放在各个旧容器自己的临时 SQLite 中，**不会自动迁移**。

接上 HTTP 数据库后重新做一次即可：

1. 私聊：`认主 <CLAIM_TOKEN>`
2. 主群：`@小苹果 设为主群`
3. **私聊**：`录入恋综 P1`
4. 继续私聊分段发送原文，不用 @小苹果
5. 私聊：`录入完成`
6. 主群随后即可查询这份档案

之后重新部署/重启，数据仍然在 CloudBase MySQL 中。


## 私聊录入流程（v0.2.4）

骰主私聊小苹果：

```text
录入恋综 P2
```

小苹果进入录入状态后，继续直接私聊发送完整资料，可以拆成多条，不需要 @。最后发送：

```text
录入完成
```

同一个 P 编号再次录入会覆盖旧档案并自动升版本。可随时发送 `取消录入` 放弃本次草稿。

主群里的 `录入恋综 P2` 不再真正开始录入，只会提示骰主回私聊操作。这样主群始终只承担对外查询与推荐。

## 7. 旧版本实例仍需清理

HTTP 数据库解决的是“几只苹果各记各的”问题；但 QQ Bot 本身仍然不应长期让多个旧容器同时连接。

新版本确认正常后，把旧的 002、003 等部署版本删除/缩容，只保留最新版本 1 个实例。

## 数据安全

`cloudbase_mysql_setup.sql` 为每张表保留了 `_openid` 字段，兼容 CloudBase MySQL 权限机制。机器人使用的是服务端 API Key，Key 只存云端环境变量。
