-- HealthMindControl v0.2：candidate 版本的“绑定工具”变更需要写入标准审计。
-- 仅放宽 action CHECK，新增 'tools_bound'，不改任何其他约束/数据。
SET search_path TO healthmind, public;

ALTER TABLE healthmind.workflow_release_audits DROP CONSTRAINT workflow_release_audits_action_check;
ALTER TABLE healthmind.workflow_release_audits
    ADD CONSTRAINT workflow_release_audits_action_check
    CHECK (action IN ('created', 'promoted', 'rolled_back', 'retired', 'tools_bound'));
