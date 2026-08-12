CREATE SCHEMA IF NOT EXISTS nutri;

CREATE OR REPLACE FUNCTION nutri.set_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;

CREATE TABLE nutri.nutrient_definitions (
    nutrient_id BIGINT PRIMARY KEY CHECK (nutrient_id > 0), nutrient_code VARCHAR(64) NOT NULL UNIQUE,
    nutrient_name VARCHAR(100) NOT NULL, unit VARCHAR(16) NOT NULL,
    nutrient_category VARCHAR(32) NOT NULL CHECK (nutrient_category IN ('energy','macro','micro','other')),
    display_order INTEGER NOT NULL DEFAULT 0 CHECK (display_order >= 0), active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE nutri.foods (
    food_id BIGINT PRIMARY KEY CHECK (food_id > 0), owner_user_id UUID,
    scope VARCHAR(16) NOT NULL DEFAULT 'public' CHECK (scope IN ('public','personal')),
    name VARCHAR(150) NOT NULL, food_type VARCHAR(32) NOT NULL CHECK (food_type IN ('ingredient','dish','packaged_food','beverage','supplement')),
    brand_name VARCHAR(100), default_serving_g NUMERIC(12,3) CHECK (default_serving_g > 0), version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((scope = 'public' AND owner_user_id IS NULL) OR (scope = 'personal' AND owner_user_id IS NOT NULL))
);
CREATE INDEX idx_foods_owner_active ON nutri.foods(owner_user_id, active) WHERE owner_user_id IS NOT NULL;
CREATE INDEX idx_foods_public_active ON nutri.foods(active) WHERE scope = 'public';
CREATE UNIQUE INDEX uq_personal_food_name_active ON nutri.foods(owner_user_id, LOWER(name)) WHERE scope = 'personal' AND active;

CREATE TABLE nutri.food_nutrient_values (
    food_id BIGINT NOT NULL REFERENCES nutri.foods(food_id), nutrient_id BIGINT NOT NULL REFERENCES nutri.nutrient_definitions(nutrient_id),
    amount_per_100g NUMERIC(18,6) NOT NULL CHECK (amount_per_100g >= 0),
    data_source VARCHAR(32) NOT NULL DEFAULT 'user_manual' CHECK (data_source IN ('official_table','user_manual','imported')),
    source_reference VARCHAR(500), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(food_id, nutrient_id)
);

CREATE TABLE nutri.food_aliases (
    alias_id BIGINT PRIMARY KEY CHECK (alias_id > 0), food_id BIGINT NOT NULL REFERENCES nutri.foods(food_id) ON DELETE CASCADE,
    alias_type VARCHAR(24) NOT NULL DEFAULT 'alias' CHECK (alias_type IN ('alias','brand','barcode','keyword')),
    alias_value VARCHAR(150) NOT NULL, normalized_value VARCHAR(150) NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(food_id, normalized_value, alias_type)
);
CREATE INDEX idx_food_aliases_lookup ON nutri.food_aliases(normalized_value, alias_type);

CREATE TABLE nutri.meal_records (
    meal_id BIGINT PRIMARY KEY CHECK (meal_id > 0), user_id UUID NOT NULL,
    meal_type VARCHAR(16) NOT NULL CHECK (meal_type IN ('breakfast','lunch','dinner','snack','other')),
    consumed_at TIMESTAMPTZ NOT NULL, timezone VARCHAR(64) NOT NULL, local_date DATE NOT NULL,
    scenario VARCHAR(64), entry_source VARCHAR(24) NOT NULL DEFAULT 'manual' CHECK (entry_source IN ('manual','photo_placeholder','import')),
    notes VARCHAR(1000), status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active','deleted')),
    idempotency_key UUID NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), deleted_at TIMESTAMPTZ,
    CHECK ((status = 'active' AND deleted_at IS NULL) OR (status = 'deleted' AND deleted_at IS NOT NULL)),
    CONSTRAINT uq_meals_user_idempotency UNIQUE(user_id,idempotency_key)
);
CREATE INDEX idx_meals_user_local_type ON nutri.meal_records(user_id, local_date DESC, meal_type) WHERE status = 'active';
CREATE INDEX idx_meals_user_time ON nutri.meal_records(user_id, consumed_at DESC) WHERE status = 'active';

CREATE TABLE nutri.meal_items (
    item_id BIGINT PRIMARY KEY CHECK (item_id > 0), meal_id BIGINT NOT NULL REFERENCES nutri.meal_records(meal_id) ON DELETE CASCADE,
    sequence_no INTEGER NOT NULL CHECK (sequence_no > 0), food_id BIGINT REFERENCES nutri.foods(food_id), food_version INTEGER CHECK (food_version > 0),
    food_name_snapshot VARCHAR(150) NOT NULL, consumed_amount_g NUMERIC(12,3) NOT NULL CHECK (consumed_amount_g > 0), notes VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(meal_id,sequence_no)
);
CREATE INDEX idx_meal_items_food ON nutri.meal_items(food_id);

CREATE TABLE nutri.meal_item_nutrient_snapshots (
    item_id BIGINT NOT NULL REFERENCES nutri.meal_items(item_id) ON DELETE CASCADE, nutrient_id BIGINT NOT NULL REFERENCES nutri.nutrient_definitions(nutrient_id),
    nutrient_code_snapshot VARCHAR(64) NOT NULL, nutrient_name_snapshot VARCHAR(100) NOT NULL, unit_snapshot VARCHAR(16) NOT NULL,
    amount NUMERIC(18,6) NOT NULL CHECK (amount >= 0), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(item_id,nutrient_id)
);
CREATE INDEX idx_item_snapshots_code ON nutri.meal_item_nutrient_snapshots(nutrient_code_snapshot);

CREATE TABLE nutri.meal_images (
    image_id BIGINT PRIMARY KEY CHECK (image_id > 0), meal_id BIGINT NOT NULL REFERENCES nutri.meal_records(meal_id) ON DELETE CASCADE, user_id UUID NOT NULL,
    bucket VARCHAR(255) NOT NULL, object_key VARCHAR(1024) NOT NULL UNIQUE, content_type VARCHAR(64) NOT NULL,
    content_length BIGINT NOT NULL CHECK (content_length BETWEEN 1 AND 10485760), captured_at TIMESTAMPTZ,
    status VARCHAR(16) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','confirmed','deleted')), confirmed_at TIMESTAMPTZ, deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((status = 'pending' AND confirmed_at IS NULL AND deleted_at IS NULL) OR (status = 'confirmed' AND confirmed_at IS NOT NULL AND deleted_at IS NULL) OR (status = 'deleted' AND deleted_at IS NOT NULL))
);
CREATE INDEX idx_meal_images_meal_status ON nutri.meal_images(meal_id,status);
CREATE INDEX idx_meal_images_user ON nutri.meal_images(user_id);

CREATE TABLE nutri.daily_nutrition_summaries (
    summary_id BIGINT PRIMARY KEY CHECK (summary_id > 0), user_id UUID NOT NULL, local_date DATE NOT NULL, meal_count INTEGER NOT NULL DEFAULT 0 CHECK (meal_count >= 0),
    last_recalculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(user_id,local_date)
);
CREATE TABLE nutri.daily_nutrition_values (
    summary_id BIGINT NOT NULL REFERENCES nutri.daily_nutrition_summaries(summary_id) ON DELETE CASCADE, nutrient_id BIGINT NOT NULL REFERENCES nutri.nutrient_definitions(nutrient_id),
    nutrient_code_snapshot VARCHAR(64) NOT NULL, nutrient_name_snapshot VARCHAR(100) NOT NULL, unit_snapshot VARCHAR(16) NOT NULL,
    total_amount NUMERIC(18,6) NOT NULL DEFAULT 0 CHECK (total_amount >= 0), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(summary_id,nutrient_id)
);

CREATE TRIGGER trg_nutrient_definitions_updated BEFORE UPDATE ON nutri.nutrient_definitions FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();
CREATE TRIGGER trg_foods_updated BEFORE UPDATE ON nutri.foods FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();
CREATE TRIGGER trg_food_nutrients_updated BEFORE UPDATE ON nutri.food_nutrient_values FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();
CREATE TRIGGER trg_meals_updated BEFORE UPDATE ON nutri.meal_records FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();
CREATE TRIGGER trg_meal_items_updated BEFORE UPDATE ON nutri.meal_items FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();
CREATE TRIGGER trg_daily_summaries_updated BEFORE UPDATE ON nutri.daily_nutrition_summaries FOR EACH ROW EXECUTE FUNCTION nutri.set_updated_at();

INSERT INTO nutri.nutrient_definitions(nutrient_id,nutrient_code,nutrient_name,unit,nutrient_category,display_order) VALUES
 (1001,'ENERGY_KCAL','能量','kcal','energy',1),(1002,'PROTEIN','蛋白质','g','macro',2),(1003,'FAT','脂肪','g','macro',3),
 (1004,'CARBOHYDRATE','碳水化合物','g','macro',4),(1005,'SUGAR','糖','g','macro',5),(1006,'DIETARY_FIBER','膳食纤维','g','macro',6),
 (1007,'SODIUM','钠','mg','micro',7),(1008,'CALCIUM','钙','mg','micro',8),(1009,'IRON','铁','mg','micro',9),
 (1010,'POTASSIUM','钾','mg','micro',10),(1011,'VITAMIN_C','维生素C','mg','micro',11);
