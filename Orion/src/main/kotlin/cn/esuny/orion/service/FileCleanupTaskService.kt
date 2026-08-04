package cn.esuny.orion.service

/** 负责写入和执行对象存储的删除任务。 */
interface FileCleanupTaskService {
    fun enqueueOldAvatar(bucket: String, objectKey: String)
    fun enqueueStagingSource(bucket: String, objectKey: String)
    fun enqueueOrphanAvatar(bucket: String, objectKey: String)
    fun processPendingTasks()
}
