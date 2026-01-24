<script lang="ts">
	import type { RecommendationsResponse, Recommendation } from '$lib/types';

	interface Props {
		recommendations: RecommendationsResponse;
		formatCurrency: (value: number, currency?: 'USD' | 'KRW') => string;
		formatDate: (dateStr: string | null) => string;
	}

	let { recommendations, formatCurrency, formatDate }: Props = $props();

	type TabType = 'day_trade' | 'swing' | 'longterm';

	const tabs: { key: TabType; label: string; icon: string }[] = [
		{ key: 'day_trade', label: '단타', icon: '⚡' },
		{ key: 'swing', label: '스윙', icon: '📊' },
		{ key: 'longterm', label: '장기', icon: '🎯' }
	];

	let activeTab = $state<TabType>('day_trade');

	function getActiveRecommendations(): Recommendation[] {
		const category = recommendations[activeTab];
		return category?.recommendations ?? [];
	}

	function getUpdatedAt(): string | null {
		return recommendations[activeTab]?.created_at ?? null;
	}

	function hasAnyRecommendations(): boolean {
		return tabs.some((tab) => (recommendations[tab.key]?.recommendations?.length ?? 0) > 0);
	}

	function getTabCount(key: TabType): number {
		return recommendations[key]?.recommendations?.length ?? 0;
	}

	function formatNum(val: number | undefined | null, decimals: number = 1): string {
		if (val === undefined || val === null) return '-';
		return val.toFixed(decimals);
	}
</script>

<section class="card recommendations-card">
	<h2>📈 추천 종목</h2>

	{#if hasAnyRecommendations()}
		<div class="tabs">
			{#each tabs as tab}
				<button
					class="tab"
					class:active={activeTab === tab.key}
					onclick={() => (activeTab = tab.key)}
				>
					<span class="tab-icon">{tab.icon}</span>
					<span class="tab-label">{tab.label}</span>
					{#if getTabCount(tab.key) > 0}
						<span class="tab-count">{getTabCount(tab.key)}</span>
					{/if}
				</button>
			{/each}
		</div>

		<div class="tab-content">
			{#if getActiveRecommendations().length > 0}
				<div class="rec-list">
					{#each getActiveRecommendations() as rec}
						<div class="rec-item">
							<div class="rec-header">
								<span class="rec-ticker">{rec.symbol}</span>
								<span class="rec-score">점수: {rec.score}</span>
								{#if rec.on_regsho}
									<span class="badge regsho">RegSHO</span>
								{/if}
							</div>

							{#if activeTab === 'day_trade'}
								<div class="rec-prices">
									<div class="price-item">
										<span class="price-label">진입</span>
										<span class="price-value">{formatCurrency(rec.entry)}</span>
									</div>
									<div class="price-item target">
										<span class="price-label">목표</span>
										<span class="price-value">{formatCurrency(rec.target)}</span>
									</div>
									<div class="price-item stop">
										<span class="price-label">손절</span>
										<span class="price-value">{formatCurrency(rec.stop_loss)}</span>
									</div>
								</div>
								<div class="rec-meta">
									<span class="meta-item">RSI {formatNum(rec.rsi)}</span>
									<span class="meta-item">거래량 {formatNum(rec.volume_surge)}x</span>
									<span class="meta-item gap" class:positive={rec.gap_pct > 0} class:negative={rec.gap_pct < 0}>
										갭 {rec.gap_pct > 0 ? '+' : ''}{formatNum(rec.gap_pct)}%
									</span>
								</div>
							{:else if activeTab === 'swing'}
								<div class="rec-prices">
									<div class="price-item">
										<span class="price-label">진입</span>
										<span class="price-value">{formatCurrency(rec.entry)}</span>
									</div>
									<div class="price-item target">
										<span class="price-label">목표</span>
										<span class="price-value">{formatCurrency(rec.target)}</span>
									</div>
									<div class="price-item stop">
										<span class="price-label">손절</span>
										<span class="price-value">{formatCurrency(rec.stop_loss)}</span>
									</div>
								</div>
								<div class="rec-meta">
									<span class="meta-item">RSI {formatNum(rec.rsi)}</span>
									<span class="meta-item">보유 {rec.hold_days ?? '-'}일</span>
									{#if rec.support}
										<span class="meta-item">지지 {formatCurrency(rec.support)}</span>
									{/if}
								</div>
							{:else if activeTab === 'longterm'}
								<div class="longterm-info">
									{#if rec.name}
										<p class="company-name">{rec.name}</p>
									{/if}
									<div class="longterm-stats">
										<div class="stat">
											<span class="stat-label">현재가</span>
											<span class="stat-value">{formatCurrency(rec.current_price)}</span>
										</div>
										<div class="stat">
											<span class="stat-label">시총</span>
											<span class="stat-value">${formatNum(rec.market_cap_b, 0)}B</span>
										</div>
										<div class="stat">
											<span class="stat-label">P/E</span>
											<span class="stat-value">{formatNum(rec.pe_ratio)}</span>
										</div>
										<div class="stat positive">
											<span class="stat-label">1년 수익률</span>
											<span class="stat-value">+{formatNum(rec.yearly_return_pct)}%</span>
										</div>
									</div>
									{#if rec.hold_months}
										<p class="hold-period">추천 보유: {rec.hold_months}개월</p>
									{/if}
								</div>
							{/if}

							{#if rec.reasons && rec.reasons.length > 0}
								<div class="rec-reasons">
									{#each rec.reasons.slice(0, 3) as reason}
										<span class="reason">{reason}</span>
									{/each}
								</div>
							{/if}
						</div>
					{/each}
				</div>
				{#if getUpdatedAt()}
					<p class="rec-updated">업데이트: {formatDate(getUpdatedAt())}</p>
				{/if}
			{:else}
				<p class="no-data">{tabs.find((t) => t.key === activeTab)?.label} 추천 종목이 없습니다</p>
			{/if}
		</div>
	{:else}
		<p class="no-data">추천 종목이 없습니다</p>
	{/if}
</section>

<style>
	.card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 12px;
		padding: 1rem;
	}

	h2 {
		font-size: 1.1rem;
		font-weight: 600;
		margin: 0 0 0.75rem;
		color: #f0f6fc;
	}

	.tabs {
		display: flex;
		gap: 0.25rem;
		margin-bottom: 0.75rem;
		background: #0d1117;
		padding: 0.25rem;
		border-radius: 8px;
	}

	.tab {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.25rem;
		padding: 0.5rem;
		background: transparent;
		border: none;
		border-radius: 6px;
		color: #8b949e;
		cursor: pointer;
		transition: all 0.2s ease;
		font-size: 0.875rem;
	}

	.tab:hover {
		background: #21262d;
		color: #c9d1d9;
	}

	.tab.active {
		background: #238636;
		color: white;
	}

	.tab-icon {
		font-size: 1rem;
	}

	.tab-label {
		font-weight: 500;
	}

	.tab-count {
		font-size: 0.7rem;
		background: rgba(255,255,255,0.2);
		padding: 0.1rem 0.4rem;
		border-radius: 10px;
	}

	.rec-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.rec-item {
		background: #21262d;
		padding: 0.875rem;
		border-radius: 10px;
		border-left: 4px solid #238636;
	}

	.rec-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.625rem;
		flex-wrap: wrap;
	}

	.rec-ticker {
		font-weight: 700;
		font-size: 1.1rem;
		color: #58a6ff;
	}

	.rec-score {
		font-size: 0.75rem;
		color: #8b949e;
		background: #0d1117;
		padding: 0.2rem 0.5rem;
		border-radius: 4px;
	}

	.badge {
		font-size: 0.65rem;
		padding: 0.15rem 0.5rem;
		border-radius: 10px;
		font-weight: 600;
		text-transform: uppercase;
	}

	.badge.regsho {
		background: #f85149;
		color: white;
	}

	.rec-prices {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.5rem;
		margin-bottom: 0.625rem;
	}

	.price-item {
		background: #0d1117;
		padding: 0.5rem;
		border-radius: 6px;
		text-align: center;
	}

	.price-label {
		display: block;
		font-size: 0.65rem;
		color: #8b949e;
		margin-bottom: 0.125rem;
	}

	.price-value {
		font-size: 0.875rem;
		font-weight: 600;
		color: #f0f6fc;
	}

	.price-item.target {
		border: 1px solid #238636;
	}

	.price-item.target .price-value {
		color: #3fb950;
	}

	.price-item.stop {
		border: 1px solid #f85149;
	}

	.price-item.stop .price-value {
		color: #f85149;
	}

	.rec-meta {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin-bottom: 0.625rem;
	}

	.meta-item {
		font-size: 0.75rem;
		background: #0d1117;
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
		color: #8b949e;
	}

	.meta-item.gap.positive {
		color: #3fb950;
		background: rgba(63, 185, 80, 0.15);
	}

	.meta-item.gap.negative {
		color: #f85149;
		background: rgba(248, 81, 73, 0.15);
	}

	.longterm-info {
		margin-bottom: 0.625rem;
	}

	.company-name {
		font-size: 0.8rem;
		color: #8b949e;
		margin: 0 0 0.5rem;
	}

	.longterm-stats {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 0.5rem;
	}

	.stat {
		background: #0d1117;
		padding: 0.5rem;
		border-radius: 6px;
	}

	.stat-label {
		display: block;
		font-size: 0.65rem;
		color: #8b949e;
	}

	.stat-value {
		font-size: 0.875rem;
		font-weight: 600;
		color: #f0f6fc;
	}

	.stat.positive .stat-value {
		color: #3fb950;
	}

	.hold-period {
		font-size: 0.75rem;
		color: #8b949e;
		margin: 0.5rem 0 0;
		text-align: center;
	}

	.rec-reasons {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem;
	}

	.reason {
		font-size: 0.7rem;
		background: #30363d;
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
		color: #c9d1d9;
	}

	.rec-updated {
		font-size: 0.7rem;
		color: #8b949e;
		margin: 0.75rem 0 0;
		text-align: right;
	}

	.no-data {
		color: #8b949e;
		text-align: center;
		padding: 2rem 1rem;
		font-size: 0.875rem;
	}
</style>
