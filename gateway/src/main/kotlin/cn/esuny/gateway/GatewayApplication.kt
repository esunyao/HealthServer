package cn.esuny.gateway

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication
import org.springframework.cloud.client.discovery.EnableDiscoveryClient
import org.springframework.scheduling.annotation.EnableScheduling

/**
 * HealthServer 网关启动类
 *
 * 这是整个网关微服务的入口。网关是所有外部请求进入后端微服务体系的"大门"，
 * 所有 API 请求都会先经过网关，再被路由到对应的下游服务。
 *
 * 注解说明：
 * - @SpringBootApplication: Spring Boot 的核心注解，自动启用组件扫描和自动配置
 * - @EnableDiscoveryClient: 启用服务发现，让网关能从 Consul 注册中心获取下游服务地址
 * - @EnableScheduling: 启用定时任务，用于限流过滤器中定期清理过期的令牌桶
 */
@SpringBootApplication
@EnableDiscoveryClient
@EnableScheduling
class GatewayApplication

/**
 * 应用程序入口函数
 *
 * 启动 Spring Boot 应用，内嵌 Tomcat 会在配置的端口上监听请求。
 */
fun main(args: Array<String>) {
    runApplication<GatewayApplication>(*args)
}
