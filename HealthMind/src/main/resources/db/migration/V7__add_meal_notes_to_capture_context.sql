-- Add user notes to the current NutriMemo capture-context response contract.
-- Existing workflow releases and tool bindings are intentionally left unchanged.
SET search_path TO healthmind, public;

DO $$
DECLARE
    updated_rows INTEGER;
BEGIN
    UPDATE healthmind.ai_tool_definitions
       SET response_schema_version = '1.1',
           response_schema = $tool${"type":"object","additionalProperties":false,"required":["capture_session_id","meal_id","meal_type","consumed_at","timezone","image_urls"],"properties":{"capture_session_id":{"type":"string","format":"uuid"},"meal_id":{"type":"integer"},"meal_type":{"type":"string"},"consumed_at":{"type":"string","format":"date-time"},"timezone":{"type":"string"},"image_urls":{"type":"array","minItems":1,"items":{"type":"object","required":["content_type","content_length","url","expires_in_seconds"],"properties":{"content_type":{"type":"string"},"content_length":{"type":"integer","minimum":1},"captured_at":{"type":["string","null"],"format":"date-time"},"url":{"type":"string","format":"uri"},"expires_in_seconds":{"type":"integer","minimum":1}},"additionalProperties":false}},"notes":{"type":["string","null"],"maxLength":1000}}}$tool$::jsonb,
           response_schema_sha256 = 'e31289c072aae1254ce214ec9a774a8c08ac5c369b63ab03dc763c59c8dddbc4'
     WHERE tool_code = 'nutrimemo.capture_context.get';

    GET DIAGNOSTICS updated_rows = ROW_COUNT;
    IF updated_rows <> 1 THEN
        RAISE EXCEPTION 'V7 expected exactly one nutrimemo.capture_context.get definition, updated %', updated_rows;
    END IF;
END $$;
