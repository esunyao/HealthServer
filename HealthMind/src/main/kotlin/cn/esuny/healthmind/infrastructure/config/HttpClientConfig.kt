package cn.esuny.healthmind.infrastructure.config

import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.cloud.client.loadbalancer.LoadBalanced
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.web.client.RestClient

@Configuration
class HttpClientConfig {
    @Bean
    @LoadBalanced
    @Qualifier("internalRestClientBuilder")
    fun internalRestClientBuilder(): RestClient.Builder = RestClient.builder()
}
