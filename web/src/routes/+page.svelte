<script lang="ts">
	import type { PageData } from './$types';
	import RecommendationTabs from '$lib/components/RecommendationTabs.svelte';
	import RegSHOBadge from '$lib/components/RegSHOBadge.svelte';

	let { data }: { data: PageData } = $props();

	let portfolio = $derived(data.portfolio);
	let regsho = $derived(data.regsho);
	let recommendations = $derived(data.recommendations);
	let error = $derived(data.error);

	function formatCurrency(value: number, currency: 'USD' | 'KRW' = 'USD'): string {
		if (currency === 'KRW') {
			return new Intl.NumberFormat('ko-KR', {
				style: 'currency',
				currency: 'KRW',
				maximumFractionDigits: 0
			}).format(value);
		}
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency: 'USD',
			minimumFractionDigits: 2
		}).format(value);
	}

	function formatPercent(value: number): string {
		const sign = value >= 0 ? '+' : '';
		return `${sign}${value.toFixed(1)}%`;
	}

	function getGainClass(value: number): string {
		if (value > 0) return 'positive';
		if (value < 0) return 'negative';
		return 'neutral';
	}

	function formatDate(dateStr: string | null): string {
		if (!dateStr) return '-';
		const date = new Date(dateStr);
		// KST로 변환 (UTC+9)
		const kstDate = new Date(date.getTime() + (9 * 60 * 60 * 1000));
		return kstDate.toLocaleString('ko-KR', {
			timeZone: 'Asia/Seoul',
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		}) + ' KST';
	}
</script>

<svelte:head>
	<title>주식 대시보드</title>
	<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
</svelte:head>

<div class="container">
	<header>
		<h1>📈 주식 대시보드</h1>
	</header>

	{#if error}
		<div class="error">
			<p>데이터를 불러올 수 없습니다</p>
			<button onclick={() => window.location.reload()}>다시 시도</button>
		</div>
	{:else}
		<div class="dashboard">
			<!-- Portfolio Section -->
			{#if portfolio}
				<section class="card portfolio-card">
					<h2>💰 내 포트폴리오</h2>

					<!-- Summary Cards -->
					<div class="summary-grid">
						<div class="summary-card total">
							<span class="summary-label">총 평가금</span>
							<span class="summary-value">{formatCurrency(portfolio.total.value_usd)}</span>
							<span class="summary-sub">{formatCurrency(portfolio.total.value_krw, 'KRW')}</span>
						</div>
						<div class="summary-card {getGainClass(portfolio.total.gain_usd)}">
							<span class="summary-label">총 수익</span>
							<span class="summary-value">{formatCurrency(portfolio.total.gain_usd)}</span>
							<span class="summary-percent">{formatPercent(portfolio.total.gain_pct)}</span>
						</div>
					</div>

					<!-- Stock Cards (Mobile-friendly) -->
					<div class="stock-list">
						{#each portfolio.portfolio as item}
							<div class="stock-card">
								<div class="stock-header">
									<div class="stock-ticker-wrap">
										<span class="stock-ticker">{item.ticker}</span>
										{#if regsho}
											<RegSHOBadge ticker={item.ticker} holdingsOnList={regsho.holdings_on_list} />
										{/if}
										{#if item.afterhours_price}
											<span class="market-badge ah">AH</span>
										{:else if item.premarket_price}
											<span class="market-badge pm">PM</span>
										{/if}
									</div>
									<div class="stock-gain {getGainClass(item.gain)}">
										<span class="gain-amount">{formatCurrency(item.gain)}</span>
										<span class="gain-pct">{formatPercent(item.gain_pct)}</span>
									</div>
								</div>
								<div class="stock-details">
									<div class="detail">
										<span class="detail-label">보유</span>
										<span class="detail-value">{item.shares}주</span>
									</div>
									<div class="detail">
										<span class="detail-label">평단</span>
										<span class="detail-value">{formatCurrency(item.avg_cost)}</span>
									</div>
									<div class="detail">
										<span class="detail-label">현재가</span>
										<span class="detail-value current">{formatCurrency(item.current_price)}</span>
									</div>
									<div class="detail">
										<span class="detail-label">평가금</span>
										<span class="detail-value">{formatCurrency(item.value)}</span>
									</div>
								</div>
							</div>
						{/each}
					</div>

					<div class="card-footer">
						<span class="exchange-rate">환율: $1 = ₩{portfolio.exchange_rate.toLocaleString()}</span>
						<span class="updated">업데이트: {formatDate(portfolio.briefing_updated_at)}</span>
					</div>
				</section>
			{/if}

			<!-- RegSHO Section -->
			{#if regsho}
				<section class="card regsho-card">
					<h2>📋 RegSHO 리스트</h2>
					{#if regsho.holdings_on_list.length > 0}
						<div class="alert-box">
							<span class="alert-icon">🔥</span>
							<span>보유 종목 등재: <strong>{regsho.holdings_on_list.join(', ')}</strong></span>
						</div>
					{/if}
					<p class="regsho-stats">총 {regsho.total_count}개 종목 | {regsho.collected_date}</p>

					<div class="regsho-list">
						{#each regsho.regsho_list.slice(0, 10) as item}
							<div class="regsho-item" class:holding={item.is_holding}>
								<span class="regsho-ticker">{item.ticker}</span>
								<span class="regsho-name">{item.security_name}</span>
							</div>
						{/each}
					</div>
					{#if regsho.total_count > 10}
						<p class="show-more">상위 10개만 표시 (총 {regsho.total_count}개)</p>
					{/if}
				</section>
			{/if}

			<!-- Recommendations Section -->
			{#if recommendations}
				<RecommendationTabs {recommendations} {formatCurrency} {formatDate} />
			{/if}
		</div>
	{/if}
</div>

<style>
	:global(body) {
		background: #0d1117;
		color: #f0f6fc;
		font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
		margin: 0;
		padding: 0;
		-webkit-font-smoothing: antialiased;
	}

	.container {
		max-width: 500px;
		margin: 0 auto;
		padding: 1rem;
		padding-bottom: 2rem;
	}

	header {
		text-align: center;
		margin-bottom: 1.25rem;
		padding-top: 0.5rem;
	}

	h1 {
		font-size: 1.5rem;
		font-weight: 700;
		margin: 0;
		color: #f0f6fc;
	}

	.error {
		text-align: center;
		padding: 2rem 1rem;
		background: #3d1f1f;
		border: 1px solid #f85149;
		border-radius: 12px;
	}

	.error p {
		margin: 0 0 1rem;
		color: #f85149;
	}

	.error button {
		padding: 0.75rem 2rem;
		background: #238636;
		border: none;
		border-radius: 8px;
		color: white;
		font-size: 1rem;
		font-weight: 600;
		cursor: pointer;
	}

	.dashboard {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 12px;
		padding: 1rem;
	}

	h2 {
		font-size: 1.1rem;
		font-weight: 600;
		margin: 0 0 0.875rem;
		color: #f0f6fc;
	}

	/* Summary Grid */
	.summary-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.75rem;
		margin-bottom: 1rem;
	}

	.summary-card {
		background: #21262d;
		padding: 0.875rem;
		border-radius: 10px;
		text-align: center;
	}

	.summary-card.total {
		border: 1px solid #30363d;
	}

	.summary-label {
		display: block;
		font-size: 0.75rem;
		color: #8b949e;
		margin-bottom: 0.25rem;
	}

	.summary-value {
		display: block;
		font-size: 1.25rem;
		font-weight: 700;
		color: #f0f6fc;
	}

	.summary-sub {
		display: block;
		font-size: 0.75rem;
		color: #8b949e;
		margin-top: 0.125rem;
	}

	.summary-percent {
		display: block;
		font-size: 0.875rem;
		font-weight: 600;
		margin-top: 0.125rem;
	}

	.summary-card.positive {
		border: 1px solid #238636;
	}

	.summary-card.positive .summary-value,
	.summary-card.positive .summary-percent {
		color: #3fb950;
	}

	.summary-card.negative {
		border: 1px solid #f85149;
	}

	.summary-card.negative .summary-value,
	.summary-card.negative .summary-percent {
		color: #f85149;
	}

	/* Stock List */
	.stock-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.stock-card {
		background: #21262d;
		border-radius: 10px;
		padding: 0.875rem;
	}

	.stock-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 0.75rem;
	}

	.stock-ticker-wrap {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.stock-ticker {
		font-size: 1.1rem;
		font-weight: 700;
		color: #58a6ff;
	}

	.market-badge {
		font-size: 0.6rem;
		padding: 0.15rem 0.4rem;
		border-radius: 4px;
		font-weight: 600;
	}

	.market-badge.ah {
		background: #1f6feb;
		color: white;
	}

	.market-badge.pm {
		background: #8957e5;
		color: white;
	}

	.stock-gain {
		text-align: right;
	}

	.gain-amount {
		display: block;
		font-size: 1rem;
		font-weight: 600;
	}

	.gain-pct {
		display: block;
		font-size: 0.8rem;
		font-weight: 500;
	}

	.stock-gain.positive .gain-amount,
	.stock-gain.positive .gain-pct {
		color: #3fb950;
	}

	.stock-gain.negative .gain-amount,
	.stock-gain.negative .gain-pct {
		color: #f85149;
	}

	.stock-details {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 0.5rem;
	}

	.detail {
		background: #0d1117;
		padding: 0.5rem;
		border-radius: 6px;
		text-align: center;
	}

	.detail-label {
		display: block;
		font-size: 0.65rem;
		color: #8b949e;
		margin-bottom: 0.125rem;
	}

	.detail-value {
		display: block;
		font-size: 0.8rem;
		font-weight: 600;
		color: #f0f6fc;
	}

	.detail-value.current {
		color: #58a6ff;
	}

	.card-footer {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-top: 0.875rem;
		padding-top: 0.75rem;
		border-top: 1px solid #30363d;
	}

	.exchange-rate {
		font-size: 0.7rem;
		color: #8b949e;
	}

	.updated {
		font-size: 0.7rem;
		color: #8b949e;
	}

	/* RegSHO Section */
	.alert-box {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		background: rgba(248, 81, 73, 0.15);
		border: 1px solid #f85149;
		padding: 0.75rem;
		border-radius: 8px;
		margin-bottom: 0.75rem;
		font-size: 0.875rem;
	}

	.alert-icon {
		font-size: 1rem;
	}

	.regsho-stats {
		font-size: 0.75rem;
		color: #8b949e;
		margin: 0 0 0.75rem;
	}

	.regsho-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.regsho-item {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		background: #21262d;
		padding: 0.625rem 0.75rem;
		border-radius: 6px;
		font-size: 0.8rem;
	}

	.regsho-item.holding {
		background: rgba(63, 185, 80, 0.15);
		border: 1px solid #238636;
	}

	.regsho-ticker {
		font-weight: 600;
		color: #58a6ff;
		min-width: 50px;
	}

	.regsho-item.holding .regsho-ticker {
		color: #3fb950;
	}

	.regsho-name {
		color: #8b949e;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		flex: 1;
	}

	.show-more {
		font-size: 0.7rem;
		color: #8b949e;
		text-align: center;
		margin: 0.75rem 0 0;
	}

	.positive {
		color: #3fb950;
	}

	.negative {
		color: #f85149;
	}

	.neutral {
		color: #8b949e;
	}
</style>
