<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';

	interface Holding {
		id: number;
		ticker: string;
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

	let holdings = $state<Holding[]>([]);
	let total = $state({ value_usd: 0, value_krw: 0, cost_usd: 0, gain_usd: 0, gain_pct: 0 });
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
	let isSearching = $state(false);
	let isSubmitting = $state(false);

	// Sell mode - selected holding
	let selectedHolding = $state<Holding | null>(null);

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	onMount(async () => {
		await loadPortfolio();
	});

	function getAuthHeaders() {
		const token = localStorage.getItem('access_token');
		if (!token) {
			goto('/login');
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
				goto('/login');
				return;
			}

			if (!response.ok) {
				throw new Error('포트폴리오를 불러올 수 없습니다');
			}

			const data = await response.json();
			holdings = data.holdings;
			total = data.total;
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
				}),
			});

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '거래 실패');
			}

			const result = await response.json();
			alert(result.message);
			closeTrade();
			await loadPortfolio();
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
	<title>포트폴리오 - 주식 대시보드</title>
</svelte:head>

<div class="container">
	<div class="header">
		<h1>💰 포트폴리오</h1>
		<button class="btn-buy" onclick={() => openBuyForm()}>
			+ 매수
		</button>
	</div>

	{#if error}
		<div class="error-box">{error}</div>
	{/if}

	{#if tradeMode}
		<div class="trade-form card">
			<h3>{tradeMode === 'buy' ? '📈 매수' : '📉 매도'}</h3>

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
							<span class="ticker">{holding.ticker}</span>
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
								<span class="value">{formatCurrency(holding.current_price)}</span>
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
</style>
