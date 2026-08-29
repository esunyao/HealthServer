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
    '1.0', $tool${"type":"object","additionalProperties":false,"required":["attempt_id","task_id"],"properties":{"attempt_id":{"type":"string","format":"uuid"},"task_id":{"type":"string","format":"uuid"}}}$tool$::jsonb,
    'b950f770bf5d38d5d03e3b047fd02a3bcb25ea28273cbff82b46f179b0b772f8',
    '1.0', $tool${"type":"object","additionalProperties":false,"required":["capture_session_id","meal_id","meal_type","consumed_at","timezone","image_urls"],"properties":{"capture_session_id":{"type":"string","format":"uuid"},"meal_id":{"type":"integer"},"meal_type":{"type":"string"},"consumed_at":{"type":"string","format":"date-time"},"timezone":{"type":"string"},"image_urls":{"type":"array","minItems":1,"items":{"type":"object","required":["content_type","content_length","url","expires_in_seconds"],"properties":{"content_type":{"type":"string"},"content_length":{"type":"integer","minimum":1},"captured_at":{"type":["string","null"],"format":"date-time"},"url":{"type":"string","format":"uri"},"expires_in_seconds":{"type":"integer","minimum":1}},"additionalProperties":false}}}}$tool$::jsonb,
    '9ac79b0967342045aba395ec3f393106c0b09020a13c3991f16adc1fddbdcf09'
),
(
    '9068ecfe-e159-40e9-94ab-a956c7f4cd36', 'orion.nutrition_context.get', '读取营养健康上下文',
    '在用户授权后读取营养分析所需的最小健康上下文。', 'Orion', 'Orion',
    'getNutritionAiContext', 'healthmind.tool.orion.nutrition-context.read',
    '1.0', $tool${"type":"object","additionalProperties":false,"required":["attempt_id","task_id"],"properties":{"attempt_id":{"type":"string","format":"uuid"},"task_id":{"type":"string","format":"uuid"}}}$tool$::jsonb,
    'b950f770bf5d38d5d03e3b047fd02a3bcb25ea28273cbff82b46f179b0b772f8',
    '1.0', $tool${"type":"object","additionalProperties":false,"required":["subject_id","age_years","gender","height_cm","latest_measurement","active_goals","allergies","medical_conditions","dietary_restrictions","cuisine_preferences"],"properties":{"subject_id":{"type":"string","format":"uuid"},"age_years":{"type":["integer","null"],"minimum":0},"gender":{"type":["string","null"]},"height_cm":{"type":["number","null"]},"latest_measurement":{"type":["object","null"]},"active_goals":{"type":"array","items":{"type":"object"}},"allergies":{"type":"array","items":{"type":"object"}},"medical_conditions":{"type":"array","items":{"type":"object"}},"dietary_restrictions":{"type":"array","items":{"type":"object"}},"cuisine_preferences":{"type":"array","items":{"type":"object"}}}}$tool$::jsonb,
    '54ab12f8f6bd828deef1bf3fd9a6aad467f2cea7c954e4af8ffa7be4e55349c6'
) ON CONFLICT (tool_code) DO NOTHING;
