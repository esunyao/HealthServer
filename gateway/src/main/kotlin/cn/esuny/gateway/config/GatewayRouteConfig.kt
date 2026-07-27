package cn.esuny.gateway.config

import org.springframework.cloud.gateway.server.mvc.filter.BeforeFilterFunctions
import org.springframework.cloud.gateway.server.mvc.handler.GatewayRouterFunctions
import org.springframework.cloud.gateway.server.mvc.handler.HandlerFunctions
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.web.servlet.function.RequestPredicates
import org.springframework.web.servlet.function.RouterFunction
import org.springframework.web.servlet.function.ServerResponse

/**
 * 核心网关路由配置（基于 Spring Cloud Gateway Server WebMVC）
 *
 * 在 Spring Cloud 体系中，网关充当了所有微服务请求的统一入口。
 * 该类通过代码（Programmatic API）的方式定义了不同请求该如何转发到对应的后端服务。
 *
 * 关键 API 说明（WebMVC 版本，不是 WebFlux）：
 * - GatewayRouterFunctions.route(id) — 创建一条命名路由
 * - HandlerFunctions.http()         — 创建 HTTP 代理处理器（无参！URI 通过 before filter 指定）
 * - BeforeFilterFunctions.uri()     — 设置请求转发的目标地址
 * - BeforeFilterFunctions.stripPrefix() — 剥离 URL 前缀
 */
@Configuration
class GatewayRouteConfig {

    /**
     * 用户服务路由配置
     *
     * 作用：把以 /api/user/ 开头的所有请求，转发到用户微服务（user-service）上。
     * 例如前端调用网关：GET http://gateway:8080/api/user/info
     * 经过 stripPrefix(2) 后变为：GET http://user-service/info
     */
    @Bean
    fun userServiceRoute(): RouterFunction<ServerResponse> {
        return GatewayRouterFunctions.route("user_service_route")
            // route(predicate, handler)：
            //   predicate = 匹配 /api/user/** 路径的所有 HTTP 方法
            //   handler   = http() 代理处理器，将请求转发到下游服务
            .route(RequestPredicates.path("/api/user/**"), HandlerFunctions.http())
            // uri("lb://user-service")：
            //   "lb://" 全称是 LoadBalancer，代表通过注册中心（Consul）查找名为 "user-service" 的服务实例
            //   并自动做负载均衡，而不是写死具体的 IP:端口
            .before(BeforeFilterFunctions.uri("lb://user-service"))
            // stripPrefix(2)：去掉 URL 路径的前两段
            //   "/api/user/info" → 去掉 "/api" 和 "/user" → 变成 "/info"
            //   这样下游服务不需要知道自己被挂在 /api/user 前缀下
            .before(BeforeFilterFunctions.stripPrefix(2))
            // 添加自定义请求头，让下游服务知道请求来自网关，而非外部直连
            .before(BeforeFilterFunctions.addRequestHeader("X-Gateway-Source", "HealthServer-Gateway")).build()
    }

    /**
     * 饮食健康服务路由配置
     * 将 /api/diet/ ** 的请求，去掉前缀后，负载均衡转发至 diet-service
     */
    @Bean
    fun dietServiceRoute(): RouterFunction<ServerResponse> {
        return GatewayRouterFunctions.route("diet_service_route")
            .route(RequestPredicates.path("/api/diet/**"), HandlerFunctions.http())
            .before(BeforeFilterFunctions.uri("lb://diet-service")).before(BeforeFilterFunctions.stripPrefix(2))
            .before(BeforeFilterFunctions.addRequestHeader("X-Gateway-Source", "HealthServer-Gateway")).build()
    }


    /**
     * 核心健康档案服务路由配置
     *
     * 将 /api/health/ ** 的请求，去掉前缀后，负载均衡转发至 health-service
     * */

    @Bean
    fun healthServiceRoute(): RouterFunction<ServerResponse> {
        return GatewayRouterFunctions.route("health_service_route")
            .route(RequestPredicates.path("/api/health/**"), HandlerFunctions.http())
            .before(BeforeFilterFunctions.uri("lb://health-service")).before(BeforeFilterFunctions.stripPrefix(2))
            .before(BeforeFilterFunctions.addRequestHeader("X-Gateway-Source", "HealthServer-Gateway")).build()
    }
}