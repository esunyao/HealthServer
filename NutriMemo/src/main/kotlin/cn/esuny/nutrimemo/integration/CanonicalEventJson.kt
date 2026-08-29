package cn.esuny.nutrimemo.integration

import org.springframework.stereotype.Component
import tools.jackson.databind.JsonNode
import tools.jackson.databind.ObjectMapper
import tools.jackson.databind.node.ArrayNode
import java.security.MessageDigest

@Component
class CanonicalEventJson(private val mapper: ObjectMapper) {
    fun parse(json: String): JsonNode = mapper.readTree(json)
    fun stringify(node: JsonNode): String = mapper.writeValueAsString(sort(node))
    fun digest(node: JsonNode): String = MessageDigest.getInstance("SHA-256")
        .digest(stringify(node).toByteArray())
        .joinToString("") { "%02x".format(it) }

    private fun sort(node: JsonNode): JsonNode = when {
        node.isObject -> mapper.createObjectNode().also { result ->
            node.propertyNames().asSequence().sorted().forEach { name -> result.set(name, sort(node[name])) }
        }
        node.isArray -> mapper.createArrayNode().also { result: ArrayNode -> node.forEach { result.add(sort(it)) } }
        else -> node.deepCopy()
    }
}
