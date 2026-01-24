<script lang="ts">
	let shares = $state('');
	let buyPrice = $state('');
	let targetPrice = $state('');
	let stopLoss = $state('');
	let exchangeRate = $state('1450');

	let result = $derived.by(() => {
		const s = parseFloat(shares) || 0;
		const bp = parseFloat(buyPrice) || 0;
		const tp = parseFloat(targetPrice) || 0;
		const sl = parseFloat(stopLoss) || 0;
		const er = parseFloat(exchangeRate) || 1450;

		if (!s || !bp) return null;

		const cost = s * bp;
		const targetValue = tp ? s * tp : 0;
		const stopValue = sl ? s * sl : 0;
		const targetGain = targetValue - cost;
		const stopGain = stopValue - cost;

		const targetGainKrw = targetGain * er;
		const taxableKrw = Math.max(0, targetGainKrw - 2500000);
		const taxKrw = Math.round(taxableKrw * 0.22);
		const netGainKrw = targetGainKrw - taxKrw;

		return {
			cost,
			targetValue,
			stopValue,
			targetGain,
			targetGainPct: bp ? (targetGain / cost * 100) : 0,
			stopGain,
			stopGainPct: bp ? (stopGain / cost * 100) : 0,
			riskReward: targetGain && stopGain ? Math.abs(targetGain / stopGain) : 0,
			targetGainKrw,
			taxKrw,
			netGainKrw,
		};
	});

	function formatUSD(value: number): string {
		return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	}

	function formatKRW(value: number): string {
		return Math.round(value).toLocaleString('ko-KR') + '원';
	}

	function formatPct(value: number): string {
		const sign = value >= 0 ? '+' : '';
		return sign + value.toFixed(1) + '%';
	}
</script>

<svelte:head>
	<title>익절 계산기 - 주식 대시보드</title>
</svelte:head>

<div class="container">
	<h1>🧮 익절 계산기</h1>

	<div class="card">
		<div class="form-row">
			<div class="form-group">
				<label>수량</label>
				<input type="number" step="1" placeholder="100" bind:value={shares} />
			</div>
			<div class="form-group">
				<label>매수가 ($)</label>
				<input type="number" step="0.01" placeholder="10.00" bind:value={buyPrice} />
			</div>
		</div>
		<div class="form-row">
			<div class="form-group">
				<label>목표가 ($)</label>
				<input type="number" step="0.01" placeholder="15.00" bind:value={targetPrice} />
			</div>
			<div class="form-group">
				<label>손절가 ($)</label>
				<input type="number" step="0.01" placeholder="8.00" bind:value={stopLoss} />
			</div>
		</div>
		<div class="form-group">
			<label>환율 ($/원)</label>
			<input type="number" step="1" bind:value={exchangeRate} />
		</div>
	</div>

	{#if result}
		<div class="results">
			<div class="card result-card">
				<h3>투자 금액</h3>
				<div class="value">{formatUSD(result.cost)}</div>
			</div>

			{#if result.targetValue}
				<div class="card result-card positive">
					<h3>익절 시</h3>
					<div class="value">{formatUSD(result.targetGain)}</div>
					<div class="sub">{formatPct(result.targetGainPct)}</div>
				</div>
			{/if}

			{#if result.stopValue}
				<div class="card result-card negative">
					<h3>손절 시</h3>
					<div class="value">{formatUSD(result.stopGain)}</div>
					<div class="sub">{formatPct(result.stopGainPct)}</div>
				</div>
			{/if}

			{#if result.riskReward > 0}
				<div class="card result-card">
					<h3>손익비</h3>
					<div class="value">1 : {result.riskReward.toFixed(1)}</div>
				</div>
			{/if}

			{#if result.targetGainKrw > 0}
				<div class="card tax-card">
					<h3>세금 계산 (익절 시)</h3>
					<div class="tax-row">
						<span>원화 수익</span>
						<span>{formatKRW(result.targetGainKrw)}</span>
					</div>
					<div class="tax-row">
						<span>예상 세금 (22%)</span>
						<span class="neg">{formatKRW(result.taxKrw)}</span>
					</div>
					<div class="tax-row highlight">
						<span>세후 순수익</span>
						<span class="pos">{formatKRW(result.netGainKrw)}</span>
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.container {
		max-width: 500px;
		margin: 0 auto;
		padding: 1rem;
	}

	h1 {
		font-size: 1.5rem;
		margin-bottom: 1rem;
	}

	.card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 12px;
		padding: 1rem;
		margin-bottom: 0.75rem;
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

	.results {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.75rem;
	}

	.result-card {
		text-align: center;
	}

	.result-card h3 {
		font-size: 0.7rem;
		color: #8b949e;
		margin: 0 0 0.5rem;
		text-transform: uppercase;
	}

	.result-card .value {
		font-size: 1.25rem;
		font-weight: 700;
	}

	.result-card .sub {
		font-size: 0.85rem;
		margin-top: 0.25rem;
	}

	.result-card.positive .value,
	.result-card.positive .sub {
		color: #3fb950;
	}

	.result-card.negative .value,
	.result-card.negative .sub {
		color: #f85149;
	}

	.tax-card {
		grid-column: span 2;
	}

	.tax-card h3 {
		font-size: 0.75rem;
		color: #8b949e;
		margin: 0 0 0.75rem;
	}

	.tax-row {
		display: flex;
		justify-content: space-between;
		padding: 0.375rem 0;
		font-size: 0.85rem;
	}

	.tax-row.highlight {
		border-top: 1px solid #30363d;
		padding-top: 0.5rem;
		margin-top: 0.25rem;
		font-weight: 600;
	}

	.pos {
		color: #3fb950;
	}

	.neg {
		color: #f85149;
	}
</style>
