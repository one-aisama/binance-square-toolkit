SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS credentials (
    account_id TEXT PRIMARY KEY,
    cookies TEXT NOT NULL,
    headers TEXT NOT NULL,
    harvested_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP,
    valid BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS actions_log (
    id INTEGER PRIMARY KEY,
    account_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    target_id TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_actions_account_type_time ON actions_log(account_id, action_type, created_at);

CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY,
    account_id TEXT NOT NULL,
    date DATE NOT NULL,
    posts_count INTEGER DEFAULT 0,
    likes_count INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    reposts_count INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    UNIQUE(account_id, date)
);

CREATE TABLE IF NOT EXISTS content_queue (
    id INTEGER PRIMARY KEY,
    account_id TEXT NOT NULL,
    text TEXT NOT NULL,
    hashtags TEXT,
    topic TEXT,
    generation_meta TEXT,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    scheduled_at TIMESTAMP,
    published_at TIMESTAMP,
    post_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_content_queue_status ON content_queue(account_id, status);
CREATE INDEX IF NOT EXISTS idx_content_queue_schedule ON content_queue(status, scheduled_at);

CREATE TABLE IF NOT EXISTS parsed_trends (
    id INTEGER PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    topics TEXT NOT NULL,
    fear_greed_index INTEGER,
    popular_coins TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS parsed_posts (
    id INTEGER PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    post_id TEXT NOT NULL,
    author_name TEXT,
    card_type TEXT,
    view_count INTEGER,
    like_count INTEGER,
    comment_count INTEGER,
    share_count INTEGER,
    hashtags TEXT,
    trading_pairs TEXT,
    is_ai_created BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(cycle_id, post_id)
);
CREATE INDEX IF NOT EXISTS idx_parsed_posts_cycle ON parsed_posts(cycle_id);

CREATE TABLE IF NOT EXISTS discovered_endpoints (
    id INTEGER PRIMARY KEY,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    purpose TEXT,
    request_headers TEXT,
    request_body TEXT,
    response_sample TEXT,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(method, path)
);
"""
