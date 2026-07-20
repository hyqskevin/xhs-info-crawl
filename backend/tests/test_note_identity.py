from app.services.note_identity import canonicalize_note_url, extract_platform_note_id
from app.services.pipeline import deduplicate_results


def test_xhs_url_variants_share_platform_note_id() -> None:
    explore = "https://www.xiaohongshu.com/explore/abc123?xsec_token=old&xsec_source=pc_search"
    discovery = "https://www.xiaohongshu.com/discovery/item/abc123?xsec_token=new"

    assert extract_platform_note_id(explore) == "abc123"
    assert extract_platform_note_id(discovery) == "abc123"
    assert canonicalize_note_url(explore) == "https://www.xiaohongshu.com/explore/abc123"


def test_search_dedup_merges_url_variants_and_keeps_latest_access_url() -> None:
    rows = [
        ("nb", {"title": "活动", "url": "https://www.xiaohongshu.com/explore/abc123?xsec_token=old", "_matched_keywords": ["活动"]}),
        ("nb", {"title": "活动", "url": "https://www.xiaohongshu.com/discovery/item/abc123?xsec_token=new", "_matched_keywords": ["展览"]}),
    ]

    result = deduplicate_results(rows)

    assert len(result) == 1
    assert result[0][1]["url"].endswith("xsec_token=new")
    assert result[0][1]["_matched_keywords"] == ["活动", "展览"]
