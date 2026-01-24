<script lang="ts">
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';

	let currentStep = $state(0);

	const steps = [
		{
			icon: '👋',
			title: '환영합니다!',
			description: '주식 대시보드에 오신 것을 환영합니다.\n포트폴리오와 추천 종목을 한눈에 확인하세요.',
		},
		{
			icon: '💰',
			title: '포트폴리오',
			description: '보유 종목의 현재가와 수익률을\n실시간으로 확인할 수 있습니다.',
		},
		{
			icon: '📊',
			title: '추천 종목',
			description: '단타, 스윙, 장기 투자 추천 종목을\n스캐너가 자동으로 분석합니다.',
		},
		{
			icon: '📋',
			title: 'RegSHO 리스트',
			description: 'NASDAQ RegSHO Threshold List를\n매일 자동으로 업데이트합니다.',
		},
		{
			icon: '📝',
			title: '블로거 인사이트',
			description: '유명 블로거의 종목 분석 글을\n티커와 키워드로 정리해 보여드립니다.',
		},
	];

	function nextStep() {
		if (currentStep < steps.length - 1) {
			currentStep++;
		} else {
			completeOnboarding();
		}
	}

	function prevStep() {
		if (currentStep > 0) {
			currentStep--;
		}
	}

	function skip() {
		completeOnboarding();
	}

	function completeOnboarding() {
		if (browser) {
			localStorage.setItem('onboarding_completed', 'true');
		}
		goto('/');
	}
</script>

<svelte:head>
	<title>시작하기 - 주식 대시보드</title>
</svelte:head>

<div class="container">
	<button class="skip-btn" onclick={skip}>건너뛰기</button>

	<div class="step-content">
		<div class="icon">{steps[currentStep].icon}</div>
		<h1>{steps[currentStep].title}</h1>
		<p class="description">{steps[currentStep].description}</p>
	</div>

	<div class="progress">
		{#each steps as _, i}
			<div
				class="dot"
				class:active={i === currentStep}
				class:completed={i < currentStep}
			></div>
		{/each}
	</div>

	<div class="actions">
		{#if currentStep > 0}
			<button class="btn secondary" onclick={prevStep}>이전</button>
		{:else}
			<div></div>
		{/if}
		<button class="btn primary" onclick={nextStep}>
			{currentStep < steps.length - 1 ? '다음' : '시작하기'}
		</button>
	</div>
</div>

<style>
	.container {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 2rem;
		background: #0d1117;
		position: relative;
	}

	.skip-btn {
		position: absolute;
		top: 1rem;
		right: 1rem;
		background: none;
		border: none;
		color: #8b949e;
		font-size: 0.9rem;
		cursor: pointer;
		padding: 0.5rem 1rem;
	}

	.skip-btn:hover {
		color: #f0f6fc;
	}

	.step-content {
		text-align: center;
		max-width: 320px;
		margin-bottom: 2rem;
	}

	.icon {
		font-size: 4rem;
		margin-bottom: 1.5rem;
	}

	h1 {
		font-size: 1.5rem;
		font-weight: 700;
		color: #f0f6fc;
		margin: 0 0 1rem;
	}

	.description {
		color: #8b949e;
		font-size: 0.95rem;
		line-height: 1.6;
		white-space: pre-line;
		margin: 0;
	}

	.progress {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 2rem;
	}

	.dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: #30363d;
		transition: all 0.3s ease;
	}

	.dot.active {
		background: #58a6ff;
		width: 24px;
		border-radius: 4px;
	}

	.dot.completed {
		background: #238636;
	}

	.actions {
		display: flex;
		gap: 1rem;
		width: 100%;
		max-width: 320px;
	}

	.btn {
		flex: 1;
		padding: 1rem;
		border: none;
		border-radius: 12px;
		font-size: 1rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn.primary {
		background: #238636;
		color: white;
	}

	.btn.primary:hover {
		background: #2ea043;
	}

	.btn.secondary {
		background: #21262d;
		color: #8b949e;
		border: 1px solid #30363d;
	}

	.btn.secondary:hover {
		color: #f0f6fc;
		border-color: #484f58;
	}
</style>
