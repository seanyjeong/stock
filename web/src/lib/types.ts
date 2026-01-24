/**
 * API response types for Daily Stock Story
 */

export interface PortfolioItem {
	ticker: string;
	shares: number;
	avg_cost: number;
	current_price: number;
	regular_price: number | null;
	afterhours_price: number | null;
	premarket_price: number | null;
	value: number;
	gain: number;
	gain_pct: number;
}

export interface PortfolioTotal {
	value_usd: number;
	value_krw: number;
	cost_usd: number;
	gain_usd: number;
	gain_pct: number;
}

export interface PortfolioResponse {
	portfolio: PortfolioItem[];
	total: PortfolioTotal;
	exchange_rate: number;
	briefing_updated_at: string | null;
}

export interface RegSHOItem {
	ticker: string;
	security_name: string;
	market_category: string;
	is_holding: boolean;
}

export interface RegSHOResponse {
	regsho_list: RegSHOItem[];
	total_count: number;
	holdings_on_list: string[];
	collected_date: string | null;
	collected_at: string | null;
}

export interface Recommendation {
	symbol: string;
	entry: number;
	target: number;
	stop_loss: number;
	current_price: number;
	gap_pct: number;
	score: number;
	reasons: string[];
	on_regsho: boolean;
	rsi: number;
	volume_surge: number;
}

export interface RecommendationCategory {
	recommendations: Recommendation[];
	created_at: string | null;
}

export interface RecommendationsResponse {
	day_trade?: RecommendationCategory;
	swing?: RecommendationCategory;
	longterm?: RecommendationCategory;
}

export interface BriefingData {
	timestamp: string;
	exchange_rate: number;
	portfolio: PortfolioItem[];
	total: {
		value_usd: number;
		value_krw: number;
		gain_usd: number;
		gain_krw: number;
		gain_pct: number;
	};
	tax: {
		taxable_krw: number;
		tax_krw: number;
		net_profit_krw: number;
	};
	regSHO: {
		total_count: number;
		holdings_on_list: string[];
		top_tickers: string[];
	};
	new_blog_posts: Array<{
		title: string;
		url?: string;
		tickers: string[];
		keywords: string[];
		date?: string;
		is_new: boolean;
	}>;
	blogger_mentioned_tickers: string[];
}

export interface BriefingResponse {
	data: BriefingData;
	created_at: string | null;
}

export interface BlogPost {
	id: number;
	title: string;
	url: string;
	tickers: string[];
	keywords: string[];
	published_at: string | null;
	is_read: boolean;
}

export interface BlogResponse {
	posts: BlogPost[];
	total_count: number;
	unread_count: number;
}

export interface SqueezeItem {
	ticker: string;
	company_name: string | null;
	borrow_rate: number | null;
	short_interest: number | null;
	days_to_cover: number | null;
	regsho_days: number;
	squeeze_score: number;
	combined_score: number;
	rating: 'HOT' | 'WATCH' | 'COLD';
	is_holding: boolean;
}

export interface SqueezeResponse {
	squeeze_list: SqueezeItem[];
	total_count: number;
	hot_count: number;
	holdings_count: number;
}
