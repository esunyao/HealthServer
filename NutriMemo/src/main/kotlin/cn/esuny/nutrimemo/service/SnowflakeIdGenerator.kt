package cn.esuny.nutrimemo.service

import com.baomidou.mybatisplus.core.toolkit.IdWorker
import org.springframework.stereotype.Component

@Component
class SnowflakeIdGenerator {
    fun nextId(): Long = IdWorker.getId()
}
