<script lang="ts">
	import Icon from './Icons.svelte';
	import RecommendationModal from './RecommendationModal.svelte';

	interface SplitEntry {
		price: number;
		pct: number;
		label: string;
	}

	interface ProfileRecommendation {
		ticker: string;
		company_name?: string;
		current_price: number;
		score: number;
		recommended_entry: number;
		stop_loss: number;
		target: number;
		rsi?: number;
		macd_cross?: string;
		news_score?: number;
		sector?: string;
		// 새 필드
		recommendation_reason?: string;
		rating?: string;
		rr_ratio?: number;
		split_entries?: SplitEntry[];
	}

	interface Props {
		profileType: string;
		recommendations: ProfileRecommendation[];
		createdAt?: string | null;
		formatCurrency: (value: number, currency?: 'USD' | 'KRW') => string;
		formatDate: (dateStr: string | null) => string;
	}

	let { profileType, recommendations, createdAt, formatCurrency, formatDate }: Props = $props();

	let selectedRecommendation = $state<ProfileRecommendation | null>(null);

	function openModal(rec: ProfileRecommendation) {
		selectedRecommendation = rec;
	}

	function closeModal() {
		selectedRecommendation = null;
	}

	const profileInfo = {
		aggressive: { emoji: '🔥', label: '공격형', color: '#f85149', desc: '단타 위주' },
		balanced: { emoji: '⚖️', label: '균형형', color: '#a371f7', desc: '스윙 위주' },
		conservative: { emoji: '🛡️', label: '안정형', color: '#58a6ff', desc: '장기 위주' }
	};

	function getProfileInfo() {
		return profileInfo[profileType as keyof typeof profileInfo] || profileInfo.balanced;
	}
</script>

<section class="card">
	<div class="header">
		<h2><Icon name="trending-up" size={20} /> 맞춤 추천</h2>
		<span class="profile-badge" style="--badge-color: {getProfileInfo().color}">
			{getProfileInfo().emoji} {getProfileInfo().label}
		</span>
	</div>

	{#if recommendations && recommendations.length > 0}
		<p class="profile-desc">{getProfileInfo().desc} 추천 종목</p>

		<div class="rec-list">
			{#each recommendations as rec}
				<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
				<div class="rec-item" onclick={() => openModal(rec)}>
					<div class="rec-header">
						<span class="rec-ticker">{rec.ticker}</span>
						{#if rec.rating}
							<span class="rating" class:high={rec.rating === '★★★'} class:mid={rec.rating === '★★'}>
								{rec.rating}
							</span>
						{/if}
						<span class="rec-score">점수 {rec.score}</span>
						{#if rec.rr_ratio}
							<span class="rr-badge">R:R {rec.rr_ratio}</span>
						{/if}
						{#if rec.news_score && rec.news_score > 5}
							<span class="badge news">뉴스 📈</span>
						{/if}
					</div>

					{#if rec.company_name}
						<p class="company-name">{rec.company_name}</p>
					{/if}

					{#if rec.recommendation_reason}
						<p class="reason">{rec.recommendation_reason}</p>
					{/if}

					<div class="rec-prices">
						<div class="price-item">
							<span class="price-label">현재</span>
							<span class="price-value">{formatCurrency(rec.current_price)}</span>
						</div>
						<div class="price-item entry">
							<span class="price-label">매수가</span>
							<span class="price-value">{formatCurrency(rec.recommended_entry)}</span>
						</div>
						<div class="price-item target">
							<span class="price-label">목표</span>
							<span class="price-value">{formatCurrency(rec.target)}</span>
						</div>
					</div>

					{#if rec.split_entries && rec.split_entries.length > 0}
						<div class="split-entries">
							<span class="split-label">💰 분할매수</span>
							<div class="split-list">
								{#each rec.split_entries as entry}
									<span class="split-item">
										{entry.label} {formatCurrency(entry.price)} ({entry.pct}%)
									</span>
								{/each}
							</div>
						</div>
					{/if}

					<div class="rec-meta">
						{#if rec.rsi}
							<span class="meta-item">RSI {rec.rsi.toFixed(1)}</span>
						{/if}
						{#if rec.macd_cross && rec.macd_cross !== 'neutral'}
							<span class="meta-item macd" class:golden={rec.macd_cross === 'golden'}>
								MACD {rec.macd_cross === 'golden' ? '골든' : '데드'}
							</span>
						{/if}
						{#if rec.sector}
							<span class="meta-item sector">{rec.sector}</span>
						{/if}
					</div>
				</div>
			{/each}
		</div>

		{#if createdAt}
			<p class="updated">업데이트: {formatDate(createdAt)}</p>
		{/if}
	{:else}
		<p class="no-data">추천 종목이 없습니다. 스캐너 실행 후 확인하세요.</p>
	{/if}
</section>

<RecommendationModal
	recommendation={selectedRecommendation}
	onClose={closeModal}
	{formatCurrency}
/>

<style>
	.card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 12px;
		padding: 1rem;
	}

	.header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	h2 {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 1.1rem;
		font-weight: 600;
		margin: 0;
		color: #f0f6fc;
	}

	.profile-badge {
		font-size: 0.75rem;
		padding: 0.25rem 0.6rem;
		border-radius: 12px;
		background: color-mix(in srgb, var(--badge-color) 20%, transparent);
		color: var(--badge-color);
		font-weight: 600;
	}

	.profile-desc {
		font-size: 0.8rem;
		color: #8b949e;
		margin: 0 0 0.75rem;
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
		text-decoration: none;
		display: block;
		transition: all 0.15s ease;
		cursor: pointer;
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
		margin-bottom: 0.375rem;
		flex-wrap: wrap;
	}

	.rec-ticker {
		font-weight: 700;
		font-size: 1.1rem;
		color: #58a6ff;
	}

	.rec-score {
		font-size: 0.7rem;
		color: #8b949e;
		background: #0d1117;
		padding: 0.15rem 0.4rem;
		border-radius: 4px;
	}

	.badge {
		font-size: 0.6rem;
		padding: 0.1rem 0.4rem;
		border-radius: 8px;
		font-weight: 600;
	}

	.badge.news {
		background: rgba(63, 185, 80, 0.2);
		color: #3fb950;
	}

	.rating {
		font-size: 0.9rem;
		color: #8b949e;
	}

	.rating.high {
		color: #ffd700;
	}

	.rating.mid {
		color: #f0883e;
	}

	.rr-badge {
		font-size: 0.6rem;
		background: #21262d;
		color: #58a6ff;
		padding: 0.1rem 0.4rem;
		border-radius: 4px;
	}

	.reason {
		font-size: 0.75rem;
		color: #c9d1d9;
		line-height: 1.5;
		margin: 0 0 0.5rem;
		padding: 0.5rem;
		background: #0d1117;
		border-radius: 6px;
		border-left: 2px solid #58a6ff;
	}

	.split-entries {
		background: #0d1117;
		padding: 0.5rem;
		border-radius: 6px;
		margin-bottom: 0.5rem;
	}

	.split-label {
		font-size: 0.7rem;
		color: #a371f7;
		font-weight: 600;
		display: block;
		margin-bottom: 0.3rem;
	}

	.split-list {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}

	.split-item {
		font-size: 0.65rem;
		background: #21262d;
		padding: 0.2rem 0.4rem;
		border-radius: 4px;
		color: #8b949e;
	}

	.company-name {
		font-size: 0.75rem;
		color: #8b949e;
		margin: 0 0 0.5rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.rec-prices {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.4rem;
		margin-bottom: 0.5rem;
	}

	.price-item {
		background: #0d1117;
		padding: 0.4rem;
		border-radius: 6px;
		text-align: center;
	}

	.price-label {
		display: block;
		font-size: 0.6rem;
		color: #8b949e;
		margin-bottom: 0.1rem;
	}

	.price-value {
		font-size: 0.8rem;
		font-weight: 600;
		color: #f0f6fc;
	}

	.price-item.entry {
		border: 1px solid #58a6ff;
	}

	.price-item.entry .price-value {
		color: #58a6ff;
	}

	.price-item.target {
		border: 1px solid #238636;
	}

	.price-item.target .price-value {
		color: #3fb950;
	}

	.rec-meta {
		display: flex;
		gap: 0.4rem;
		flex-wrap: wrap;
	}

	.meta-item {
		font-size: 0.65rem;
		background: #0d1117;
		padding: 0.2rem 0.4rem;
		border-radius: 4px;
		color: #8b949e;
	}

	.meta-item.macd.golden {
		color: #3fb950;
		background: rgba(63, 185, 80, 0.15);
	}

	.meta-item.sector {
		color: #a371f7;
	}

	.updated {
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
