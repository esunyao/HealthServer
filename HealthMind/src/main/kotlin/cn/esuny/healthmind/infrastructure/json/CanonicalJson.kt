package cn.esuny.healthmind.infrastructure.json

import org.springframework.stereotype.Component
import tools.jackson.databind.JsonNode
import tools.jackson.databind.ObjectMapper
import tools.jackson.databind.node.ArrayNode
import tools.jackson.databind.node.ObjectNode
import java.security.MessageDigest

@Component
class CanonicalJson(private val objectMapper: ObjectMapper) {
    fun parse(json: String): JsonNode = objectMapper.readTree(json)

    fun stringify(node: JsonNode): String = objectMapper.writeValueAsString(sort(node))

    fun sha256(node: JsonNode): String = sha256(stringify(node))

    fun sha256(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }

    private fun sort(node: JsonNode): JsonNode = when {
        node.isObject -> {
            val result = objectMapper.createObjectNode()
            node.propertyNames().asSequence().sorted().forEach { name -> result.set(name, sort(node[name])) }
            result
        }
        node.isArray -> {
            val result: ArrayNode = objectMapper.createArrayNode()
            node.forEach { result.add(sort(it)) }
            result
        }
        else -> node.deepCopy()
    }
}
