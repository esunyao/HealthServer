package cn.esuny.orion.service.impl

import cn.esuny.orion.config.OssProperties
import cn.esuny.orion.mapper.UserMapper
import cn.esuny.orion.service.FileCleanupTaskService
import org.slf4j.LoggerFactory
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Service
import software.amazon.awssdk.services.s3.S3Client
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request
import java.time.Instant
import java.time.temporal.ChronoUnit

/** 每日识别因跨系统事务失败而遗留的正式区孤儿头像。 */
@Service
class AvatarOrphanReconciler(
    private val s3Client: S3Client,
    private val ossProperties: OssProperties,
    private val userMapper: UserMapper,
    private val fileCleanupTaskService: FileCleanupTaskService
) {
    private val log = LoggerFactory.getLogger(AvatarOrphanReconciler::class.java)

    // 1. 定时任务触发：通过配置文件中的 cron 表达式定时执行（默认每天凌晨 3:30 运行）
    @Scheduled(cron = "\${oss.cleanup.orphan-scan-cron:0 30 3 * * *}")
    fun enqueueOrphans() {
        // 2. 从数据库中查询出所有正在被用户使用的头像文件 Key，存入 HashSet（O(1) 检索）
        val referencedKeys = userMapper.selectAvatarObjectKeys().toHashSet()

        // 3. 计算安全截止时间：当前时间向前推 24 小时（保护期）
        val cutoff = Instant.now().minus(24, ChronoUnit.HOURS)
        var count = 0

        // 4. 分页遍历对象存储桶中 `avatars/` 前缀下的所有头像文件
        s3Client.listObjectsV2Paginator(
            ListObjectsV2Request.builder().bucket(ossProperties.bucket).prefix("avatars/").build()
        ).contents().forEach { objectSummary ->

            // 5. 孤儿文件判断逻辑：
            // ① 该文件 Key 不在数据库引用的集合 `referencedKeys` 中
            // 并且 ② 该文件的修改时间早于 24 小时之前（避免误杀用户刚刚上传但数据库还没提交的合法头像）
            if (objectSummary.key() !in referencedKeys && objectSummary.lastModified().isBefore(cutoff)) {

                // 6. 将判定为孤儿文件的删除任务推入上文提到的 `file_cleanup_tasks` 异步清理队列中
                fileCleanupTaskService.enqueueOrphanAvatar(ossProperties.bucket, objectSummary.key())
                count++
            }
        }
        // 7. 打印对账完成日志及入队的文件数量
        log.info("头像孤儿对象对账完成: candidates={}", count)
    }
}
