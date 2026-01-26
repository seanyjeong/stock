<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import ReportProgress from '$lib/components/ReportProgress.svelte';

	interface WatchlistItem {
		id: number;
		ticker: string;
		company_name?: string | null;
		note: string | null;
		target_price: number | null;
		alert_price: number | null;
		folder_id: number | null;
		folder_name: string | null;
		folder_color: string | null;
		current_price: number | null;
		regular_price: number | null;
		afterhours_price: number | null;
		premarket_price: number | null;
		target_diff_pct: number | null;
		created_at: string | null;
		rsi?: number | null;
		rsi_signal?: string | null;
		macd_trend?: string | null;
	}

	interface Folder {
		id: number;
		name: string;
		color: string;
		is_default: boolean;
		item_count: number;
	}

	interface SelectedTickerInfo {
		symbol: string;
		name: string;
		current_price: number | null;
		rsi: number | null;
		rsi_signal: string | null;
		macd_trend: string | null;
	}

	let watchlist = $state<WatchlistItem[]>([]);
	let folders = $state<Folder[]>([]);
	let selectedFolderId = $state<number | null>(null); // null = 전체
	let unfiledCount = $state(0);
	let isLoading = $state(true);
	let error = $state('');

	// Add form
	let showAddForm = $state(false);
	let ticker = $state('');
	let note = $state('');
	let targetPrice = $state('');
	let alertPrice = $state('');
	let addFolderId = $state<number | null>(null);
	let isSubmitting = $state(false);
	let selectedInfo = $state<SelectedTickerInfo | null>(null);
	let isLoadingInfo = $state(false);

	// Folder management
	let showFolderForm = $state(false);
	let newFolderName = $state('');
	let newFolderColor = $state('#3b82f6');

	// Search
	let searchQuery = $state('');
	let searchResults = $state<Array<{symbol: string; name: string}>>([]);
	let isSearching = $state(false);
	let searchTimeout: ReturnType<typeof setTimeout>;

	// Report generation
	let showReportProgress = $state(false);
	let reportJobId = $state('');
	let reportProgress = $state(0);
	let reportStep = $state('');
	let reportStatus = $state<'pending' | 'running' | 'completed' | 'failed'>('pending');
	let reportError = $state('');
	let reportTicker = $state('');
	let pollInterval: ReturnType<typeof setInterval> | null = null;

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	onMount(async () => {
		await Promise.all([loadWatchlist(), loadFolders()]);
	});

	async function loadFolders() {
		try {
			const response = await fetch(`${API_BASE}/api/watchlist/folders`, {
				headers: getAuthHeaders(),
			});
			if (response.ok) {
				const data = await response.json();
				folders = data.folders;
				unfiledCount = data.unfiled_count;
			}
		} catch {
			// Ignore
		}
	}

	function getAuthHeaders(): Record<string, string> {
		const token = localStorage.getItem('access_token');
		if (!token) {
			goto('/login');
			return { 'Content-Type': 'application/json' };
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

	async function selectTicker(symbol: string, name: string) {
		ticker = symbol;
		searchQuery = symbol;
		searchResults = [];
		selectedInfo = null;
		isLoadingInfo = true;

		try {
			const response = await fetch(`${API_BASE}/api/indicators/${symbol}`, {
				headers: getAuthHeaders(),
			});
			if (response.ok) {
				const data = await response.json();
				selectedInfo = {
					symbol,
					name,
					current_price: data.current_price,
					rsi: data.rsi?.value,
					rsi_signal: data.rsi?.signal,
					macd_trend: data.macd?.trend
				};
			}
		} catch {
			selectedInfo = { symbol, name, current_price: null, rsi: null, rsi_signal: null, macd_trend: null };
		} finally {
			isLoadingInfo = false;
		}
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
					folder_id: addFolderId,
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
			addFolderId = null;

			await Promise.all([loadWatchlist(), loadFolders()]);
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

	// Report generation
	async function generateReport(ticker: string) {
		const token = localStorage.getItem('access_token');
		if (!token) {
			alert('로그인이 필요합니다');
			return;
		}

		reportTicker = ticker;
		reportProgress = 0;
		reportStep = '시작 중...';
		reportStatus = 'pending';
		reportError = '';
		showReportProgress = true;

		try {
			const response = await fetch(`${API_BASE}/api/reports/generate`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'Authorization': `Bearer ${token}`
				},
				body: JSON.stringify({ ticker, include_portfolio: true })
			});

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '리포트 생성 실패');
			}

			const data = await response.json();
			reportJobId = data.job_id;
			reportStatus = 'running';
			startPolling(token);
		} catch (e) {
			reportStatus = 'failed';
			reportError = e instanceof Error ? e.message : '오류 발생';
		}
	}

	function startPolling(token: string) {
		if (pollInterval) clearInterval(pollInterval);
		pollInterval = setInterval(() => pollStatus(token), 2000);
	}

	async function pollStatus(token: string) {
		try {
			const response = await fetch(`${API_BASE}/api/reports/${reportJobId}/status`, {
				headers: { 'Authorization': `Bearer ${token}` }
			});

			if (response.ok) {
				const data = await response.json();
				reportProgress = data.progress;
				reportStep = data.current_step || '';
				reportStatus = data.status;

				if (data.status === 'completed' || data.status === 'failed') {
					if (pollInterval) {
						clearInterval(pollInterval);
						pollInterval = null;
					}
					if (data.status === 'failed') {
						reportError = data.error_message || '분석 실패';
					}
				}
			}
		} catch {
			// 무시
		}
	}

	async function downloadReport() {
		const token = localStorage.getItem('access_token');
		if (!token || !reportJobId) return;

		try {
			const response = await fetch(`${API_BASE}/api/reports/${reportJobId}/download`, {
				headers: { 'Authorization': `Bearer ${token}` }
			});

			if (response.ok) {
				const blob = await response.blob();
				const url = window.URL.createObjectURL(blob);
				const a = document.createElement('a');
				a.href = url;
				a.download = `${reportTicker}_report.pdf`;
				document.body.appendChild(a);
				a.click();
				window.URL.revokeObjectURL(url);
				a.remove();
				closeReportModal();
			}
		} catch {
			alert('다운로드 실패');
		}
	}

	function closeReportModal() {
		showReportProgress = false;
		if (pollInterval) {
			clearInterval(pollInterval);
			pollInterval = null;
		}
	}

	onDestroy(() => {
		if (pollInterval) {
			clearInterval(pollInterval);
		}
	});

	// Filtered watchlist based on selected folder
	function getFilteredWatchlist(): WatchlistItem[] {
		if (selectedFolderId === null) return watchlist;
		if (selectedFolderId === -1) return watchlist.filter(item => !item.folder_id); // unfiled
		return watchlist.filter(item => item.folder_id === selectedFolderId);
	}

	async function createFolder() {
		if (!newFolderName.trim()) return;
		try {
			const response = await fetch(`${API_BASE}/api/watchlist/folders`, {
				method: 'POST',
				headers: getAuthHeaders(),
				body: JSON.stringify({ name: newFolderName, color: newFolderColor }),
			});
			if (response.ok) {
				newFolderName = '';
				showFolderForm = false;
				await loadFolders();
			} else {
				const data = await response.json();
				alert(data.detail || '폴더 생성 실패');
			}
		} catch {
			alert('폴더 생성 실패');
		}
	}

	async function deleteFolder(folderId: number) {
		if (!confirm('폴더를 삭제하시겠습니까? 종목은 삭제되지 않습니다.')) return;
		try {
			const response = await fetch(`${API_BASE}/api/watchlist/folders/${folderId}`, {
				method: 'DELETE',
				headers: getAuthHeaders(),
			});
			if (response.ok) {
				if (selectedFolderId === folderId) selectedFolderId = null;
				await Promise.all([loadFolders(), loadWatchlist()]);
			}
		} catch {
			alert('폴더 삭제 실패');
		}
	}
</script>

<svelte:head>
	<title>관심 종목 - 주식 대시보드</title>
</svelte:head>

<div class="container">
	<div class="header">
		<h1>Star 관심 종목</h1>
		<div class="header-buttons">
			<button class="btn-folder" onclick={() => showFolderForm = !showFolderForm} title="폴더 관리">
				+폴더
			</button>
			<button class="btn-add" onclick={() => showAddForm = !showAddForm}>
				{showAddForm ? '취소' : '+ 추가'}
			</button>
		</div>
	</div>

	<!-- Folder Tabs -->
	{#if folders.length > 0}
		<div class="folder-tabs">
			<button
				class="folder-tab"
				class:active={selectedFolderId === null}
				onclick={() => selectedFolderId = null}
			>
				전체 ({watchlist.length})
			</button>
			{#each folders as folder}
				<button
					class="folder-tab"
					class:active={selectedFolderId === folder.id}
					onclick={() => selectedFolderId = folder.id}
					style="--folder-color: {folder.color}"
				>
					{folder.name} ({folder.item_count})
					{#if !folder.is_default}
						<span class="folder-delete" onclick={(e) => { e.stopPropagation(); deleteFolder(folder.id); }}>×</span>
					{/if}
				</button>
			{/each}
			{#if unfiledCount > 0}
				<button
					class="folder-tab unfiled"
					class:active={selectedFolderId === -1}
					onclick={() => selectedFolderId = -1}
				>
					미분류 ({unfiledCount})
				</button>
			{/if}
		</div>
	{/if}

	<!-- New Folder Form -->
	{#if showFolderForm}
		<div class="folder-form card">
			<input
				type="text"
				placeholder="폴더 이름"
				bind:value={newFolderName}
				class="folder-input"
			/>
			<input type="color" bind:value={newFolderColor} class="folder-color" />
			<button class="btn-create-folder" onclick={createFolder}>생성</button>
			<button class="btn-cancel-folder" onclick={() => showFolderForm = false}>취소</button>
		</div>
	{/if}

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
							<button class="search-item" onclick={() => selectTicker(result.symbol, result.name)}>
								<span class="symbol">{result.symbol}</span>
								<span class="name">{result.name}</span>
							</button>
						{/each}
					</div>
				{/if}
			</div>
			{#if ticker}
				<div class="selected-ticker-card">
					<div class="ticker-header">
						<strong class="symbol">{ticker}</strong>
						{#if isLoadingInfo}
							<span class="loading-text">로딩...</span>
						{:else if selectedInfo}
							<span class="current-price">{formatCurrency(selectedInfo.current_price)}</span>
						{/if}
					</div>
					{#if selectedInfo && !isLoadingInfo}
						<div class="ticker-indicators">
							<div class="indicator" title="상대강도지수: 70이상 과매수(매도고려), 30이하 과매도(매수고려)">
								<span class="label">RSI</span>
								<span class="value" class:overbought={selectedInfo.rsi && selectedInfo.rsi >= 70} class:oversold={selectedInfo.rsi && selectedInfo.rsi <= 30}>
									{selectedInfo.rsi ?? '-'}
								</span>
								<span class="signal">{selectedInfo.rsi_signal ?? ''}</span>
							</div>
							<div class="indicator" title="이동평균수렴확산: 추세 방향과 전환점 파악">
								<span class="label">MACD</span>
								<span class="value">{selectedInfo.macd_trend ?? '-'}</span>
							</div>
						</div>
					{/if}
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
			{#if folders.length > 0}
				<div class="form-group">
					<label>폴더</label>
					<select bind:value={addFolderId} class="folder-select">
						<option value={null}>폴더 없음</option>
						{#each folders as folder}
							<option value={folder.id}>{folder.name}</option>
						{/each}
					</select>
				</div>
			{/if}
			<button class="btn-submit" onclick={addToWatchlist} disabled={isSubmitting || !ticker}>
				{isSubmitting ? '추가 중...' : '관심 종목 추가'}
			</button>
		</div>
	{/if}

	{#if isLoading}
		<div class="loading">로딩 중...</div>
	{:else}
		{@const filteredList = getFilteredWatchlist()}
		{#if filteredList.length > 0}
			<div class="watchlist">
				{#each filteredList as item}
					<div class="watchlist-card card">
						<div class="card-header">
							<div class="ticker-info">
								<div class="ticker-with-name">
									<a href="/stock/{item.ticker}" class="ticker">{item.ticker}</a>
									{#if item.company_name}
										<span class="company-name">{item.company_name}</span>
									{/if}
								</div>
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

						<div class="card-actions">
							<a href="/stock/{item.ticker}" class="btn-chart">차트</a>
							<button class="btn-report" onclick={() => generateReport(item.ticker)}>리포트</button>
							<button class="btn-delete" onclick={() => removeFromWatchlist(item)}>삭제</button>
						</div>
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

{#if showReportProgress}
	<ReportProgress
		progress={reportProgress}
		currentStep={reportStep}
		status={reportStatus}
		errorMessage={reportError}
		onClose={closeReportModal}
		onDownload={reportStatus === 'completed' ? downloadReport : undefined}
	/>
{/if}

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

	.selected-ticker-card {
		background: rgba(88, 166, 255, 0.1);
		border: 1px solid #58a6ff;
		padding: 0.75rem;
		border-radius: 8px;
		margin-bottom: 0.75rem;
	}

	.selected-ticker-card .ticker-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.selected-ticker-card .symbol {
		color: #58a6ff;
		font-size: 1.1rem;
	}

	.selected-ticker-card .current-price {
		font-size: 1.1rem;
		font-weight: 600;
	}

	.selected-ticker-card .loading-text {
		color: #8b949e;
		font-size: 0.8rem;
	}

	.ticker-indicators {
		display: flex;
		gap: 1rem;
		padding-top: 0.5rem;
		border-top: 1px solid rgba(88, 166, 255, 0.3);
	}

	.ticker-indicators .indicator {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.8rem;
	}

	.ticker-indicators .label {
		color: #8b949e;
	}

	.ticker-indicators .value {
		font-weight: 600;
	}

	.ticker-indicators .value.overbought {
		color: #f85149;
	}

	.ticker-indicators .value.oversold {
		color: #3fb950;
	}

	.ticker-indicators .signal {
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

	.watchlist {
		display: flex;
		flex-direction: column;
	}

	.watchlist-card {
		/* card styles inherited from .card */
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

	.ticker-with-name {
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}

	.ticker {
		font-weight: 700;
		font-size: 1.1rem;
		color: #58a6ff;
		text-decoration: none;
	}

	.company-name {
		font-size: 0.7rem;
		color: #8b949e;
		max-width: 140px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
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

	.card-actions {
		display: flex;
		gap: 0.5rem;
		margin-top: 0.75rem;
		padding-top: 0.75rem;
		border-top: 1px solid #21262d;
	}

	.btn-chart {
		flex: 1;
		padding: 0.5rem;
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 6px;
		font-size: 0.75rem;
		color: #58a6ff;
		text-decoration: none;
		text-align: center;
	}

	.btn-chart:hover {
		background: #30363d;
	}

	.btn-report {
		padding: 0.5rem 0.75rem;
		background: #1f6feb;
		border: none;
		border-radius: 6px;
		font-size: 0.75rem;
		color: white;
		cursor: pointer;
		font-weight: 500;
	}

	.btn-report:hover {
		background: #388bfd;
	}

	.btn-delete {
		padding: 0.5rem 0.75rem;
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

	/* Folder styles */
	.header-buttons {
		display: flex;
		gap: 0.5rem;
	}

	.btn-folder {
		padding: 0.5rem 0.75rem;
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 8px;
		color: #8b949e;
		font-size: 0.8rem;
		cursor: pointer;
	}

	.btn-folder:hover {
		border-color: #58a6ff;
		color: #58a6ff;
	}

	.folder-tabs {
		display: flex;
		gap: 0.5rem;
		overflow-x: auto;
		padding-bottom: 0.5rem;
		margin-bottom: 1rem;
		-webkit-overflow-scrolling: touch;
	}

	.folder-tab {
		flex-shrink: 0;
		padding: 0.5rem 0.75rem;
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 8px;
		color: #8b949e;
		font-size: 0.8rem;
		cursor: pointer;
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	.folder-tab:hover {
		border-color: #484f58;
	}

	.folder-tab.active {
		background: var(--folder-color, #238636);
		border-color: var(--folder-color, #238636);
		color: white;
	}

	.folder-tab.unfiled {
		--folder-color: #8b949e;
	}

	.folder-delete {
		margin-left: 0.25rem;
		opacity: 0.6;
		font-weight: bold;
	}

	.folder-delete:hover {
		opacity: 1;
		color: #f85149;
	}

	.folder-form {
		display: flex;
		gap: 0.5rem;
		align-items: center;
		padding: 0.75rem;
		margin-bottom: 1rem;
	}

	.folder-input {
		flex: 1;
		padding: 0.5rem;
		background: #0d1117;
		border: 1px solid #30363d;
		border-radius: 6px;
		color: #f0f6fc;
		font-size: 0.85rem;
	}

	.folder-color {
		width: 36px;
		height: 36px;
		padding: 0;
		border: none;
		border-radius: 6px;
		cursor: pointer;
	}

	.btn-create-folder {
		padding: 0.5rem 0.75rem;
		background: #238636;
		border: none;
		border-radius: 6px;
		color: white;
		font-size: 0.8rem;
		cursor: pointer;
	}

	.btn-cancel-folder {
		padding: 0.5rem 0.75rem;
		background: transparent;
		border: 1px solid #30363d;
		border-radius: 6px;
		color: #8b949e;
		font-size: 0.8rem;
		cursor: pointer;
	}

	.folder-select {
		width: 100%;
		padding: 0.75rem;
		background: #0d1117;
		border: 1px solid #30363d;
		border-radius: 8px;
		color: #f0f6fc;
		font-size: 0.9rem;
	}
</style>
