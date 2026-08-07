package cn.esuny.orion.model.entity.file

import com.baomidou.mybatisplus.annotation.IdType
import com.baomidou.mybatisplus.annotation.TableId
import com.baomidou.mybatisplus.annotation.TableName
import java.time.OffsetDateTime

/** 对象存储删除的可重试任务。 */
@TableName("file_cleanup_tasks")
data class FileCleanupTask(
    @TableId(type = IdType.ASSIGN_ID)
    val taskId: Long? = null,
    val bucket: String = "",
    val objectKey: String = "",
    val taskType: String = "",
    val status: String = STATUS_PENDING,
    val attempts: Int = 0,
    val nextAttemptAt: OffsetDateTime = OffsetDateTime.now(),
    val lastError: String? = null,
    val createdAt: OffsetDateTime = OffsetDateTime.now(),
    val processingStartedAt: OffsetDateTime? = null,
    val completedAt: OffsetDateTime? = null
) {
    companion object {
        const val STATUS_PENDING = "pending"
        const val STATUS_PROCESSING = "processing"
        const val STATUS_COMPLETED = "completed"
        const val STATUS_FAILED = "failed"
        const val TYPE_OLD_AVATAR = "old_avatar"
        const val TYPE_STAGING_SOURCE = "staging_source"
        const val TYPE_ORPHAN_AVATAR = "orphan_avatar"
    }
}


