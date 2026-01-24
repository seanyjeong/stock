<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';

	interface Trade {
		id: number;
		ticker: string;
		trade_type: 'buy' | 'sell';
		shares: number;
		price: number;
		total_amount: number;
		note: string | null;
		traded_at: string | null;
	}

	let trades = $state<Trade[]>([]);
	let isLoading = $state(true);
	let error = $state('');

	// Add form
	let showAddForm = $state(false);
	let ticker = $state('');
	let tradeType = $state<'buy' | 'sell'>('buy');
	let shares = $state('');
	let price = $state('');
	let note = $state('');
	let isSubmitting = $state(false);

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	onMount(async () => {
		await loadTrades();
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

	async function loadTrades() {
		isLoading = true;
		error = '';

		try {
			const response = await fetch(`${API_BASE}/api/trades/`, {
				headers: getAuthHeaders(),
			});

			if (response.status === 401 || response.status === 403) {
				goto('/login');
				return;
			}

			if (!response.ok) {
				throw new Error('매매 기록을 불러올 수 없습니다');
			}

			const data = await response.json();
			trades = data.trades;
		} catch (e) {
			error = e instanceof Error ? e.message : '오류가 발생했습니다';
		} finally {
			isLoading = false;
		}
	}

	async function addTrade() {
		if (!ticker || !shares || !price) {
			alert('모든 필드를 입력해주세요');
			return;
		}

		isSubmitting = true;
		try {
			const response = await fetch(`${API_BASE}/api/trades/`, {
				method: 'POST',
				headers: getAuthHeaders(),
				body: JSON.stringify({
					ticker: ticker.toUpperCase(),
					trade_type: tradeType,
					shares: parseFloat(shares),
					price: parseFloat(price),
					note: note || null,
				}),
			});

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '기록 추가에 실패했습니다');
			}

			showAddForm = false;
			ticker = '';
			tradeType = 'buy';
			shares = '';
			price = '';
			note = '';

			await loadTrades();
		} catch (e) {
			alert(e instanceof Error ? e.message : '오류가 발생했습니다');
		} finally {
			isSubmitting = false;
		}
	}

	async function deleteTrade(trade: Trade) {
		if (!confirm(`${trade.ticker} ${trade.trade_type === 'buy' ? '매수' : '매도'} 기록을 삭제하시겠습니까?`)) return;

		try {
			const response = await fetch(`${API_BASE}/api/trades/${trade.id}`, {
				method: 'DELETE',
				headers: getAuthHeaders(),
			});

			if (!response.ok) {
				throw new Error('삭제에 실패했습니다');
			}

			await loadTrades();
		} catch (e) {
			alert(e instanceof Error ? e.message : '오류가 발생했습니다');
		}
	}

	function formatCurrency(value: number): string {
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency: 'USD',
			minimumFractionDigits: 2
		}).format(value);
	}

	function formatDate(dateStr: string | null): string {
		if (!dateStr) return '-';
		const date = new Date(dateStr);
		return date.toLocaleDateString('ko-KR', {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit',
		});
	}
</script>

<svelte:head>
	<title>매매 이력 - 주식 대시보드</title>
</svelte:head>

<div class="container">
	<div class="header">
		<h1>📋 매매 이력</h1>
		<button class="btn-add" onclick={() => showAddForm = !showAddForm}>
			{showAddForm ? '취소' : '+ 기록'}
		</button>
	</div>

	{#if error}
		<div class="error-box">{error}</div>
	{/if}

	{#if showAddForm}
		<div class="add-form card">
			<h3>매매 기록 추가</h3>
			<div class="form-row">
				<div class="form-group">
					<label>종목</label>
					<input type="text" placeholder="AAPL" bind:value={ticker} />
				</div>
				<div class="form-group">
					<label>유형</label>
					<select bind:value={tradeType}>
						<option value="buy">매수</option>
						<option value="sell">매도</option>
					</select>
				</div>
			</div>
			<div class="form-row">
				<div class="form-group">
					<label>수량</label>
					<input type="number" step="0.0001" placeholder="0" bind:value={shares} />
				</div>
				<div class="form-group">
					<label>가격 ($)</label>
					<input type="number" step="0.01" placeholder="0.00" bind:value={price} />
				</div>
			</div>
			<div class="form-group">
				<label>메모 (선택)</label>
				<input type="text" placeholder="손절/익절 이유 등" bind:value={note} />
			</div>
			<button class="btn-submit" onclick={addTrade} disabled={isSubmitting}>
				{isSubmitting ? '추가 중...' : '기록 추가'}
			</button>
		</div>
	{/if}

	{#if isLoading}
		<div class="loading">로딩 중...</div>
	{:else}
		{#if trades.length > 0}
			<div class="trades">
				{#each trades as trade}
					<div class="trade-card card" class:buy={trade.trade_type === 'buy'} class:sell={trade.trade_type === 'sell'}>
						<div class="trade-header">
							<div class="trade-main">
								<span class="ticker">{trade.ticker}</span>
								<span class="type-badge" class:buy={trade.trade_type === 'buy'} class:sell={trade.trade_type === 'sell'}>
									{trade.trade_type === 'buy' ? '매수' : '매도'}
								</span>
							</div>
							<span class="amount">{formatCurrency(trade.total_amount)}</span>
						</div>
						<div class="trade-details">
							<span>{trade.shares}주 × {formatCurrency(trade.price)}</span>
							<span class="date">{formatDate(trade.traded_at)}</span>
						</div>
						{#if trade.note}
							<div class="trade-note">{trade.note}</div>
						{/if}
						<button class="btn-delete" onclick={() => deleteTrade(trade)}>삭제</button>
					</div>
				{/each}
			</div>
		{:else}
			<div class="empty card">
				<p>매매 기록이 없습니다</p>
				<button class="btn-add-first" onclick={() => showAddForm = true}>
					+ 첫 기록 추가하기
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
	}

	.form-group label {
		display: block;
		font-size: 0.75rem;
		color: #8b949e;
		margin-bottom: 0.25rem;
	}

	.form-group input,
	.form-group select {
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
	}

	.trades {
		display: flex;
		flex-direction: column;
	}

	.trade-card {
		position: relative;
	}

	.trade-card.buy {
		border-left: 3px solid #f85149;
	}

	.trade-card.sell {
		border-left: 3px solid #3fb950;
	}

	.trade-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.trade-main {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.ticker {
		font-weight: 700;
		color: #58a6ff;
	}

	.type-badge {
		font-size: 0.65rem;
		padding: 0.15rem 0.4rem;
		border-radius: 4px;
		font-weight: 600;
	}

	.type-badge.buy {
		background: rgba(248, 81, 73, 0.2);
		color: #f85149;
	}

	.type-badge.sell {
		background: rgba(63, 185, 80, 0.2);
		color: #3fb950;
	}

	.amount {
		font-weight: 600;
	}

	.trade-details {
		display: flex;
		justify-content: space-between;
		font-size: 0.8rem;
		color: #8b949e;
	}

	.trade-note {
		margin-top: 0.5rem;
		padding: 0.5rem;
		background: #0d1117;
		border-radius: 6px;
		font-size: 0.8rem;
		color: #8b949e;
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
