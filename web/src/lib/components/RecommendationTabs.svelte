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
</script>

<section class="card recommendations-card">
	<h2>Recommendations</h2>

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
								<span class="rec-score">Score: {rec.score}</span>
								{#if rec.on_regsho}
									<span class="badge regsho">RegSHO</span>
								{/if}
							</div>
							<div class="rec-prices">
								<span>Entry: {formatCurrency(rec.entry)}</span>
								<span>Target: {formatCurrency(rec.target)}</span>
								<span>Stop: {formatCurrency(rec.stop_loss)}</span>
							</div>
							<div class="rec-meta">
								<span class="meta-item" title="RSI">RSI: {rec.rsi.toFixed(1)}</span>
								<span class="meta-item" title="Volume Surge">Vol: {rec.volume_surge.toFixed(1)}x</span>
								<span class="meta-item" title="Gap %">Gap: {rec.gap_pct.toFixed(1)}%</span>
							</div>
							{#if rec.reasons.length > 0}
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
					<p class="rec-updated">Updated: {formatDate(getUpdatedAt())}</p>
				{/if}
			{:else}
				<p class="no-data">No {tabs.find((t) => t.key === activeTab)?.label} recommendations available</p>
			{/if}
		</div>
	{:else}
		<p class="no-data">No recommendations available</p>
	{/if}
</section>

<style>
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

	.tabs {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 1rem;
		border-bottom: 1px solid #30363d;
		padding-bottom: 0.5rem;
	}

	.tab {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 1rem;
		background: transparent;
		border: 1px solid transparent;
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
		background: #21262d;
		border-color: #58a6ff;
		color: #f0f6fc;
	}

	.tab-icon {
		font-size: 1rem;
	}

	.tab-label {
		font-weight: 500;
	}

	.tab-count {
		font-size: 0.75rem;
		background: #30363d;
		padding: 0.125rem 0.5rem;
		border-radius: 10px;
		color: #8b949e;
	}

	.tab.active .tab-count {
		background: #1f6feb;
		color: white;
	}

	.tab-content {
		min-height: 200px;
	}

	.rec-list {
		display: grid;
		gap: 0.75rem;
	}

	.rec-item {
		background: #21262d;
		padding: 0.75rem 1rem;
		border-radius: 6px;
		border-left: 3px solid #1f6feb;
	}

	.rec-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.5rem;
	}

	.rec-ticker {
		font-weight: 600;
		font-size: 1rem;
		color: #58a6ff;
	}

	.rec-score {
		font-size: 0.75rem;
		color: #8b949e;
	}

	.badge {
		font-size: 0.625rem;
		padding: 0.125rem 0.5rem;
		border-radius: 10px;
		font-weight: 600;
		text-transform: uppercase;
	}

	.badge.regsho {
		background: #f85149;
		color: white;
	}

	.rec-prices {
		display: flex;
		gap: 1rem;
		font-size: 0.75rem;
		color: #8b949e;
		margin-bottom: 0.5rem;
	}

	.rec-meta {
		display: flex;
		gap: 1rem;
		font-size: 0.75rem;
		color: #6e7681;
		margin-bottom: 0.5rem;
	}

	.meta-item {
		background: #161b22;
		padding: 0.125rem 0.375rem;
		border-radius: 3px;
	}

	.rec-reasons {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.reason {
		font-size: 0.75rem;
		background: #30363d;
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
		color: #c9d1d9;
	}

	.rec-updated {
		font-size: 0.75rem;
		color: #8b949e;
		margin: 0.75rem 0 0;
		text-align: right;
	}

	.no-data {
		color: #8b949e;
		text-align: center;
		padding: 2rem 1rem;
	}

	@media (max-width: 768px) {
		.tabs {
			flex-wrap: wrap;
		}

		.tab {
			flex: 1;
			min-width: 80px;
			justify-content: center;
			padding: 0.5rem 0.75rem;
		}

		.tab-label {
			display: none;
		}

		.rec-prices,
		.rec-meta {
			flex-direction: column;
			gap: 0.25rem;
		}
	}
</style>
