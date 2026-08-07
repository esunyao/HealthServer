package cn.esuny.orion.service.impl

import cn.esuny.orion.config.OssProperties
import cn.esuny.orion.mapper.FileCleanupTaskMapper
import cn.esuny.orion.model.entity.file.FileCleanupTask
import cn.esuny.orion.service.FileCleanupTaskService
import com.baomidou.mybatisplus.core.toolkit.IdWorker
import org.slf4j.LoggerFactory
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Service
import software.amazon.awssdk.services.s3.S3Client
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest
import java.time.OffsetDateTime

/**
 * 对象存储异步清理任务服务实现类。
 * 负责入队清理任务，并由定时任务轮询消费清理 S3/RustFS 中的无用文件。
 */
@Service
class FileCleanupTaskServiceImpl(
    private val fileCleanupTaskMapper: FileCleanupTaskMapper,
    private val s3Client: S3Client,
    private val ossProperties: OssProperties
) : FileCleanupTaskService {

    private val log = LoggerFactory.getLogger(FileCleanupTaskServiceImpl::class.java)

    /** 提交旧头像清理任务 */
    override fun enqueueOldAvatar(bucket: String, objectKey: String) =
        enqueue(bucket, objectKey, FileCleanupTask.TYPE_OLD_AVATAR)

    /** 提交暂存区源文件清理任务 */
    override fun enqueueStagingSource(bucket: String, objectKey: String) =
        enqueue(bucket, objectKey, FileCleanupTask.TYPE_STAGING_SOURCE)

    /** 提交对账扫描出的孤儿头像清理任务 */
    override fun enqueueOrphanAvatar(bucket: String, objectKey: String) =
        enqueue(bucket, objectKey, FileCleanupTask.TYPE_ORPHAN_AVATAR)

    /**
     * 批量提交对账扫描出的孤儿头像清理任务。
     * 将解析出的多个孤儿文件 Key 批量映射为带雪花算法 ID 的任务实体，并调用批量 SQL 幂等写入数据库。
     */
    override fun enqueueOrphanAvatars(bucket: String, objectKeys: Collection<String>) {
        // 1. 空集合直接返回，避免无意义的数据库交互
        if (objectKeys.isEmpty()) return

        // 2. 构造对象列表并执行批量幂等入队 (ON CONFLICT DO NOTHING)
        fileCleanupTaskMapper.enqueueIfAbsentBatch(
            objectKeys.map {
                FileCleanupTask(
                    taskId = IdWorker.getId(), // 生成分布式雪花算法唯一 ID
                    bucket = bucket, objectKey = it, taskType = FileCleanupTask.TYPE_ORPHAN_AVATAR
                )
            })
    }

    /**
     * 定时消费待处理的清理任务。
     * 上一次处理完后间隔 fixed-delay 毫秒（默认 60 秒）再次拉取执行。
     */
    @Scheduled(fixedDelayString = "\${oss.cleanup.fixed-delay:60000}", scheduler = "cleanupConsumerScheduler")
    override fun processPendingTasks() {
        fileCleanupTaskMapper.requeueStaleProcessing(ossProperties.cleanup.processingTimeoutMinutes)
        // 1. 从数据库竞争抢占并锁定指定批次数量（batchSize）的 pending 状态任务
        val tasks = fileCleanupTaskMapper.claimPending(ossProperties.cleanup.batchSize)

        tasks.forEach { task ->
            try {
                // 2. 调用 S3/RustFS API 物理删除对象文件
                s3Client.deleteObject(
                    DeleteObjectRequest.builder().bucket(task.bucket).key(task.objectKey).build()
                )
                // 3. 删除成功，更新任务状态为 completed
                fileCleanupTaskMapper.markCompleted(requireNotNull(task.taskId))
            } catch (exception: Exception) {
                // 4. 删除失败，使用指数退避算法计算下一次重试时间
                val nextAttemptAt = OffsetDateTime.now().plusMinutes(backoffMinutes(task.attempts))

                // 5. 重新调度任务：恢复 status 为 pending，增加尝试次数，记录错误日志
                fileCleanupTaskMapper.reschedule(
                    requireNotNull(task.taskId),
                    nextAttemptAt,
                    exception.message?.take(1000) ?: exception.javaClass.simpleName,
                    ossProperties.cleanup.maxAttempts
                )
                log.warn("删除对象失败，已安排重试: taskId={}, objectKey={}", task.taskId, task.objectKey, exception)
            }
        }
    }

    /**
     * 内部通用的任务入队逻辑（存在则忽略/幂等入队）
     */
    private fun enqueue(bucket: String, objectKey: String, taskType: String) {
        fileCleanupTaskMapper.enqueueIfAbsent(
            FileCleanupTask(
                taskId = IdWorker.getId(), // 使用 MyBatis-Plus 雪花算法生成分布式唯一 ID
                bucket = bucket, objectKey = objectKey, taskType = taskType
            )
        )
    }

    /**
     * 计算指数退避时间（单位：分钟）。
     * 公式为：2^attempts 分钟。限制 attempts 范围在 0 ~ 8 之间（即间隔 1 分钟 到 256 分钟）。
     */
    private fun backoffMinutes(attempts: Int): Long = 1L shl attempts.coerceIn(0, 8)
}








