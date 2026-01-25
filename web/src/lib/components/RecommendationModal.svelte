<script lang="ts">
	import Icon from './Icons.svelte';
	import ReportProgress from './ReportProgress.svelte';

	const API_URL = import.meta.env.VITE_API_URL || 'https://stock-api.sean8320.dedyn.io';

	interface SplitEntry {
		price: number;
		pct: number;
		label: string;
	}

	interface Recommendation {
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
		recommendation_reason?: string;
		rating?: string;
		rr_ratio?: number;
		split_entries?: SplitEntry[];
	}

	interface ReportStatus {
		job_id: string;
		status: 'pending' | 'running' | 'completed' | 'failed';
		progress: number;
		current_step: string | null;
		error_message: string | null;
		pdf_path: string | null;
	}

	interface Props {
		recommendation: Recommendation | null;
		onClose: () => void;
		formatCurrency: (value: number) => string;
		onAddToWatchlist?: (ticker: string) => void;
		watchlistTickers?: string[];
	}

	let { recommendation, onClose, formatCurrency, onAddToWatchlist, watchlistTickers = [] }: Props = $props();

	let adding = $state(false);
	let generatingReport = $state(false);
	let reportStatus = $state<ReportStatus | null>(null);
	let showReportProgress = $state(false);
	let pollingInterval: ReturnType<typeof setInterval> | null = null;

	function isInWatchlist(ticker: string): boolean {
		return watchlistTickers.includes(ticker);
	}

	async function handleAddToWatchlist() {
		if (!recommendation || !onAddToWatchlist) return;
		adding = true;
		await onAddToWatchlist(recommendation.ticker);
		adding = false;
	}

	function handleBackdropClick(e: MouseEvent) {
		if (e.target === e.currentTarget) {
			onClose();
		}
	}

	function getRatingColor(rating: string): string {
		if (rating === '★★★') return '#ffd700';
		if (rating === '★★') return '#f0883e';
		return '#8b949e';
	}

	function getRsiStatus(rsi: number): { label: string; color: string } {
		if (rsi < 30) return { label: '과매도', color: '#3fb950' };
		if (rsi > 70) return { label: '과매수', color: '#f85149' };
		return { label: '중립', color: '#8b949e' };
	}

	async function startReportGeneration() {
		if (!recommendation) return;

		const token = localStorage.getItem('access_token');
		if (!token) {
			alert('로그인이 필요합니다');
			return;
		}

		generatingReport = true;
		showReportProgress = true;

		try {
			const res = await fetch(`${API_URL}/api/reports/generate`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${token}`
				},
				body: JSON.stringify({
					ticker: recommendation.ticker,
					include_portfolio: true
				})
			});

			if (!res.ok) {
				const err = await res.json();
				throw new Error(err.detail || '리포트 생성 실패');
			}

			const data = await res.json();
			reportStatus = {
				job_id: data.job_id,
				status: 'running',
				progress: 0,
				current_step: '시작',
				error_message: null,
				pdf_path: null
			};

			// 2초마다 폴링 시작
			startPolling(data.job_id);
		} catch (e) {
			generatingReport = false;
			alert(e instanceof Error ? e.message : '리포트 생성 실패');
		}
	}

	function startPolling(jobId: string) {
		if (pollingInterval) clearInterval(pollingInterval);

		pollingInterval = setInterval(async () => {
			await checkReportStatus(jobId);
		}, 2000);
	}

	async function checkReportStatus(jobId: string) {
		const token = localStorage.getItem('access_token');
		if (!token) return;

		try {
			const res = await fetch(`${API_URL}/api/reports/${jobId}/status`, {
				headers: { Authorization: `Bearer ${token}` }
			});

			if (!res.ok) return;

			const status: ReportStatus = await res.json();
			reportStatus = status;

			if (status.status === 'completed' || status.status === 'failed') {
				stopPolling();
				generatingReport = false;
			}
		} catch {
			// 네트워크 오류 무시
		}
	}

	function stopPolling() {
		if (pollingInterval) {
			clearInterval(pollingInterval);
			pollingInterval = null;
		}
	}

	async function downloadReport() {
		if (!reportStatus?.job_id) return;

		const token = localStorage.getItem('access_token');
		if (!token) return;

		try {
			const res = await fetch(`${API_URL}/api/reports/${reportStatus.job_id}/download`, {
				headers: { Authorization: `Bearer ${token}` }
			});

			if (!res.ok) throw new Error('다운로드 실패');

			const blob = await res.blob();
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = `${recommendation?.ticker}_report.pdf`;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			URL.revokeObjectURL(url);
		} catch {
			alert('PDF 다운로드 실패');
		}
	}

	function closeReportProgress() {
		showReportProgress = false;
		stopPolling();
	}

	// 컴포넌트 언마운트 시 폴링 정리
	$effect(() => {
		return () => {
			stopPolling();
		};
	});
</script>

{#if recommendation}
	<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
	<div class="modal-backdrop" onclick={handleBackdropClick}>
		<div class="modal">
			<button class="close-btn" onclick={onClose}>
				<Icon name="x" size={20} />
			</button>

			<div class="modal-header">
				<div class="ticker-row">
					<h2>{recommendation.ticker}</h2>
					{#if recommendation.rating}
						<span class="rating" style="color: {getRatingColor(recommendation.rating)}">
							{recommendation.rating}
						</span>
					{/if}
				</div>
				{#if recommendation.company_name}
					<p class="company">{recommendation.company_name}</p>
				{/if}
				{#if recommendation.sector}
					<span class="sector-badge">{recommendation.sector}</span>
				{/if}
			</div>

			{#if recommendation.recommendation_reason}
				<div class="section">
					<h3><Icon name="info" size={16} /> AI 분석</h3>
					<p class="reason-text">{recommendation.recommendation_reason}</p>
				</div>
			{/if}

			<div class="section">
				<h3><Icon name="chart" size={16} /> 기술적 지표</h3>
				<div class="indicators">
					{#if recommendation.rsi}
						{@const rsiStatus = getRsiStatus(recommendation.rsi)}
						<div class="indicator">
							<span class="ind-label">RSI</span>
							<span class="ind-value">{recommendation.rsi.toFixed(1)}</span>
							<span class="ind-status" style="color: {rsiStatus.color}">{rsiStatus.label}</span>
						</div>
					{/if}
					{#if recommendation.macd_cross}
						<div class="indicator">
							<span class="ind-label">MACD</span>
							<span class="ind-value" class:golden={recommendation.macd_cross === 'golden'} class:dead={recommendation.macd_cross === 'dead'}>
								{recommendation.macd_cross === 'golden' ? '골든크로스' : recommendation.macd_cross === 'dead' ? '데드크로스' : '중립'}
							</span>
						</div>
					{/if}
					{#if recommendation.news_score}
						<div class="indicator">
							<span class="ind-label">뉴스</span>
							<span class="ind-value">{recommendation.news_score}</span>
							<span class="ind-status" style="color: {recommendation.news_score > 5 ? '#3fb950' : '#8b949e'}">
								{recommendation.news_score > 5 ? '호재' : '중립'}
							</span>
						</div>
					{/if}
					{#if recommendation.rr_ratio}
						<div class="indicator">
							<span class="ind-label">R:R</span>
							<span class="ind-value">{recommendation.rr_ratio}</span>
							<span class="ind-status" style="color: {recommendation.rr_ratio >= 1.5 ? '#3fb950' : '#f0883e'}">
								{recommendation.rr_ratio >= 1.5 ? '양호' : '주의'}
							</span>
						</div>
					{/if}
				</div>
			</div>

			<div class="section">
				<h3><Icon name="dollar" size={16} /> 가격 분석</h3>
				<div class="price-grid">
					<div class="price-box current">
						<span class="box-label">현재가</span>
						<span class="box-value">{formatCurrency(recommendation.current_price)}</span>
					</div>
					<div class="price-box entry">
						<span class="box-label">추천 매수가</span>
						<span class="box-value">{formatCurrency(recommendation.recommended_entry)}</span>
					</div>
					<div class="price-box stop">
						<span class="box-label">손절가</span>
						<span class="box-value">{formatCurrency(recommendation.stop_loss)}</span>
					</div>
					<div class="price-box target">
						<span class="box-label">목표가</span>
						<span class="box-value">{formatCurrency(recommendation.target)}</span>
					</div>
				</div>
			</div>

			{#if recommendation.split_entries && recommendation.split_entries.length > 0}
				<div class="section">
					<h3><Icon name="layers" size={16} /> 분할매수 제안</h3>
					<div class="split-grid">
						{#each recommendation.split_entries as entry, i}
							<div class="split-box">
								<span class="split-num">{i + 1}차</span>
								<span class="split-price">{formatCurrency(entry.price)}</span>
								<span class="split-pct">{entry.pct}%</span>
								<span class="split-label">{entry.label}</span>
							</div>
						{/each}
					</div>
				</div>
			{/if}

			<div class="modal-footer">
				<button
					class="btn-report"
					onclick={startReportGeneration}
					disabled={generatingReport}
				>
					<Icon name="file" size={16} />
					{generatingReport ? '생성 중...' : '리포트'}
				</button>
				{#if onAddToWatchlist}
					<button
						class="btn-watchlist"
						onclick={handleAddToWatchlist}
						disabled={adding || isInWatchlist(recommendation.ticker)}
					>
						<Icon name="star" size={16} />
						{#if isInWatchlist(recommendation.ticker)}
							추가됨
						{:else if adding}
							추가 중...
						{:else}
							관심종목
						{/if}
					</button>
				{/if}
				<a href="/stock/{recommendation.ticker}" class="btn-chart">
					<Icon name="chart" size={16} /> 차트 보기
				</a>
			</div>
		</div>
	</div>
{/if}

{#if showReportProgress && reportStatus}
	<ReportProgress
		progress={reportStatus.progress}
		currentStep={reportStatus.current_step || ''}
		status={reportStatus.status}
		errorMessage={reportStatus.error_message || undefined}
		onClose={closeReportProgress}
		onDownload={reportStatus.status === 'completed' ? downloadReport : undefined}
	/>
{/if}

<style>
	.modal-backdrop {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.8);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: 1rem;
	}

	.modal {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 16px;
		width: 100%;
		max-width: 400px;
		max-height: 85vh;
		overflow-y: auto;
		position: relative;
	}

	.close-btn {
		position: absolute;
		top: 0.75rem;
		right: 0.75rem;
		background: none;
		border: none;
		color: #8b949e;
		cursor: pointer;
		padding: 0.25rem;
		border-radius: 4px;
		transition: all 0.15s;
	}

	.close-btn:hover {
		background: #21262d;
		color: #f0f6fc;
	}

	.modal-header {
		padding: 1.25rem 1.25rem 0;
	}

	.ticker-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	h2 {
		margin: 0;
		font-size: 1.5rem;
		color: #58a6ff;
	}

	.rating {
		font-size: 1.25rem;
	}

	.company {
		margin: 0.25rem 0 0.5rem;
		color: #8b949e;
		font-size: 0.85rem;
	}

	.sector-badge {
		display: inline-block;
		font-size: 0.7rem;
		background: #21262d;
		color: #a371f7;
		padding: 0.2rem 0.5rem;
		border-radius: 4px;
	}

	.section {
		padding: 1rem 1.25rem;
		border-top: 1px solid #21262d;
	}

	h3 {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		margin: 0 0 0.75rem;
		font-size: 0.9rem;
		color: #f0f6fc;
		font-weight: 600;
	}

	.reason-text {
		margin: 0;
		font-size: 0.85rem;
		color: #c9d1d9;
		line-height: 1.6;
		padding: 0.75rem;
		background: #0d1117;
		border-radius: 8px;
		border-left: 3px solid #58a6ff;
	}

	.indicators {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 0.5rem;
	}

	.indicator {
		background: #0d1117;
		padding: 0.6rem;
		border-radius: 8px;
		text-align: center;
	}

	.ind-label {
		display: block;
		font-size: 0.65rem;
		color: #8b949e;
		margin-bottom: 0.2rem;
	}

	.ind-value {
		display: block;
		font-size: 1rem;
		font-weight: 600;
		color: #f0f6fc;
	}

	.ind-value.golden {
		color: #3fb950;
	}

	.ind-value.dead {
		color: #f85149;
	}

	.ind-status {
		display: block;
		font-size: 0.65rem;
		margin-top: 0.1rem;
	}

	.price-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 0.5rem;
	}

	.price-box {
		padding: 0.6rem;
		border-radius: 8px;
		text-align: center;
		background: #0d1117;
	}

	.box-label {
		display: block;
		font-size: 0.65rem;
		color: #8b949e;
		margin-bottom: 0.2rem;
	}

	.box-value {
		font-size: 0.95rem;
		font-weight: 600;
		color: #f0f6fc;
	}

	.price-box.entry {
		border: 1px solid #58a6ff;
	}

	.price-box.entry .box-value {
		color: #58a6ff;
	}

	.price-box.stop {
		border: 1px solid #f85149;
	}

	.price-box.stop .box-value {
		color: #f85149;
	}

	.price-box.target {
		border: 1px solid #3fb950;
	}

	.price-box.target .box-value {
		color: #3fb950;
	}

	.split-grid {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.split-box {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		background: #0d1117;
		padding: 0.6rem 0.75rem;
		border-radius: 8px;
	}

	.split-num {
		font-size: 0.75rem;
		color: #a371f7;
		font-weight: 600;
		min-width: 2rem;
	}

	.split-price {
		font-size: 0.9rem;
		font-weight: 600;
		color: #f0f6fc;
		flex: 1;
	}

	.split-pct {
		font-size: 0.8rem;
		color: #58a6ff;
		font-weight: 600;
	}

	.split-label {
		font-size: 0.7rem;
		color: #8b949e;
	}

	.modal-footer {
		padding: 1rem 1.25rem 1.25rem;
		border-top: 1px solid #21262d;
		display: flex;
		gap: 0.5rem;
	}

	.btn-report {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.4rem;
		flex: 1;
		padding: 0.75rem;
		background: #8b5cf6;
		color: white;
		border: none;
		border-radius: 8px;
		font-size: 0.9rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.15s;
	}

	.btn-report:hover:not(:disabled) {
		background: #7c3aed;
	}

	.btn-report:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-watchlist {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.4rem;
		flex: 1;
		padding: 0.75rem;
		background: #21262d;
		color: #f0f6fc;
		border: 1px solid #30363d;
		border-radius: 8px;
		font-size: 0.9rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.15s;
	}

	.btn-watchlist:hover:not(:disabled) {
		background: #30363d;
		border-color: #58a6ff;
	}

	.btn-watchlist:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-chart {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.4rem;
		flex: 1;
		padding: 0.75rem;
		background: #238636;
		color: white;
		border: none;
		border-radius: 8px;
		font-size: 0.9rem;
		font-weight: 600;
		text-decoration: none;
		transition: all 0.15s;
	}

	.btn-chart:hover {
		background: #2ea043;
	}
</style>
