-- 小苹果 v0.2.3：CloudBase MySQL HTTP API 持久化表
-- 在 CloudBase → SQL 型数据库 → SQL 编辑器中一次性执行。
-- 所有表都保留 _openid 字段，兼容 CloudBase MySQL 数据权限机制。

CREATE TABLE IF NOT EXISTS `xp_admins` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `user_openid` VARCHAR(200) NOT NULL,
  `_openid` VARCHAR(64) NULL,
  `created_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_xp_admin_openid` (`user_openid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `xp_settings` (
  `key` VARCHAR(100) NOT NULL,
  `value` LONGTEXT NOT NULL,
  `_openid` VARCHAR(64) NULL,
  `updated_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `xp_shows` (
  `code` VARCHAR(40) NOT NULL,
  `series` VARCHAR(150) NOT NULL DEFAULT '',
  `title` VARCHAR(250) NOT NULL DEFAULT '',
  `full_name` VARCHAR(350) NOT NULL DEFAULT '',
  `tags_json` LONGTEXT NOT NULL,
  `schedule_json` LONGTEXT NOT NULL,
  `identity_cards_json` LONGTEXT NOT NULL,
  `summary` LONGTEXT NOT NULL,
  `metadata_json` LONGTEXT NOT NULL,
  `raw_text` LONGTEXT NOT NULL,
  `raw_chunks_json` LONGTEXT NOT NULL,
  `version` INT NOT NULL DEFAULT 1,
  `_openid` VARCHAR(64) NULL,
  `created_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`code`),
  KEY `idx_xp_shows_updated_at` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `xp_ingest_drafts` (
  `admin_openid` VARCHAR(200) NOT NULL,
  `show_code` VARCHAR(40) NOT NULL,
  `mode` VARCHAR(20) NOT NULL DEFAULT 'upsert',
  `chunks_json` LONGTEXT NOT NULL,
  `_openid` VARCHAR(64) NULL,
  `created_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`admin_openid`),
  KEY `idx_xp_drafts_show_code` (`show_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `xp_ai_history` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `conversation_key` VARCHAR(300) NOT NULL,
  `role` VARCHAR(20) NOT NULL,
  `content` LONGTEXT NOT NULL,
  `_openid` VARCHAR(64) NULL,
  `created_at` TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `idx_xp_history_conversation` (`conversation_key`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
