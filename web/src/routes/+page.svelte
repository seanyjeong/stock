<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import type { PageData } from './$types';
	import RecommendationTabs from '$lib/components/RecommendationTabs.svelte';
	import ProfileRecommendations from '$lib/components/ProfileRecommendations.svelte';
	import RegSHOBadge from '$lib/components/RegSHOBadge.svelte';
	import Icon from '$lib/components/Icons.svelte';
	import GlossaryModal from '$lib/components/GlossaryModal.svelte';

	let { data }: { data: PageData } = $props();

	// Portfolio loaded client-side with auth
	interface PortfolioItem {
		id: number;
		ticker: string;
		company_name?: string;
		shares: number;
		avg_cost: number;
		current_price: number;
		regular_price?: number;
		afterhours_price?: number;
		premarket_price?: number;
		value: number;
		gain: number;
		gain_pct: number;
	}
	interface PortfolioData {
		holdings: PortfolioItem[];
		total: {
			value_usd: number;
			value_krw: number;
			cost_usd: number;
			gain_usd: number;
			gain_pct: number;
		};
		exchange_rate: number;
	}

	let portfolio = $state<PortfolioData | null>(null);
	let portfolioLoading = $state(true);
	let portfolioRefreshing = $state(false);
	let portfolioUpdatedAt = $state<Date | null>(null);
	let isLoggedIn = $state(false);
	let isAdmin = $state(false);
	let blogExpanded = $state(browser ? localStorage.getItem('blogExpanded') !== 'false' : true);
	let showGlossaryModal = $state(false);

	// 섹션 접기/펼치기 상태 (localStorage 저장)
	let taxExpanded = $state(browser ? localStorage.getItem('taxExpanded') !== 'false' : true);
	let portfolioExpanded = $state(browser ? localStorage.getItem('portfolioExpanded') !== 'false' : true);
	let squeezeExpanded = $state(browser ? localStorage.getItem('squeezeExpanded') !== 'false' : true);
	let recExpanded = $state(browser ? localStorage.getItem('recExpanded') !== 'false' : true);

	// 공지사항 팝업
	let showAnnouncementPopup = $state(false);
	let currentAnnouncement = $state<{id: number; title: string; content: string; is_important: boolean} | null>(null);

	function checkAnnouncementPopup() {
		if (!announcements?.announcements?.length) return;

		const latestAnn = announcements.announcements[0];
		const dismissedKey = `ann_dismissed_${latestAnn.id}`;
		const dismissedAt = localStorage.getItem(dismissedKey);

		if (dismissedAt) {
			const dismissedTime = parseInt(dismissedAt);
			const now = Date.now();
			// 24시간 이내면 표시 안함
			if (now - dismissedTime < 24 * 60 * 60 * 1000) return;
		}

		currentAnnouncement = latestAnn;
		showAnnouncementPopup = true;
	}

	function dismissAnnouncement(hours: number) {
		if (!currentAnnouncement) return;
		if (hours > 0) {
			localStorage.setItem(`ann_dismissed_${currentAnnouncement.id}`, Date.now().toString());
		}
		showAnnouncementPopup = false;
		currentAnnouncement = null;
	}

	// 접기/펼치기 상태 저장
	$effect(() => {
		if (browser) {
			localStorage.setItem('taxExpanded', String(taxExpanded));
			localStorage.setItem('portfolioExpanded', String(portfolioExpanded));
			localStorage.setItem('squeezeExpanded', String(squeezeExpanded));
			localStorage.setItem('recExpanded', String(recExpanded));
		}
	});

	// 실시간 가격
	let realtimePrices = $state<Record<string, { current: number; change_pct: number; source?: string }>>({});
	let marketStatus = $state<{ status: string; is_regular: boolean; label: string } | null>(null);
	let isRealtime = $state(false);
	let realtimeInterval: ReturnType<typeof setInterval> | null = null;

	// Profile recommendations (client-side with auth)
	interface ProfileRec {
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
	}
	let profileRecs = $state<ProfileRec[]>([]);
	let profileType = $state<string>('balanced');
	let profileRecsUpdated = $state<string | null>(null);

	// 토글용 모든 추천
	interface AllRecs {
		day_trade: ProfileRec[];
		swing: ProfileRec[];
		longterm: ProfileRec[];
	}
	let allRecs = $state<AllRecs | null>(null);
	let selectedRecType = $state<'day_trade' | 'swing' | 'longterm'>('swing');

	$effect(() => {
		if (browser) localStorage.setItem('blogExpanded', String(blogExpanded));
	});
	let regsho = $derived(data.regsho);
	let recommendations = $derived(data.recommendations);
	let blog = $derived(data.blog);
	let announcements = $derived(data.announcements);
	let squeeze = $derived(data.squeeze);
	let error = $derived(data.error);

	// Get squeeze data for a ticker
	function getSqueezeForTicker(ticker: string) {
		if (!squeeze?.squeeze_list) return null;
		return squeeze.squeeze_list.find(s => s.ticker === ticker);
	}

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	onDestroy(() => {
		if (realtimeInterval) {
			clearInterval(realtimeInterval);
		}
	});

	function startRealtimePolling() {
		fetchRealtimePrices();
		realtimeInterval = setInterval(fetchRealtimePrices, 10000);
	}

	async function fetchRealtimePrices() {
		if (!portfolio?.holdings?.length) return;

		const tickers = portfolio.holdings.map(h => h.ticker).join(',');
		try {
			const response = await fetch(`${API_BASE}/realtime/hybrid?tickers=${tickers}`);
			if (response.ok) {
				const data = await response.json();
				realtimePrices = data.prices;
				marketStatus = data.market_status;
				isRealtime = data.is_realtime;

				// holdings 가격 업데이트
				portfolio = {
					...portfolio,
					holdings: portfolio.holdings.map(h => {
						const rt = realtimePrices[h.ticker];
						if (rt && rt.current) {
							const newPrice = rt.current;
							const newValue = h.shares * newPrice;
							const newGain = newValue - (h.shares * h.avg_cost);
							const newGainPct = h.avg_cost > 0 ? (newGain / (h.shares * h.avg_cost)) * 100 : 0;
							return { ...h, current_price: newPrice, value: newValue, gain: newGain, gain_pct: newGainPct };
						}
						return h;
					})
				};

				// total 재계산
				const totalValue = portfolio.holdings.reduce((sum, h) => sum + h.value, 0);
				const totalCost = portfolio.holdings.reduce((sum, h) => sum + (h.shares * h.avg_cost), 0);
				const totalGain = totalValue - totalCost;
				portfolio = {
					...portfolio,
					total: {
						...portfolio.total,
						value_usd: totalValue,
						value_krw: totalValue * portfolio.exchange_rate,
						gain_usd: totalGain,
						gain_pct: totalCost > 0 ? (totalGain / totalCost) * 100 : 0
					}
				};
				portfolioUpdatedAt = new Date();

				// 폴링 간격 조정
				if (realtimeInterval) {
					clearInterval(realtimeInterval);
					const interval = isRealtime ? 10000 : 60000;
					realtimeInterval = setInterval(fetchRealtimePrices, interval);
				}
			}
		} catch (e) {
			console.error('Realtime price fetch failed:', e);
		}
	}

	onMount(async () => {
		const token = localStorage.getItem('access_token');
		const userStr = localStorage.getItem('user');

		if (!token) {
			portfolioLoading = false;
			return;
		}
		isLoggedIn = true;

		// Check admin status
		if (userStr) {
			try {
				const user = JSON.parse(userStr);
				isAdmin = user.is_admin === true;
			} catch {}
		}

		try {
			const response = await fetch(`${API_BASE}/api/portfolio/my`, {
				headers: { 'Authorization': `Bearer ${token}` }
			});
			if (response.ok) {
				portfolio = await response.json();
				portfolioUpdatedAt = new Date();
				// 실시간 가격 폴링 시작
				startRealtimePolling();
			} else if (response.status === 401) {
				localStorage.removeItem('access_token');
				localStorage.removeItem('user');
				isLoggedIn = false;
				isAdmin = false;
			}
		} catch (e) {
			console.error('Failed to load portfolio:', e);
		} finally {
			portfolioLoading = false;
		}

		// Load profile-based recommendations
		try {
			const recResponse = await fetch(`${API_BASE}/api/recommendations`, {
				headers: { 'Authorization': `Bearer ${token}` }
			});
			if (recResponse.ok) {
				const recData = await recResponse.json();
				profileType = recData.profile_type || 'balanced';
				profileRecs = recData.recommendations || [];
				profileRecsUpdated = recData.created_at || null;
				// 토글용 모든 추천 저장
				if (recData.all_recommendations) {
					allRecs = recData.all_recommendations;
					// 사용자 프로필에 맞는 초기 선택
					if (profileType === 'aggressive') selectedRecType = 'day_trade';
					else if (profileType === 'conservative') selectedRecType = 'longterm';
					else selectedRecType = 'swing';
				}
			}
		} catch (e) {
			console.error('Failed to load profile recommendations:', e);
		}

		// 공지사항 팝업 체크
		checkAnnouncementPopup();
	});

	// Tax calculation (22% capital gains tax, 2.5M KRW deduction)
	let taxCalc = $derived.by(() => {
		if (!portfolio || portfolio.total.gain_usd <= 0) return null;
		const gainKrw = portfolio.total.gain_usd * portfolio.exchange_rate;
		const taxableKrw = Math.max(0, gainKrw - 2500000);
		const taxKrw = Math.round(taxableKrw * 0.22);
		const netProfitKrw = gainKrw - taxKrw;
		return { gainKrw, taxableKrw, taxKrw, netProfitKrw };
	});

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

	async function refreshPortfolio() {
		if (portfolioRefreshing) return;
		const token = localStorage.getItem('access_token');
		if (!token) return;

		portfolioRefreshing = true;
		try {
			const response = await fetch(`${API_BASE}/api/portfolio/my`, {
				headers: { 'Authorization': `Bearer ${token}` }
			});
			if (response.ok) {
				portfolio = await response.json();
				portfolioUpdatedAt = new Date();
			}
		} catch (e) {
			console.error('Failed to refresh portfolio:', e);
		} finally {
			portfolioRefreshing = false;
		}
	}

	function formatUpdatedTime(date: Date | null): string {
		if (!date) return '';
		const now = new Date();
		const diff = Math.floor((now.getTime() - date.getTime()) / 1000);
		if (diff < 60) return '방금 전';
		if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
		return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
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
	<title>달러농장</title>
	<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
</svelte:head>

<div class="container">
	<header>
		<div class="header-top">
			<h1><Icon name="chart" size={28} class="header-icon" /> 달러농장</h1>
			<button class="glossary-btn" onclick={() => showGlossaryModal = true}>
				<Icon name="book" size={16} /> 용어사전
			</button>
		</div>
		<p class="tagline">미국 주식 포트폴리오 트래커</p>
	</header>

	{#if error}
		<div class="error">
			<p>데이터를 불러올 수 없습니다</p>
			<button onclick={() => window.location.reload()}>다시 시도</button>
		</div>
	{:else}
		<div class="dashboard">
			<!-- Portfolio Section -->
			{#if portfolioLoading}
				<section class="card portfolio-card">
					<h2><Icon name="wallet" size={20} /> 내 포트폴리오</h2>
					<div class="loading-state">
						<span class="spinner"></span>
						<p>로딩 중...</p>
					</div>
				</section>
			{:else if !isLoggedIn}
				<section class="card portfolio-card login-prompt">
					<h2><Icon name="wallet" size={20} /> 내 포트폴리오</h2>
					<p>포트폴리오를 보려면 로그인하세요</p>
					<a href="/login" class="login-btn">카카오로 로그인</a>
				</section>
			{:else if portfolio && portfolio.holdings}
				<section class="card portfolio-card">
					<div class="portfolio-header">
						<h2><Icon name="wallet" size={20} /> 내 포트폴리오</h2>
						<div class="refresh-area">
							{#if marketStatus}
								<span class="market-tag" class:live={isRealtime}>
									{#if isRealtime}🟢{:else if marketStatus.status === 'premarket'}🟡 PM{:else if marketStatus.status === 'afterhours'}🟡 AH{:else}⚪{/if}
								</span>
							{/if}
							{#if portfolioUpdatedAt}
								<span class="updated-time">{formatUpdatedTime(portfolioUpdatedAt)}</span>
							{/if}
							<button class="refresh-btn" onclick={refreshPortfolio} disabled={portfolioRefreshing}>
								<Icon name="refresh" size={16} />
							</button>
						</div>
					</div>

					<!-- Summary Cards -->
					<div class="summary-grid">
						<div class="summary-card total">
							<span class="summary-label">총 평가금</span>
							<span class="summary-value">{formatCurrency(portfolio.total.value_usd)}</span>
							<span class="summary-sub">{formatCurrency(portfolio.total.value_krw, 'KRW')}</span>
							{#if taxCalc}
								<span class="summary-after-tax">세후 {formatCurrency(portfolio.total.value_krw - taxCalc.taxKrw, 'KRW')}</span>
							{/if}
						</div>
						<div class="summary-card {getGainClass(portfolio.total.gain_usd)}">
							<span class="summary-label">총 수익</span>
							<span class="summary-value">{formatCurrency(portfolio.total.gain_usd)}</span>
							<span class="summary-percent">{formatPercent(portfolio.total.gain_pct)}</span>
							{#if taxCalc}
								<span class="summary-sub">{formatCurrency(taxCalc.gainKrw, 'KRW')}</span>
								<span class="summary-after-tax">세후 {formatCurrency(taxCalc.netProfitKrw, 'KRW')}</span>
							{/if}
						</div>
					</div>

					<!-- Tax Calculation (접기/펼치기) -->
					{#if taxCalc}
						<div class="tax-section">
							<button class="tax-toggle" onclick={() => taxExpanded = !taxExpanded}>
								<span class="tax-header">예상 세금 (익절 시)</span>
								<span class="toggle-icon" class:expanded={taxExpanded}>
									<Icon name="arrow-right" size={14} />
								</span>
							</button>
							{#if taxExpanded}
								<div class="tax-grid">
									<div class="tax-item">
										<span class="tax-label">총 수익</span>
										<span class="tax-value">{formatCurrency(taxCalc.gainKrw, 'KRW')}</span>
									</div>
									<div class="tax-item">
										<span class="tax-label">공제 (250만)</span>
										<span class="tax-value">-{formatCurrency(Math.min(taxCalc.gainKrw, 2500000), 'KRW')}</span>
									</div>
									<div class="tax-item">
										<span class="tax-label">과세 대상</span>
										<span class="tax-value">{formatCurrency(taxCalc.taxableKrw, 'KRW')}</span>
									</div>
									<div class="tax-item highlight">
										<span class="tax-label">세금 (22%)</span>
										<span class="tax-value negative">{formatCurrency(taxCalc.taxKrw, 'KRW')}</span>
									</div>
									<div class="tax-item highlight">
										<span class="tax-label">세후 순수익</span>
										<span class="tax-value positive">{formatCurrency(taxCalc.netProfitKrw, 'KRW')}</span>
									</div>
								</div>
							{/if}
						</div>
					{/if}

					<!-- Stock Cards (Mobile-friendly) -->
					<div class="stock-list">
						{#each portfolio.holdings as item}
							{@const squeezeInfo = getSqueezeForTicker(item.ticker)}
							<div class="stock-card">
								<div class="stock-header">
									<div class="stock-ticker-wrap">
										<div class="ticker-row">
											<a href="/stock/{item.ticker}" class="ticker-link">
												<span class="stock-ticker">{item.ticker}</span>
											</a>
											{#if squeezeInfo}
												<span class="squeeze-score {squeezeInfo.rating.toLowerCase()}" title="스퀴즈 점수">
													{squeezeInfo.combined_score}
												</span>
											{/if}
											{#if regsho}
												<RegSHOBadge ticker={item.ticker} holdingsOnList={regsho.holdings_on_list} />
											{/if}
											{#if item.afterhours_price}
												<span class="market-badge ah">AH</span>
											{:else if item.premarket_price}
												<span class="market-badge pm">PM</span>
											{/if}
										</div>
										{#if squeezeInfo}
											<div class="squeeze-tags">
												{#if squeezeInfo.borrow_rate}
													<span class="sq-tag br" title="대차이자">{squeezeInfo.borrow_rate}%</span>
												{/if}
												{#if squeezeInfo.short_interest}
													<span class="sq-tag si" title="공매도비율">SI {squeezeInfo.short_interest}%</span>
												{/if}
												{#if squeezeInfo.regsho_days > 0}
													<span class="sq-tag reg" title="RegSHO 등재일">+{squeezeInfo.regsho_days}일</span>
												{/if}
											</div>
										{:else if item.company_name}
											<span class="company-name">{item.company_name}</span>
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
										<span class="detail-value current">
											{formatCurrency(item.current_price)}
											{#if realtimePrices[item.ticker]?.source}
												{@const src = realtimePrices[item.ticker].source}
												{#if src === 'regular'}
													<span class="price-tag live">🟢</span>
												{:else if src === 'premarket'}
													<span class="price-tag pm">PM</span>
												{:else if src === 'afterhours'}
													<span class="price-tag ah">AH</span>
												{/if}
											{/if}
										</span>
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
					</div>
				</section>
			{/if}

			<!-- RegSHO Top 5 by Score -->
			{#if squeeze?.squeeze_list?.length > 0}
				{@const top5 = [...squeeze.squeeze_list].sort((a, b) => b.combined_score - a.combined_score).slice(0, 5)}
				<section class="card regsho-card">
					<div class="regsho-title-row">
						<h2><Icon name="fire" size={20} /> RegSHO Top 5</h2>
						<a href="/squeeze" class="see-all-link">전체보기 →</a>
					</div>
					<p class="regsho-desc">숏스퀴즈 점수 상위 종목</p>

					<div class="squeeze-header-row">
						<span class="col-ticker">티커</span>
						<span class="col-metric">공매도</span>
						<span class="col-metric">대차</span>
						<span class="col-metric">커버일</span>
						<span class="col-score">점수</span>
					</div>
					<div class="squeeze-list">
						{#each top5 as item}
							{@const isHolding = regsho?.holdings_on_list?.includes(item.ticker)}
							<a href="/stock/{item.ticker}" class="squeeze-item" class:holding={isHolding}>
								<span class="squeeze-ticker">
									{item.ticker}
									{#if item.zero_borrow}<span class="mini-badge zb">ZB</span>{/if}
									{#if item.dilution_protected}<span class="mini-badge dp">DP</span>{/if}
								</span>
								<span class="squeeze-metric">{item.short_interest ? item.short_interest.toFixed(0) : '-'}</span>
								<span class="squeeze-metric">{item.zero_borrow ? '불가' : (item.borrow_rate ? item.borrow_rate.toFixed(0) : '-')}</span>
								<span class="squeeze-metric">{item.days_to_cover ? item.days_to_cover.toFixed(1) : '-'}</span>
								<span class="squeeze-score-cell {item.rating.toLowerCase()}">{item.combined_score.toFixed(0)}</span>
							</a>
						{/each}
					</div>
				</section>
			{/if}

			<!-- Profile-based Recommendations (logged in users) -->
			{#if isLoggedIn && allRecs}
				<section class="card rec-section">
					<div class="rec-header-row">
						<h2><Icon name="trending-up" size={20} /> 종목 추천</h2>
						<div class="rec-toggle">
							<button
								class="toggle-btn"
								class:active={selectedRecType === 'day_trade'}
								onclick={() => selectedRecType = 'day_trade'}
							>
								🔥 단타
							</button>
							<button
								class="toggle-btn"
								class:active={selectedRecType === 'swing'}
								onclick={() => selectedRecType = 'swing'}
							>
								⚖️ 스윙
							</button>
							<button
								class="toggle-btn"
								class:active={selectedRecType === 'longterm'}
								onclick={() => selectedRecType = 'longterm'}
							>
								🛡️ 장기
							</button>
						</div>
					</div>

					<p class="rec-update-time">
						{#if selectedRecType === 'day_trade'}
							🕐 프리마켓 1시간 전 (17:30 KST)
						{:else if selectedRecType === 'swing'}
							🕐 장 마감 후 (09:00 KST)
						{:else}
							🕐 장 마감 후 (09:05 KST)
						{/if}
						{#if profileRecsUpdated} • 최종: {formatDate(profileRecsUpdated)}{/if}
					</p>

					<ProfileRecommendations
						profileType={selectedRecType === 'day_trade' ? 'aggressive' : selectedRecType === 'longterm' ? 'conservative' : 'balanced'}
						recommendations={allRecs[selectedRecType] || []}
						createdAt={profileRecsUpdated}
						{formatCurrency}
						{formatDate}
						showHeader={false}
					/>

					<p class="investment-disclaimer">⚠️ 투자 판단과 책임은 본인에게 있습니다</p>
				</section>
			{:else if isLoggedIn && profileRecs.length > 0}
				<ProfileRecommendations
					{profileType}
					recommendations={profileRecs}
					createdAt={profileRecsUpdated}
					{formatCurrency}
					{formatDate}
				/>
			{/if}

			<!-- Legacy Recommendations Section -->
			{#if recommendations && !profileRecs.length}
				<RecommendationTabs {recommendations} {formatCurrency} {formatDate} />
			{/if}

			<!-- 공지사항은 팝업으로 표시 -->

			<!-- Disclaimer Section -->
			<section class="card disclaimer-card">
				<h2><Icon name="shield" size={18} /> 안내사항</h2>
				<ul class="disclaimer-list">
					<li>달러농장은 <strong>자동매매 프로그램이 아닙니다</strong>. 포트폴리오 조회 및 정보 제공 서비스입니다.</li>
					<li>추천 종목은 참고용이며, <strong>투자 판단과 책임은 본인</strong>에게 있습니다.</li>
					<li>본 서비스 이용으로 발생한 손실에 대해 어떠한 책임도 지지 않습니다.</li>
				</ul>
			</section>

			<!-- Blog Insights Section (Admin Only) -->
			{#if isAdmin && blog && blog.posts.length > 0}
				<section class="card blog-card">
					<button class="blog-header" onclick={() => blogExpanded = !blogExpanded}>
						<h2><Icon name="book" size={20} /> 블로거 인사이트</h2>
						<span class="blog-toggle" class:expanded={blogExpanded}>
							<Icon name="arrow-right" size={18} />
						</span>
					</button>

					{#if blogExpanded}
						{#if blog.unread_count > 0}
							<p class="blog-stats">새 글 {blog.unread_count}개 | 총 {blog.total_count}개</p>
						{:else}
							<p class="blog-stats">총 {blog.total_count}개</p>
						{/if}

						<div class="blog-list">
							{#each blog.posts.slice(0, 5) as post}
								<div class="blog-item" class:unread={!post.is_read}>
									<div class="blog-content">
										<a href={post.url} target="_blank" rel="noopener noreferrer" class="blog-title">
											{post.title}
										</a>
										<div class="blog-meta">
											{#if post.published_at}
												<span class="blog-date">{formatDate(post.published_at)}</span>
											{/if}
										</div>
										{#if post.tickers.length > 0 || post.keywords.length > 0}
											<div class="blog-tags">
												{#each post.tickers as ticker}
													<span class="tag ticker">${ticker}</span>
												{/each}
												{#each post.keywords.slice(0, 3) as keyword}
													<span class="tag keyword">{keyword}</span>
												{/each}
											</div>
										{/if}
									</div>
									<a href={post.url} target="_blank" rel="noopener noreferrer" class="blog-link-btn">
										<Icon name="external-link" size={14} />
									</a>
								</div>
							{/each}
						</div>
						{#if blog.total_count > 5}
							<p class="show-more">최근 5개만 표시 (총 {blog.total_count}개)</p>
						{/if}
					{/if}
				</section>
			{/if}
		</div>
	{/if}

	<!-- 공지사항 팝업 -->
	{#if showAnnouncementPopup && currentAnnouncement}
		<div class="announcement-overlay" onclick={() => dismissAnnouncement(0)}>
			<div class="announcement-popup" onclick={(e) => e.stopPropagation()}>
				{#if currentAnnouncement.is_important}
					<div class="popup-badge">중요</div>
				{/if}
				<h3 class="popup-title">{currentAnnouncement.title}</h3>
				<p class="popup-content">{currentAnnouncement.content}</p>
				<div class="popup-actions">
					<button class="popup-btn secondary" onclick={() => dismissAnnouncement(24)}>
						24시간 보지 않기
					</button>
					<button class="popup-btn primary" onclick={() => dismissAnnouncement(0)}>
						확인
					</button>
				</div>
			</div>
		</div>
	{/if}

	{#if showGlossaryModal}
		<GlossaryModal onClose={() => showGlossaryModal = false} />
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
	}

	header {
		text-align: center;
		margin-bottom: 1.25rem;
		padding-top: 0.5rem;
	}

	.header-top {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 1rem;
		position: relative;
	}

	h1 {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		font-size: 1.5rem;
		font-weight: 700;
		margin: 0;
		color: #f0f6fc;
	}

	.glossary-btn {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.4rem 0.75rem;
		background: rgba(88, 166, 255, 0.15);
		border: 1px solid #58a6ff;
		border-radius: 8px;
		color: #58a6ff;
		font-size: 0.75rem;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.15s;
		position: absolute;
		right: 0;
	}

	.glossary-btn:hover {
		background: rgba(88, 166, 255, 0.25);
	}

	.tagline {
		font-size: 0.8rem;
		color: #8b949e;
		margin: 0.25rem 0 0;
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

	.loading-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.75rem;
		padding: 2rem;
		color: #8b949e;
	}

	.loading-state .spinner {
		width: 24px;
		height: 24px;
		border: 2px solid #30363d;
		border-top-color: #58a6ff;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.login-prompt {
		text-align: center;
		padding: 1.5rem !important;
	}

	.login-prompt p {
		color: #8b949e;
		margin: 0.75rem 0 1rem;
	}

	.login-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 1.5rem;
		background: #FEE500;
		color: #000;
		text-decoration: none;
		border-radius: 8px;
		font-weight: 600;
		transition: background 0.15s;
	}

	.login-btn:hover {
		background: #F5DC00;
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

	/* Portfolio Header */
	.portfolio-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.75rem;
	}

	.portfolio-header h2 {
		margin: 0;
	}

	.refresh-area {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.updated-time {
		font-size: 0.7rem;
		color: #6e7681;
	}

	.refresh-btn {
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 6px;
		padding: 0.35rem;
		cursor: pointer;
		color: #8b949e;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.15s;
	}

	.refresh-btn:hover:not(:disabled) {
		background: #30363d;
		color: #58a6ff;
		border-color: #58a6ff;
	}

	.refresh-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
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
		flex-direction: column;
		gap: 0.25rem;
		min-width: 0;
	}

	.ticker-row {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		flex-wrap: wrap;
	}

	.ticker-link {
		text-decoration: none;
	}

	.ticker-link:hover .stock-ticker {
		text-decoration: underline;
	}

	.squeeze-tags {
		display: flex;
		gap: 0.25rem;
		flex-wrap: wrap;
	}

	.stock-ticker {
		font-size: 1.1rem;
		font-weight: 700;
		color: #58a6ff;
	}

	.company-name {
		font-size: 0.7rem;
		color: #8b949e;
		max-width: 150px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.sq-tag {
		font-size: 0.6rem;
		padding: 0.1rem 0.3rem;
		border-radius: 3px;
		font-weight: 600;
	}

	.sq-tag.br {
		background: rgba(248, 81, 73, 0.2);
		color: #f85149;
	}

	.sq-tag.si {
		background: rgba(136, 87, 229, 0.2);
		color: #a371f7;
	}

	.sq-tag.reg {
		background: rgba(240, 136, 62, 0.2);
		color: #f0883e;
	}

	.squeeze-score {
		font-size: 0.7rem;
		padding: 0.15rem 0.4rem;
		border-radius: 4px;
		font-weight: 700;
	}

	.squeeze-score.squeeze {
		background: rgba(168, 85, 247, 0.3);
		color: #a855f7;
	}

	.squeeze-score.hot {
		background: rgba(248, 81, 73, 0.3);
		color: #ff6b6b;
	}

	.squeeze-score.watch {
		background: rgba(240, 136, 62, 0.3);
		color: #f0883e;
	}

	.squeeze-score.cold {
		background: rgba(139, 148, 158, 0.2);
		color: #8b949e;
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

	.regsho-desc {
		font-size: 0.75rem;
		color: #58a6ff;
		margin: 0 0 0.5rem;
		padding: 0.5rem;
		background: rgba(88, 166, 255, 0.1);
		border-radius: 6px;
	}

	.regsho-stats {
		font-size: 0.75rem;
		color: #8b949e;
		margin: 0 0 0.5rem;
	}


	.show-more {
		font-size: 0.7rem;
		color: #8b949e;
		text-align: center;
		margin: 0.75rem 0 0;
	}

	.show-more-btn {
		display: block;
		width: 100%;
		padding: 0.5rem;
		margin-top: 0.75rem;
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 6px;
		font-size: 0.75rem;
		color: #58a6ff;
		cursor: pointer;
		text-align: center;
	}

	.show-more-btn:hover {
		background: #30363d;
	}

	/* Squeeze Top 5 Styles */
	.regsho-title-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.regsho-title-row h2 {
		margin: 0;
	}

	.see-all-link {
		font-size: 0.75rem;
		color: #58a6ff;
		text-decoration: none;
	}

	.see-all-link:hover {
		text-decoration: underline;
	}

	.squeeze-header-row {
		display: flex;
		align-items: center;
		padding: 0.5rem 0.75rem;
		font-size: 0.7rem;
		color: #8b949e;
		border-bottom: 1px solid #30363d;
		margin-bottom: 0.25rem;
	}

	.squeeze-header-row .col-ticker {
		flex: 1;
		font-weight: 600;
	}

	.squeeze-header-row .col-metric {
		width: 45px;
		text-align: center;
		font-weight: 600;
	}

	.squeeze-header-row .col-score {
		width: 45px;
		text-align: center;
		font-weight: 600;
	}

	.squeeze-list {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.squeeze-item {
		display: flex;
		align-items: center;
		background: #21262d;
		padding: 0.625rem 0.75rem;
		border-radius: 6px;
		font-size: 0.8rem;
		text-decoration: none;
		color: inherit;
		transition: background 0.15s;
	}

	.squeeze-item:hover {
		background: #30363d;
	}

	.squeeze-item.holding {
		background: rgba(63, 185, 80, 0.15);
		border: 1px solid #238636;
	}

	.squeeze-ticker {
		flex: 1;
		font-weight: 600;
		color: #58a6ff;
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.squeeze-item.holding .squeeze-ticker {
		color: #3fb950;
	}

	.mini-badge {
		font-size: 0.55rem;
		padding: 0.1rem 0.25rem;
		border-radius: 3px;
		font-weight: 600;
	}

	.mini-badge.zb {
		background: rgba(248, 81, 73, 0.3);
		color: #f85149;
	}

	.mini-badge.dp {
		background: rgba(63, 185, 80, 0.3);
		color: #3fb950;
	}

	.squeeze-metric {
		width: 45px;
		text-align: center;
		color: #8b949e;
		font-size: 0.75rem;
	}

	.squeeze-score-cell {
		width: 45px;
		text-align: center;
		font-weight: 700;
		font-size: 0.8rem;
		padding: 0.2rem 0.4rem;
		border-radius: 4px;
	}

	.squeeze-score-cell.squeeze {
		background: rgba(168, 85, 247, 0.3);
		color: #a855f7;
	}

	.squeeze-score-cell.hot {
		background: rgba(248, 81, 73, 0.3);
		color: #ff6b6b;
	}

	.squeeze-score-cell.watch {
		background: rgba(240, 136, 62, 0.3);
		color: #f0883e;
	}

	.squeeze-score-cell.cold {
		background: rgba(139, 148, 158, 0.2);
		color: #8b949e;
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

	/* Blog Section */
	.blog-stats {
		font-size: 0.75rem;
		color: #8b949e;
		margin: 0 0 0.75rem;
	}

	.blog-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.blog-item {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.75rem;
		background: #21262d;
		padding: 0.75rem;
		border-radius: 8px;
	}

	.blog-item.unread {
		border-left: 3px solid #58a6ff;
	}

	.blog-content {
		flex: 1;
		min-width: 0;
	}

	.blog-title {
		display: block;
		font-size: 0.85rem;
		font-weight: 500;
		color: #f0f6fc;
		text-decoration: none;
		margin-bottom: 0.375rem;
		overflow: hidden;
		text-overflow: ellipsis;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
	}

	.blog-title:hover {
		color: #58a6ff;
	}

	.blog-meta {
		margin-bottom: 0.375rem;
	}

	.blog-date {
		font-size: 0.7rem;
		color: #8b949e;
	}

	.blog-tags {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem;
	}

	.tag {
		font-size: 0.65rem;
		padding: 0.125rem 0.375rem;
		border-radius: 4px;
		font-weight: 500;
	}

	.tag.ticker {
		background: rgba(88, 166, 255, 0.2);
		color: #58a6ff;
	}

	.tag.keyword {
		background: rgba(139, 148, 158, 0.2);
		color: #8b949e;
	}

	.blog-link-btn {
		flex-shrink: 0;
		padding: 0.375rem 0.625rem;
		background: #30363d;
		border-radius: 6px;
		font-size: 0.7rem;
		color: #8b949e;
		text-decoration: none;
		font-weight: 500;
	}

	.blog-link-btn:hover {
		background: #3d444d;
		color: #f0f6fc;
	}

	/* Tax Section */
	.tax-section {
		background: #21262d;
		border-radius: 10px;
		padding: 0.75rem;
		margin-top: 0.75rem;
		margin-bottom: 1rem;
	}

	.tax-header {
		font-size: 0.75rem;
		font-weight: 600;
		color: #8b949e;
		margin-bottom: 0.5rem;
	}

	.tax-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.5rem;
	}

	.tax-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.375rem 0.5rem;
		background: #0d1117;
		border-radius: 6px;
		font-size: 0.75rem;
	}

	.tax-item.highlight {
		grid-column: span 2;
		background: rgba(88, 166, 255, 0.1);
		border: 1px solid #30363d;
	}

	.tax-label {
		color: #8b949e;
	}

	.tax-value {
		font-weight: 600;
		color: #f0f6fc;
	}

	.tax-value.negative {
		color: #f85149;
	}

	.tax-value.positive {
		color: #3fb950;
	}

	/* 공지사항 팝업 */
	.announcement-overlay {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.7);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: 1rem;
	}

	.announcement-popup {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 16px;
		padding: 1.5rem;
		max-width: 320px;
		width: 100%;
		position: relative;
	}

	.popup-badge {
		position: absolute;
		top: -8px;
		left: 1rem;
		font-size: 0.7rem;
		padding: 0.2rem 0.6rem;
		background: #f0883e;
		color: #fff;
		border-radius: 4px;
		font-weight: 600;
	}

	.popup-title {
		font-size: 1.1rem;
		font-weight: 700;
		color: #f0f6fc;
		margin: 0 0 0.75rem;
		line-height: 1.3;
	}

	.popup-content {
		font-size: 0.9rem;
		color: #8b949e;
		line-height: 1.5;
		margin: 0 0 1.25rem;
	}

	.popup-actions {
		display: flex;
		gap: 0.5rem;
	}

	.popup-btn {
		flex: 1;
		padding: 0.75rem;
		border: none;
		border-radius: 8px;
		font-size: 0.85rem;
		font-weight: 600;
		cursor: pointer;
	}

	.popup-btn.secondary {
		background: #21262d;
		color: #8b949e;
		border: 1px solid #30363d;
	}

	.popup-btn.primary {
		background: #238636;
		color: white;
	}

	.popup-btn:active {
		transform: scale(0.98);
	}

	/* Blog Header Toggle */
	.blog-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		background: none;
		border: none;
		padding: 0;
		cursor: pointer;
		margin-bottom: 0.5rem;
	}

	.blog-header h2 {
		margin: 0;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.blog-toggle {
		color: #8b949e;
		transition: transform 0.2s;
		display: flex;
		align-items: center;
	}

	.blog-toggle.expanded {
		transform: rotate(90deg);
	}

	.blog-header:hover .blog-toggle {
		color: #f0f6fc;
	}

	/* Disclaimer Section */
	.disclaimer-card {
		background: #161b22;
		border: 1px solid #30363d;
		border-left: 3px solid #8b949e;
	}

	.disclaimer-card h2 {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.9rem;
		color: #8b949e;
	}

	.disclaimer-list {
		margin: 0;
		padding-left: 1.25rem;
		font-size: 0.75rem;
		color: #8b949e;
		line-height: 1.6;
	}

	.disclaimer-list li {
		margin-bottom: 0.375rem;
	}

	.disclaimer-list li:last-child {
		margin-bottom: 0;
	}

	.disclaimer-list strong {
		color: #f0f6fc;
	}

	/* 추천 토글 스타일 */
	.rec-section {
		padding: 1rem;
	}

	.rec-header-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.rec-header-row h2 {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin: 0;
		font-size: 1rem;
	}

	.rec-toggle {
		display: flex;
		gap: 0.25rem;
		background: #21262d;
		border-radius: 8px;
		padding: 0.25rem;
	}

	.toggle-btn {
		padding: 0.375rem 0.75rem;
		border: none;
		background: transparent;
		color: #8b949e;
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.75rem;
		transition: all 0.2s;
	}

	.toggle-btn:hover {
		background: #30363d;
	}

	.toggle-btn.active {
		background: #238636;
		color: white;
	}

	.rec-update-time {
		font-size: 0.7rem;
		color: #6e7681;
		margin: 0 0 0.75rem;
	}

	.investment-disclaimer {
		font-size: 0.7rem;
		color: #f0883e;
		text-align: center;
		margin: 0.75rem 0 0;
		padding-top: 0.75rem;
		border-top: 1px solid #30363d;
	}

	/* 시장 상태 태그 */
	.market-tag {
		font-size: 0.7rem;
		padding: 0.15rem 0.4rem;
		border-radius: 4px;
		background: rgba(139, 148, 158, 0.2);
	}

	.market-tag.live {
		background: rgba(63, 185, 80, 0.2);
	}

	/* 세후 금액 표시 */
	.summary-after-tax {
		display: block;
		font-size: 0.7rem;
		color: #3fb950;
		margin-top: 0.25rem;
	}

	/* 세금 토글 */
	.tax-toggle {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		background: none;
		border: none;
		padding: 0;
		cursor: pointer;
		margin-bottom: 0.5rem;
	}

	.tax-toggle .tax-header {
		font-size: 0.75rem;
		font-weight: 600;
		color: #8b949e;
	}

	.toggle-icon {
		color: #8b949e;
		transition: transform 0.2s;
		display: flex;
		align-items: center;
	}

	.toggle-icon.expanded {
		transform: rotate(90deg);
	}

	/* 가격 태그 */
	.price-tag {
		font-size: 0.55rem;
		padding: 0.1rem 0.2rem;
		border-radius: 3px;
		font-weight: 600;
		margin-left: 0.2rem;
		vertical-align: middle;
	}

	.price-tag.live {
		font-size: 0.6rem;
	}

	.price-tag.pm {
		background: rgba(136, 87, 229, 0.3);
		color: #a371f7;
	}

	.price-tag.ah {
		background: rgba(31, 111, 235, 0.3);
		color: #58a6ff;
	}
</style>
