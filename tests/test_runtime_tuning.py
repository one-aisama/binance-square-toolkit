"""Tests for RuntimeTuning defaults and persona_policy integration."""

from src.runtime.persona_policy import (
    ContentLengthConfig,
    DelayConfig,
    FeedCollectionConfig,
    RuntimeTuning,
    ScoringConfig,
    SimilarityThresholds,
)


def test_similarity_thresholds_defaults():
    t = SimilarityThresholds()
    assert t.comment_diversity == 0.82
    assert t.self_novelty_text == 0.58
    assert t.self_novelty_relaxed == 0.52
    assert t.feed_novelty_format == 0.45
    assert t.feed_novelty_coin == 0.50


def test_delay_config_defaults():
    d = DelayConfig()
    assert len(d.buckets) == 4
    assert d.idle_visit_probability == 0.25
    assert d.post_action_delay_min == 8.0
    assert d.light_action_delay_min == 3.0


def test_feed_collection_defaults():
    f = FeedCollectionConfig()
    assert f.primary_limit == 60
    assert f.min_text_length == 40
    assert f.max_text_length == 400
    assert "airdrop" in f.spam_words


def test_content_length_defaults():
    c = ContentLengthConfig()
    assert c.min_post_length == 80
    assert c.min_comment_length == 15


def test_scoring_defaults():
    s = ScoringConfig()
    assert s.family_repetition_penalty == 60.0
    assert s.symbol_self_overlap_penalty == 220.0
    assert s.news_url_overlap_penalty == 500.0
    assert s.news_title_overlap_penalty == 450.0
    assert s.feed_source_overlap_penalty == 300.0


def test_runtime_tuning_nested_defaults():
    rt = RuntimeTuning()
    assert isinstance(rt.similarity, SimilarityThresholds)
    assert isinstance(rt.delays, DelayConfig)
    assert isinstance(rt.feed, FeedCollectionConfig)
    assert isinstance(rt.content_length, ContentLengthConfig)
    assert isinstance(rt.scoring, ScoringConfig)


def test_custom_thresholds():
    custom = SimilarityThresholds(comment_diversity=0.70, self_novelty_text=0.40)
    assert custom.comment_diversity == 0.70
    assert custom.self_novelty_text == 0.40
    assert custom.feed_novelty_format == 0.45  # default preserved
