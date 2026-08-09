package cn.esuny.orion.service

import java.util.UUID

/**
 * 对象存储异步清理任务服务接口。
 * 负责定义对象清理任务的入队（单条/批量）以及后台定时消费任务的规范。
 */
interface FileCleanupTaskService {

    /**
     * 将更换下来的旧头像文件加入清理队列。
     *
     * @param bucket 对象存储桶名称
     * @param objectKey 旧头像在对象存储中的相对路径（Key）
     */
    fun enqueueOldAvatar(bucket: String, objectKey: String, ownerUserId: UUID? = null)

    /**
     * 将暂存区（Staging）源文件加入清理队列。
     * 用于清理已完成裁剪或处理后的临时上传文件。
     *
     * @param bucket 对象存储桶名称
     * @param objectKey 暂存文件在对象存储中的相对路径（Key）
     */
    fun enqueueStagingSource(bucket: String, objectKey: String, ownerUserId: UUID? = null)

    /**
     * 将扫描出的单个孤儿头像文件加入清理队列。
     *
     * @param bucket 对象存储桶名称
     * @param objectKey 孤儿头像文件在对象存储中的相对路径（Key）
     */
    fun enqueueOrphanAvatar(bucket: String, objectKey: String, ownerUserId: UUID? = null)

    /**
     * 批量将扫描出的孤儿头像文件加入清理队列。
     * 适用于每日定时对账扫描出多个孤儿对象时的批量入队，提升数据库操作性能。
     *
     * @param bucket 对象存储桶名称
     * @param objectKeys 孤儿头像文件路径集合
     */
    fun enqueueOrphanAvatars(bucket: String, objectKeys: Collection<String>)

    /**
     * 定时消费并处理待清理的任务队列。
     * 从数据库抢占待处理的任务，调用 S3/RustFS API 实施物理删除；若失败则安排指数退避重试。
     */
    fun processPendingTasks()
}
