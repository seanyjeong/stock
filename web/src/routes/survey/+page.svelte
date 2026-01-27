<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import { page } from '$app/stores';
	import Icon from '$lib/components/Icons.svelte';
	import { createProfile, updateProfile } from '$lib/api';

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	let currentStep = $state(0);
	let isSubmitting = $state(false);
	let error = $state('');
	let isRetake = $state(false);

	// Survey answers
	let answers = $state({
		experience: '',
		risk_tolerance: '',
		duration_preference: '',
		profit_expectation: '',
		sectors: [] as string[]
	});

	// Result after submission
	let resultProfile = $state<{ type: string; emoji: string; label: string } | null>(null);

	const questions = [
		{
			key: 'experience',
			title: '투자 경험이 얼마나 되셨나요?',
			subtitle: '주식 투자 경험 기간을 알려주세요',
			options: [
				{ value: 'under_1y', label: '1년 미만', icon: 'seedling' },
				{ value: '1_3y', label: '1~3년', icon: 'sprout' },
				{ value: 'over_3y', label: '3년 이상', icon: 'tree' }
			]
		},
		{
			key: 'risk_tolerance',
			title: '얼마나 손실을 감수할 수 있나요?',
			subtitle: '투자금 대비 최대 허용 손실률',
			options: [
				{ value: 'under_5', label: '5% 미만', desc: '안정 추구' },
				{ value: 'under_10', label: '10% 미만', desc: '적당한 위험' },
				{ value: 'under_20', label: '20% 미만', desc: '중간 위험' },
				{ value: 'over_20', label: '20% 이상', desc: '고위험 수용' }
			]
		},
		{
			key: 'duration_preference',
			title: '선호하는 투자 기간은?',
			subtitle: '주로 어떤 스타일로 투자하시나요',
			options: [
				{ value: 'day', label: '단타 (1~3일)', desc: '빠른 수익 실현' },
				{ value: 'swing', label: '스윙 (1~2주)', desc: '추세 추종' },
				{ value: 'long', label: '장기 (1개월+)', desc: '가치 투자' },
				{ value: 'mixed', label: '혼합', desc: '상황에 따라' }
			]
		},
		{
			key: 'profit_expectation',
			title: '기대 수익률은 어느 정도인가요?',
			subtitle: '한 거래당 목표 수익률',
			options: [
				{ value: 'stable', label: '5~10%', desc: '안정적 수익' },
				{ value: 'moderate', label: '10~30%', desc: '중간 수익' },
				{ value: 'aggressive', label: '30% 이상', desc: '공격적 수익' }
			]
		},
		{
			key: 'sectors',
			title: '관심 있는 섹터를 선택하세요',
			subtitle: '여러 개 선택 가능합니다',
			multiple: true,
			options: [
				{ value: 'tech', label: '기술주', icon: 'cpu' },
				{ value: 'bio', label: '바이오', icon: 'heart' },
				{ value: 'energy', label: '에너지', icon: 'zap' },
				{ value: 'finance', label: '금융', icon: 'dollar' },
				{ value: 'all', label: '전체', icon: 'globe' }
			]
		}
	];

	const profileTypes = {
		conservative: { emoji: '🛡️', label: '안정형', desc: '장기 투자, 우량주 중심의 안정적인 포트폴리오' },
		balanced: { emoji: '⚖️', label: '균형형', desc: '스윙과 장기를 혼합한 균형 잡힌 전략' },
		aggressive: { emoji: '🔥', label: '공격형', desc: '단타와 고변동성 종목을 활용한 적극적 투자' }
	};

	onMount(() => {
		// Check if user is logged in
		const token = localStorage.getItem('access_token');
		if (!token) {
			goto('/login', { replaceState: true });
		}

		// Check if this is a retake
		isRetake = $page.url.searchParams.get('retake') === 'true';
	});

	function selectOption(key: string, value: string, multiple = false) {
		if (multiple) {
			const current = answers[key as keyof typeof answers] as string[];
			if (value === 'all') {
				// 'all' 선택 시 다른 것들 해제
				answers = { ...answers, [key]: ['all'] };
			} else {
				// 다른 옵션 선택 시 'all' 해제
				let newValues = current.filter(v => v !== 'all');
				if (newValues.includes(value)) {
					newValues = newValues.filter(v => v !== value);
				} else {
					newValues = [...newValues, value];
				}
				answers = { ...answers, [key]: newValues };
			}
		} else {
			answers = { ...answers, [key]: value };
		}
	}

	function isSelected(key: string, value: string): boolean {
		const answer = answers[key as keyof typeof answers];
		if (Array.isArray(answer)) {
			return answer.includes(value);
		}
		return answer === value;
	}

	function canProceed(): boolean {
		const q = questions[currentStep];
		const answer = answers[q.key as keyof typeof answers];
		if (q.multiple) {
			return (answer as string[]).length > 0;
		}
		return answer !== '';
	}

	function nextStep() {
		if (currentStep < questions.length - 1) {
			currentStep++;
		} else {
			submitSurvey();
		}
	}

	function prevStep() {
		if (currentStep > 0) {
			currentStep--;
		}
	}

	async function submitSurvey() {
		isSubmitting = true;
		error = '';

		try {
			// Use updateProfile if retaking, createProfile otherwise
			const result = isRetake
				? await updateProfile(answers)
				: await createProfile(answers);

			// Show result
			const pType = result.profile_type as keyof typeof profileTypes;
			resultProfile = {
				type: result.profile_type,
				...profileTypes[pType]
			};
		} catch (e) {
			error = e instanceof Error ? e.message : '프로필 저장에 실패했습니다';
		} finally {
			isSubmitting = false;
		}
	}

	function goToNextPage() {
		// If retaking survey, go to settings
		if (isRetake) {
			goto('/settings', { replaceState: true });
			return;
		}

		// Check if user is approved
		const userStr = localStorage.getItem('user');
		if (userStr) {
			const user = JSON.parse(userStr);
			if (user.is_approved) {
				goto('/', { replaceState: true });
			} else {
				goto('/pending-approval', { replaceState: true });
			}
		} else {
			goto('/pending-approval', { replaceState: true });
		}
	}
</script>

<svelte:head>
	<title>투자성향 설문 - 달러농장</title>
</svelte:head>

<div class="container">
	{#if resultProfile}
		<!-- Result Screen -->
		<div class="result-card">
			<div class="result-emoji">{resultProfile.emoji}</div>
			<h1>당신은 <span class="highlight">{resultProfile.label}</span>입니다!</h1>
			<p class="result-desc">{profileTypes[resultProfile.type as keyof typeof profileTypes].desc}</p>

			<div class="result-summary">
				<h3>설문 결과</h3>
				<div class="summary-item">
					<span class="label">투자 경험</span>
					<span class="value">{questions[0].options.find(o => o.value === answers.experience)?.label}</span>
				</div>
				<div class="summary-item">
					<span class="label">손실 허용</span>
					<span class="value">{questions[1].options.find(o => o.value === answers.risk_tolerance)?.label}</span>
				</div>
				<div class="summary-item">
					<span class="label">투자 기간</span>
					<span class="value">{questions[2].options.find(o => o.value === answers.duration_preference)?.label}</span>
				</div>
				<div class="summary-item">
					<span class="label">기대 수익</span>
					<span class="value">{questions[3].options.find(o => o.value === answers.profit_expectation)?.label}</span>
				</div>
				<div class="summary-item">
					<span class="label">관심 섹터</span>
					<span class="value">{answers.sectors.map(s => questions[4].options.find(o => o.value === s)?.label).join(', ')}</span>
				</div>
			</div>

			<button class="btn-primary" onclick={goToNextPage}>
				시작하기
			</button>
		</div>
	{:else}
		<!-- Survey Screen -->
		<div class="progress-bar">
			<div class="progress-fill" style="width: {((currentStep + 1) / questions.length) * 100}%"></div>
		</div>

		<div class="step-indicator">
			{currentStep + 1} / {questions.length}
		</div>

		<div class="question-card">
			<h1>{questions[currentStep].title}</h1>
			<p class="subtitle">{questions[currentStep].subtitle}</p>

			<div class="options" class:multiple={questions[currentStep].multiple}>
				{#each questions[currentStep].options as option}
					<button
						class="option"
						class:selected={isSelected(questions[currentStep].key, option.value)}
						onclick={() => selectOption(questions[currentStep].key, option.value, questions[currentStep].multiple)}
					>
						{#if 'icon' in option}
							<Icon name={option.icon} size={24} />
						{/if}
						<span class="option-label">{option.label}</span>
						{#if 'desc' in option}
							<span class="option-desc">{option.desc}</span>
						{/if}
					</button>
				{/each}
			</div>

			{#if error}
				<div class="error-message">{error}</div>
			{/if}
		</div>

		<div class="nav-buttons">
			{#if currentStep > 0}
				<button class="btn-secondary" onclick={prevStep}>
					이전
				</button>
			{:else}
				<div></div>
			{/if}

			<button
				class="btn-primary"
				onclick={nextStep}
				disabled={!canProceed() || isSubmitting}
			>
				{#if isSubmitting}
					<span class="spinner"></span>
				{:else if currentStep < questions.length - 1}
					다음
				{:else}
					완료
				{/if}
			</button>
		</div>
	{/if}
</div>

<style>
	.container {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		padding: 1.5rem;
		background: #0d1117;
		max-width: 480px;
		margin: 0 auto;
	}

	.progress-bar {
		height: 4px;
		background: #21262d;
		border-radius: 2px;
		margin-bottom: 1rem;
		overflow: hidden;
	}

	.progress-fill {
		height: 100%;
		background: linear-gradient(90deg, #238636, #3fb950);
		transition: width 0.3s ease;
	}

	.step-indicator {
		text-align: center;
		color: #8b949e;
		font-size: 0.85rem;
		margin-bottom: 2rem;
	}

	.question-card {
		flex: 1;
	}

	h1 {
		font-size: 1.5rem;
		font-weight: 700;
		color: #f0f6fc;
		margin: 0 0 0.5rem;
		line-height: 1.3;
	}

	.subtitle {
		color: #8b949e;
		margin: 0 0 2rem;
		font-size: 0.9rem;
	}

	.options {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.options.multiple {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 0.75rem;
	}

	.option {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
		padding: 1.25rem 1rem;
		background: #161b22;
		border: 2px solid #30363d;
		border-radius: 12px;
		color: #f0f6fc;
		cursor: pointer;
		transition: all 0.15s ease;
		text-align: center;
	}

	.option:hover {
		border-color: #484f58;
		background: #1c2128;
	}

	.option.selected {
		border-color: #238636;
		background: rgba(35, 134, 54, 0.15);
	}

	.option-label {
		font-weight: 600;
		font-size: 1rem;
	}

	.option-desc {
		font-size: 0.8rem;
		color: #8b949e;
	}

	.nav-buttons {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 2rem;
		padding-bottom: 2rem;
	}

	.btn-primary,
	.btn-secondary {
		flex: 1;
		padding: 1rem;
		border: none;
		border-radius: 12px;
		font-size: 1rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.15s ease;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
	}

	.btn-primary {
		background: #238636;
		color: white;
	}

	.btn-primary:hover:not(:disabled) {
		background: #2ea043;
	}

	.btn-primary:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-secondary {
		background: #21262d;
		color: #8b949e;
		border: 1px solid #30363d;
	}

	.btn-secondary:hover {
		color: #f0f6fc;
		border-color: #484f58;
	}

	.spinner {
		width: 18px;
		height: 18px;
		border: 2px solid transparent;
		border-top-color: #fff;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.error-message {
		background: rgba(248, 81, 73, 0.15);
		border: 1px solid #f85149;
		color: #f85149;
		padding: 0.75rem 1rem;
		border-radius: 8px;
		font-size: 0.875rem;
		margin-top: 1rem;
	}

	/* Result Screen */
	.result-card {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		text-align: center;
	}

	.result-emoji {
		font-size: 4rem;
		margin-bottom: 1rem;
	}

	.result-card h1 {
		font-size: 1.75rem;
		margin-bottom: 0.75rem;
	}

	.highlight {
		color: #3fb950;
	}

	.result-desc {
		color: #8b949e;
		font-size: 0.95rem;
		margin: 0 0 2rem;
		line-height: 1.5;
	}

	.result-summary {
		width: 100%;
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 12px;
		padding: 1.25rem;
		margin-bottom: 2rem;
		text-align: left;
	}

	.result-summary h3 {
		font-size: 0.85rem;
		color: #8b949e;
		margin: 0 0 1rem;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.summary-item {
		display: flex;
		justify-content: space-between;
		padding: 0.5rem 0;
		border-bottom: 1px solid #21262d;
	}

	.summary-item:last-child {
		border-bottom: none;
	}

	.summary-item .label {
		color: #8b949e;
		font-size: 0.85rem;
	}

	.summary-item .value {
		color: #f0f6fc;
		font-size: 0.85rem;
		font-weight: 500;
	}

	.result-card .btn-primary {
		width: 100%;
		max-width: 280px;
	}
</style>
