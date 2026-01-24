<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import Icon from '$lib/components/Icons.svelte';

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
	<title>매매 이력 - 달러농장</title>
</svelte:head>

<div class="container">
	<div class="header">
		<h1><Icon name="list" size={24} /> 매매 이력</h1>
	</div>

	<p class="info-text">포트폴리오에서 매수/매도 시 자동 기록됩니다</p>

	{#if error}
		<div class="error-box">{error}</div>
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
						<div class="trade-actions">
							<button class="btn-delete" onclick={() => deleteTrade(trade)}>삭제</button>
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<div class="empty card">
				<p>매매 기록이 없습니다</p>
				<p class="empty-sub">포트폴리오에서 매수/매도 시 자동 기록됩니다</p>
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
		margin-bottom: 0.5rem;
	}

	h1 {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 1.5rem;
		margin: 0;
	}

	.info-text {
		font-size: 0.8rem;
		color: #8b949e;
		margin: 0 0 1rem;
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

	.trades {
		display: flex;
		flex-direction: column;
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

	.trade-actions {
		margin-top: 0.75rem;
		padding-top: 0.75rem;
		border-top: 1px solid #21262d;
		display: flex;
		justify-content: flex-end;
	}

	.btn-delete {
		padding: 0.35rem 0.75rem;
		background: transparent;
		border: 1px solid #30363d;
		border-radius: 6px;
		font-size: 0.75rem;
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
		margin: 0;
	}

	.empty-sub {
		font-size: 0.8rem;
		margin-top: 0.5rem !important;
	}
</style>
