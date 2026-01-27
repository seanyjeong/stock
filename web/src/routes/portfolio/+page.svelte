<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import Icon from '$lib/components/Icons.svelte';

	interface Holding {
		id: number;
		ticker: string;
		company_name?: string;
		shares: number;
		avg_cost: number;
		current_price: number;
		value: number;
		gain: number;
		gain_pct: number;
	}

	interface SearchResult {
		symbol: string;
		name: string;
		exchange: string;
		type: string;
	}

	interface Trade {
		id: number;
		ticker: string;
		trade_type: 'buy' | 'sell';
		shares: number;
		price: number;
		total_amount: number;
		note: string | null;
		traded_at: string;
	}

	let holdings = $state<Holding[]>([]);
	let trades = $state<Trade[]>([]);
	let total = $state({ value_usd: 0, value_krw: 0, cost_usd: 0, gain_usd: 0, gain_pct: 0 });
	let exchangeRate = $state(0);
	let isLoading = $state(true);
	let error = $state('');

	// Trade form
	type TradeMode = 'buy' | 'sell' | null;
	let tradeMode = $state<TradeMode>(null);
	let searchQuery = $state('');
	let searchResults = $state<SearchResult[]>([]);
	let selectedTicker = $state('');
	let tradeShares = $state('');
	let tradePrice = $state('');
	let tradeNote = $state('');
	let isSearching = $state(false);
	let isSubmitting = $state(false);

	// Sell mode - selected holding
	let selectedHolding = $state<Holding | null>(null);

	// Realtime prices
	let realtimePrices = $state<Record<string, { current: number; change_pct: number; source?: string }>>({});
	let lastRealtimeUpdate = $state<Date | null>(null);
	let realtimeInterval: ReturnType<typeof setInterval> | null = null;
	let marketStatus = $state<{ status: string; is_regular: boolean; label: string } | null>(null);
	let priceSource = $state<string>('');
	let isRealtime = $state(false);

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	onMount(async () => {
		await Promise.all([loadPortfolio(), loadTrades()]);
		// 실시간 가격 폴링 시작 (10초 간격)
		startRealtimePolling();
	});

	onDestroy(() => {
		// 폴링 정리
		if (realtimeInterval) {
			clearInterval(realtimeInterval);
		}
	});

	function startRealtimePolling() {
		// 즉시 한 번 실행
		fetchRealtimePrices();
		// 10초마다 폴링
		realtimeInterval = setInterval(fetchRealtimePrices, 10000);
	}

	async function fetchRealtimePrices() {
		if (holdings.length === 0) return;

		const tickers = holdings.map(h => h.ticker).join(',');
		try {
			const response = await fetch(`${API_BASE}/realtime/hybrid?tickers=${tickers}`);
			if (response.ok) {
				const data = await response.json();
				realtimePrices = data.prices;
				marketStatus = data.market_status;
				priceSource = data.price_source;
				isRealtime = data.is_realtime;
				lastRealtimeUpdate = new Date();

				// holdings 가격 업데이트
				holdings = holdings.map(h => {
					const rt = realtimePrices[h.ticker];
					if (rt && rt.current) {
						const newPrice = rt.current;
						const newValue = h.shares * newPrice;
						const newGain = newValue - (h.shares * h.avg_cost);
						const newGainPct = h.avg_cost > 0 ? (newGain / (h.shares * h.avg_cost)) * 100 : 0;
						return {
							...h,
							current_price: newPrice,
							value: newValue,
							gain: newGain,
							gain_pct: newGainPct
						};
					}
					return h;
				});

				// total 재계산 (한화 포함)
				const totalValue = holdings.reduce((sum, h) => sum + h.value, 0);
				const totalCost = holdings.reduce((sum, h) => sum + (h.shares * h.avg_cost), 0);
				const totalGain = totalValue - totalCost;
				total = {
					...total,
					value_usd: totalValue,
					value_krw: exchangeRate > 0 ? Math.round(totalValue * exchangeRate) : total.value_krw,
					gain_usd: totalGain,
					gain_pct: totalCost > 0 ? (totalGain / totalCost) * 100 : 0
				};

				// 폴링 간격 조정: 정규장 10초, 장외 60초
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

	async function loadTrades() {
		try {
			const response = await fetch(`${API_BASE}/api/trades/`, {
				headers: getAuthHeaders(),
			});

			if (response.ok) {
				const data = await response.json();
				trades = data.trades || [];
			}
		} catch (e) {
			console.error('Failed to load trades:', e);
		}
	}

	function getAuthHeaders() {
		const token = localStorage.getItem('access_token');
		if (!token) {
			goto('/login', { replaceState: true });
			return {};
		}
		return {
			'Authorization': `Bearer ${token}`,
			'Content-Type': 'application/json',
		};
	}

	async function loadPortfolio() {
		isLoading = true;
		error = '';

		try {
			const response = await fetch(`${API_BASE}/api/portfolio/my`, {
				headers: getAuthHeaders(),
			});

			if (response.status === 401 || response.status === 403) {
				goto('/login', { replaceState: true });
				return;
			}

			if (!response.ok) {
				throw new Error('포트폴리오를 불러올 수 없습니다');
			}

			const data = await response.json();
			holdings = data.holdings;
			total = data.total;
			exchangeRate = data.exchange_rate || 0;
		} catch (e) {
			error = e instanceof Error ? e.message : '오류가 발생했습니다';
		} finally {
			isLoading = false;
		}
	}

	let searchTimeout: ReturnType<typeof setTimeout>;
	async function handleSearch() {
		if (searchTimeout) clearTimeout(searchTimeout);

		if (searchQuery.length < 1) {
			searchResults = [];
			return;
		}

		searchTimeout = setTimeout(async () => {
			isSearching = true;
			try {
				const url = `${API_BASE}/api/portfolio/search?q=${encodeURIComponent(searchQuery)}`;
				const response = await fetch(url);
				const data = await response.json();
				searchResults = data.results || [];
			} catch (e) {
				searchResults = [];
			} finally {
				isSearching = false;
			}
		}, 300);
	}

	function selectTicker(result: SearchResult) {
		selectedTicker = result.symbol;
		searchQuery = `${result.symbol} - ${result.name}`;
		searchResults = [];
	}

	function openBuyForm(holding?: Holding) {
		tradeMode = 'buy';
		if (holding) {
			// 추가 매수
			selectedTicker = holding.ticker;
			selectedHolding = holding;
		} else {
			// 새 종목 매수
			selectedTicker = '';
			selectedHolding = null;
		}
		tradeShares = '';
		tradePrice = '';
		searchQuery = '';
		searchResults = [];
	}

	function openSellForm(holding: Holding) {
		tradeMode = 'sell';
		selectedTicker = holding.ticker;
		selectedHolding = holding;
		tradeShares = '';
		tradePrice = holding.current_price.toString();
	}

	function closeTrade() {
		tradeMode = null;
		selectedTicker = '';
		selectedHolding = null;
		tradeShares = '';
		tradePrice = '';
		tradeNote = '';
		searchQuery = '';
		searchResults = [];
	}

	async function submitTrade() {
		if (!selectedTicker || !tradeShares || !tradePrice) {
			alert('모든 필드를 입력해주세요');
			return;
		}

		const shares = parseFloat(tradeShares);
		const price = parseFloat(tradePrice);

		if (tradeMode === 'sell' && selectedHolding && shares > selectedHolding.shares) {
			alert(`보유 수량(${selectedHolding.shares}주)보다 많이 매도할 수 없습니다`);
			return;
		}

		isSubmitting = true;
		try {
			const response = await fetch(`${API_BASE}/api/trades/`, {
				method: 'POST',
				headers: getAuthHeaders(),
				body: JSON.stringify({
					ticker: selectedTicker,
					trade_type: tradeMode,
					shares: shares,
					price: price,
					note: tradeNote || null,
				}),
			});

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '거래 실패');
			}

			const result = await response.json();
			alert(result.message);
			closeTrade();
			await Promise.all([loadPortfolio(), loadTrades()]);
		} catch (e) {
			alert(e instanceof Error ? e.message : '오류가 발생했습니다');
		} finally {
			isSubmitting = false;
		}
	}

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
		return '';
	}
</script>

<svelte:head>
	<title>포트폴리오 - 달러농장</title>
</svelte:head>

<div class="container">
	<div class="header">
		<h1><Icon name="wallet" size={24} /> 포트폴리오</h1>
		<button class="btn-buy" onclick={() => openBuyForm()}>
			+ 매수
		</button>
	</div>

	{#if error}
		<div class="error-box">{error}</div>
	{/if}

	{#if tradeMode}
		<div class="trade-form card">
			<h3>
				{#if tradeMode === 'buy'}
					<Icon name="trending-up" size={20} /> 매수
				{:else}
					<Icon name="trending-down" size={20} /> 매도
				{/if}
			</h3>

			{#if tradeMode === 'buy' && !selectedHolding}
				<!-- 새 종목 매수: 검색 필요 -->
				<div class="form-group">
					<label>종목 검색</label>
					<input
						type="text"
						placeholder="티커 또는 종목명 검색..."
						bind:value={searchQuery}
						oninput={handleSearch}
					/>
					{#if isSearching}
						<div class="search-loading">검색 중...</div>
					{/if}
					{#if searchResults.length > 0}
						<div class="search-results">
							{#each searchResults as result}
								<button class="search-item" onclick={() => selectTicker(result)}>
									<span class="ticker">{result.symbol}</span>
									<span class="name">{result.name}</span>
									<span class="exchange">{result.exchange}</span>
								</button>
							{/each}
						</div>
					{/if}
				</div>
			{:else}
				<!-- 기존 종목 매수/매도: 티커 표시 -->
				<div class="selected-ticker">
					<span class="ticker-badge">{selectedTicker}</span>
					{#if selectedHolding}
						<span class="current-shares">현재 보유: {selectedHolding.shares}주 (평단: ${selectedHolding.avg_cost.toFixed(2)})</span>
					{/if}
				</div>
			{/if}

			{#if selectedTicker}
				<div class="form-row">
					<div class="form-group">
						<label>수량</label>
						<input type="number" step="1" min="1" placeholder="0" bind:value={tradeShares} />
						{#if tradeMode === 'sell' && selectedHolding}
							<button class="btn-all" onclick={() => tradeShares = selectedHolding.shares.toString()}>전량</button>
						{/if}
					</div>
					<div class="form-group">
						<label>{tradeMode === 'buy' ? '매수가' : '매도가'} ($)</label>
						<input type="number" step="0.01" placeholder="0.00" bind:value={tradePrice} />
					</div>
				</div>

				{#if tradeShares && tradePrice}
					<div class="trade-summary">
						<span>총 {tradeMode === 'buy' ? '매수' : '매도'}금액:</span>
						<span class="amount">${(parseFloat(tradeShares) * parseFloat(tradePrice)).toFixed(2)}</span>
					</div>
				{/if}

				<div class="form-group">
					<label>메모 (선택)</label>
					<input type="text" placeholder="예: 숏스퀴즈 기대" bind:value={tradeNote} />
				</div>
			{/if}

			<div class="form-actions">
				<button class="btn-cancel" onclick={closeTrade}>취소</button>
				<button
					class="btn-submit {tradeMode}"
					onclick={submitTrade}
					disabled={isSubmitting || !selectedTicker || !tradeShares || !tradePrice}
				>
					{isSubmitting ? '처리 중...' : (tradeMode === 'buy' ? '매수하기' : '매도하기')}
				</button>
			</div>
		</div>
	{/if}

	{#if isLoading}
		<div class="loading">로딩 중...</div>
	{:else}
		{#if holdings.length > 0}
			{#if lastRealtimeUpdate && marketStatus}
				<div class="realtime-status" class:regular={isRealtime} class:extended={!isRealtime}>
					<span class="realtime-indicator" class:live={isRealtime}></span>
					<span class="realtime-text">
						{#if isRealtime}
							🟢 실시간
						{:else if marketStatus.status === 'premarket'}
							🟡 PM
						{:else if marketStatus.status === 'afterhours'}
							🟡 AH
						{:else}
							⚪ {marketStatus.label}
						{/if}
					</span>
					<span class="realtime-time">
						{lastRealtimeUpdate.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
					</span>
					<span class="realtime-interval">
						({isRealtime ? '10초' : '1분'} 갱신)
					</span>
				</div>
			{/if}
			<div class="summary card">
				<div class="summary-item">
					<span class="label">총 평가금</span>
					<span class="value">{formatCurrency(total.value_usd)}</span>
					<span class="sub">{formatCurrency(total.value_krw, 'KRW')}</span>
				</div>
				<div class="summary-item {getGainClass(total.gain_usd)}">
					<span class="label">총 수익</span>
					<span class="value">{formatCurrency(total.gain_usd)}</span>
					<span class="pct">{formatPercent(total.gain_pct)}</span>
				</div>
			</div>

			<div class="holdings">
				{#each holdings as holding}
					<div class="holding-card card">
						<div class="holding-header">
							<div class="ticker-with-name">
								<a href="/stock/{holding.ticker}" class="ticker">{holding.ticker}</a>
								{#if holding.company_name}
									<span class="company-name">{holding.company_name}</span>
								{/if}
							</div>
							<span class="gain {getGainClass(holding.gain)}">
								{formatCurrency(holding.gain)} ({formatPercent(holding.gain_pct)})
							</span>
						</div>
						<div class="holding-details">
							<div class="detail">
								<span class="label">수량</span>
								<span class="value">{holding.shares}주</span>
							</div>
							<div class="detail">
								<span class="label">평단</span>
								<span class="value">{formatCurrency(holding.avg_cost)}</span>
							</div>
							<div class="detail">
								<span class="label">현재가</span>
								<span class="value">
									{formatCurrency(holding.current_price)}
									{#if realtimePrices[holding.ticker]?.source}
										{@const src = realtimePrices[holding.ticker].source}
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
								<span class="label">평가금</span>
								<span class="value">{formatCurrency(holding.value)}</span>
							</div>
						</div>
						<div class="holding-actions">
							<button class="btn-buy-more" onclick={() => openBuyForm(holding)}>+ 매수</button>
							<button class="btn-sell" onclick={() => openSellForm(holding)}>- 매도</button>
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<div class="empty card">
				<p>보유 종목이 없습니다</p>
				<button class="btn-add-first" onclick={() => openBuyForm()}>
					+ 첫 종목 매수하기
				</button>
			</div>
		{/if}

		<!-- 거래 이력 섹션 -->
		{#if trades.length > 0}
			<section class="trades-section">
				<h2>거래 이력</h2>
				<div class="trades-list">
					{#each trades as trade}
						<div class="trade-item card">
							<div class="trade-header">
								<span class="trade-ticker">{trade.ticker}</span>
								<span class="trade-type {trade.trade_type}">
									{trade.trade_type === 'buy' ? '매수' : '매도'}
								</span>
							</div>
							<div class="trade-details">
								<div class="trade-detail">
									<span class="label">수량</span>
									<span class="value">{trade.shares}주</span>
								</div>
								<div class="trade-detail">
									<span class="label">단가</span>
									<span class="value">{formatCurrency(trade.price)}</span>
								</div>
								<div class="trade-detail">
									<span class="label">금액</span>
									<span class="value">{formatCurrency(trade.total_amount)}</span>
								</div>
							</div>
							{#if trade.note}
								<div class="trade-note">{trade.note}</div>
							{/if}
							<div class="trade-date">
								{new Date(trade.traded_at).toLocaleDateString('ko-KR', {
									year: 'numeric',
									month: 'short',
									day: 'numeric',
									hour: '2-digit',
									minute: '2-digit'
								})}
							</div>
						</div>
					{/each}
				</div>
			</section>
		{/if}
	{/if}
</div>

<style>
	.container {
		max-width: 500px;
		margin: 0 auto;
		padding: 1rem;
	}

	.header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1rem;
	}

	h1 {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 1.5rem;
		margin: 0;
	}

	.btn-buy {
		padding: 0.5rem 1rem;
		background: #238636;
		border: none;
		border-radius: 8px;
		color: white;
		font-weight: 600;
		cursor: pointer;
	}

	.btn-buy:hover {
		background: #2ea043;
	}

	.card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 12px;
		padding: 1rem;
		margin-bottom: 1rem;
	}

	.error-box {
		background: rgba(248, 81, 73, 0.15);
		border: 1px solid #f85149;
		color: #f85149;
		padding: 1rem;
		border-radius: 8px;
		margin-bottom: 1rem;
	}

	.loading {
		text-align: center;
		padding: 3rem;
		color: #8b949e;
	}

	.trade-form h3 {
		margin: 0 0 1rem;
		font-size: 1.1rem;
	}

	.selected-ticker {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		margin-bottom: 1rem;
	}

	.ticker-badge {
		display: inline-block;
		padding: 0.5rem 1rem;
		background: #30363d;
		border-radius: 8px;
		font-weight: 700;
		font-size: 1.1rem;
	}

	.current-shares {
		font-size: 0.8rem;
		color: #8b949e;
	}

	.btn-all {
		position: absolute;
		right: 8px;
		top: 50%;
		transform: translateY(-50%);
		padding: 0.25rem 0.5rem;
		background: #30363d;
		border: none;
		border-radius: 4px;
		color: #8b949e;
		font-size: 0.7rem;
		cursor: pointer;
	}

	.trade-summary {
		display: flex;
		justify-content: space-between;
		padding: 0.75rem;
		background: #0d1117;
		border-radius: 8px;
		margin-bottom: 1rem;
	}

	.trade-summary .amount {
		font-weight: 700;
		color: #58a6ff;
	}

	.form-actions {
		display: flex;
		gap: 0.5rem;
	}

	.form-actions .btn-cancel {
		flex: 1;
		padding: 0.75rem;
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 8px;
		color: #f0f6fc;
		cursor: pointer;
	}

	.form-actions .btn-submit {
		flex: 2;
		padding: 0.75rem;
		border: none;
		border-radius: 8px;
		font-weight: 600;
		cursor: pointer;
	}

	.form-actions .btn-submit.buy {
		background: #238636;
		color: white;
	}

	.form-actions .btn-submit.sell {
		background: #da3633;
		color: white;
	}

	.form-actions .btn-submit:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.form-group {
		margin-bottom: 1rem;
		position: relative;
	}

	.form-group label {
		display: block;
		font-size: 0.75rem;
		color: #8b949e;
		margin-bottom: 0.25rem;
	}

	.form-group input {
		width: 100%;
		padding: 0.75rem;
		background: #0d1117;
		border: 1px solid #30363d;
		border-radius: 8px;
		color: #f0f6fc;
		font-size: 0.9rem;
	}

	.form-row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.75rem;
	}

	.search-loading {
		font-size: 0.75rem;
		color: #8b949e;
		padding: 0.5rem;
	}

	.search-results {
		position: absolute;
		top: 100%;
		left: 0;
		right: 0;
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 8px;
		max-height: 200px;
		overflow-y: auto;
		z-index: 10;
	}

	.search-item {
		display: flex;
		gap: 0.5rem;
		padding: 0.75rem;
		width: 100%;
		background: none;
		border: none;
		border-bottom: 1px solid #30363d;
		color: #f0f6fc;
		text-align: left;
		cursor: pointer;
	}

	.search-item:hover {
		background: #30363d;
	}

	.search-item:last-child {
		border-bottom: none;
	}

	.search-item .ticker {
		font-weight: 600;
		color: #58a6ff;
		min-width: 60px;
	}

	.search-item .name {
		flex: 1;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.85rem;
	}

	.search-item .exchange {
		font-size: 0.7rem;
		color: #8b949e;
	}

	.btn-submit {
		width: 100%;
		padding: 0.875rem;
		background: #238636;
		border: none;
		border-radius: 8px;
		color: white;
		font-weight: 600;
		cursor: pointer;
	}

	.btn-submit:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.summary {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 1rem;
	}

	.summary-item {
		text-align: center;
	}

	.summary-item .label {
		display: block;
		font-size: 0.7rem;
		color: #8b949e;
		margin-bottom: 0.25rem;
	}

	.summary-item .value {
		display: block;
		font-size: 1.25rem;
		font-weight: 700;
	}

	.summary-item .sub,
	.summary-item .pct {
		display: block;
		font-size: 0.8rem;
		color: #8b949e;
	}

	.summary-item.positive .value,
	.summary-item.positive .pct {
		color: #3fb950;
	}

	.summary-item.negative .value,
	.summary-item.negative .pct {
		color: #f85149;
	}

	.holdings {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.holding-card {
		padding: 0.875rem;
	}

	.holding-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.75rem;
	}

	.holding-header .ticker {
		font-size: 1.1rem;
		font-weight: 700;
		color: #58a6ff;
		text-decoration: none;
	}

	.holding-header .ticker:hover {
		text-decoration: underline;
	}

	.ticker-with-name {
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}

	.company-name {
		font-size: 0.7rem;
		color: #8b949e;
	}

	.holding-header .gain {
		font-size: 0.85rem;
		font-weight: 600;
	}

	.gain.positive { color: #3fb950; }
	.gain.negative { color: #f85149; }

	.holding-details {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.detail {
		background: #0d1117;
		padding: 0.5rem;
		border-radius: 6px;
		text-align: center;
	}

	.detail .label {
		display: block;
		font-size: 0.6rem;
		color: #8b949e;
	}

	.detail .value {
		display: block;
		font-size: 0.75rem;
		font-weight: 600;
	}

	.holding-actions {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.75rem;
	}

	.btn-buy-more, .btn-sell {
		flex: 1;
		padding: 0.5rem;
		border: none;
		border-radius: 6px;
		font-size: 0.8rem;
		font-weight: 600;
		cursor: pointer;
	}

	.btn-buy-more {
		background: rgba(35, 134, 54, 0.2);
		color: #3fb950;
	}

	.btn-buy-more:hover {
		background: rgba(35, 134, 54, 0.3);
	}

	.btn-sell {
		background: rgba(218, 54, 51, 0.2);
		color: #f85149;
	}

	.btn-sell:hover {
		background: rgba(218, 54, 51, 0.3);
	}

	.btn-add-first {
		padding: 0.75rem 1.5rem;
		background: #238636;
		border: none;
		border-radius: 8px;
		color: white;
		font-weight: 600;
		cursor: pointer;
		border: 1px solid #30363d;
		border-radius: 6px;
		color: #f0f6fc;
	}

	.edit-actions {
		display: flex;
		gap: 0.5rem;
	}

	.btn-save, .btn-cancel {
		flex: 1;
		padding: 0.5rem;
		border: none;
		border-radius: 6px;
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
	}

	.btn-save {
		background: #238636;
		color: white;
	}

	.btn-cancel {
		background: #21262d;
		color: #8b949e;
	}

	.empty {
		text-align: center;
		padding: 3rem 1rem;
	}

	.empty p {
		color: #8b949e;
		margin: 0 0 1rem;
	}

	.btn-add-first {
		padding: 0.75rem 1.5rem;
		background: #238636;
		border: none;
		border-radius: 8px;
		color: white;
		font-weight: 600;
		cursor: pointer;
	}

	/* 거래 이력 스타일 */
	.trades-section {
		margin-top: 1.5rem;
	}

	.trades-section h2 {
		font-size: 1rem;
		color: #8b949e;
		margin-bottom: 0.75rem;
		font-weight: 600;
	}

	.trades-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.trade-item {
		padding: 0.75rem;
	}

	.trade-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.trade-ticker {
		font-weight: 700;
		color: #58a6ff;
	}

	.trade-type {
		font-size: 0.75rem;
		font-weight: 600;
		padding: 0.2rem 0.5rem;
		border-radius: 4px;
	}

	.trade-type.buy {
		background: rgba(35, 134, 54, 0.2);
		color: #3fb950;
	}

	.trade-type.sell {
		background: rgba(218, 54, 51, 0.2);
		color: #f85149;
	}

	.trade-details {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.5rem;
		margin-bottom: 0.5rem;
	}

	.trade-detail {
		text-align: center;
		background: #0d1117;
		padding: 0.4rem;
		border-radius: 4px;
	}

	.trade-detail .label {
		display: block;
		font-size: 0.6rem;
		color: #8b949e;
	}

	.trade-detail .value {
		display: block;
		font-size: 0.75rem;
		font-weight: 600;
	}

	.trade-note {
		font-size: 0.75rem;
		color: #8b949e;
		padding: 0.4rem;
		background: #0d1117;
		border-radius: 4px;
		margin-bottom: 0.5rem;
	}

	.trade-date {
		font-size: 0.7rem;
		color: #6e7681;
		text-align: right;
	}

	/* 실시간 가격 표시 */
	.realtime-status {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.5rem;
		margin-bottom: 0.75rem;
		background: rgba(35, 134, 54, 0.1);
		border-radius: 8px;
		font-size: 0.75rem;
	}

	.realtime-indicator {
		width: 8px;
		height: 8px;
		background: #3fb950;
		border-radius: 50%;
		animation: pulse 2s infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.5; }
	}

	.realtime-text {
		color: #3fb950;
		font-weight: 600;
	}

	.realtime-time {
		color: #8b949e;
	}

	.realtime-interval {
		color: #8b949e;
		font-size: 0.7rem;
	}

	.realtime-status.extended {
		background: rgba(240, 136, 62, 0.1);
	}

	.realtime-status.extended .realtime-indicator {
		background: #f0883e;
	}

	.realtime-indicator.live {
		background: #3fb950;
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
