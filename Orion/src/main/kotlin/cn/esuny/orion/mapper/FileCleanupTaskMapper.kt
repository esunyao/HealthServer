package cn.esuny.orion.mapper

import cn.esuny.orion.model.entity.file.FileCleanupTask
import com.baomidou.mybatisplus.core.mapper.BaseMapper
import org.apache.ibatis.annotations.*
import java.time.OffsetDateTime

/**
 * 对象存储清理任务数据访问接口 (MyBatis-Plus Mapper)。
 * 封装了任务入队、分布式并发抢占锁、状态变更及僵尸任务恢复的原生 SQL。
 */
@Mapper
interface FileCleanupTaskMapper : BaseMapper<FileCleanupTask> {

    /**
     * 单条入队清理任务（幂等插入）。
     * 利用 PostgreSQL 的 `ON CONFLICT (bucket, object_key, task_type) DO NOTHING` 特性，
     * 当表中已存在完全相同的待清理记录时自动忽略，防止重复入队。
     */
    @Insert(
        "INSERT INTO orion.file_cleanup_tasks (task_id,owner_user_id,bucket,object_key,task_type,status,attempts,next_attempt_at,created_at) VALUES " +
        "(#{taskId},#{ownerUserId,typeHandler=cn.esuny.orion.model.typehandler.PgUuidTypeHandler},#{bucket},#{objectKey},#{taskType},#{status},#{attempts},#{nextAttemptAt},#{createdAt}) " +
        "ON CONFLICT (bucket,object_key,task_type) DO NOTHING"
    )
    fun enqueueIfAbsent(task: FileCleanupTask): Int

    /**
     * 批量入队清理任务（幂等批量插入）。
     * 使用 MyBatis `<script>` 和 `<foreach>` 标签拼接批量插入语句，同样具备 `ON CONFLICT DO NOTHING` 防重能力。
     */
    @Insert(
        "<script>INSERT INTO orion.file_cleanup_tasks (task_id,owner_user_id,bucket,object_key,task_type,status,attempts,next_attempt_at,created_at) VALUES " +
        "<foreach collection='tasks' item='task' separator=','>(#{task.taskId},#{task.ownerUserId,typeHandler=cn.esuny.orion.model.typehandler.PgUuidTypeHandler},#{task.bucket},#{task.objectKey},#{task.taskType},#{task.status},#{task.attempts},#{task.nextAttemptAt},#{task.createdAt})</foreach> " +
        "ON CONFLICT (bucket,object_key,task_type) DO NOTHING</script>"
    )
    fun enqueueIfAbsentBatch(@Param("tasks") tasks: Collection<FileCleanupTask>): Int

    /**
     * 分布式并发抢占式拉取 pending 状态的任务（核心竞争控制 SQL）。
     *
     * 技术细节：
     * 1. `WITH claimed AS (...)`：在 CTE 子查询中筛选 status='pending' 且达到了执行时间（next_attempt_at <= NOW()）的任务。
     * 2. `FOR UPDATE SKIP LOCKED`：PostgreSQL 高并发利器！锁定所选行，如果某行已被其他节点锁住则直接跳过，避免行锁等待和死锁，实现无锁并发消费。
     * 3. `UPDATE ... SET status='processing', processing_started_at=NOW()`：瞬间将抢占到的行状态修改为 processing，并记录开始时间。
     * 4. `RETURNING task.*`：原子地将修改后的任务完整记录返回给应用层。
     */
    @Select(
        "WITH claimed AS (" +
        "  SELECT task_id FROM orion.file_cleanup_tasks " +
        "  WHERE status='pending' AND next_attempt_at<=NOW() " +
        "  ORDER BY next_attempt_at FOR UPDATE SKIP LOCKED LIMIT #{limit}" +
        ") " +
        "UPDATE orion.file_cleanup_tasks task " +
        "SET status='processing', processing_started_at=NOW() " +
        "FROM claimed WHERE task.task_id=claimed.task_id " +
        "RETURNING task.*"
    )
    fun claimPending(@Param("limit") limit: Int): List<FileCleanupTask>

    /**
     * 标记任务完成。
     * 文件成功删除后调用：把状态改为 'completed'，清空处理开始时间与最近错误，记录完成时间。
     */
    @Update(
        "UPDATE orion.file_cleanup_tasks " +
        "SET status='completed',completed_at=NOW(),processing_started_at=NULL,last_error=NULL " +
        "WHERE task_id=#{taskId}"
    )
    fun markCompleted(@Param("taskId") taskId: Long): Int

    /**
     * 重新调度失败的任务（重试或彻底标记失败）。
     *
     * 逻辑：
     * 1. 尝试次数 `attempts + 1`。
     * 2. 如果新次数达到了最大尝试上限 (`maxAttempts`)，则把状态修改为 'failed'；否则恢复为 'pending' 等待下一次重试。
     * 3. 更新下一次允许尝试的时间 (`nextAttemptAt`) 和截断后的报错日志 (`lastError`)。
     */
    @Update(
        "UPDATE orion.file_cleanup_tasks SET status=" +
        "CASE WHEN attempts+1>=#{maxAttempts} THEN 'failed' ELSE 'pending' END,attempts=attempts+1,processing_started_at=NULL,next_attempt_at=#{nextAttemptAt},last_error=#{lastError} " +
        "WHERE task_id=#{taskId}"
    )
    fun reschedule(
        @Param("taskId") taskId: Long,
        @Param("nextAttemptAt") nextAttemptAt: OffsetDateTime,
        @Param("lastError") lastError: String,
        @Param("maxAttempts") maxAttempts: Int
    ): Int

    /**
     * 恢复死锁/僵尸任务（超时自动救活）。
     *
     * 场景：如果某个服务节点在处理任务时（status='processing'）突然宕机、OOM 或网络中断，会导致任务永久卡在 'processing' 状态。
     * 作用：扫描处理开始时间 `processing_started_at` 已经超过指定超时时间（如 10 分钟）的任务，强行重置为 'pending' 状态，由其他健康节点接管重新处理。
     */
    @Update(
        "UPDATE orion.file_cleanup_tasks " +
        "SET status='pending',processing_started_at=NULL " +
        "WHERE status='processing' AND processing_started_at < NOW() - (#{timeoutMinutes} * INTERVAL '1 minute')"
    )
    fun requeueStaleProcessing(@Param("timeoutMinutes") timeoutMinutes: Long): Int
}
