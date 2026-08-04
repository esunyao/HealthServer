-- ============================================================
-- V1: 创建 file_cleanup_tasks 表
-- ============================================================
-- 说明：
-- 存储对象存储（RustFS/S3 兼容）文件的异步删除任务。
-- 用于头像替换时异步清理旧文件，支持失败重试（指数退避）。
-- task_id 为 BIGINT，由应用层雪花算法生成。
-- ============================================================

CREATE TABLE IF NOT EXISTS "User".file_cleanup_tasks (
    task_id         BIGINT          NOT NULL,
    bucket          VARCHAR(255)    NOT NULL,
    object_key      VARCHAR(1024)   NOT NULL,
    task_type       VARCHAR(32)     NOT NULL,
    status          VARCHAR(16)     NOT NULL DEFAULT 'pending',
    attempts        INTEGER         NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    last_error      TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,

    CONSTRAINT file_cleanup_tasks_pk
        PRIMARY KEY (task_id),

    CONSTRAINT chk_file_cleanup_tasks_task_id_positive
        CHECK (task_id > 0),

    CONSTRAINT chk_file_cleanup_tasks_status
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),

    CONSTRAINT chk_file_cleanup_tasks_attempts
        CHECK (attempts >= 0),

    CONSTRAINT uq_file_cleanup_tasks_object
        UNIQUE (bucket, object_key, task_type)
);

COMMENT ON TABLE  "User".file_cleanup_tasks IS '对象存储文件的异步清理任务队列。记录需要从 RustFS 删除的旧头像、临时文件等，支持失败指数退避重试。';
COMMENT ON COLUMN "User".file_cleanup_tasks.task_id         IS '任务唯一标识，BIGINT，由应用层雪花算法生成';
COMMENT ON COLUMN "User".file_cleanup_tasks.bucket          IS '对象存储桶名称';
COMMENT ON COLUMN "User".file_cleanup_tasks.object_key      IS '对象存储中的文件路径（key）';
COMMENT ON COLUMN "User".file_cleanup_tasks.task_type       IS '任务类型：old_avatar / staging_source / orphan_avatar';
COMMENT ON COLUMN "User".file_cleanup_tasks.status          IS '任务状态：pending / processing / completed / failed';
COMMENT ON COLUMN "User".file_cleanup_tasks.attempts        IS '已尝试次数，用于指数退避计算';
COMMENT ON COLUMN "User".file_cleanup_tasks.next_attempt_at IS '下次重试时间，pending 状态下按此时间调度';
COMMENT ON COLUMN "User".file_cleanup_tasks.last_error      IS '最近一次失败的错误信息（截取前 1000 字符）';
COMMENT ON COLUMN "User".file_cleanup_tasks.created_at      IS '任务创建时间';
COMMENT ON COLUMN "User".file_cleanup_tasks.completed_at    IS '任务完成时间';

-- 调度查询索引：每分钟批量拉取 pending 任务时使用
CREATE INDEX IF NOT EXISTS idx_file_cleanup_tasks_pending
    ON "User".file_cleanup_tasks (status, next_attempt_at)
    WHERE status = 'pending';

