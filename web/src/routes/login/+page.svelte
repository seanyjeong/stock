<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { browser } from '$app/environment';
	import Icon from '$lib/components/Icons.svelte';

	let isLoading = $state(false);
	let error = $state('');

	// API base URL
	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	onMount(async () => {
		// Check if we have a code from Kakao OAuth callback
		const code = $page.url.searchParams.get('code');
		if (code) {
			await handleKakaoCallback(code);
		}

		// Check if already logged in
		const token = localStorage.getItem('access_token');
		if (token) {
			goto('/', { replaceState: true });
		}
	});

	async function handleKakaoLogin() {
		isLoading = true;
		error = '';

		try {
			const response = await fetch(`${API_BASE}/api/auth/kakao/login-url`);
			if (!response.ok) {
				throw new Error('로그인 URL을 가져올 수 없습니다');
			}
			const data = await response.json();
			window.location.href = data.login_url;
		} catch (e) {
			error = e instanceof Error ? e.message : '로그인 중 오류가 발생했습니다';
			isLoading = false;
		}
	}

	async function handleKakaoCallback(code: string) {
		isLoading = true;
		error = '';

		try {
			const response = await fetch(`${API_BASE}/api/auth/kakao/callback`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ code }),
			});

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '로그인에 실패했습니다');
			}

			const data = await response.json();

			// Store token and user info
			localStorage.setItem('access_token', data.access_token);
			localStorage.setItem('user', JSON.stringify(data.user));

			// Check if user has a profile (investment survey)
			try {
				const profileCheck = await fetch(`${API_BASE}/api/profile/check`, {
					headers: { 'Authorization': `Bearer ${data.access_token}` },
				});
				const profileData = await profileCheck.json();

				if (!profileData.has_profile) {
					// No profile - redirect to survey first
					goto('/survey', { replaceState: true });
					return;
				}
			} catch {
				// If profile check fails, continue with normal flow
			}

			// Check approval status
			if (!data.user.is_approved) {
				goto('/pending-approval', { replaceState: true });
				return;
			}

			goto('/', { replaceState: true });
		} catch (e) {
			error = e instanceof Error ? e.message : '로그인 중 오류가 발생했습니다';
			window.history.replaceState({}, '', '/login');
		} finally {
			isLoading = false;
		}
	}
</script>

<svelte:head>
	<title>로그인 - 달러농장</title>
</svelte:head>

<div class="login-container">
	<div class="login-card">
		<div class="logo">
			<Icon name="chart" size={48} />
		</div>
		<h1>달러농장</h1>
		<p class="subtitle">카카오 로그인으로 시작하세요</p>

		{#if error}
			<div class="error-message">{error}</div>
		{/if}

		<button
			class="kakao-btn"
			onclick={handleKakaoLogin}
			disabled={isLoading}
		>
			{#if isLoading}
				<span class="spinner"></span>
				로그인 중...
			{:else}
				<svg viewBox="0 0 24 24" class="kakao-icon">
					<path d="M12 3c5.799 0 10.5 3.664 10.5 8.185 0 4.52-4.701 8.184-10.5 8.184a13.5 13.5 0 01-1.727-.11l-4.408 2.883c-.501.265-.678.236-.472-.413l.892-3.678c-2.88-1.46-4.785-3.99-4.785-6.866C1.5 6.665 6.201 3 12 3z" fill="currentColor"/>
				</svg>
				카카오로 로그인
			{/if}
		</button>

		<p class="info">
			로그인 후 관리자 승인이 필요합니다
		</p>
	</div>
</div>

<style>
	.login-container {
		min-height: 100vh;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		background: #0d1117;
	}

	.login-card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 16px;
		padding: 2.5rem 2rem;
		width: 100%;
		max-width: 360px;
		text-align: center;
	}

	.logo {
		display: flex;
		justify-content: center;
		align-items: center;
		width: 80px;
		height: 80px;
		margin: 0 auto 1rem;
		background: linear-gradient(135deg, #238636 0%, #3fb950 100%);
		border-radius: 20px;
		color: #fff;
	}

	h1 {
		font-size: 1.5rem;
		font-weight: 700;
		margin: 0;
		color: #f0f6fc;
	}

	.subtitle {
		color: #8b949e;
		margin: 0.5rem 0 2rem;
		font-size: 0.9rem;
	}

	.error-message {
		background: rgba(248, 81, 73, 0.15);
		border: 1px solid #f85149;
		color: #f85149;
		padding: 0.75rem 1rem;
		border-radius: 8px;
		font-size: 0.875rem;
		margin-bottom: 1.5rem;
	}

	.kakao-btn {
		width: 100%;
		padding: 1rem;
		border: none;
		border-radius: 12px;
		font-size: 1rem;
		font-weight: 600;
		background: #FEE500;
		color: #000000;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		transition: all 0.15s ease;
	}

	.kakao-btn:hover:not(:disabled) {
		background: #F5DC00;
		transform: translateY(-1px);
	}

	.kakao-btn:active:not(:disabled) {
		transform: translateY(0);
	}

	.kakao-btn:disabled {
		opacity: 0.7;
		cursor: not-allowed;
	}

	.kakao-icon {
		width: 20px;
		height: 20px;
	}

	.spinner {
		width: 18px;
		height: 18px;
		border: 2px solid transparent;
		border-top-color: #000;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.info {
		margin-top: 1.5rem;
		font-size: 0.75rem;
		color: #8b949e;
	}
</style>
