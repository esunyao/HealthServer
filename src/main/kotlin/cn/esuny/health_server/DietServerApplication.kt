package cn.esuny.health_server

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication

@SpringBootApplication
class DietServerApplication

fun main(args: Array<String>) {
    runApplication<DietServerApplication>(*args)
}
