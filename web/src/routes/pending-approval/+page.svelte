<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import Icon from '$lib/components/Icons.svelte';

	let user = $state<{ nickname: string } | null>(null);

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	onMount(() => {
		const userStr = localStorage.getItem('user');
		if (userStr) {
			user = JSON.parse(userStr);
		} else {
			goto('/login');
		}
	});

	function handleLogout() {
		localStorage.removeItem('access_token');
		localStorage.removeItem('user');
		goto('/login');
	}

	async function checkApproval() {
		const token = localStorage.getItem('access_token');
		if (!token) {
			goto('/login');
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
					goto('/');
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

		<p class="message">
			관리자가 회원 가입을 승인하면<br/>
			서비스를 이용하실 수 있습니다.
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
</style>
