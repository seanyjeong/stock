<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';

	interface SqueezeItem {
		ticker: string;
		company_name: string | null;
		short_interest: number | null;
		borrow_rate: number | null;
		days_to_cover: number | null;
		zero_borrow: boolean;
		available_shares: number | null;
		float_shares: number | null;
		dilution_protected: boolean;
		regsho_days: number;
		squeeze_score: number;
		combined_score: number;
		rating: string;
		is_holding: boolean;
	}

	interface SqueezeData {
		squeeze_list: SqueezeItem[];
		total_count: number;
		hot_count: number;
		holdings_count: number;
	}

	let data = $state<SqueezeData | null>(null);
	let isLoading = $state(true);
	let error = $state('');
	let filterRating = $state('all');

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	onMount(async () => {
		await loadData();
	});

	async function loadData() {
		isLoading = true;
		error = '';

		try {
			const response = await fetch(`${API_BASE}/api/squeeze`);
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
			case 'HOT': return '#f85149';
			case 'WATCH': return '#f0883e';
			default: return '#8b949e';
		}
	}

	function getRatingEmoji(rating: string): string {
		switch (rating) {
			case 'HOT': return '🔥';
			case 'WATCH': return '👀';
			default: return '❄️';
		}
	}

	function formatNumber(n: number | null): string {
		if (n === null) return '-';
		if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
		if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K';
		return n.toLocaleString();
	}

	$effect(() => {
		// Filter logic handled in template
	});
</script>

<svelte:head>
	<title>숏스퀴즈 분석 - Stock Dashboard</title>
</svelte:head>

<div class="container">
	<div class="header">
		<h1>🔥 숏스퀴즈 분석 v2</h1>
		{#if data}
			<div class="stats">
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
		<button class:active={filterRating === 'HOT'} onclick={() => filterRating = 'HOT'}>🔥 HOT</button>
		<button class:active={filterRating === 'WATCH'} onclick={() => filterRating = 'WATCH'}>👀 WATCH</button>
		<button class:active={filterRating === 'holding'} onclick={() => filterRating = 'holding'}>💼 보유</button>
	</div>

	<!-- Legend -->
	<div class="legend">
		<div class="legend-item"><span class="dot si"></span> SI: Short Interest %</div>
		<div class="legend-item"><span class="dot br"></span> BR: Borrow Rate %</div>
		<div class="legend-item"><span class="dot dtc"></span> DTC: Days to Cover</div>
		<div class="legend-item"><span class="dot zb"></span> ZB: Zero Borrow</div>
		<div class="legend-item"><span class="dot dp"></span> DP: Dilution Protected</div>
	</div>

	{#if isLoading}
		<div class="loading">로딩 중...</div>
	{:else if data}
		<div class="squeeze-list">
			{#each data.squeeze_list.filter(item => {
				if (filterRating === 'all') return true;
				if (filterRating === 'holding') return item.is_holding;
				return item.rating === filterRating;
			}) as item, i}
				<div class="squeeze-card" class:hot={item.rating === 'HOT'} class:holding={item.is_holding}>
					<div class="card-rank">#{i + 1}</div>
					<div class="card-main">
						<div class="card-header">
							<div class="ticker-section">
								<a href="/stock/{item.ticker}" class="ticker">{item.ticker}</a>
								{#if item.is_holding}
									<span class="badge holding">보유</span>
								{/if}
								{#if item.zero_borrow}
									<span class="badge zero-borrow">Zero Borrow</span>
								{/if}
								{#if item.dilution_protected}
									<span class="badge protected">희석방어</span>
								{/if}
							</div>
							<div class="score-section">
								<span class="rating" style="color: {getRatingColor(item.rating)}">
									{getRatingEmoji(item.rating)} {item.rating}
								</span>
								<span class="score">{item.combined_score}점</span>
							</div>
						</div>

						{#if item.company_name}
							<div class="company-name">{item.company_name}</div>
						{/if}

						<div class="metrics">
							<div class="metric" title="Short Interest %">
								<span class="label">SI</span>
								<span class="value" class:high={item.short_interest && item.short_interest > 20}>
									{item.short_interest ? item.short_interest.toFixed(1) + '%' : '-'}
								</span>
							</div>
							<div class="metric" title="Borrow Rate %">
								<span class="label">BR</span>
								<span class="value" class:extreme={item.borrow_rate && item.borrow_rate >= 999}>
									{item.borrow_rate ? (item.borrow_rate >= 999 ? '999+%' : item.borrow_rate.toFixed(0) + '%') : '-'}
								</span>
							</div>
							<div class="metric" title="Days to Cover">
								<span class="label">DTC</span>
								<span class="value">{item.days_to_cover ? item.days_to_cover.toFixed(2) : '-'}</span>
							</div>
							<div class="metric" title="Float Shares">
								<span class="label">Float</span>
								<span class="value" class:low={item.float_shares && item.float_shares < 10_000_000}>
									{formatNumber(item.float_shares)}
								</span>
							</div>
							<div class="metric" title="RegSHO 연속 등재일">
								<span class="label">RegSHO</span>
								<span class="value">{item.regsho_days}일</span>
							</div>
						</div>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

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
</style>
