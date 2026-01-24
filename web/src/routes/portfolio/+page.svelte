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

	// Add form
	let showAddForm = $state(false);
	let searchQuery = $state('');
	let searchResults = $state<SearchResult[]>([]);
	let selectedTicker = $state('');
	let shares = $state('');
	let avgCost = $state('');
	let isSearching = $state(false);
	let isSubmitting = $state(false);

	// Edit
	let editingId = $state<number | null>(null);
	let editShares = $state('');
	let editAvgCost = $state('');

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

	async function addHolding() {
		if (!selectedTicker || !shares || !avgCost) {
			alert('모든 필드를 입력해주세요');
			return;
		}

		isSubmitting = true;
		try {
			const response = await fetch(`${API_BASE}/api/portfolio/holdings`, {
				method: 'POST',
				headers: getAuthHeaders(),
				body: JSON.stringify({
					ticker: selectedTicker,
					shares: parseFloat(shares),
					avg_cost: parseFloat(avgCost),
				}),
			});

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '추가에 실패했습니다');
			}

			showAddForm = false;
			searchQuery = '';
			selectedTicker = '';
			shares = '';
			avgCost = '';
			searchResults = [];

			await loadPortfolio();
		} catch (e) {
			alert(e instanceof Error ? e.message : '오류가 발생했습니다');
		} finally {
			isSubmitting = false;
		}
	}

	function startEdit(holding: Holding) {
		editingId = holding.id;
		editShares = holding.shares.toString();
		editAvgCost = holding.avg_cost.toString();
	}

	function cancelEdit() {
		editingId = null;
		editShares = '';
		editAvgCost = '';
	}

	async function saveEdit(holdingId: number) {
		isSubmitting = true;
		try {
			const response = await fetch(`${API_BASE}/api/portfolio/holdings/${holdingId}`, {
				method: 'PUT',
				headers: getAuthHeaders(),
				body: JSON.stringify({
					shares: parseFloat(editShares),
					avg_cost: parseFloat(editAvgCost),
				}),
			});

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '수정에 실패했습니다');
			}

			cancelEdit();
			await loadPortfolio();
		} catch (e) {
			alert(e instanceof Error ? e.message : '오류가 발생했습니다');
		} finally {
			isSubmitting = false;
		}
	}

	async function deleteHolding(holding: Holding) {
		if (!confirm(`${holding.ticker}를 삭제하시겠습니까?`)) return;

		try {
			const response = await fetch(`${API_BASE}/api/portfolio/holdings/${holding.id}`, {
				method: 'DELETE',
				headers: getAuthHeaders(),
			});

			if (!response.ok) {
				throw new Error('삭제에 실패했습니다');
			}

			await loadPortfolio();
		} catch (e) {
			alert(e instanceof Error ? e.message : '오류가 발생했습니다');
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
		<button class="btn-add" onclick={() => showAddForm = !showAddForm}>
			{showAddForm ? '취소' : '+ 추가'}
		</button>
	</div>

	{#if error}
		<div class="error-box">{error}</div>
	{/if}

	{#if showAddForm}
		<div class="add-form card">
			<h3>종목 추가</h3>
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
			<div class="form-row">
				<div class="form-group">
					<label>수량</label>
					<input type="number" step="0.0001" placeholder="0" bind:value={shares} />
				</div>
				<div class="form-group">
					<label>평균단가 ($)</label>
					<input type="number" step="0.01" placeholder="0.00" bind:value={avgCost} />
				</div>
			</div>
			<button
				class="btn-submit"
				onclick={addHolding}
				disabled={isSubmitting || !selectedTicker || !shares || !avgCost}
			>
				{isSubmitting ? '추가 중...' : '추가하기'}
			</button>
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
						{#if editingId === holding.id}
							<div class="edit-form">
								<div class="ticker">{holding.ticker}</div>
								<div class="edit-inputs">
									<input type="number" step="0.0001" bind:value={editShares} placeholder="수량" />
									<input type="number" step="0.01" bind:value={editAvgCost} placeholder="평단" />
								</div>
								<div class="edit-actions">
									<button class="btn-save" onclick={() => saveEdit(holding.id)} disabled={isSubmitting}>저장</button>
									<button class="btn-cancel" onclick={cancelEdit}>취소</button>
								</div>
							</div>
						{:else}
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
								<button class="btn-edit" onclick={() => startEdit(holding)}>수정</button>
								<button class="btn-delete" onclick={() => deleteHolding(holding)}>삭제</button>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{:else}
			<div class="empty card">
				<p>보유 종목이 없습니다</p>
				<button class="btn-add-first" onclick={() => showAddForm = true}>
					+ 첫 종목 추가하기
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

	.btn-add {
		padding: 0.5rem 1rem;
		background: #238636;
		border: none;
		border-radius: 8px;
		color: white;
		font-weight: 600;
		cursor: pointer;
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

	.add-form h3 {
		margin: 0 0 1rem;
		font-size: 1rem;
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
	}

	.btn-edit, .btn-delete {
		flex: 1;
		padding: 0.5rem;
		border: 1px solid #30363d;
		border-radius: 6px;
		background: transparent;
		font-size: 0.75rem;
		cursor: pointer;
	}

	.btn-edit {
		color: #58a6ff;
	}

	.btn-delete {
		color: #f85149;
	}

	.edit-form .ticker {
		font-size: 1.1rem;
		font-weight: 700;
		color: #58a6ff;
		margin-bottom: 0.75rem;
	}

	.edit-inputs {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.edit-inputs input {
		padding: 0.5rem;
		background: #0d1117;
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
