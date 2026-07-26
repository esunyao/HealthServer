package cn.esuny.gateway.health

import org.springframework.boot.actuate.health.Health
import org.springframework.boot.actuate.health.HealthIndicator
import org.springframework.stereotype.Component
import java.time.Duration
import java.time.Instant

/**
 * 自定义健康检查指示器 (Custom Health Indicator)
 * 
 * 作用：扩展 Spring Boot Actuator 的 /actuator/health 接口。
 * 默认的 health 接口通常只返回系统是否 UP。
 * 通过实现 HealthIndicator，我们可以向健康检查响应中添加额外的诊断信息，
 * 比如当前网关的启动时间、持续运行时间 (Uptime)。这对于运维监控非常有用。
 */
@Component
class GatewayHealthIndicator : HealthIndicator {

    // 记录组件被 Spring 容器初始化的时间，作为应用启动时间
    private val startupTime: Instant = Instant.now()

    override fun health(): Health {
        val now = Instant.now()
        // 计算运行时间
        val uptimeDuration = Duration.between(startupTime, now)
        
        // 格式化为人类可读的格式 (例如: 12h 30m 15s)
        val uptimeString = formatDuration(uptimeDuration)

        // 返回健康状态为 UP，并附带详细信息
        return Health.up()
            .withDetail("startupTime", startupTime.toString())
            .withDetail("uptime", uptimeString)
            .build()
    }

    /**
     * 将 Duration 格式化为易读的字符串
     */
    private fun formatDuration(duration: Duration): String {
        val days = duration.toDays()
        val hours = duration.toHoursPart()
        val minutes = duration.toMinutesPart()
        val seconds = duration.toSecondsPart()

        return buildString {
            if (days > 0) append("${days}d ")
            if (hours > 0) append("${hours}h ")
            if (minutes > 0) append("${minutes}m ")
            append("${seconds}s")
        }.trim()
    }
}
