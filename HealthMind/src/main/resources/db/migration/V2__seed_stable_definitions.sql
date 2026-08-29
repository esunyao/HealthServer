SET search_path TO healthmind, public;

INSERT INTO ai_task_types (
    task_type_id, task_type_code, domain_code, display_name, description,
    default_invocation_mode, default_timeout_seconds, max_attempts
) VALUES (
    '18bd9330-35d1-4db7-a47a-65a4e8b5ed80', 'nutrition.meal_analysis', 'nutrition',
    '餐食图像营养分析', '根据 NutriMemo 采集上下文生成结构化餐食营养分析。', 'async', 120, 3
) ON CONFLICT (task_type_code) DO NOTHING;

INSERT INTO ai_tool_definitions (
    tool_id, tool_code, display_name, description, owner_service, nacos_service_name,
    operation_id, auth_scope, request_schema_version, request_schema, request_schema_sha256,
    response_schema_version, response_schema, response_schema_sha256
) VALUES
(
    '7b9c8a47-fd5b-43d3-a522-e1efb8464d50', 'nutrimemo.capture_context.get', '读取餐食采集上下文',
    '按任务归属读取已确认图片的短时 URL 和餐次元数据。', 'NutriMemo', 'NutriMemo',
    'getNutritionCaptureContext', 'healthmind.tool.nutrimemo.capture-context.read',
    '1.0', '{}'::jsonb, '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
    '1.0', '{}'::jsonb, '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'
),
(
    '9068ecfe-e159-40e9-94ab-a956c7f4cd36', 'orion.nutrition_context.get', '读取营养健康上下文',
    '在用户授权后读取营养分析所需的最小健康上下文。', 'Orion', 'Orion',
    'getNutritionAiContext', 'healthmind.tool.orion.nutrition-context.read',
    '1.0', '{}'::jsonb, '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
    '1.0', '{}'::jsonb, '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'
) ON CONFLICT (tool_code) DO NOTHING;
