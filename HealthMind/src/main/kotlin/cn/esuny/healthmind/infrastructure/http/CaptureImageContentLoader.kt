package cn.esuny.healthmind.infrastructure.http

import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import io.modelcontextprotocol.spec.McpSchema
import org.springframework.stereotype.Component
import tools.jackson.databind.JsonNode
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.util.Base64

@Component
class CaptureImageContentLoader(private val properties: HealthMindProperties) {
    private val client: HttpClient = HttpClient.newBuilder()
        .connectTimeout(properties.oauth.connectTimeout)
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build()

    fun load(context: JsonNode): List<McpSchema.ImageContent> {
        val imageNodes = context["image_urls"]
            ?: throw CaptureImageFetchException("Capture context does not contain image_urls")
        if (!imageNodes.isArray) throw CaptureImageFetchException("Capture context image_urls is not an array")

        val limits = properties.mcp.captureImages
        if (imageNodes.size() > limits.maxCount) {
            throw CaptureImageFetchException("Capture context contains too many images")
        }

        var totalBytes = 0L
        return buildList {
            imageNodes.forEach { image ->
                val uri = parseUri(image.path("url").asText())
                val declaredMimeType = normalizeMimeType(image.path("content_type").asText())
                requireAllowedMimeType(declaredMimeType)
                val declaredLength = image.path("content_length").takeIf(JsonNode::isNumber)?.asLong()
                if (declaredLength != null && declaredLength > limits.maxImageBytes) {
                    throw CaptureImageFetchException("Capture image exceeds the configured size limit")
                }

                val request = HttpRequest.newBuilder(uri)
                    .timeout(properties.oauth.readTimeout)
                    .GET()
                    .build()
                val response = try {
                    client.send(request, HttpResponse.BodyHandlers.ofInputStream())
                } catch (exception: InterruptedException) {
                    Thread.currentThread().interrupt()
                    throw CaptureImageFetchException("Capture image download was interrupted")
                } catch (_: Exception) {
                    throw CaptureImageFetchException("Capture image download failed")
                }

                response.body().use { body ->
                    if (response.statusCode() !in 200..299) {
                        throw CaptureImageFetchException("Capture image server returned HTTP ${response.statusCode()}")
                    }
                    val mimeType = normalizeMimeType(response.headers().firstValue("Content-Type").orElse(""))
                    requireAllowedMimeType(mimeType)
                    if (declaredMimeType.isNotBlank() && mimeType != declaredMimeType) {
                        throw CaptureImageFetchException("Capture image content type does not match its metadata")
                    }
                    val responseLength = response.headers().firstValueAsLong("Content-Length").orElse(-1L)
                    if (responseLength > limits.maxImageBytes || responseLength > limits.maxTotalBytes - totalBytes) {
                        throw CaptureImageFetchException("Capture image exceeds the configured size limit")
                    }

                    val remainingTotal = limits.maxTotalBytes - totalBytes
                    val bytes = body.readBounded(minOf(limits.maxImageBytes, remainingTotal))
                    if (bytes.isEmpty()) throw CaptureImageFetchException("Capture image response was empty")
                    totalBytes += bytes.size
                    add(McpSchema.ImageContent.builder(Base64.getEncoder().encodeToString(bytes), mimeType).build())
                }
            }
        }
    }

    private fun parseUri(rawUrl: String): URI {
        val uri = runCatching { URI.create(rawUrl) }
            .getOrElse { throw CaptureImageFetchException("Capture image URL is invalid") }
        if (uri.scheme !in setOf("http", "https") || uri.host.isNullOrBlank()) {
            throw CaptureImageFetchException("Capture image URL is invalid")
        }
        return uri
    }

    private fun normalizeMimeType(value: String): String = value.substringBefore(';').trim().lowercase()

    private fun requireAllowedMimeType(mimeType: String) {
        if (mimeType !in properties.mcp.captureImages.allowedMimeTypes.map(String::lowercase)) {
            throw CaptureImageFetchException("Capture image content type is not allowed")
        }
    }

    private fun InputStream.readBounded(limit: Long): ByteArray {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
        var total = 0L
        while (true) {
            val read = read(buffer)
            if (read < 0) break
            total += read
            if (total > limit) throw CaptureImageFetchException("Capture image exceeds the configured size limit")
            output.write(buffer, 0, read)
        }
        return output.toByteArray()
    }
}

class CaptureImageFetchException(message: String) : RuntimeException(message)
