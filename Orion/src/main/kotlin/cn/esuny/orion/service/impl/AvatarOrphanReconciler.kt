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
import javax.sql.DataSource

/**
 * 头像孤儿对象对账与清理调度器。
 * 每日定时扫描 S3/RustFS 存储桶中的头像文件，识别并清理因网络超时、分布式事务回滚等原因遗留在存储桶中、
 * 但数据库中已没有任何用户引用的“孤儿头像文件”。
 */
@Service
class AvatarOrphanReconciler(
    private val s3Client: S3Client,
    private val ossProperties: OssProperties,
    private val userMapper: UserMapper,
    private val fileCleanupTaskService: FileCleanupTaskService,
    private val dataSource: DataSource
) {
    private val log = LoggerFactory.getLogger(javaClass)

    /**
     * 孤儿头像对账定时任务入口。
     * 默认每日凌晨 03:30 在专属线程池 `orphanReconcileScheduler` 中触发。
     *
     * 使用 PostgreSQL 的分布式咨询锁 (Advisory Lock) 保证多节点部署时，同一时间只有一个集群节点在执行对账。
     */
    @Scheduled(cron = "\${oss.cleanup.orphan-scan-cron:0 30 3 * * *}", scheduler = "orphanReconcileScheduler")
    fun enqueueOrphans() {
        dataSource.connection.use { connection ->
            // 使用特定的魔术 ID (114514) 尝试获取非阻塞的 Postgres 分布式咨询锁
            val locked = connection.prepareStatement("SELECT pg_try_advisory_lock(114514)")
                .use { statement -> statement.executeQuery().use { rs -> rs.next(); rs.getBoolean(1) } }
            
            // 如果抢锁失败，说明集群中已有其他节点正在执行对账，本节点直接退出
            if (!locked) {
                log.info("已有实例执行头像孤儿对账，本实例跳过"); return
            }
            try {
                // 抢锁成功，开始执行具体的对账扫描逻辑
                scan()
            } finally {
                // 执行完毕后，显式释放分布式锁
                connection.prepareStatement("SELECT pg_advisory_unlock(114514)").use { it.executeQuery() }
            }
        }
    }

    /**
     * 分页扫描 S3 桶中的头像对象并过滤出候选孤儿文件。
     * 我去，孤儿
     */
    private fun scan() {
        // 计算安全截止时间：当前时间减去保护期小时数（如 24 小时），避开刚上传但事务未提交的新文件
        val cutoff = Instant.now().minus(ossProperties.cleanup.orphanProtectionHours, ChronoUnit.HOURS)
        val batch = ArrayList<String>(ossProperties.cleanup.orphanScanBatchSize)
        var count = 0

        // 分页遍历 S3 存储桶中 `avatars/` 前缀下的所有对象
        s3Client.listObjectsV2Paginator(
            ListObjectsV2Request.builder().bucket(ossProperties.bucket).prefix("avatars/").build()
        ).contents().forEach { summary ->
            // 只处理修改时间早于截止时间（超出保护期）的文件
            if (summary.lastModified().isBefore(cutoff)) {
                batch += summary.key()
                // 当批次达到配置的大小（如 500 条）时，发起一次批量对账和入队
                if (batch.size >= ossProperties.cleanup.orphanScanBatchSize) {
                    count += enqueueBatch(batch); batch.clear()
                }
            }
        }
        // 处理不足一个完整批次的剩余文件
        if (batch.isNotEmpty()) count += enqueueBatch(batch)
        log.info("头像孤儿对象对账完成: candidates={}", count)
    }

    /**
     * 将本批次待核验的 S3 文件 Key 列表与数据库引用比对，找出真正的孤儿文件并推入清理队列。
     *
     * @param keys 本批次待核查的 S3 对象路径集合
     * @return 本批次成功入队的孤儿文件数量
     */
    private fun enqueueBatch(keys: Collection<String>): Int {
        // 批量查询数据库，获取本批次 Key 列表中依然被用户表引用的有效 Key 集合
        val referenced = userMapper.selectReferencedAvatarKeys(keys).toHashSet()
        // 过滤出在数据库中没有任何引用的孤儿文件 Key
        val orphans = keys.filterNot(referenced::contains)
        
        // 将真正的孤儿文件批量提交至 file_cleanup_tasks 异步清理队列
        if (orphans.isNotEmpty()) fileCleanupTaskService.enqueueOrphanAvatars(ossProperties.bucket, orphans)
        return orphans.size
    }
}

