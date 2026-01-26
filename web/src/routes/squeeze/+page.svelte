<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';

	interface SqueezeItem {
		ticker: string;
		company_name?: string | null;
		short_interest: number | null;
		borrow_rate: number | null;
		days_to_cover: number | null;
		zero_borrow: boolean;
		available_shares: number | null;
		float_shares: number | null;
		dilution_protected: boolean;
		has_positive_news: boolean;
		has_negative_news: boolean;
		squeeze_score: number;
		combined_score: number;
		rating: string;
		is_holding: boolean;
		market_cap: number | null;
		market_cap_tier: string | null;
		price_change_5d: number | null;
		vol_ratio: number | null;
	}

	interface SqueezeData {
		squeeze_list: SqueezeItem[];
		total_count: number;
		hot_count: number;
		squeeze_count: number;
		holdings_count: number;
	}

	let data = $state<SqueezeData | null>(null);
	let isLoading = $state(true);
	let error = $state('');
	let filterRating = $state('all');
	let showScoreModal = $state(false);
	let showAll = $state(false);
	const TOP_N = 10;

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	onMount(async () => {
		await loadData();
	});

	async function loadData() {
		isLoading = true;
		error = '';

		try {
			const token = browser ? localStorage.getItem('access_token') : null;
			const headers: Record<string, string> = {};
			if (token) headers['Authorization'] = `Bearer ${token}`;

			const response = await fetch(`${API_BASE}/api/squeeze`, { headers });
			if (!response.ok) throw new Error('데이터를 불러올 수 없습니다');
			data = await response.json();
		} catch (e) {
			error = e instanceof Error ? e.message : '오류가 발생했습니다';
		} finally {
			isLoading = false;
		}
	}

	function getRatingColor(rating: string): string {
		switch (rating) {
			case 'SQUEEZE': return '#a855f7';
			case 'HOT': return '#f85149';
			case 'WATCH': return '#f0883e';
			default: return '#8b949e';
		}
	}

	function getRatingEmoji(rating: string): string {
		switch (rating) {
			case 'SQUEEZE': return '🚀';
			case 'HOT': return '🔥';
			case 'WATCH': return '👀';
			default: return '❄️';
		}
	}

	function formatMarketCap(mc: number | null): string {
		if (!mc) return '-';
		if (mc >= 1_000_000_000) return '$' + (mc / 1_000_000_000).toFixed(1) + 'B';
		if (mc >= 1_000_000) return '$' + (mc / 1_000_000).toFixed(0) + 'M';
		return '$' + (mc / 1_000).toFixed(0) + 'K';
	}

	function formatNumber(n: number | null): string {
		if (n === null) return '-';
		if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
		if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K';
		return n.toLocaleString();
	}

	let filtered = $derived(data?.squeeze_list?.filter(item => {
		if (filterRating === 'all') return true;
		if (filterRating === 'holding') return item.is_holding;
		return item.rating === filterRating;
	}) ?? []);

	let displayList = $derived(showAll ? filtered : filtered.slice(0, TOP_N));

	$effect(() => {
		filterRating;
		showAll = false;
	});
</script>

<svelte:head>
	<title>숏스퀴즈 분석 - Stock Dashboard</title>
</svelte:head>

<div class="container">
	<div class="header">
		<div class="title-row">
			<h1>🔥 숏스퀴즈 분석 v4</h1>
			<button class="info-btn" onclick={() => showScoreModal = true} title="스코어 계산법">?</button>
		</div>
		{#if data}
			<div class="stats">
				{#if data.squeeze_count > 0}
					<span class="stat squeeze">SQUEEZE {data.squeeze_count}</span>
				{/if}
				<span class="stat hot">HOT {data.hot_count}</span>
				<span class="stat total">전체 {data.total_count}</span>
			</div>
		{/if}
	</div>

	{#if error}
		<div class="error-box">{error}</div>
	{/if}

	<!-- Filter -->
	<div class="filter-bar">
		<button class:active={filterRating === 'all'} onclick={() => filterRating = 'all'}>전체</button>
		<button class:active={filterRating === 'SQUEEZE'} onclick={() => filterRating = 'SQUEEZE'}>🚀 SQUEEZE</button>
		<button class:active={filterRating === 'HOT'} onclick={() => filterRating = 'HOT'}>🔥 HOT</button>
		<button class:active={filterRating === 'WATCH'} onclick={() => filterRating = 'WATCH'}>👀 WATCH</button>
		<button class:active={filterRating === 'holding'} onclick={() => filterRating = 'holding'}>💼 보유</button>
	</div>

	<!-- Legend -->
	<div class="legend">
		<div class="legend-item"><span class="dot si"></span> SI: 공매도 비율</div>
		<div class="legend-item"><span class="dot br"></span> BR: 대차이자</div>
		<div class="legend-item"><span class="dot dtc"></span> DTC: 커버 소요일</div>
		<div class="legend-item"><span class="dot zb"></span> ZB: 대차불가</div>
		<div class="legend-item"><span class="dot dp"></span> DP: 희석방어</div>
		<div class="legend-item"><span class="dot pn"></span> PN: 호재</div>
		<div class="legend-item"><span class="dot nn"></span> NN: 악재</div>
	</div>

	{#if isLoading}
		<div class="loading">로딩 중...</div>
	{:else if data}
		<div class="squeeze-list">
			{#each displayList as item, i}
				<div class="squeeze-card" class:squeeze={item.rating === 'SQUEEZE'} class:hot={item.rating === 'HOT'} class:holding={item.is_holding}>
					<div class="card-rank">#{i + 1}</div>
					<div class="card-main">
						<div class="card-header">
							<div class="ticker-section">
								<a href="/stock/{item.ticker}" class="ticker" title={item.company_name || item.ticker}>{item.ticker}</a>
								{#if item.market_cap_tier && item.market_cap_tier !== 'Unknown'}
									<span class="badge tier">{item.market_cap_tier}</span>
								{/if}
								{#if item.is_holding}
									<span class="badge holding">보유</span>
								{/if}
								{#if item.zero_borrow}
									<span class="badge zero-borrow">ZB</span>
								{/if}
								{#if item.dilution_protected}
									<span class="badge protected">DP</span>
								{/if}
								{#if item.has_positive_news}
									<span class="badge positive-news">PN</span>
								{/if}
								{#if item.has_negative_news}
									<span class="badge negative-news">NN</span>
								{/if}
							</div>
							<div class="score-section">
								<span class="rating" style="color: {getRatingColor(item.rating)}">
									{getRatingEmoji(item.rating)} {item.rating}
								</span>
								<span class="score">{item.combined_score}점</span>
							</div>
						</div>

						<div class="metrics">
							<div class="metric" title="Short Interest %">
								<span class="label">SI</span>
								<span class="value" class:high={item.short_interest && item.short_interest > 20}>
									{item.short_interest ? item.short_interest.toFixed(1) + '%' : '-'}
								</span>
							</div>
							<div class="metric" title="대차이자">
								<span class="label">BR</span>
								<span class="value" class:extreme={item.zero_borrow} class:high={!item.zero_borrow && item.borrow_rate && item.borrow_rate >= 50}>
									{item.zero_borrow ? '불가' : (item.borrow_rate ? item.borrow_rate.toFixed(0) + '%' : '-')}
								</span>
							</div>
							<div class="metric" title="Days to Cover">
								<span class="label">DTC</span>
								<span class="value">{item.days_to_cover ? item.days_to_cover.toFixed(1) : '-'}</span>
							</div>
							<div class="metric" title="Float Shares">
								<span class="label">Float</span>
								<span class="value" class:low={item.float_shares && item.float_shares < 10_000_000}>
									{formatNumber(item.float_shares)}
								</span>
							</div>
							<div class="metric" title="5일 변화율">
								<span class="label">5D</span>
								<span class="value" class:momentum-up={item.price_change_5d && item.price_change_5d > 10} class:momentum-down={item.price_change_5d && item.price_change_5d < -10}>
									{item.price_change_5d ? (item.price_change_5d > 0 ? '+' : '') + item.price_change_5d.toFixed(0) + '%' : '-'}
								</span>
							</div>
							<div class="metric" title="거래량 배수">
								<span class="label">VOL</span>
								<span class="value" class:high={item.vol_ratio && item.vol_ratio > 3}>
									{item.vol_ratio ? item.vol_ratio.toFixed(1) + 'x' : '-'}
								</span>
							</div>
						</div>

						{#if item.market_cap}
							<div class="market-cap-row">
								<span class="mc-label">MCap</span>
								<span class="mc-value">{formatMarketCap(item.market_cap)}</span>
							</div>
						{/if}
					</div>
				</div>
			{/each}

			{#if !showAll && filtered.length > TOP_N}
				<button class="show-more-btn" onclick={() => showAll = true}>
					+{filtered.length - TOP_N}개 더보기
				</button>
			{/if}
		</div>
	{/if}
</div>

<!-- Score Modal -->
{#if showScoreModal}
	<div class="modal-overlay" onclick={() => showScoreModal = false}>
		<div class="modal" onclick={(e) => e.stopPropagation()}>
			<div class="modal-header">
				<h2>스코어 v4 계산법</h2>
				<button class="close-btn" onclick={() => showScoreModal = false}>&times;</button>
			</div>
			<div class="modal-body">
				<div class="score-info">
					<h3>1단계: 시가총액 가중치</h3>
					<ul>
						<li><strong>Nano</strong> &lt;$100M: x1.0</li>
						<li><strong>Micro</strong> $100-500M: x0.85</li>
						<li><strong>Small</strong> $500M-2B: x0.6</li>
						<li><strong>Mid/Large</strong> &gt;$2B: x0.3</li>
					</ul>
				</div>
				<div class="score-info">
					<h3>A. 공급 압박 (max 35)</h3>
					<ul>
						<li><strong>ZB</strong> Zero Borrow: +25</li>
						<li>Hard to Borrow (BR&ge;100%): +12</li>
						<li>BR 가산: 100%+ (+8) / 50%+ (+5) / 20%+ (+2)</li>
						<li>Available 0: +5 / &lt;50K: +3</li>
					</ul>
				</div>
				<div class="score-info">
					<h3>B. 숏 포지션 (max 25)</h3>
					<ul>
						<li>SI 40%+: +20 / 30%+: +15 / 20%+: +10 / 10%+: +5</li>
						<li>DTC 7일+: +5 / 3일+: +3</li>
					</ul>
				</div>
				<div class="score-info">
					<h3>C. 촉매 & 모멘텀 (max 25)</h3>
					<ul>
						<li>호재: +10 / 악재: -10 / 뉴스 없음: -5</li>
						<li>5일 변화: 50%+ (+10) / 20%+ (+7) / 10%+ (+4)</li>
						<li>거래량: 5x+ (+5) / 3x+ (+3) / 1.5x+ (+1)</li>
					</ul>
				</div>
				<div class="score-info">
					<h3>D. 구조적 보호 (max 15)</h3>
					<ul>
						<li>Float &lt;5M: +7 / &lt;10M: +4 / &lt;20M: +2</li>
						<li><strong>DP</strong> 희석 보호: +3</li>
						<li>RegSHO 등재: +5</li>
					</ul>
				</div>
				<div class="rating-guide">
					<h3>등급 = Raw Score x 시가총액 가중치</h3>
					<p>🚀 SQUEEZE: 75+ | 🔥 HOT: 55-74 | 👀 WATCH: 35-54 | ❄️ COLD: &lt;35</p>
				</div>
			</div>
		</div>
	</div>
{/if}

<style>
	.container {
		max-width: 600px;
		margin: 0 auto;
		padding: 1rem;
		padding-bottom: 80px;
	}

	.header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1rem;
	}

	h1 {
		font-size: 1.3rem;
		margin: 0;
	}

	.stats {
		display: flex;
		gap: 0.5rem;
	}

	.stat {
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
		font-size: 0.75rem;
		font-weight: 600;
	}

	.stat.squeeze {
		background: rgba(168, 85, 247, 0.2);
		color: #a855f7;
	}

	.stat.hot {
		background: rgba(248, 81, 73, 0.2);
		color: #f85149;
	}

	.stat.total {
		background: #21262d;
		color: #8b949e;
	}

	.error-box {
		background: rgba(248, 81, 73, 0.15);
		border: 1px solid #f85149;
		color: #f85149;
		padding: 1rem;
		border-radius: 8px;
		margin-bottom: 1rem;
	}

	.filter-bar {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 1rem;
		overflow-x: auto;
	}

	.filter-bar button {
		padding: 0.5rem 1rem;
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 20px;
		color: #8b949e;
		font-size: 0.8rem;
		cursor: pointer;
		white-space: nowrap;
	}

	.filter-bar button.active {
		background: #238636;
		border-color: #238636;
		color: white;
	}

	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		padding: 0.75rem;
		background: #161b22;
		border-radius: 8px;
		margin-bottom: 1rem;
		font-size: 0.7rem;
		color: #8b949e;
	}

	.legend-item {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	.dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
	}

	.dot.si { background: #58a6ff; }
	.dot.br { background: #f85149; }
	.dot.dtc { background: #a371f7; }
	.dot.zb { background: #f0883e; }
	.dot.dp { background: #3fb950; }
	.dot.pn { background: #d2a8ff; }
	.dot.nn { background: #f85149; }

	.loading {
		text-align: center;
		padding: 3rem;
		color: #8b949e;
	}

	.squeeze-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.squeeze-card {
		display: flex;
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 12px;
		overflow: hidden;
	}

	.squeeze-card.squeeze {
		border-color: #a855f7;
		box-shadow: 0 0 12px rgba(168, 85, 247, 0.3);
	}

	.squeeze-card.hot {
		border-color: #f85149;
		box-shadow: 0 0 10px rgba(248, 81, 73, 0.2);
	}

	.squeeze-card.holding {
		border-left: 3px solid #58a6ff;
	}

	.card-rank {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 40px;
		background: #21262d;
		font-weight: 700;
		color: #8b949e;
		font-size: 0.8rem;
	}

	.squeeze-card.squeeze .card-rank {
		background: rgba(168, 85, 247, 0.2);
		color: #a855f7;
	}

	.squeeze-card.hot .card-rank {
		background: rgba(248, 81, 73, 0.2);
		color: #f85149;
	}

	.card-main {
		flex: 1;
		padding: 0.75rem;
	}

	.card-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 0.25rem;
	}

	.ticker-section {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.ticker {
		font-weight: 700;
		font-size: 1.1rem;
		color: #58a6ff;
		text-decoration: none;
	}

	.ticker:hover {
		text-decoration: underline;
	}

	.badge {
		padding: 0.1rem 0.4rem;
		border-radius: 4px;
		font-size: 0.6rem;
		font-weight: 600;
	}

	.badge.holding {
		background: rgba(88, 166, 255, 0.2);
		color: #58a6ff;
	}

	.badge.zero-borrow {
		background: rgba(248, 81, 73, 0.2);
		color: #f85149;
	}

	.badge.protected {
		background: rgba(63, 185, 80, 0.2);
		color: #3fb950;
	}

	.badge.positive-news {
		background: rgba(163, 113, 247, 0.2);
		color: #a371f7;
	}

	.badge.negative-news {
		background: rgba(248, 81, 73, 0.2);
		color: #f85149;
	}

	.badge.tier {
		background: rgba(139, 148, 158, 0.2);
		color: #8b949e;
		font-size: 0.55rem;
	}

	.score-section {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
	}

	.rating {
		font-weight: 700;
		font-size: 0.9rem;
	}

	.score {
		font-size: 1.2rem;
		font-weight: 700;
	}

	.company-name {
		font-size: 0.7rem;
		color: #8b949e;
		margin-bottom: 0.5rem;
	}

	.metrics {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}

	.metric {
		display: flex;
		flex-direction: column;
		align-items: center;
		min-width: 45px;
	}

	.metric .label {
		font-size: 0.6rem;
		color: #8b949e;
		text-transform: uppercase;
	}

	.metric .value {
		font-size: 0.85rem;
		font-weight: 600;
	}

	.metric .value.high {
		color: #f0883e;
	}

	.metric .value.extreme {
		color: #f85149;
	}

	.metric .value.low {
		color: #3fb950;
	}

	.metric .value.momentum-up {
		color: #3fb950;
	}

	.metric .value.momentum-down {
		color: #f85149;
	}

	.market-cap-row {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.25rem;
		font-size: 0.7rem;
		color: #8b949e;
	}

	.mc-label {
		color: #6e7681;
	}

	.mc-value {
		color: #8b949e;
	}

	.show-more-btn {
		width: 100%;
		padding: 0.75rem;
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 8px;
		color: #8b949e;
		font-size: 0.85rem;
		cursor: pointer;
		margin-top: 0.5rem;
	}

	.show-more-btn:hover {
		background: #30363d;
		color: #c9d1d9;
	}

	/* Title row with info button */
	.title-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.info-btn {
		width: 22px;
		height: 22px;
		border-radius: 50%;
		border: 1px solid #8b949e;
		background: transparent;
		color: #8b949e;
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.info-btn:hover {
		border-color: #58a6ff;
		color: #58a6ff;
	}

	/* Modal */
	.modal-overlay {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.7);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 2000;
		padding: 1rem;
	}

	.modal {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 12px;
		max-width: 400px;
		width: 100%;
		max-height: 80vh;
		overflow-y: auto;
	}

	.modal-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1rem;
		border-bottom: 1px solid #30363d;
	}

	.modal-header h2 {
		margin: 0;
		font-size: 1.1rem;
	}

	.close-btn {
		background: none;
		border: none;
		color: #8b949e;
		font-size: 1.5rem;
		cursor: pointer;
		line-height: 1;
	}

	.close-btn:hover {
		color: #f0f6fc;
	}

	.modal-body {
		padding: 1rem;
	}

	.score-info {
		margin-bottom: 1rem;
	}

	.score-info h3 {
		font-size: 0.85rem;
		color: #58a6ff;
		margin: 0 0 0.5rem 0;
	}

	.score-info ul {
		margin: 0;
		padding-left: 1.25rem;
		font-size: 0.8rem;
		color: #c9d1d9;
	}

	.score-info li {
		margin-bottom: 0.25rem;
	}

	.rating-guide {
		margin-top: 1rem;
		padding-top: 1rem;
		border-top: 1px solid #30363d;
	}

	.rating-guide h3 {
		font-size: 0.85rem;
		color: #58a6ff;
		margin: 0 0 0.5rem 0;
	}

	.rating-guide p {
		font-size: 0.8rem;
		margin: 0;
	}
</style>
