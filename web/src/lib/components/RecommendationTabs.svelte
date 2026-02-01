<script lang="ts">
	import type { RecommendationsResponse, Recommendation } from '$lib/types';
	import Icon from './Icons.svelte';

	interface Props {
		recommendations: RecommendationsResponse;
		formatCurrency: (value: number, currency?: 'USD' | 'KRW') => string;
		formatDate: (dateStr: string | null) => string;
		initialTab?: 'day_trade' | 'swing' | 'longterm';
	}

	let { recommendations, formatCurrency, formatDate, initialTab }: Props = $props();

	type TabType = 'day_trade' | 'swing' | 'longterm';

	const tabs: { key: TabType; label: string; icon: string }[] = [
		{ key: 'day_trade', label: '단타', icon: 'zap' },
		{ key: 'swing', label: '스윙', icon: 'chart' },
		{ key: 'longterm', label: '장기', icon: 'target' }
	];

	let activeTab = $state<TabType>(initialTab ?? 'day_trade');
	let selectedRec = $state<Recommendation | null>(null);

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

	function openModal(rec: Recommendation) {
		selectedRec = rec;
	}

	function closeModal() {
		selectedRec = null;
	}

	function handleBackdropClick(e: MouseEvent) {
		if (e.target === e.currentTarget) {
			closeModal();
		}
	}

	function getRsiStatus(rsi: number): { label: string; color: string } {
		if (rsi < 30) return { label: '과매도', color: '#3fb950' };
		if (rsi > 70) return { label: '과매수', color: '#f85149' };
		return { label: '중립', color: '#8b949e' };
	}
</script>

<section class="card recommendations-card">
	<h2><Icon name="trending-up" size={20} /> 추천 종목</h2>

	{#if hasAnyRecommendations()}
		<div class="tabs">
			{#each tabs as tab}
				<button
					class="tab"
					class:active={activeTab === tab.key}
					onclick={() => (activeTab = tab.key)}
				>
					<span class="tab-icon"><Icon name={tab.icon} size={16} /></span>
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
						<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
						<div class="rec-item" onclick={() => openModal(rec)}>
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

<!-- 상세 모달 -->
{#if selectedRec}
	<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
	<div class="modal-backdrop" onclick={handleBackdropClick}>
		<div class="modal">
			<button class="close-btn" onclick={closeModal}>
				<Icon name="x" size={20} />
			</button>

			<div class="modal-header">
				<h2>{selectedRec.symbol}</h2>
				{#if selectedRec.name}
					<p class="company">{selectedRec.name}</p>
				{/if}
			</div>

			<div class="section">
				<h3><Icon name="chart" size={16} /> 기술적 지표</h3>
				<div class="indicators">
					{#if selectedRec.rsi}
						{@const rsiStatus = getRsiStatus(selectedRec.rsi)}
						<div class="indicator">
							<span class="ind-label">RSI</span>
							<span class="ind-value">{selectedRec.rsi.toFixed(1)}</span>
							<span class="ind-status" style="color: {rsiStatus.color}">{rsiStatus.label}</span>
						</div>
					{/if}
					{#if selectedRec.volume_surge}
						<div class="indicator">
							<span class="ind-label">거래량</span>
							<span class="ind-value">{selectedRec.volume_surge.toFixed(1)}x</span>
							<span class="ind-status" style="color: {selectedRec.volume_surge > 2 ? '#3fb950' : '#8b949e'}">
								{selectedRec.volume_surge > 2 ? '급증' : '보통'}
							</span>
						</div>
					{/if}
					{#if selectedRec.gap_pct !== undefined}
						<div class="indicator">
							<span class="ind-label">갭</span>
							<span class="ind-value" class:positive={selectedRec.gap_pct > 0} class:negative={selectedRec.gap_pct < 0}>
								{selectedRec.gap_pct > 0 ? '+' : ''}{selectedRec.gap_pct.toFixed(1)}%
							</span>
						</div>
					{/if}
					<div class="indicator">
						<span class="ind-label">점수</span>
						<span class="ind-value">{selectedRec.score}</span>
					</div>
				</div>
			</div>

			<div class="section">
				<h3><Icon name="dollar" size={16} /> 가격 분석</h3>
				<div class="price-grid">
					<div class="price-box current">
						<span class="box-label">현재가</span>
						<span class="box-value">{formatCurrency(selectedRec.current_price)}</span>
					</div>
					<div class="price-box entry">
						<span class="box-label">진입가</span>
						<span class="box-value">{formatCurrency(selectedRec.entry)}</span>
					</div>
					<div class="price-box stop">
						<span class="box-label">손절가</span>
						<span class="box-value">{formatCurrency(selectedRec.stop_loss)}</span>
					</div>
					<div class="price-box target">
						<span class="box-label">목표가</span>
						<span class="box-value">{formatCurrency(selectedRec.target)}</span>
					</div>
				</div>
			</div>

			{#if selectedRec.reasons && selectedRec.reasons.length > 0}
				<div class="section">
					<h3><Icon name="info" size={16} /> 추천 이유</h3>
					<div class="reasons-list">
						{#each selectedRec.reasons as reason}
							<span class="reason-tag">{reason}</span>
						{/each}
					</div>
				</div>
			{/if}

			<div class="modal-footer">
				<a href="/stock/{selectedRec.symbol}" class="btn-chart">
					<Icon name="chart" size={16} /> 차트 보기
				</a>
			</div>
		</div>
	</div>
{/if}

<style>
	.card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 12px;
		padding: 1rem;
	}

	h2 {
		display: flex;
		align-items: center;
		gap: 0.5rem;
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
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.rec-item:hover {
		background: #30363d;
		transform: translateX(2px);
	}

	.rec-item:active {
		transform: translateX(1px);
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

	/* Modal styles */
	.modal-backdrop {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.8);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: 1rem;
	}

	.modal {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 16px;
		width: 100%;
		max-width: 400px;
		max-height: 85vh;
		overflow-y: auto;
		position: relative;
	}

	.close-btn {
		position: absolute;
		top: 0.75rem;
		right: 0.75rem;
		background: none;
		border: none;
		color: #8b949e;
		cursor: pointer;
		padding: 0.25rem;
		border-radius: 4px;
		transition: all 0.15s;
	}

	.close-btn:hover {
		background: #21262d;
		color: #f0f6fc;
	}

	.modal-header {
		padding: 1.25rem 1.25rem 0;
	}

	.modal-header h2 {
		margin: 0;
		font-size: 1.5rem;
		color: #58a6ff;
	}

	.company {
		margin: 0.25rem 0 0;
		color: #8b949e;
		font-size: 0.85rem;
	}

	.section {
		padding: 1rem 1.25rem;
		border-top: 1px solid #21262d;
	}

	.section h3 {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		margin: 0 0 0.75rem;
		font-size: 0.9rem;
		color: #f0f6fc;
		font-weight: 600;
	}

	.indicators {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 0.5rem;
	}

	.indicator {
		background: #0d1117;
		padding: 0.6rem;
		border-radius: 8px;
		text-align: center;
	}

	.ind-label {
		display: block;
		font-size: 0.65rem;
		color: #8b949e;
		margin-bottom: 0.2rem;
	}

	.ind-value {
		display: block;
		font-size: 1rem;
		font-weight: 600;
		color: #f0f6fc;
	}

	.ind-value.positive {
		color: #3fb950;
	}

	.ind-value.negative {
		color: #f85149;
	}

	.ind-status {
		display: block;
		font-size: 0.65rem;
		margin-top: 0.1rem;
	}

	.price-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 0.5rem;
	}

	.price-box {
		padding: 0.6rem;
		border-radius: 8px;
		text-align: center;
		background: #0d1117;
	}

	.box-label {
		display: block;
		font-size: 0.65rem;
		color: #8b949e;
		margin-bottom: 0.2rem;
	}

	.box-value {
		font-size: 0.95rem;
		font-weight: 600;
		color: #f0f6fc;
	}

	.price-box.entry {
		border: 1px solid #58a6ff;
	}

	.price-box.entry .box-value {
		color: #58a6ff;
	}

	.price-box.stop {
		border: 1px solid #f85149;
	}

	.price-box.stop .box-value {
		color: #f85149;
	}

	.price-box.target {
		border: 1px solid #3fb950;
	}

	.price-box.target .box-value {
		color: #3fb950;
	}

	.reasons-list {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}

	.reason-tag {
		font-size: 0.75rem;
		background: #30363d;
		padding: 0.3rem 0.6rem;
		border-radius: 6px;
		color: #c9d1d9;
	}

	.modal-footer {
		padding: 1rem 1.25rem 1.25rem;
		border-top: 1px solid #21262d;
	}

	.btn-chart {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.4rem;
		width: 100%;
		padding: 0.75rem;
		background: #238636;
		color: white;
		border: none;
		border-radius: 8px;
		font-size: 0.9rem;
		font-weight: 600;
		text-decoration: none;
		transition: all 0.15s;
	}

	.btn-chart:hover {
		background: #2ea043;
	}
</style>
