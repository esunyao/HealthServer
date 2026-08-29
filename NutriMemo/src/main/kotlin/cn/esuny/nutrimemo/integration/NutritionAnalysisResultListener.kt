package cn.esuny.nutrimemo.integration

import org.springframework.kafka.annotation.KafkaListener
import org.springframework.stereotype.Component

@Component
class NutritionAnalysisResultListener(private val service: NutritionAnalysisResultService) {
    @KafkaListener(
        topics = ["\${nutri.integration.analysis-completed-destination}", "\${nutri.integration.analysis-failed-destination}"],
        groupId = "\${nutri.integration.consumer-group}",
    )
    fun receive(raw: String) = service.process(raw)
}
