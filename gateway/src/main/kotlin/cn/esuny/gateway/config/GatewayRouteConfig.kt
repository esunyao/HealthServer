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
 * 注意：本类使用的是基于 Servlet / WebMVC 架构的 Spring Cloud Gateway API，
 * 不是基于 WebFlux 的版本。返回的类型是 RouterFunction<ServerResponse>。
 */
@Configuration
class GatewayRouteConfig {

    /**
     * 用户服务路由配置
     * 
     * 作用：把以 /api/user/ 开头的所有请求，转发到用户微服务（user-service）上。
     * 例如前端调用网关：GET http://gateway:port/api/user/info
     * 会被转发到用户服务：GET http://user-service/info
     */
    @Bean
    fun userServiceRoute(): RouterFunction<ServerResponse> {
        return GatewayRouterFunctions.route("user_service_route")
            // 1. route(predicate, handler) 决定了如何匹配请求以及最终把请求交给谁处理
            // - RequestPredicates.path("/api/user/**")：匹配路径前缀，**代表多层任意路径
            // - HandlerFunctions.http("lb://user-service")：
            //   "lb://" 全称是 LoadBalancer，代表在注册中心（如 Nacos/Consul）寻找名为 "user-service" 的服务实例，
            //   并实现负载均衡把请求发给它，而不是写死具体的 IP 端口。
            .route(
                RequestPredicates.path("/api/user/**"),
                HandlerFunctions.http("lb://user-service")
            )
            // 2. before() 用于在请求转发出去之前进行拦截和修改，就像快递发货前的重新包装
            // - stripPrefix(2)：顾名思义是“剥离前缀”。参数 2 表示去掉 URL 路径里的前两段。
            //   请求的 "/api/user/info" 经过剥离后变成了 "/info"，然后再发给 user-service。
            //   这样一来，下游的用户微服务代码就不必知道自己是被挂在 "/api/user" 这个前缀底下了，代码更纯粹。
            .before(BeforeFilterFunctions.stripPrefix(2))
            // - addRequestHeader(...)：在发往微服务的请求里加上一个自定义的请求头。
            //   这样后端微服务可以通过读取 "X-Gateway-Source" 来确认请求确实是从网关进来的，而非外部恶意直连绕过网关。
            .before(BeforeFilterFunctions.addRequestHeader("X-Gateway-Source", "HealthServer-Gateway"))
            .build()
    }

    /**
     * 饮食健康服务路由配置
     * 
     * 将 /api/diet/** 的请求，去掉 /api/diet 前缀后，负载均衡转发至 diet-service
     */
    @Bean
    fun dietServiceRoute(): RouterFunction<ServerResponse> {
        return GatewayRouterFunctions.route("diet_service_route")
            .route(
                RequestPredicates.path("/api/diet/**"),
                HandlerFunctions.http("lb://diet-service")
            )
            .before(BeforeFilterFunctions.stripPrefix(2))
            .before(BeforeFilterFunctions.addRequestHeader("X-Gateway-Source", "HealthServer-Gateway"))
            .build()
    }

    /**
     * 核心健康档案服务路由配置
     * 
     * 将 /api/health/** 的请求，去掉 /api/health 前缀后，负载均衡转发至 health-service
     */
    @Bean
    fun healthServiceRoute(): RouterFunction<ServerResponse> {
        return GatewayRouterFunctions.route("health_service_route")
            .route(
                RequestPredicates.path("/api/health/**"),
                HandlerFunctions.http("lb://health-service")
            )
            .before(BeforeFilterFunctions.stripPrefix(2))
            .before(BeforeFilterFunctions.addRequestHeader("X-Gateway-Source", "HealthServer-Gateway"))
            .build()
    }
}
