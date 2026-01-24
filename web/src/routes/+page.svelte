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
		return new Date(dateStr).toLocaleString('ko-KR', {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}
</script>

<svelte:head>
	<title>Daily Stock Story</title>
</svelte:head>

<div class="container">
	<header>
		<h1>Daily Stock Story</h1>
		<p class="subtitle">Portfolio Dashboard</p>
	</header>

	{#if error}
		<div class="error">
			<p>{error}</p>
			<button onclick={() => window.location.reload()}>Retry</button>
		</div>
	{:else}
		<div class="dashboard">
			<!-- Portfolio Section -->
			{#if portfolio}
				<section class="card portfolio-card">
					<h2>Portfolio</h2>
					<div class="portfolio-summary">
						<div class="summary-item total-value">
							<span class="label">Total Value</span>
							<span class="value">{formatCurrency(portfolio.total.value_usd)}</span>
							<span class="sub-value">{formatCurrency(portfolio.total.value_krw, 'KRW')}</span>
						</div>
						<div class="summary-item {getGainClass(portfolio.total.gain_usd)}">
							<span class="label">Total Gain</span>
							<span class="value">{formatCurrency(portfolio.total.gain_usd)}</span>
							<span class="percent">{formatPercent(portfolio.total.gain_pct)}</span>
						</div>
						<div class="summary-item">
							<span class="label">Exchange Rate</span>
							<span class="value">1 USD = {portfolio.exchange_rate.toLocaleString()} KRW</span>
						</div>
					</div>

					<div class="table-container">
						<table class="portfolio-table">
							<thead>
								<tr>
									<th>Ticker</th>
									<th class="right">Shares</th>
									<th class="right">Avg Cost</th>
									<th class="right">Current</th>
									<th class="right">Value</th>
									<th class="right">Gain</th>
								</tr>
							</thead>
							<tbody>
								{#each portfolio.portfolio as item}
									<tr>
										<td class="ticker">
											{item.ticker}
											{#if regsho}
												<RegSHOBadge ticker={item.ticker} holdingsOnList={regsho.holdings_on_list} />
											{/if}
										</td>
										<td class="right">{item.shares}</td>
										<td class="right">{formatCurrency(item.avg_cost)}</td>
										<td class="right">
											<span class="price">{formatCurrency(item.current_price)}</span>
											{#if item.afterhours_price}
												<span class="market-indicator ah">AH</span>
											{:else if item.premarket_price}
												<span class="market-indicator pm">PM</span>
											{/if}
										</td>
										<td class="right">{formatCurrency(item.value)}</td>
										<td class="right {getGainClass(item.gain)}">
											<span>{formatCurrency(item.gain)}</span>
											<span class="percent">{formatPercent(item.gain_pct)}</span>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<p class="updated">Updated: {formatDate(portfolio.briefing_updated_at)}</p>
				</section>
			{/if}

			<!-- RegSHO Section -->
			{#if regsho}
				<section class="card regsho-card">
					<h2>RegSHO Threshold List</h2>
					{#if regsho.holdings_on_list.length > 0}
						<div class="alert alert-info">
							<strong>Holdings on list:</strong> {regsho.holdings_on_list.join(', ')}
						</div>
					{/if}
					<p class="stats">Total: {regsho.total_count} securities | Date: {regsho.collected_date}</p>

					<div class="table-container regsho-table-container">
						<table class="regsho-table">
							<thead>
								<tr>
									<th>Ticker</th>
									<th>Security Name</th>
									<th>Market</th>
								</tr>
							</thead>
							<tbody>
								{#each regsho.regsho_list.slice(0, 20) as item}
									<tr class:holding={item.is_holding}>
										<td class="ticker">{item.ticker}</td>
										<td class="name">{item.security_name}</td>
										<td>{item.market_category}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					{#if regsho.total_count > 20}
						<p class="more">Showing 20 of {regsho.total_count}</p>
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
	.container {
		max-width: 1200px;
		margin: 0 auto;
		padding: 1.5rem;
	}

	header {
		text-align: center;
		margin-bottom: 2rem;
	}

	h1 {
		font-size: 2rem;
		font-weight: 600;
		margin: 0;
		color: #f0f6fc;
	}

	.subtitle {
		color: #8b949e;
		margin: 0.5rem 0 0;
	}

	.error {
		text-align: center;
		padding: 2rem;
		background: #3d1f1f;
		border: 1px solid #f85149;
		border-radius: 8px;
	}

	.error button {
		margin-top: 1rem;
		padding: 0.5rem 1.5rem;
		background: #238636;
		border: none;
		border-radius: 6px;
		color: white;
		cursor: pointer;
	}

	.error button:hover {
		background: #2ea043;
	}

	.dashboard {
		display: grid;
		gap: 1.5rem;
	}

	.card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 8px;
		padding: 1.5rem;
	}

	h2 {
		font-size: 1.25rem;
		font-weight: 600;
		margin: 0 0 1rem;
		color: #f0f6fc;
	}

	/* Portfolio styles */
	.portfolio-summary {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 1rem;
		margin-bottom: 1.5rem;
	}

	.summary-item {
		background: #21262d;
		padding: 1rem;
		border-radius: 6px;
	}

	.summary-item .label {
		display: block;
		font-size: 0.875rem;
		color: #8b949e;
		margin-bottom: 0.25rem;
	}

	.summary-item .value {
		display: block;
		font-size: 1.5rem;
		font-weight: 600;
		color: #f0f6fc;
	}

	.summary-item .sub-value {
		display: block;
		font-size: 0.875rem;
		color: #8b949e;
	}

	.summary-item .percent {
		display: block;
		font-size: 1rem;
	}

	.summary-item.positive .value,
	.summary-item.positive .percent {
		color: #3fb950;
	}

	.summary-item.negative .value,
	.summary-item.negative .percent {
		color: #f85149;
	}

	.table-container {
		overflow-x: auto;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.875rem;
	}

	th,
	td {
		padding: 0.75rem;
		text-align: left;
		border-bottom: 1px solid #21262d;
	}

	th {
		color: #8b949e;
		font-weight: 500;
	}

	.right {
		text-align: right;
	}

	.ticker {
		font-weight: 600;
		color: #58a6ff;
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

	.percent {
		font-size: 0.75rem;
		margin-left: 0.25rem;
	}

	.market-indicator {
		font-size: 0.625rem;
		padding: 0.125rem 0.375rem;
		border-radius: 3px;
		margin-left: 0.5rem;
		font-weight: 600;
	}

	.market-indicator.ah {
		background: #1f6feb;
		color: white;
	}

	.market-indicator.pm {
		background: #8957e5;
		color: white;
	}

	.updated {
		font-size: 0.75rem;
		color: #8b949e;
		margin: 1rem 0 0;
		text-align: right;
	}

	/* RegSHO styles */
	.alert {
		padding: 0.75rem 1rem;
		border-radius: 6px;
		margin-bottom: 1rem;
	}

	.alert-info {
		background: #0c2d6b;
		border: 1px solid #1f6feb;
		color: #79c0ff;
	}

	.stats {
		font-size: 0.875rem;
		color: #8b949e;
		margin-bottom: 1rem;
	}

	.regsho-table-container {
		max-height: 400px;
		overflow-y: auto;
	}

	.regsho-table .holding {
		background: #1f3d1f;
	}

	.regsho-table .holding .ticker {
		color: #3fb950;
	}

	.regsho-table .name {
		max-width: 300px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.more {
		font-size: 0.75rem;
		color: #8b949e;
		margin: 0.75rem 0 0;
		text-align: center;
	}

	@media (max-width: 768px) {
		.container {
			padding: 1rem;
		}

		.portfolio-summary {
			grid-template-columns: 1fr;
		}

		.summary-item .value {
			font-size: 1.25rem;
		}

		table {
			font-size: 0.8rem;
		}

		th,
		td {
			padding: 0.5rem;
		}
	}
</style>
