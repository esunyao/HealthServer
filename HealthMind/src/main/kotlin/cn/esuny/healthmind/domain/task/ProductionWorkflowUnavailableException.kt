package cn.esuny.healthmind.domain.task

/** Signals a deployment prerequisite; the input event must remain unacknowledged. */
class ProductionWorkflowUnavailableException : RuntimeException("No production workflow release for nutrition.meal_analysis")
