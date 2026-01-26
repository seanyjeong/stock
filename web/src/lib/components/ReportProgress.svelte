<script lang="ts">
	import { onDestroy } from 'svelte';

	interface Props {
		progress: number;
		currentStep: string;
		status: 'pending' | 'running' | 'completed' | 'failed';
		onClose?: () => void;
		onDownload?: () => void;
		errorMessage?: string;
	}

	let { progress, currentStep, status, onClose, onDownload, errorMessage }: Props = $props();

	// 부드러운 진행률 보간
	let displayProgress = $state(0);
	let interpolationInterval: ReturnType<typeof setInterval> | null = null;

	$effect(() => {
		const target = progress;
		if (interpolationInterval) clearInterval(interpolationInterval);
		interpolationInterval = setInterval(() => {
			if (displayProgress < target) {
				displayProgress = Math.min(displayProgress + 1, target);
			} else {
				if (interpolationInterval) clearInterval(interpolationInterval);
			}
		}, 80);
	});

	onDestroy(() => {
		if (interpolationInterval) clearInterval(interpolationInterval);
	});

	// SVG 원형 프로그레스바 계산
	const radius = 45;
	const circumference = 2 * Math.PI * radius;
	const strokeDashoffset = $derived(circumference - (displayProgress / 100) * circumference);

	function getStatusColor(): string {
		switch (status) {
			case 'completed':
				return '#22c55e';
			case 'failed':
				return '#ef4444';
			default:
				return '#3b82f6';
		}
	}

	function getStatusText(): string {
		switch (status) {
			case 'pending':
				return '대기 중...';
			case 'running':
				return currentStep || '분석 중...';
			case 'completed':
				return '완료!';
			case 'failed':
				return '실패';
			default:
				return '';
		}
	}
</script>

<div class="progress-overlay">
	<div class="progress-modal">
		{#if onClose}
			<button class="close-btn" onclick={onClose}>
				<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path d="M18 6L6 18M6 6l12 12" />
				</svg>
			</button>
		{/if}

		<div class="progress-circle">
			<svg width="120" height="120" viewBox="0 0 100 100">
				<!-- 배경 원 -->
				<circle
					cx="50"
					cy="50"
					r={radius}
					fill="none"
					stroke="#21262d"
					stroke-width="8"
				/>
				<!-- 진행 원 -->
				<circle
					cx="50"
					cy="50"
					r={radius}
					fill="none"
					stroke={getStatusColor()}
					stroke-width="8"
					stroke-linecap="round"
					stroke-dasharray={circumference}
					stroke-dashoffset={strokeDashoffset}
					transform="rotate(-90 50 50)"
					class="progress-ring"
				/>
			</svg>
			<div class="progress-text">
				<span class="progress-value">{displayProgress}%</span>
			</div>
		</div>

		<div class="status-info">
			<p class="status-text" class:completed={status === 'completed'} class:failed={status === 'failed'}>
				{getStatusText()}
			</p>

			{#if status === 'failed' && errorMessage}
				<p class="error-text">{errorMessage}</p>
			{/if}
		</div>

		{#if status === 'completed' && onDownload}
			<button class="download-btn" onclick={onDownload}>
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
				</svg>
				PDF 다운로드
			</button>
		{/if}

		{#if status === 'running'}
			<p class="hint-text">약 1분 정도 소요됩니다. 다른 페이지로 이동해도 계속 진행됩니다.</p>
		{/if}
	</div>
</div>

<style>
	.progress-overlay {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.85);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1100;
		padding: 1rem;
	}

	.progress-modal {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 16px;
		padding: 2rem;
		text-align: center;
		position: relative;
		min-width: 280px;
		max-width: 320px;
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

	.progress-circle {
		position: relative;
		display: inline-block;
		margin-bottom: 1.5rem;
	}

	.progress-ring {
		transition: stroke-dashoffset 0.3s ease;
	}

	.progress-text {
		position: absolute;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		text-align: center;
	}

	.progress-value {
		font-size: 1.75rem;
		font-weight: 700;
		color: #f0f6fc;
	}

	.status-info {
		margin-bottom: 1rem;
	}

	.status-text {
		font-size: 0.95rem;
		color: #8b949e;
		margin: 0;
		min-height: 1.5em;
	}

	.status-text.completed {
		color: #22c55e;
		font-weight: 600;
	}

	.status-text.failed {
		color: #ef4444;
		font-weight: 600;
	}

	.error-text {
		font-size: 0.8rem;
		color: #f85149;
		margin-top: 0.5rem;
		padding: 0.5rem;
		background: rgba(248, 81, 73, 0.1);
		border-radius: 6px;
	}

	.download-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		width: 100%;
		padding: 0.875rem 1.5rem;
		background: #238636;
		color: white;
		border: none;
		border-radius: 8px;
		font-size: 0.95rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.15s;
	}

	.download-btn:hover {
		background: #2ea043;
	}

	.hint-text {
		font-size: 0.75rem;
		color: #6e7681;
		margin-top: 1rem;
	}
</style>
