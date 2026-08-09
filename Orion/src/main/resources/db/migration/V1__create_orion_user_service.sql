CREATE SCHEMA IF NOT EXISTS orion;

CREATE OR REPLACE FUNCTION orion.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE orion.users (
    user_id UUID PRIMARY KEY,
    username VARCHAR(150) NOT NULL,
    email VARCHAR(320),
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    display_name VARCHAR(150) NOT NULL DEFAULT '',
    avatar_object_key VARCHAR(1024),
    business_status VARCHAR(16) NOT NULL DEFAULT 'active'
        CHECK (business_status IN ('active', 'suspended', 'deactivated')),
    locale VARCHAR(16) NOT NULL DEFAULT 'zh-CN',
    timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai',
    last_seen_at TIMESTAMPTZ,
    identity_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_users_username_active
    ON orion.users (LOWER(username))
    WHERE deleted_at IS NULL AND business_status = 'active';
CREATE UNIQUE INDEX uq_users_email_lower
    ON orion.users (LOWER(email))
    WHERE email IS NOT NULL;
CREATE INDEX idx_users_business_status ON orion.users (business_status);
CREATE INDEX idx_users_last_seen_at ON orion.users (last_seen_at);
CREATE INDEX idx_users_deleted_at ON orion.users (deleted_at);

CREATE TABLE orion.user_profiles (
    user_id UUID PRIMARY KEY REFERENCES orion.users(user_id) ON DELETE CASCADE,
    birth_date DATE,
    gender VARCHAR(16) CHECK (gender IN ('male', 'female', 'other', 'unknown')),
    height_cm NUMERIC(5, 1) CHECK (height_cm BETWEEN 50 AND 300),
    activity_level VARCHAR(24) CHECK (activity_level IN ('sedentary', 'light', 'moderate', 'active', 'very_active')),
    daily_water_target_ml INTEGER NOT NULL DEFAULT 2000 CHECK (daily_water_target_ml BETWEEN 0 AND 10000),
    profile_completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE orion.user_body_measurements (
    measurement_id BIGINT PRIMARY KEY CHECK (measurement_id > 0),
    user_id UUID NOT NULL REFERENCES orion.users(user_id) ON DELETE CASCADE,
    measured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    height_cm NUMERIC(5, 1) CHECK (height_cm BETWEEN 50 AND 300),
    weight_kg NUMERIC(6, 2) CHECK (weight_kg BETWEEN 10 AND 500),
    body_fat_percentage NUMERIC(5, 2) CHECK (body_fat_percentage BETWEEN 0 AND 100),
    waist_cm NUMERIC(5, 1) CHECK (waist_cm BETWEEN 20 AND 300),
    systolic_bp SMALLINT CHECK (systolic_bp BETWEEN 40 AND 300),
    diastolic_bp SMALLINT CHECK (diastolic_bp BETWEEN 20 AND 200),
    resting_heart_rate SMALLINT CHECK (resting_heart_rate BETWEEN 20 AND 250),
    source VARCHAR(32) NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'device', 'import', 'clinical')),
    source_reference VARCHAR(255),
    notes VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (num_nonnulls(height_cm, weight_kg, body_fat_percentage, waist_cm, systolic_bp, diastolic_bp, resting_heart_rate) > 0)
);
CREATE INDEX idx_body_measurements_user_time ON orion.user_body_measurements (user_id, measured_at DESC);

CREATE TABLE orion.user_health_goals (
    goal_id BIGINT PRIMARY KEY CHECK (goal_id > 0),
    user_id UUID NOT NULL REFERENCES orion.users(user_id) ON DELETE CASCADE,
    goal_type VARCHAR(32) NOT NULL CHECK (goal_type IN ('weight_loss', 'muscle_gain', 'maintain', 'health_improve')),
    target_weight_kg NUMERIC(6, 2) CHECK (target_weight_kg BETWEEN 10 AND 500),
    target_body_fat_percentage NUMERIC(5, 2) CHECK (target_body_fat_percentage BETWEEN 0 AND 100),
    priority SMALLINT NOT NULL DEFAULT 1 CHECK (priority BETWEEN 1 AND 10),
    status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('planned', 'active', 'achieved', 'cancelled')),
    started_on DATE NOT NULL DEFAULT CURRENT_DATE,
    target_date DATE,
    completed_at TIMESTAMPTZ,
    notes VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (target_date IS NULL OR target_date >= started_on)
);
CREATE INDEX idx_health_goals_user_status ON orion.user_health_goals (user_id, status, started_on DESC);
CREATE UNIQUE INDEX uq_health_goals_active_type ON orion.user_health_goals (user_id, goal_type) WHERE status = 'active';

CREATE TABLE orion.user_allergies (
    allergy_id BIGINT PRIMARY KEY CHECK (allergy_id > 0),
    user_id UUID NOT NULL REFERENCES orion.users(user_id) ON DELETE CASCADE,
    allergen_code VARCHAR(64) NOT NULL,
    allergen_name VARCHAR(100) NOT NULL,
    severity VARCHAR(24) CHECK (severity IN ('mild', 'moderate', 'severe', 'life_threatening')),
    reaction_description VARCHAR(500),
    diagnosis_status VARCHAR(24) NOT NULL DEFAULT 'self_reported' CHECK (diagnosis_status IN ('self_reported', 'suspected', 'confirmed')),
    recorded_on DATE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    notes VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_user_allergies_user ON orion.user_allergies (user_id, active);
CREATE UNIQUE INDEX uq_user_allergies_active ON orion.user_allergies (user_id, allergen_code) WHERE active;

CREATE TABLE orion.user_medical_conditions (
    condition_id BIGINT PRIMARY KEY CHECK (condition_id > 0),
    user_id UUID NOT NULL REFERENCES orion.users(user_id) ON DELETE CASCADE,
    condition_code VARCHAR(64) NOT NULL,
    condition_name VARCHAR(150) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'remission', 'resolved')),
    diagnosed_on DATE,
    resolved_on DATE,
    source VARCHAR(24) NOT NULL DEFAULT 'self_reported' CHECK (source IN ('self_reported', 'clinical', 'imported')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (resolved_on IS NULL OR diagnosed_on IS NULL OR resolved_on >= diagnosed_on)
);
CREATE INDEX idx_conditions_user_status ON orion.user_medical_conditions (user_id, status);
CREATE UNIQUE INDEX uq_conditions_active ON orion.user_medical_conditions (user_id, condition_code) WHERE status = 'active';

CREATE TABLE orion.user_dietary_restrictions (
    restriction_id BIGINT PRIMARY KEY CHECK (restriction_id > 0),
    user_id UUID NOT NULL REFERENCES orion.users(user_id) ON DELETE CASCADE,
    restriction_code VARCHAR(64) NOT NULL,
    restriction_name VARCHAR(100) NOT NULL,
    category VARCHAR(24) NOT NULL CHECK (category IN ('medical', 'religious', 'lifestyle', 'preference')),
    source VARCHAR(24) NOT NULL DEFAULT 'self_reported' CHECK (source IN ('self_reported', 'clinician', 'system')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    starts_on DATE,
    ends_on DATE,
    notes VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (ends_on IS NULL OR starts_on IS NULL OR ends_on >= starts_on)
);
CREATE INDEX idx_restrictions_user_active ON orion.user_dietary_restrictions (user_id, active);
CREATE UNIQUE INDEX uq_restrictions_active ON orion.user_dietary_restrictions (user_id, restriction_code) WHERE active;

CREATE TABLE orion.user_cuisine_preferences (
    user_id UUID NOT NULL REFERENCES orion.users(user_id) ON DELETE CASCADE,
    cuisine_code VARCHAR(64) NOT NULL,
    cuisine_name VARCHAR(100) NOT NULL,
    preference_score SMALLINT NOT NULL DEFAULT 0 CHECK (preference_score BETWEEN -2 AND 2),
    notes VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, cuisine_code)
);
CREATE INDEX idx_cuisine_preferences_score ON orion.user_cuisine_preferences (user_id, preference_score DESC);

CREATE TABLE orion.clinical_observations (
    observation_id BIGINT PRIMARY KEY CHECK (observation_id > 0),
    user_id UUID NOT NULL REFERENCES orion.users(user_id) ON DELETE CASCADE,
    observation_code VARCHAR(64) NOT NULL,
    observation_name VARCHAR(150) NOT NULL,
    value_numeric NUMERIC(18, 6),
    value_text VARCHAR(500),
    unit VARCHAR(32),
    reference_low NUMERIC(18, 6),
    reference_high NUMERIC(18, 6),
    interpretation VARCHAR(16) NOT NULL DEFAULT 'unknown' CHECK (interpretation IN ('low', 'normal', 'high', 'critical', 'unknown')),
    observed_at TIMESTAMPTZ NOT NULL,
    source VARCHAR(32) NOT NULL DEFAULT 'self_reported' CHECK (source IN ('self_reported', 'clinical', 'device', 'imported')),
    report_object_key VARCHAR(1024),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (num_nonnulls(value_numeric, value_text) = 1),
    CHECK (reference_high IS NULL OR reference_low IS NULL OR reference_high >= reference_low),
    CHECK (jsonb_typeof(metadata) = 'object')
);
CREATE INDEX idx_observations_user_code_time ON orion.clinical_observations (user_id, observation_code, observed_at DESC);
CREATE INDEX idx_observations_metadata_gin ON orion.clinical_observations USING GIN (metadata);

CREATE TABLE orion.user_consents (
    consent_id BIGINT PRIMARY KEY CHECK (consent_id > 0),
    user_id UUID NOT NULL REFERENCES orion.users(user_id) ON DELETE RESTRICT,
    consent_type VARCHAR(64) NOT NULL,
    policy_version VARCHAR(32) NOT NULL,
    granted BOOLEAN NOT NULL DEFAULT TRUE,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source VARCHAR(24) NOT NULL DEFAULT 'mobile' CHECK (source IN ('mobile', 'web', 'admin', 'imported')),
    client_ip INET,
    user_agent VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_consents_user_type_time ON orion.user_consents (user_id, consent_type, recorded_at DESC);

CREATE TABLE orion.file_cleanup_tasks (
    task_id BIGINT PRIMARY KEY CHECK (task_id > 0),
    owner_user_id UUID REFERENCES orion.users(user_id) ON DELETE SET NULL,
    bucket VARCHAR(255) NOT NULL,
    object_key VARCHAR(1024) NOT NULL,
    task_type VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processing_started_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    UNIQUE (bucket, object_key, task_type)
);
CREATE INDEX idx_cleanup_owner_user ON orion.file_cleanup_tasks (owner_user_id);
CREATE INDEX idx_file_cleanup_tasks_pending ON orion.file_cleanup_tasks (next_attempt_at) WHERE status = 'pending';
CREATE INDEX idx_file_cleanup_tasks_processing ON orion.file_cleanup_tasks (processing_started_at) WHERE status = 'processing';

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON orion.users
    FOR EACH ROW EXECUTE FUNCTION orion.set_updated_at();
CREATE TRIGGER trg_user_profiles_updated_at BEFORE UPDATE ON orion.user_profiles
    FOR EACH ROW EXECUTE FUNCTION orion.set_updated_at();
CREATE TRIGGER trg_body_measurements_updated_at BEFORE UPDATE ON orion.user_body_measurements
    FOR EACH ROW EXECUTE FUNCTION orion.set_updated_at();
CREATE TRIGGER trg_health_goals_updated_at BEFORE UPDATE ON orion.user_health_goals
    FOR EACH ROW EXECUTE FUNCTION orion.set_updated_at();
CREATE TRIGGER trg_user_allergies_updated_at BEFORE UPDATE ON orion.user_allergies
    FOR EACH ROW EXECUTE FUNCTION orion.set_updated_at();
CREATE TRIGGER trg_medical_conditions_updated_at BEFORE UPDATE ON orion.user_medical_conditions
    FOR EACH ROW EXECUTE FUNCTION orion.set_updated_at();
CREATE TRIGGER trg_dietary_restrictions_updated_at BEFORE UPDATE ON orion.user_dietary_restrictions
    FOR EACH ROW EXECUTE FUNCTION orion.set_updated_at();
CREATE TRIGGER trg_cuisine_preferences_updated_at BEFORE UPDATE ON orion.user_cuisine_preferences
    FOR EACH ROW EXECUTE FUNCTION orion.set_updated_at();
