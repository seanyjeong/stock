"""
lib/ - 주식 분석 공통 패키지
deep_analyzer, api, scanners 등 어디서든 재사용 가능

Usage:
    from lib import get_borrow_data, check_regsho, get_sec_info
    from lib.base import get_db, fmt_num, fmt_pct
"""

# base
from lib.base import DB_CONFIG, HEADERS, SEC_HEADERS, get_db, fmt_num, fmt_pct

# regsho
from lib.regsho import check_regsho, fetch_historical_regsho

# borrow
from lib.borrow import get_borrow_data, get_borrow_data_playwright, get_fintel_data

# sec
from lib.sec import get_sec_info, get_ftd_data, get_sec_filings, parse_8k_content

# social
from lib.social import get_social_sentiment

# news
from lib.news import (
    get_news, search_recent_news, get_sector_news, get_finviz_news,
    get_biotech_news, get_tech_news, get_energy_news,
    get_automotive_news, get_retail_news, get_consumer_news,
    get_financial_news, get_industrial_news, get_realestate_news,
)

# technicals
from lib.technicals import get_technicals, get_fibonacci_levels, get_volume_profile

# options
from lib.options import get_options_data

# darkpool
from lib.darkpool import get_darkpool_data

# institutional
from lib.institutional import (
    get_officers, get_insider_transactions, get_institutional_holders,
    get_institutional_changes, get_peer_comparison, get_short_history,
)

# catalysts
from lib.catalysts import (
    get_catalyst_calendar, get_biotech_catalysts, get_automotive_catalysts,
    get_retail_catalysts, get_financial_catalysts, get_industrial_catalysts,
    get_realestate_catalysts,
)

# news_vectors
from lib.news_vectors import (
    init_vector_tables, embed_and_dedup, check_market_reflection,
    cleanup_old_news, calculate_time_weights, get_time_weighted_score,
    search_similar_news,
)

# sec_patterns
from lib.sec_patterns import (
    analyze_sec_patterns, get_cached_patterns, collect_sec_patterns,
    discover_new_13d_filings, init_sec_patterns_table,
)
