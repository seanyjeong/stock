<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';

	interface WatchlistItem {
		id: number;
		ticker: string;
		note: string | null;
		target_price: number | null;
		alert_price: number | null;
		current_price: number | null;
		regular_price: number | null;
		afterhours_price: number | null;
		premarket_price: number | null;
		target_diff_pct: number | null;
		created_at: string | null;
	}

	let watchlist = $state<WatchlistItem[]>([]);
	let isLoading = $state(true);
	let error = $state('');

	// Add form
	let showAddForm = $state(false);
	let ticker = $state('');
	let note = $state('');
	let targetPrice = $state('');
	let alertPrice = $state('');
	let isSubmitting = $state(false);

	// Search
	let searchQuery = $state('');
	let searchResults = $state<Array<{symbol: string; name: string}>>([]);
	let isSearching = $state(false);
	let searchTimeout: ReturnType<typeof setTimeout>;

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	onMount(async () => {
		await loadWatchlist();
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

	async function loadWatchlist() {
		isLoading = true;
		error = '';

		try {
			const response = await fetch(`${API_BASE}/api/watchlist/`, {
				headers: getAuthHeaders(),
			});

			if (response.status === 401 || response.status === 403) {
				goto('/login');
				return;
			}

			if (!response.ok) {
				throw new Error('관심 종목을 불러올 수 없습니다');
			}

			const data = await response.json();
			watchlist = data.watchlist;
		} catch (e) {
			error = e instanceof Error ? e.message : '오류가 발생했습니다';
		} finally {
			isLoading = false;
		}
	}

	async function searchTicker(query: string) {
		if (query.length < 1) {
			searchResults = [];
			return;
		}

		isSearching = true;
		try {
			const response = await fetch(`${API_BASE}/api/portfolio/search?q=${encodeURIComponent(query)}`, {
				headers: getAuthHeaders(),
			});
			if (response.ok) {
				const data = await response.json();
				searchResults = data.results || [];
			}
		} catch {
			searchResults = [];
		} finally {
			isSearching = false;
		}
	}

	function handleSearchInput() {
		clearTimeout(searchTimeout);
		searchTimeout = setTimeout(() => {
			searchTicker(searchQuery);
		}, 300);
	}

	function selectTicker(symbol: string) {
		ticker = symbol;
		searchQuery = symbol;
		searchResults = [];
	}

	async function addToWatchlist() {
		if (!ticker) {
			alert('종목을 선택해주세요');
			return;
		}

		isSubmitting = true;
		try {
			const response = await fetch(`${API_BASE}/api/watchlist/`, {
				method: 'POST',
				headers: getAuthHeaders(),
				body: JSON.stringify({
					ticker: ticker.toUpperCase(),
					note: note || null,
					target_price: targetPrice ? parseFloat(targetPrice) : null,
					alert_price: alertPrice ? parseFloat(alertPrice) : null,
				}),
			});

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '추가에 실패했습니다');
			}

			showAddForm = false;
			ticker = '';
			searchQuery = '';
			note = '';
			targetPrice = '';
			alertPrice = '';

			await loadWatchlist();
		} catch (e) {
			alert(e instanceof Error ? e.message : '오류가 발생했습니다');
		} finally {
			isSubmitting = false;
		}
	}

	async function removeFromWatchlist(item: WatchlistItem) {
		if (!confirm(`${item.ticker}를 관심 종목에서 삭제하시겠습니까?`)) return;

		try {
			const response = await fetch(`${API_BASE}/api/watchlist/${item.id}`, {
				method: 'DELETE',
				headers: getAuthHeaders(),
			});

			if (!response.ok) {
				throw new Error('삭제에 실패했습니다');
			}

			await loadWatchlist();
		} catch (e) {
			alert(e instanceof Error ? e.message : '오류가 발생했습니다');
		}
	}

	function formatCurrency(value: number | null): string {
		if (value === null) return '-';
		return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	}

	function formatPct(value: number | null): string {
		if (value === null) return '';
		const sign = value >= 0 ? '+' : '';
		return sign + value.toFixed(1) + '%';
	}
</script>

<svelte:head>
	<title>관심 종목 - 주식 대시보드</title>
</svelte:head>

<div class="container">
	<div class="header">
		<h1>Star 관심 종목</h1>
		<button class="btn-add" onclick={() => showAddForm = !showAddForm}>
			{showAddForm ? '취소' : '+ 추가'}
		</button>
	</div>

	{#if error}
		<div class="error-box">{error}</div>
	{/if}

	{#if showAddForm}
		<div class="add-form card">
			<h3>관심 종목 추가</h3>
			<div class="form-group">
				<label>종목 검색</label>
				<input
					type="text"
					placeholder="티커 또는 회사명"
					bind:value={searchQuery}
					oninput={handleSearchInput}
				/>
				{#if isSearching}
					<div class="search-loading">검색 중...</div>
				{/if}
				{#if searchResults.length > 0}
					<div class="search-results">
						{#each searchResults as result}
							<button class="search-item" onclick={() => selectTicker(result.symbol)}>
								<span class="symbol">{result.symbol}</span>
								<span class="name">{result.name}</span>
							</button>
						{/each}
					</div>
				{/if}
			</div>
			{#if ticker}
				<div class="selected-ticker">
					선택: <strong>{ticker}</strong>
				</div>
			{/if}
			<div class="form-row">
				<div class="form-group">
					<label>목표가 ($)</label>
					<input type="number" step="0.01" placeholder="15.00" bind:value={targetPrice} />
				</div>
				<div class="form-group">
					<label>알림가 ($)</label>
					<input type="number" step="0.01" placeholder="10.00" bind:value={alertPrice} />
				</div>
			</div>
			<div class="form-group">
				<label>메모 (선택)</label>
				<input type="text" placeholder="관심 이유, 진입 시점 등" bind:value={note} />
			</div>
			<button class="btn-submit" onclick={addToWatchlist} disabled={isSubmitting || !ticker}>
				{isSubmitting ? '추가 중...' : '관심 종목 추가'}
			</button>
		</div>
	{/if}

	{#if isLoading}
		<div class="loading">로딩 중...</div>
	{:else}
		{#if watchlist.length > 0}
			<div class="watchlist">
				{#each watchlist as item}
					<div class="watchlist-card card">
						<div class="card-header">
							<div class="ticker-info">
								<a href="/stock/{item.ticker}" class="ticker">{item.ticker}</a>
								{#if item.target_diff_pct !== null}
									<span class="target-diff" class:positive={item.target_diff_pct > 0} class:negative={item.target_diff_pct < 0}>
										목표 {formatPct(item.target_diff_pct)}
									</span>
								{/if}
							</div>
							<div class="price">{formatCurrency(item.current_price)}</div>
						</div>

						<div class="card-details">
							{#if item.target_price}
								<div class="detail-row">
									<span class="label">목표가</span>
									<span class="value">{formatCurrency(item.target_price)}</span>
								</div>
							{/if}
							{#if item.alert_price}
								<div class="detail-row">
									<span class="label">알림가</span>
									<span class="value">{formatCurrency(item.alert_price)}</span>
								</div>
							{/if}
						</div>

						{#if item.note}
							<div class="card-note">{item.note}</div>
						{/if}

						<button class="btn-delete" onclick={() => removeFromWatchlist(item)}>삭제</button>
					</div>
				{/each}
			</div>
		{:else}
			<div class="empty card">
				<p>관심 종목이 없습니다</p>
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
		margin-bottom: 0.75rem;
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
		margin-bottom: 0.75rem;
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
		justify-content: space-between;
		align-items: center;
		width: 100%;
		padding: 0.75rem;
		background: none;
		border: none;
		border-bottom: 1px solid #30363d;
		color: #f0f6fc;
		cursor: pointer;
		text-align: left;
	}

	.search-item:hover {
		background: #30363d;
	}

	.search-item:last-child {
		border-bottom: none;
	}

	.search-item .symbol {
		font-weight: 600;
		color: #58a6ff;
	}

	.search-item .name {
		font-size: 0.8rem;
		color: #8b949e;
		flex: 1;
		margin-left: 0.5rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.selected-ticker {
		background: rgba(88, 166, 255, 0.1);
		border: 1px solid #58a6ff;
		padding: 0.5rem 0.75rem;
		border-radius: 6px;
		font-size: 0.85rem;
		margin-bottom: 0.75rem;
	}

	.selected-ticker strong {
		color: #58a6ff;
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

	.watchlist {
		display: flex;
		flex-direction: column;
	}

	.watchlist-card {
		position: relative;
	}

	.card-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.ticker-info {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.ticker {
		font-weight: 700;
		font-size: 1.1rem;
		color: #58a6ff;
		text-decoration: none;
	}

	.ticker:hover {
		text-decoration: underline;
	}

	.target-diff {
		font-size: 0.7rem;
		padding: 0.15rem 0.4rem;
		border-radius: 4px;
		font-weight: 600;
	}

	.target-diff.positive {
		background: rgba(63, 185, 80, 0.2);
		color: #3fb950;
	}

	.target-diff.negative {
		background: rgba(248, 81, 73, 0.2);
		color: #f85149;
	}

	.price {
		font-size: 1.1rem;
		font-weight: 600;
	}

	.card-details {
		display: flex;
		gap: 1.5rem;
		margin-bottom: 0.5rem;
	}

	.detail-row {
		display: flex;
		gap: 0.5rem;
		font-size: 0.8rem;
	}

	.detail-row .label {
		color: #8b949e;
	}

	.detail-row .value {
		color: #f0f6fc;
	}

	.card-note {
		padding: 0.5rem;
		background: #0d1117;
		border-radius: 6px;
		font-size: 0.8rem;
		color: #8b949e;
		margin-top: 0.5rem;
	}

	.btn-delete {
		position: absolute;
		top: 0.75rem;
		right: 0.75rem;
		padding: 0.25rem 0.5rem;
		background: transparent;
		border: 1px solid #30363d;
		border-radius: 4px;
		font-size: 0.65rem;
		color: #8b949e;
		cursor: pointer;
	}

	.btn-delete:hover {
		border-color: #f85149;
		color: #f85149;
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
