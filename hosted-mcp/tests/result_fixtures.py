"""Synthetic payloads matching the observed public API shapes."""
AUDIT = {
    "score": 88, "grade": "A", "ai_discoverability_status": "PARTIAL",
    "schema_detected": ["WebSite"], "recommendations": ["Declare a canonical URL."],
    "full_report_url": "https://nymrel.com/site-audit",
}
CLIP = {
    "target_platform": "tiktok",
    "hook_score": 35, "hook_strength": "weak", "suggested_edits": ["Shorten the opening."],
    "signals": {
        "opening_word_count": 13, "opens_with_hook_pattern": False, "addresses_viewer": True,
        "has_curiosity_signal": False, "opening_contains_number": False,
        "total_word_count": 22, "platform_word_range": [45, 160],
        "total_word_count_in_platform_range": False,
    },
}
