<script lang="ts">
	import { onMount, onDestroy, tick } from 'svelte';
	import { page } from '$app/stores';
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';

	// Types
	interface Candle {
		time: number;
		open: number;
		high: number;
		low: number;
		close: number;
		volume: number;
	}

	interface RsiPoint {
		time: number;
		value: number;
	}

	interface MacdPoint {
		time: number;
		macd: number;
		signal: number | null;
		histogram: number | null;
	}

	interface ChartData {
		ticker: string;
		current_price: number;
		period: string;
		candles: Candle[];
		rsi: RsiPoint[];
		macd: MacdPoint[];
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

	// Chart instances
	let mainChartContainer: HTMLDivElement;
	let rsiChartContainer: HTMLDivElement;
	let macdChartContainer: HTMLDivElement;
	let mainChart: any;
	let rsiChart: any;
	let macdChart: any;

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	const periods = [
		{ value: '1mo', label: '1개월' },
		{ value: '3mo', label: '3개월' },
		{ value: '6mo', label: '6개월' },
		{ value: '1y', label: '1년' },
	];

	onMount(async () => {
		await loadChartData();
	});

	onDestroy(() => {
		if (mainChart) mainChart.remove();
		if (rsiChart) rsiChart.remove();
		if (macdChart) macdChart.remove();
	});

	async function loadChartData() {
		if (!ticker) return;

		isLoading = true;
		error = '';

		try {
			const response = await fetch(`${API_BASE}/api/chart/${ticker}?period=${selectedPeriod}`);

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '데이터를 불러올 수 없습니다');
			}

			chartData = await response.json();
			// Wait for DOM update before rendering charts
			await tick();
			await renderCharts();
		} catch (e) {
			error = e instanceof Error ? e.message : '오류가 발생했습니다';
		} finally {
			isLoading = false;
		}
	}

	async function renderCharts() {
		if (!chartData || !browser) return;

		// Wait for next frame to ensure DOM is ready
		await new Promise(resolve => requestAnimationFrame(resolve));

		// Dynamically import lightweight-charts
		const { createChart, ColorType, CrosshairMode } = await import('lightweight-charts');

		// Clear previous charts
		if (mainChart) mainChart.remove();
		if (rsiChart) rsiChart.remove();
		if (macdChart) macdChart.remove();

		const chartOptions = {
			layout: {
				background: { type: ColorType.Solid, color: '#0d1117' },
				textColor: '#8b949e',
			},
			grid: {
				vertLines: { color: '#21262d' },
				horzLines: { color: '#21262d' },
			},
			crosshair: {
				mode: CrosshairMode.Normal,
			},
			timeScale: {
				borderColor: '#30363d',
				timeVisible: true,
			},
			rightPriceScale: {
				borderColor: '#30363d',
			},
		};

		// Main candlestick chart
		if (mainChartContainer) {
			mainChart = createChart(mainChartContainer, {
				...chartOptions,
				width: mainChartContainer.clientWidth,
				height: 300,
			});

			const candlestickSeries = mainChart.addCandlestickSeries({
				upColor: '#3fb950',
				downColor: '#f85149',
				borderUpColor: '#3fb950',
				borderDownColor: '#f85149',
				wickUpColor: '#3fb950',
				wickDownColor: '#f85149',
			});

			candlestickSeries.setData(chartData.candles);

			// Volume
			const volumeSeries = mainChart.addHistogramSeries({
				color: '#58a6ff',
				priceFormat: { type: 'volume' },
				priceScaleId: '',
			});
			volumeSeries.priceScale().applyOptions({
				scaleMargins: { top: 0.8, bottom: 0 },
			});
			volumeSeries.setData(
				chartData.candles.map((c) => ({
					time: c.time,
					value: c.volume,
					color: c.close >= c.open ? 'rgba(63, 185, 80, 0.3)' : 'rgba(248, 81, 73, 0.3)',
				}))
			);

			mainChart.timeScale().fitContent();
		}

		// RSI chart
		if (rsiChartContainer && chartData.rsi.length > 0) {
			rsiChart = createChart(rsiChartContainer, {
				...chartOptions,
				width: rsiChartContainer.clientWidth,
				height: 120,
			});

			const rsiSeries = rsiChart.addLineSeries({
				color: '#a371f7',
				lineWidth: 2,
			});
			rsiSeries.setData(chartData.rsi);

			// RSI levels (30, 70)
			rsiSeries.createPriceLine({ price: 70, color: '#f85149', lineWidth: 1, lineStyle: 2, title: '과매수' });
			rsiSeries.createPriceLine({ price: 30, color: '#3fb950', lineWidth: 1, lineStyle: 2, title: '과매도' });

			rsiChart.timeScale().fitContent();
		}

		// MACD chart
		if (macdChartContainer && chartData.macd.length > 0) {
			macdChart = createChart(macdChartContainer, {
				...chartOptions,
				width: macdChartContainer.clientWidth,
				height: 120,
			});

			// MACD line
			const macdLineSeries = macdChart.addLineSeries({
				color: '#58a6ff',
				lineWidth: 2,
			});
			macdLineSeries.setData(chartData.macd.map((m) => ({ time: m.time, value: m.macd })));

			// Signal line
			const signalSeries = macdChart.addLineSeries({
				color: '#f0883e',
				lineWidth: 1,
			});
			signalSeries.setData(
				chartData.macd.filter((m) => m.signal !== null).map((m) => ({ time: m.time, value: m.signal }))
			);

			// Histogram
			const histogramSeries = macdChart.addHistogramSeries({
				color: '#3fb950',
			});
			histogramSeries.setData(
				chartData.macd
					.filter((m) => m.histogram !== null)
					.map((m) => ({
						time: m.time,
						value: m.histogram,
						color: m.histogram! >= 0 ? 'rgba(63, 185, 80, 0.5)' : 'rgba(248, 81, 73, 0.5)',
					}))
			);

			macdChart.timeScale().fitContent();
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
	<button class="btn-back" onclick={() => goto('/watchlist')}>← 뒤로</button>

	<div class="header">
		<div class="ticker-info">
			<h1>{ticker}</h1>
			{#if chartData}
				<span class="current-price">{formatCurrency(chartData.current_price)}</span>
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
		<!-- Summary -->
		<div class="summary card">
			<div class="indicator">
				<span class="label">
					RSI
					<span class="tooltip-icon" title="RSI 70↑ 과매수(매도 고려), 30↓ 과매도(매수 고려)">?</span>
				</span>
				<span class="value" class:overbought={chartData.summary.rsi && chartData.summary.rsi >= 70} class:oversold={chartData.summary.rsi && chartData.summary.rsi <= 30}>
					{chartData.summary.rsi ?? '-'}
				</span>
				<span class="signal">{chartData.summary.rsi_signal}</span>
			</div>
			<div class="indicator">
				<span class="label">
					MACD
					<span class="tooltip-icon" title="MACD > Signal = 상승추세, 골든크로스 = 매수신호">?</span>
				</span>
				<span class="value">{chartData.summary.macd ?? '-'}</span>
				<span class="signal-value">Signal: {chartData.summary.macd_signal ?? '-'}</span>
			</div>
		</div>

		<!-- Charts -->
		<div class="chart-section">
			<div class="chart-title">캔들스틱</div>
			<div class="chart-container" bind:this={mainChartContainer}></div>
		</div>

		<div class="chart-section">
			<div class="chart-title">
				RSI (14)
				<span class="tooltip-icon" title="상대강도지수: 14일간 가격 변동의 강도 측정. 70 이상 과매수, 30 이하 과매도">?</span>
			</div>
			<div class="chart-container rsi-chart" bind:this={rsiChartContainer}></div>
		</div>

		<div class="chart-section">
			<div class="chart-title">
				MACD (12, 26, 9)
				<span class="tooltip-icon" title="이동평균수렴확산: 단기(12일)와 장기(26일) EMA 차이. 시그널선(9일 EMA)과 교차 시 매매 신호">?</span>
			</div>
			<div class="chart-container macd-chart" bind:this={macdChartContainer}></div>
		</div>
	{/if}
</div>

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
		align-items: baseline;
		gap: 0.75rem;
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
		display: flex;
		align-items: center;
		gap: 0.25rem;
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

	.indicator .signal-value {
		font-size: 0.7rem;
		color: #8b949e;
	}

	.tooltip-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 14px;
		height: 14px;
		background: #30363d;
		border-radius: 50%;
		font-size: 0.6rem;
		color: #8b949e;
		cursor: help;
	}

	.chart-section {
		margin-bottom: 1rem;
	}

	.chart-title {
		font-size: 0.85rem;
		color: #8b949e;
		margin-bottom: 0.5rem;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.chart-container {
		background: #0d1117;
		border: 1px solid #30363d;
		border-radius: 8px;
		overflow: hidden;
		min-height: 300px;
	}

	.chart-container.rsi-chart {
		min-height: 120px;
	}

	.chart-container.macd-chart {
		min-height: 120px;
	}
</style>
