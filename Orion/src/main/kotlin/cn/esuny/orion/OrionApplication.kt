package cn.esuny.orion

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication

@SpringBootApplication
class OrionApplication

fun main(args: Array<String>) {
    runApplication<OrionApplication>(*args)
}
