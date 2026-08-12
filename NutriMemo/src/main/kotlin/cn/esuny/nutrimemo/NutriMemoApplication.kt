package cn.esuny.nutrimemo

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication

@SpringBootApplication
class NutriMemoApplication

fun main(args: Array<String>) {
    runApplication<NutriMemoApplication>(*args)
}
