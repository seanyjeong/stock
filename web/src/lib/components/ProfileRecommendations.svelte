<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { browser } from '$app/environment';
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
		signal_tags?: string[];
	}

	interface Props {
		profileType: string;
		recommendations: ProfileRecommendation[];
		createdAt?: string | null;
		formatCurrency: (value: number, currency?: 'USD' | 'KRW') => string;
		formatDate: (dateStr: string | null) => string;
		showHeader?: boolean;
	}

	let { profileType, recommendations, createdAt, formatCurrency, formatDate, showHeader = true }: Props = $props();

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	let selectedRecommendation = $state<ProfileRecommendation | null>(null);
	let watchlistTickers = $state<string[]>([]);
	let toastMessage = $state('');

	// 실시간 가격
	interface RealtimePrice {
		current: number;
		change_pct: number;
		source?: string; // 'regular' | 'premarket' | 'afterhours'
	}
	let realtimePrices = $state<Record<string, RealtimePrice>>({});
	let realtimeInterval: ReturnType<typeof setInterval> | null = null;

	onMount(async () => {
		await loadWatchlistTickers();
		await fetchRealtimePrices();
		// 30초마다 갱신
		realtimeInterval = setInterval(fetchRealtimePrices, 30000);
	});

	onDestroy(() => {
		if (realtimeInterval) clearInterval(realtimeInterval);
	});

	async function fetchRealtimePrices() {
		if (!recommendations?.length) return;
		const tickers = recommendations.map(r => r.ticker).join(',');
		try {
			const response = await fetch(`${API_BASE}/realtime/hybrid?tickers=${tickers}`);
			if (response.ok) {
				const data = await response.json();
				realtimePrices = data.prices || {};
			}
		} catch {
			// ignore
		}
	}

	// 종가 대비 갭 계산
	function getGapInfo(rec: ProfileRecommendation) {
		const rt = realtimePrices[rec.ticker];
		if (!rt || !rt.current || rt.source === 'regular') return null;

		const closePrice = rec.current_price; // 스캐너 실행 시점 가격 = 종가
		const gap = ((rt.current - closePrice) / closePrice) * 100;
		return {
			price: rt.current,
			gap: gap,
			source: rt.source // 'premarket' or 'afterhours'
		};
	}

	// 실시간 기준 탈락 체크
	function isDisqualified(rec: ProfileRecommendation): { disqualified: boolean; reason: string } {
		const rt = realtimePrices[rec.ticker];
		if (!rt || !rt.current) return { disqualified: false, reason: '' };

		const currentPrice = rt.current;
		const stopLoss = rec.stop_loss;
		const entryPrice = rec.recommended_entry;

		// 1. 손절라인 이탈 → 무조건 탈락
		if (currentPrice <= stopLoss) {
			return { disqualified: true, reason: '손절라인 이탈' };
		}

		// 2. 매수가 아래로 내려갔고 + 손절라인에 가까움 (손절가 대비 3% 이내) → 탈락
		if (currentPrice < entryPrice) {
			const stopDistance = ((currentPrice - stopLoss) / stopLoss) * 100;
			if (stopDistance <= 3) {
				return { disqualified: true, reason: `손절라인 임박 (${stopDistance.toFixed(1)}%)` };
			}
		}

		// 3. 매수가 대비 너무 높아짐 (갭업) → 탈락
		// 단타: +10%, 스윙/장기: +15%
		const entryGap = ((currentPrice - entryPrice) / entryPrice) * 100;
		const maxGap = profileType === 'aggressive' ? 10 : 15;
		if (entryGap > maxGap) {
			return { disqualified: true, reason: `매수가 이탈 (+${entryGap.toFixed(1)}%)` };
		}

		return { disqualified: false, reason: '' };
	}

	// 필터링된 추천 목록
	let filteredRecommendations = $derived(
		recommendations.filter(rec => {
			const { disqualified } = isDisqualified(rec);
			return !disqualified;
		})
	);

	// 탈락된 종목 수
	let disqualifiedCount = $derived(recommendations.length - filteredRecommendations.length);

	async function loadWatchlistTickers() {
		const token = browser ? localStorage.getItem('access_token') : null;
		if (!token) return;

		try {
			const response = await fetch(`${API_BASE}/api/watchlist/`, {
				headers: { 'Authorization': `Bearer ${token}` }
			});
			if (response.ok) {
				const data = await response.json();
				watchlistTickers = data.watchlist?.map((item: { ticker: string }) => item.ticker) || [];
			}
		} catch {
			// 로그인 안 된 경우 무시
		}
	}

	async function addToWatchlist(ticker: string) {
		const token = browser ? localStorage.getItem('access_token') : null;
		if (!token) {
			showToast('로그인이 필요합니다');
			return;
		}

		try {
			const response = await fetch(`${API_BASE}/api/watchlist/`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'Authorization': `Bearer ${token}`
				},
				body: JSON.stringify({ ticker })
			});

			if (response.ok) {
				watchlistTickers = [...watchlistTickers, ticker];
				showToast(`${ticker} 관심종목에 추가됨`);
			} else if (response.status === 401) {
				localStorage.removeItem('access_token');
				localStorage.removeItem('user');
				showToast('세션 만료. 다시 로그인해주세요');
			} else {
				const data = await response.json();
				showToast(data.detail || '추가 실패');
			}
		} catch {
			showToast('네트워크 오류');
		}
	}

	function showToast(message: string) {
		toastMessage = message;
		setTimeout(() => { toastMessage = ''; }, 2000);
	}

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

<section class={showHeader ? 'card' : ''}>
	{#if showHeader}
		<div class="header">
			<h2><Icon name="trending-up" size={20} /> 맞춤 추천</h2>
			<span class="profile-badge" style="--badge-color: {getProfileInfo().color}">
				{getProfileInfo().emoji} {getProfileInfo().label}
			</span>
		</div>
	{/if}

	{#if recommendations && recommendations.length > 0}
		{#if showHeader}
			<p class="profile-desc">{getProfileInfo().desc} 추천 종목 <span class="update-time">장 마감 후 업데이트</span></p>
		{/if}

		{#if disqualifiedCount > 0}
			<div class="disqualified-notice">
				⚠️ {disqualifiedCount}종목 실시간 탈락 (손절/매수가 이탈)
			</div>
		{/if}

		<div class="rec-list">
			{#each filteredRecommendations as rec}
				{@const gapInfo = getGapInfo(rec)}
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

					{#if rec.signal_tags && rec.signal_tags.length > 0}
						<div class="signal-tags">
							{#each rec.signal_tags as tag}
								<span class="signal-tag">{tag}</span>
							{/each}
						</div>
					{/if}

					{#if rec.recommendation_reason}
						<p class="reason">{rec.recommendation_reason}</p>
					{/if}

					<div class="rec-prices">
						<div class="price-item">
							<span class="price-label">종가</span>
							<span class="price-value">{formatCurrency(rec.current_price)}</span>
						</div>
						{#if gapInfo}
							<div class="price-item gap" class:gap-up={gapInfo.gap > 0} class:gap-down={gapInfo.gap < 0}>
								<span class="price-label">{gapInfo.source === 'premarket' ? 'PM' : 'AH'}</span>
								<span class="price-value">
									{formatCurrency(gapInfo.price)}
									<span class="gap-pct">{gapInfo.gap > 0 ? '+' : ''}{gapInfo.gap.toFixed(1)}%</span>
								</span>
							</div>
						{/if}
						<div class="price-item entry">
							<span class="price-label">매수가</span>
							<span class="price-value">{formatCurrency(rec.recommended_entry)}</span>
						</div>
						<div class="price-item target">
							<span class="price-label">목표</span>
							<span class="price-value">{formatCurrency(rec.target)}</span>
						</div>
					</div>
					{#if gapInfo && gapInfo.gap > 10}
						<div class="gap-warning">⚠️ 갭업 주의: 매수가 조정 필요</div>
					{:else if gapInfo && gapInfo.gap < -10}
						<div class="gap-warning down">📉 갭다운: 추가 하락 주의</div>
					{/if}

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
	onAddToWatchlist={addToWatchlist}
	{watchlistTickers}
/>

{#if toastMessage}
	<div class="toast">{toastMessage}</div>
{/if}

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

	.update-time {
		font-size: 0.65rem;
		color: #6e7681;
		margin-left: 0.5rem;
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

	.signal-tags {
		display: flex;
		gap: 0.3rem;
		flex-wrap: wrap;
		margin-bottom: 0.5rem;
	}

	.signal-tag {
		font-size: 0.65rem;
		padding: 0.2rem 0.5rem;
		border-radius: 6px;
		background: rgba(63, 185, 80, 0.15);
		color: #3fb950;
		font-weight: 600;
	}

	.rec-prices {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(60px, 1fr));
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

	/* 장외가격 (PM/AH) */
	.price-item.gap {
		border: 1px solid #8b949e;
	}

	.price-item.gap-up {
		border-color: #f85149;
		background: rgba(248, 81, 73, 0.1);
	}

	.price-item.gap-up .price-value {
		color: #f85149;
	}

	.price-item.gap-down {
		border-color: #3fb950;
		background: rgba(63, 185, 80, 0.1);
	}

	.price-item.gap-down .price-value {
		color: #3fb950;
	}

	.gap-pct {
		display: block;
		font-size: 0.65rem;
		font-weight: 700;
	}

	.gap-warning {
		font-size: 0.7rem;
		padding: 0.4rem 0.6rem;
		background: rgba(248, 81, 73, 0.15);
		border: 1px solid #f85149;
		border-radius: 6px;
		color: #f85149;
		margin-bottom: 0.5rem;
	}

	.gap-warning.down {
		background: rgba(63, 185, 80, 0.15);
		border-color: #3fb950;
		color: #3fb950;
	}

	/* 탈락 알림 */
	.disqualified-notice {
		font-size: 0.75rem;
		padding: 0.5rem 0.75rem;
		background: rgba(248, 81, 73, 0.1);
		border: 1px solid rgba(248, 81, 73, 0.3);
		border-radius: 8px;
		color: #f85149;
		margin-bottom: 0.75rem;
		text-align: center;
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

	.toast {
		position: fixed;
		bottom: 5rem;
		left: 50%;
		transform: translateX(-50%);
		background: #238636;
		color: white;
		padding: 0.75rem 1.25rem;
		border-radius: 8px;
		font-size: 0.85rem;
		font-weight: 500;
		z-index: 1100;
		animation: fadeInOut 2s ease;
	}

	@keyframes fadeInOut {
		0% { opacity: 0; transform: translateX(-50%) translateY(10px); }
		15% { opacity: 1; transform: translateX(-50%) translateY(0); }
		85% { opacity: 1; transform: translateX(-50%) translateY(0); }
		100% { opacity: 0; transform: translateX(-50%) translateY(-10px); }
	}
</style>
