<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import Icon from '$lib/components/Icons.svelte';

	let user = $state<{ nickname: string } | null>(null);
	let profileType = $state<string | null>(null);

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	const profileTypes = {
		conservative: { emoji: '🛡️', label: '안정형' },
		balanced: { emoji: '⚖️', label: '균형형' },
		aggressive: { emoji: '🔥', label: '공격형' }
	};

	onMount(async () => {
		const userStr = localStorage.getItem('user');
		if (userStr) {
			user = JSON.parse(userStr);
			await loadProfile();
		} else {
			goto('/login', { replaceState: true });
		}
	});

	async function loadProfile() {
		const token = localStorage.getItem('access_token');
		if (!token) return;

		try {
			const response = await fetch(`${API_BASE}/api/profile/`, {
				headers: { 'Authorization': `Bearer ${token}` }
			});
			if (response.ok) {
				const profile = await response.json();
				profileType = profile.profile_type;
			}
		} catch {
			// Profile not found
		}
	}

	function handleLogout() {
		localStorage.removeItem('access_token');
		localStorage.removeItem('user');
		goto('/login', { replaceState: true });
	}

	async function checkApproval() {
		const token = localStorage.getItem('access_token');
		if (!token) {
			goto('/login', { replaceState: true });
			return;
		}

		try {
			const response = await fetch(`${API_BASE}/api/auth/me`, {
				headers: { 'Authorization': `Bearer ${token}` },
			});

			if (response.ok) {
				const data = await response.json();
				if (data.is_approved) {
					localStorage.setItem('user', JSON.stringify(data));
					goto('/', { replaceState: true });
				}
			}
		} catch (e) {
			// Ignore errors
		}
	}
</script>

<svelte:head>
	<title>승인 대기 - 달러농장</title>
</svelte:head>

<div class="container">
	<div class="card">
		<div class="icon">
			<Icon name="clock" size={48} />
		</div>
		<h1>승인 대기 중</h1>
		
		{#if user}
			<p class="greeting">안녕하세요, <strong>{user.nickname}</strong>님!</p>
		{/if}

		{#if profileType}
			<div class="profile-badge">
				<span class="profile-emoji">{profileTypes[profileType as keyof typeof profileTypes]?.emoji}</span>
				<span class="profile-label">{profileTypes[profileType as keyof typeof profileTypes]?.label}으로 설정됨</span>
			</div>
		{/if}

		<p class="message">
			관리자가 회원 가입을 승인하면<br/>
			맞춤 추천을 받아보실 수 있습니다.
		</p>

		<div class="actions">
			<button class="btn-check" onclick={checkApproval}>
				승인 상태 확인
			</button>
			<button class="btn-logout" onclick={handleLogout}>
				로그아웃
			</button>
		</div>
	</div>
</div>

<style>
	.container {
		min-height: 100vh;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		background: #0d1117;
	}

	.card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 16px;
		padding: 2.5rem 2rem;
		width: 100%;
		max-width: 360px;
		text-align: center;
	}

	.icon {
		display: flex;
		justify-content: center;
		align-items: center;
		width: 80px;
		height: 80px;
		margin: 0 auto 1rem;
		background: linear-gradient(135deg, #f0883e 0%, #f8b878 100%);
		border-radius: 20px;
		color: #fff;
	}

	h1 {
		font-size: 1.5rem;
		font-weight: 700;
		margin: 0 0 1rem;
		color: #f0f6fc;
	}

	.greeting {
		color: #8b949e;
		margin: 0 0 0.5rem;
	}

	.greeting strong {
		color: #58a6ff;
	}

	.message {
		color: #8b949e;
		margin: 0 0 2rem;
		line-height: 1.6;
	}

	.actions {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.btn-check {
		width: 100%;
		padding: 0.875rem;
		border: none;
		border-radius: 10px;
		font-size: 0.9rem;
		font-weight: 600;
		background: #238636;
		color: white;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-check:hover {
		background: #2ea043;
	}

	.btn-logout {
		width: 100%;
		padding: 0.875rem;
		border: 1px solid #30363d;
		border-radius: 10px;
		font-size: 0.9rem;
		font-weight: 500;
		background: transparent;
		color: #8b949e;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn-logout:hover {
		border-color: #f85149;
		color: #f85149;
	}

	.profile-badge {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		background: rgba(35, 134, 54, 0.15);
		border: 1px solid #238636;
		border-radius: 8px;
		padding: 0.75rem 1rem;
		margin-bottom: 1rem;
	}

	.profile-emoji {
		font-size: 1.25rem;
	}

	.profile-label {
		color: #3fb950;
		font-weight: 600;
		font-size: 0.9rem;
	}
</style>
