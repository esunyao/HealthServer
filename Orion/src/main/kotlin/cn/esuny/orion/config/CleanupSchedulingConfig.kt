package cn.esuny.orion.config

import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler

@Configuration
class CleanupSchedulingConfig {
    @Bean("orphanReconcileScheduler")
    fun orphanReconcileScheduler() = scheduler("orphan-reconcile-")

    @Bean("cleanupConsumerScheduler")
    fun cleanupConsumerScheduler() = scheduler("cleanup-consumer-")

    private fun scheduler(prefix: String) = ThreadPoolTaskScheduler().apply {
        poolSize = 1
        setThreadNamePrefix(prefix)
        setWaitForTasksToCompleteOnShutdown(true)
        setAwaitTerminationSeconds(30)
    }
}
