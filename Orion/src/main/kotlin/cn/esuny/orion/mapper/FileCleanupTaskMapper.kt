package cn.esuny.orion.mapper

import cn.esuny.orion.model.entity.file.FileCleanupTask
import com.baomidou.mybatisplus.core.mapper.BaseMapper
import org.apache.ibatis.annotations.Insert
import org.apache.ibatis.annotations.Mapper
import org.apache.ibatis.annotations.Param
import org.apache.ibatis.annotations.Select
import org.apache.ibatis.annotations.Update
import java.time.OffsetDateTime

@Mapper
interface FileCleanupTaskMapper : BaseMapper<FileCleanupTask> {

    @Insert("""
        INSERT INTO "User".file_cleanup_tasks
            (task_id, bucket, object_key, task_type, status, attempts, next_attempt_at, created_at)
        VALUES
            (#{taskId}, #{bucket}, #{objectKey}, #{taskType}, #{status}, #{attempts}, #{nextAttemptAt}, #{createdAt})
        ON CONFLICT (bucket, object_key, task_type) DO NOTHING
    """)
    fun enqueueIfAbsent(task: FileCleanupTask): Int

    @Select("""
        WITH claimed AS (
            SELECT task_id
            FROM "User".file_cleanup_tasks
            WHERE status = 'pending' AND next_attempt_at <= NOW()
            ORDER BY next_attempt_at
            FOR UPDATE SKIP LOCKED
            LIMIT #{limit}
        )
        UPDATE "User".file_cleanup_tasks task
        SET status = 'processing'
        FROM claimed
        WHERE task.task_id = claimed.task_id
        RETURNING task.*
    """)
    fun claimPending(@Param("limit") limit: Int): List<FileCleanupTask>

    @Update("""
        UPDATE "User".file_cleanup_tasks
        SET status = 'completed', completed_at = NOW(), last_error = NULL
        WHERE task_id = #{taskId}
    """)
    fun markCompleted(@Param("taskId") taskId: Long): Int

    @Update("""
        UPDATE "User".file_cleanup_tasks
        SET status = 'pending', attempts = attempts + 1,
            next_attempt_at = #{nextAttemptAt}, last_error = #{lastError}
        WHERE task_id = #{taskId}
    """)
    fun reschedule(
        @Param("taskId") taskId: Long,
        @Param("nextAttemptAt") nextAttemptAt: OffsetDateTime,
        @Param("lastError") lastError: String
    ): Int
}
