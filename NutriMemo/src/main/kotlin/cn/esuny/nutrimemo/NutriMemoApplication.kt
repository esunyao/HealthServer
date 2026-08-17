package cn.esuny.nutrimemo

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication
import org.springframework.scheduling.annotation.EnableScheduling

@SpringBootApplication
@EnableScheduling
class NutriMemoApplication

fun main(args: Array<String>) {
    runApplication<NutriMemoApplication>(*args)
}
