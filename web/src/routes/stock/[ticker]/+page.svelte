<script lang="ts">
	import { onMount, onDestroy, tick } from 'svelte';
	import { page } from '$app/stores';
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import Icon from '$lib/components/Icons.svelte';

	interface Candle {
		time: number;
		open: number;
		high: number;
		low: number;
		close: number;
		volume: number;
	}

	interface ChartData {
		ticker: string;
		company_name?: string;
		current_price: number;
		period: string;
		candles: Candle[];
		rsi: Array<{ time: number; value: number }>;
		macd: Array<{ time: number; macd: number; signal: number | null; histogram: number | null }>;
		summary: {
			rsi: number | null;
			rsi_signal: string;
			macd: number | null;
			macd_signal: number | null;
		};
	}

	let ticker = $derived($page.params.ticker?.toUpperCase() || '');
	let chartData = $state<ChartData | null>(null);
	let isLoading = $state(true);
	let error = $state('');
	let selectedPeriod = $state('3mo');
	let chartRendered = $state(false);
	let showHelp = $state<string | null>(null);

	const helpTexts: Record<string, string> = {
		rsi: 'RSI (상대강도지수): 70 이상이면 과매수 상태로 하락 가능성, 30 이하면 과매도 상태로 상승 가능성이 높습니다.',
		macd: 'MACD: 파란선(MACD)이 주황선(시그널) 위로 교차하면 매수신호, 아래로 교차하면 매도신호입니다.',
		candle: '캔들스틱: 초록색은 상승(종가>시가), 빨간색은 하락(종가<시가). 꼬리는 고가/저가를 나타냅니다.',
	};

	function toggleHelp(key: string) {
		showHelp = showHelp === key ? null : key;
	}

	// Chart containers
	let mainChartContainer: HTMLDivElement | undefined = $state();
	let rsiChartContainer: HTMLDivElement | undefined = $state();
	let macdChartContainer: HTMLDivElement | undefined = $state();

	// Chart instances (stored outside of reactivity)
	let mainChart: any = null;
	let rsiChart: any = null;
	let macdChart: any = null;

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	const periods = [
		{ value: '1mo', label: '1개월' },
		{ value: '3mo', label: '3개월' },
		{ value: '6mo', label: '6개월' },
		{ value: '1y', label: '1년' },
	];

	let isInWatchlist = $state(false);
	let addingToWatchlist = $state(false);
	let toastMessage = $state('');

	onMount(async () => {
		await Promise.all([loadChartData(), checkWatchlist()]);
	});

	async function checkWatchlist() {
		const token = localStorage.getItem('access_token');
		if (!token) return;

		try {
			const response = await fetch(`${API_BASE}/api/watchlist/`, {
				headers: { 'Authorization': `Bearer ${token}` }
			});
			if (response.ok) {
				const data = await response.json();
				const tickers = data.items?.map((item: { ticker: string }) => item.ticker) || [];
				isInWatchlist = tickers.includes(ticker);
			}
		} catch {
			// 로그인 안 된 경우 무시
		}
	}

	async function addToWatchlist() {
		const token = localStorage.getItem('access_token');
		if (!token) {
			showToast('로그인이 필요합니다');
			return;
		}

		addingToWatchlist = true;
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
				isInWatchlist = true;
				showToast(`${ticker} 관심종목에 추가됨`);
			} else {
				const data = await response.json();
				showToast(data.detail || '추가 실패');
			}
		} catch {
			showToast('네트워크 오류');
		} finally {
			addingToWatchlist = false;
		}
	}

	function showToast(message: string) {
		toastMessage = message;
		setTimeout(() => { toastMessage = ''; }, 2000);
	}

	onDestroy(() => {
		cleanupCharts();
	});

	function cleanupCharts() {
		if (mainChart) { mainChart.remove(); mainChart = null; }
		if (rsiChart) { rsiChart.remove(); rsiChart = null; }
		if (macdChart) { macdChart.remove(); macdChart = null; }
	}

	// Use $effect to render charts when data AND container are ready
	$effect(() => {
		if (chartData && mainChartContainer && browser && !isLoading) {
			// Use requestAnimationFrame to ensure DOM is painted
			requestAnimationFrame(() => {
				requestAnimationFrame(() => {
					renderCharts();
				});
			});
		}
	});

	async function loadChartData() {
		if (!ticker) return;

		isLoading = true;
		error = '';
		chartRendered = false;
		cleanupCharts();

		try {
			const response = await fetch(`${API_BASE}/api/chart/${ticker}?period=${selectedPeriod}`);

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '데이터를 불러올 수 없습니다');
			}

			chartData = await response.json();
		} catch (e) {
			error = e instanceof Error ? e.message : '오류가 발생했습니다';
		} finally {
			isLoading = false;
		}
	}

	function toChartTime(timestamp: number): string {
		const date = new Date(timestamp * 1000);
		return date.toISOString().split('T')[0];
	}

	async function renderCharts() {
		if (!chartData || !browser || !mainChartContainer) {
			console.log('Cannot render: missing data or container', {
				hasData: !!chartData,
				browser,
				hasContainer: !!mainChartContainer
			});
			return;
		}

		// Log container dimensions for debugging
		console.log('Container dimensions:', mainChartContainer.clientWidth, mainChartContainer.clientHeight);
		console.log('Container offsetWidth:', mainChartContainer.offsetWidth);

		try {
			const LightweightCharts = await import('lightweight-charts');
			const { createChart, ColorType, CandlestickSeries, LineSeries } = LightweightCharts;

			console.log('lightweight-charts loaded:', !!createChart, !!CandlestickSeries);

			// Clear previous charts
			cleanupCharts();

			const chartOptions = {
				layout: {
					background: { type: ColorType.Solid, color: '#0d1117' },
					textColor: '#8b949e',
				},
				grid: {
					vertLines: { color: '#21262d' },
					horzLines: { color: '#21262d' },
				},
				timeScale: {
					borderColor: '#30363d',
				},
				rightPriceScale: {
					borderColor: '#30363d',
				},
				watermark: {
					visible: false,
				},
			};

			// Main chart
			console.log('Creating main chart...');
			mainChart = createChart(mainChartContainer, {
				...chartOptions,
				autoSize: true,
			});

			const candleSeries = mainChart.addSeries(CandlestickSeries, {
				upColor: '#3fb950',
				downColor: '#f85149',
				borderUpColor: '#3fb950',
				borderDownColor: '#f85149',
				wickUpColor: '#3fb950',
				wickDownColor: '#f85149',
			});

			const candleData = chartData.candles.map(c => ({
				time: toChartTime(c.time),
				open: c.open,
				high: c.high,
				low: c.low,
				close: c.close,
			}));

			console.log('Setting candle data, count:', candleData.length);
			console.log('First candle:', candleData[0]);
			console.log('Last candle:', candleData[candleData.length - 1]);

			candleSeries.setData(candleData);
			mainChart.timeScale().fitContent();

			// RSI chart
			if (rsiChartContainer && chartData.rsi.length > 0) {
				rsiChart = createChart(rsiChartContainer, {
					...chartOptions,
					autoSize: true,
				});

				const rsiSeries = rsiChart.addSeries(LineSeries, {
					color: '#a371f7',
					lineWidth: 2,
				});
				rsiSeries.setData(chartData.rsi.map(r => ({
					time: toChartTime(r.time),
					value: r.value,
				})));
				rsiChart.timeScale().fitContent();
				console.log('RSI chart created with', chartData.rsi.length, 'points');
			}

			// MACD chart
			if (macdChartContainer && chartData.macd.length > 0) {
				macdChart = createChart(macdChartContainer, {
					...chartOptions,
					autoSize: true,
				});

				const macdLine = macdChart.addSeries(LineSeries, {
					color: '#58a6ff',
					lineWidth: 2,
				});
				macdLine.setData(chartData.macd.map(m => ({
					time: toChartTime(m.time),
					value: m.macd,
				})));

				const signalLine = macdChart.addSeries(LineSeries, {
					color: '#f0883e',
					lineWidth: 1,
				});
				signalLine.setData(
					chartData.macd
						.filter(m => m.signal !== null)
						.map(m => ({ time: toChartTime(m.time), value: m.signal }))
				);
				macdChart.timeScale().fitContent();
				console.log('MACD chart created with', chartData.macd.length, 'points');
			}

			chartRendered = true;
			console.log('All charts rendered successfully!');
		} catch (e) {
			console.error('Chart render error:', e);
			error = e instanceof Error ? e.message : '차트 렌더링 오류';
		}
	}

	function handlePeriodChange(period: string) {
		selectedPeriod = period;
		loadChartData();
	}

	function formatCurrency(value: number | null): string {
		if (value === null) return '-';
		return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	}
</script>

<svelte:head>
	<title>{ticker} - 차트</title>
</svelte:head>

<div class="container">
	<button class="btn-back" onclick={() => history.length > 1 ? history.back() : goto('/')}>← 뒤로</button>

	<div class="header">
		<div class="ticker-info">
			<div class="ticker-price-row">
				<h1>{ticker}</h1>
				{#if chartData}
					<span class="current-price">{formatCurrency(chartData.current_price)}</span>
				{/if}
				<button
					class="btn-star"
					class:active={isInWatchlist}
					onclick={addToWatchlist}
					disabled={addingToWatchlist || isInWatchlist}
					title={isInWatchlist ? '관심종목에 추가됨' : '관심종목 추가'}
				>
					<Icon name={isInWatchlist ? 'star-filled' : 'star'} size={18} />
				</button>
			</div>
			{#if chartData?.company_name}
				<span class="company-name">{chartData.company_name}</span>
			{/if}
		</div>
		<div class="period-selector">
			{#each periods as p}
				<button
					class="period-btn"
					class:active={selectedPeriod === p.value}
					onclick={() => handlePeriodChange(p.value)}
				>
					{p.label}
				</button>
			{/each}
		</div>
	</div>

	{#if error}
		<div class="error-box">{error}</div>
	{/if}

	{#if isLoading}
		<div class="loading">차트 로딩 중...</div>
	{:else if chartData}
		<div class="summary card">
			<div class="indicator">
				<span class="label">RSI <button class="help" onclick={() => toggleHelp('rsi')}>?</button></span>
				<span class="value" class:overbought={chartData.summary.rsi && chartData.summary.rsi >= 70} class:oversold={chartData.summary.rsi && chartData.summary.rsi <= 30}>
					{chartData.summary.rsi ?? '-'}
				</span>
				<span class="signal">{chartData.summary.rsi_signal}</span>
			</div>
			<div class="indicator">
				<span class="label">MACD <button class="help" onclick={() => toggleHelp('macd')}>?</button></span>
				<span class="value">{chartData.summary.macd ?? '-'}</span>
			</div>
		</div>

		{#if showHelp}
			<div class="help-box" onclick={() => showHelp = null}>
				{helpTexts[showHelp]}
				<span class="close-hint">(탭하여 닫기)</span>
			</div>
		{/if}

		<div class="chart-section">
			<div class="chart-title">캔들스틱 ({chartData.candles.length}개) <button class="help" onclick={() => toggleHelp('candle')}>?</button></div>
			<div class="chart-container" bind:this={mainChartContainer} id="main-chart"></div>
		</div>

		<div class="chart-section">
			<div class="chart-title">RSI (14) <button class="help" onclick={() => toggleHelp('rsi')}>?</button></div>
			<div class="chart-container small" bind:this={rsiChartContainer} id="rsi-chart"></div>
		</div>

		<div class="chart-section">
			<div class="chart-title">MACD <button class="help" onclick={() => toggleHelp('macd')}>?</button></div>
			<div class="chart-container small" bind:this={macdChartContainer} id="macd-chart"></div>
		</div>
	{/if}
</div>

{#if toastMessage}
	<div class="toast">{toastMessage}</div>
{/if}

<style>
	.container {
		max-width: 800px;
		margin: 0 auto;
		padding: 1rem;
		padding-bottom: 5rem;
	}

	.btn-back {
		background: none;
		border: none;
		color: #58a6ff;
		font-size: 0.9rem;
		cursor: pointer;
		padding: 0.5rem 0;
		margin-bottom: 0.5rem;
	}

	.header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 1rem;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.ticker-info {
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}

	.ticker-price-row {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
	}

	h1 {
		font-size: 1.5rem;
		margin: 0;
		color: #58a6ff;
	}

	.current-price {
		font-size: 1.25rem;
		font-weight: 600;
	}

	.company-name {
		font-size: 0.75rem;
		color: #8b949e;
	}

	.period-selector {
		display: flex;
		gap: 0.25rem;
	}

	.period-btn {
		padding: 0.4rem 0.75rem;
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 6px;
		color: #8b949e;
		font-size: 0.8rem;
		cursor: pointer;
	}

	.period-btn.active {
		background: #58a6ff;
		border-color: #58a6ff;
		color: #0d1117;
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

	.card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 12px;
		padding: 1rem;
		margin-bottom: 1rem;
	}

	.summary {
		display: flex;
		justify-content: space-around;
		gap: 1rem;
	}

	.indicator {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
	}

	.indicator .label {
		font-size: 0.75rem;
		color: #8b949e;
	}

	.indicator .value {
		font-size: 1.25rem;
		font-weight: 700;
	}

	.indicator .value.overbought {
		color: #f85149;
	}

	.indicator .value.oversold {
		color: #3fb950;
	}

	.indicator .signal {
		font-size: 0.7rem;
		padding: 0.15rem 0.4rem;
		background: #21262d;
		border-radius: 4px;
		color: #8b949e;
	}

	.chart-section {
		margin-bottom: 1rem;
	}

	.chart-title {
		font-size: 0.85rem;
		color: #8b949e;
		margin-bottom: 0.5rem;
		cursor: help;
	}

	.help {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 16px;
		height: 16px;
		font-size: 0.65rem;
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 50%;
		color: #8b949e;
		margin-left: 0.25rem;
		cursor: pointer;
		padding: 0;
	}

	.help:hover {
		background: #30363d;
		color: #f0f6fc;
	}

	.help-box {
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 8px;
		padding: 0.75rem;
		margin-bottom: 1rem;
		font-size: 0.85rem;
		color: #c9d1d9;
		line-height: 1.5;
		cursor: pointer;
	}

	.help-box .close-hint {
		display: block;
		margin-top: 0.5rem;
		font-size: 0.7rem;
		color: #6e7681;
	}

	.chart-container {
		background: #0d1117;
		border: 1px solid #30363d;
		border-radius: 8px;
		overflow: hidden;
		width: 100%;
		height: 300px;
	}

	.chart-container.small {
		height: 100px;
	}

	.btn-star {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 6px;
		color: #8b949e;
		cursor: pointer;
		transition: all 0.15s;
		margin-left: 0.5rem;
	}

	.btn-star:hover:not(:disabled) {
		background: #30363d;
		border-color: #58a6ff;
		color: #58a6ff;
	}

	.btn-star.active {
		background: #ffd700;
		border-color: #ffd700;
		color: #0d1117;
	}

	.btn-star:disabled {
		cursor: not-allowed;
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
