package cn.esuny.healthmind.infrastructure.http

import cn.esuny.healthmind.infrastructure.config.HealthMindProperties
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okio.Buffer
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import tools.jackson.databind.ObjectMapper
import java.util.Base64
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse

class CaptureImageContentLoaderTest {
    private val server = MockWebServer()
    private val objectMapper = ObjectMapper()

    @AfterEach
    fun close() = server.close()

    @Test
    fun `returns every image in source order with unchanged bytes`() {
        val jpeg = byteArrayOf(1, 2, 3, 4)
        val webp = byteArrayOf(5, 6, 7)
        server.enqueue(MockResponse().setHeader("Content-Type", "image/jpeg").setBody(Buffer().write(jpeg)))
        server.enqueue(MockResponse().setHeader("Content-Type", "image/webp").setBody(Buffer().write(webp)))
        server.start()

        val result = loader().load(context(
            image("/first.jpg", "image/jpeg", jpeg.size),
            image("/second.webp", "image/webp", webp.size),
        ))

        assertEquals(2, result.size)
        assertEquals("image/jpeg", result[0].mimeType())
        assertEquals(jpeg.toList(), Base64.getDecoder().decode(result[0].data()).toList())
        assertEquals("image/webp", result[1].mimeType())
        assertEquals(webp.toList(), Base64.getDecoder().decode(result[1].data()).toList())
    }

    @Test
    fun `rejects failed download without exposing signed URL`() {
        server.enqueue(MockResponse().setResponseCode(403))
        server.start()
        val secret = "do-not-leak-this-signature"

        val exception = assertFailsWith<CaptureImageFetchException> {
            loader().load(context(image("/meal.jpg?X-Amz-Signature=$secret", "image/jpeg", 10)))
        }

        assertFalse(exception.message.orEmpty().contains(secret))
        assertEquals("Capture image server returned HTTP 403", exception.message)
    }

    @Test
    fun `rejects empty disallowed and oversized images`() {
        server.enqueue(MockResponse().setHeader("Content-Type", "image/jpeg").setBody(""))
        server.enqueue(MockResponse().setHeader("Content-Type", "text/plain").setBody("bad"))
        server.enqueue(MockResponse().setHeader("Content-Type", "image/jpeg").setBody("12345"))
        server.start()

        assertFailsWith<CaptureImageFetchException> {
            loader().load(context(image("/empty.jpg", "image/jpeg", 0)))
        }
        assertFailsWith<CaptureImageFetchException> {
            loader().load(context(image("/wrong.jpg", "image/jpeg", 3)))
        }
        assertFailsWith<CaptureImageFetchException> {
            loader(maxImageBytes = 4).load(context(image("/large.jpg", "image/jpeg", 5)))
        }
    }

    private fun loader(maxImageBytes: Long = 1024): CaptureImageContentLoader = CaptureImageContentLoader(
        HealthMindProperties(
            mcp = HealthMindProperties.Mcp(
                captureImages = HealthMindProperties.Mcp.CaptureImages(
                    maxImageBytes = maxImageBytes,
                    maxTotalBytes = 2048,
                ),
            ),
        ),
    )

    private fun context(vararg images: String) = objectMapper.readTree(
        """{"capture_session_id":"session","meal_id":42,"image_urls":[${images.joinToString(",")}] }""",
    )

    private fun image(path: String, mimeType: String, length: Int): String =
        """{"url":"${server.url(path)}","content_type":"$mimeType","content_length":$length}"""
}
