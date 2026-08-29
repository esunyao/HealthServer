package cn.esuny.healthmind.infrastructure.config

import org.springframework.beans.factory.annotation.Qualifier
import org.springframework.cloud.client.loadbalancer.LoadBalanced
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import org.springframework.http.client.JdkClientHttpRequestFactory
import org.springframework.web.client.RestClient
import java.net.http.HttpClient

@Configuration
class HttpClientConfig(private val properties: HealthMindProperties) {
    @Bean
    @Qualifier("directRestClientBuilder")
    fun directRestClientBuilder(): RestClient.Builder = configuredBuilder()

    @Bean
    @LoadBalanced
    @Qualifier("internalRestClientBuilder")
    fun internalRestClientBuilder(): RestClient.Builder = configuredBuilder()

    private fun configuredBuilder(): RestClient.Builder {
        val client = HttpClient.newBuilder()
            .connectTimeout(properties.oauth.connectTimeout)
            .build()
        val requestFactory = JdkClientHttpRequestFactory(client).apply {
            setReadTimeout(properties.oauth.readTimeout)
        }
        return RestClient.builder().requestFactory(requestFactory)
    }
}
