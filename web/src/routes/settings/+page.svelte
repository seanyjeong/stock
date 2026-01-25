<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import Icon from '$lib/components/Icons.svelte';
	import type { UserProfile } from '$lib/types';

	interface User {
		id: number;
		kakao_id: string;
		nickname: string;
		email: string | null;
		profile_image: string | null;
		is_approved: boolean;
		is_admin?: boolean;
	}

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	let user = $state<User | null>(null);
	let isLoggedIn = $state(false);
	let profile = $state<UserProfile | null>(null);
	let isLoadingProfile = $state(false);

	const profileTypes = {
		conservative: { emoji: '🛡️', label: '안정형', color: '#58a6ff' },
		balanced: { emoji: '⚖️', label: '균형형', color: '#a371f7' },
		aggressive: { emoji: '🔥', label: '공격형', color: '#f85149' }
	};

	onMount(async () => {
		if (browser) {
			const token = localStorage.getItem('access_token');
			const userStr = localStorage.getItem('user');

			if (token && userStr) {
				isLoggedIn = true;
				user = JSON.parse(userStr);
				await loadProfile(token);
			}
		}
	});

	async function loadProfile(token: string) {
		isLoadingProfile = true;
		try {
			const response = await fetch(`${API_BASE}/api/profile/`, {
				headers: { 'Authorization': `Bearer ${token}` }
			});
			if (response.ok) {
				profile = await response.json();
			}
		} catch {
			// Profile not found
		} finally {
			isLoadingProfile = false;
		}
	}

	function retakeSurvey() {
		goto('/survey?retake=true');
	}

	function handleLogin() {
		goto('/login');
	}

	function handleLogout() {
		localStorage.removeItem('access_token');
		localStorage.removeItem('user');
		isLoggedIn = false;
		user = null;
		goto('/login');
	}
</script>

<svelte:head>
	<title>설정 - 달러농장</title>
</svelte:head>

<div class="container">
	<h1><Icon name="settings" size={24} /> 설정</h1>

	<section class="card">
		<h2>계정</h2>

		{#if isLoggedIn && user}
			<div class="user-info">
				{#if user.profile_image}
					<img src={user.profile_image} alt="" class="avatar" />
				{:else}
					<div class="avatar placeholder"><Icon name="user" size={24} /></div>
				{/if}
				<div class="user-details">
					<div class="user-name">{user.nickname}</div>
					{#if user.email}
						<div class="user-email">{user.email}</div>
					{/if}
					<div class="user-status">
						{#if user.is_approved}
							<span class="status approved">승인됨</span>
						{:else}
							<span class="status pending">승인 대기</span>
						{/if}
					</div>
				</div>
			</div>

			<div class="actions">
				{#if user.is_admin}
					<a href="/admin" class="btn admin">
						<Icon name="user" size={16} /> 사용자 관리
					</a>
				{/if}
				<button class="btn logout" onclick={handleLogout}>
					로그아웃
				</button>
			</div>
		{:else}
			<p class="login-prompt">로그인하면 개인화된 서비스를 이용할 수 있습니다.</p>
			<button class="btn login" onclick={handleLogin}>
				카카오로 로그인
			</button>
		{/if}
	</section>

	{#if isLoggedIn}
		<section class="card">
			<h2>투자성향</h2>
			{#if isLoadingProfile}
				<div class="profile-loading">불러오는 중...</div>
			{:else if profile}
				<div class="profile-info">
					<div class="profile-type" style="--profile-color: {profileTypes[profile.profile_type as keyof typeof profileTypes]?.color}">
						<span class="profile-emoji">{profileTypes[profile.profile_type as keyof typeof profileTypes]?.emoji}</span>
						<span class="profile-label">{profileTypes[profile.profile_type as keyof typeof profileTypes]?.label}</span>
					</div>
					<button class="btn-retake" onclick={retakeSurvey}>
						다시하기
					</button>
				</div>
			{:else}
				<div class="no-profile">
					<p>투자성향 설문을 완료해주세요</p>
					<button class="btn-survey" onclick={() => goto('/survey')}>
						설문하기
					</button>
				</div>
			{/if}
		</section>
	{/if}

	<section class="card">
		<h2>알림</h2>
		<a href="/notifications" class="menu-link">
			<span>Push 알림 설정</span>
			<span class="arrow">→</span>
		</a>
	</section>

	<section class="card">
		<h2>정보</h2>
		<div class="info-list">
			<div class="info-item">
				<span class="info-label">버전</span>
				<span class="info-value">2.0.0</span>
			</div>
			<div class="info-item">
				<span class="info-label">개발자</span>
				<span class="info-value">정으뜸</span>
			</div>
			<div class="info-item">
				<span class="info-label">이메일</span>
				<span class="info-value">sean8320@gmail.com</span>
			</div>
		</div>
	</section>
</div>

<style>
	.container {
		max-width: 500px;
		margin: 0 auto;
		padding: 1rem;
	}

	h1 {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 1.5rem;
		margin-bottom: 1rem;
	}

	.card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 12px;
		padding: 1rem;
		margin-bottom: 1rem;
	}

	h2 {
		font-size: 0.9rem;
		font-weight: 600;
		color: #8b949e;
		margin: 0 0 1rem;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.user-info {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-bottom: 1rem;
	}

	.avatar {
		width: 60px;
		height: 60px;
		border-radius: 50%;
		object-fit: cover;
	}

	.avatar.placeholder {
		background: #21262d;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.5rem;
	}

	.user-details {
		flex: 1;
	}

	.user-name {
		font-size: 1.1rem;
		font-weight: 600;
		color: #f0f6fc;
		margin-bottom: 0.25rem;
	}

	.user-email {
		font-size: 0.8rem;
		color: #8b949e;
		margin-bottom: 0.25rem;
	}

	.status {
		font-size: 0.7rem;
		padding: 0.2rem 0.5rem;
		border-radius: 4px;
		font-weight: 600;
	}

	.status.approved {
		background: rgba(35, 134, 54, 0.2);
		color: #3fb950;
	}

	.status.pending {
		background: rgba(240, 136, 62, 0.2);
		color: #f0883e;
	}

	.actions {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.btn {
		display: block;
		width: 100%;
		padding: 0.875rem;
		border: none;
		border-radius: 10px;
		font-size: 0.9rem;
		font-weight: 600;
		cursor: pointer;
		text-decoration: none;
		text-align: center;
		transition: all 0.15s ease;
	}

	.btn.admin {
		background: #21262d;
		color: #58a6ff;
		border: 1px solid #30363d;
	}

	.btn.admin:hover {
		border-color: #58a6ff;
	}

	.btn.logout {
		background: #21262d;
		color: #f85149;
		border: 1px solid #30363d;
	}

	.btn.logout:hover {
		border-color: #f85149;
	}

	.btn.login {
		background: #FEE500;
		color: #000000;
	}

	.btn.login:hover {
		background: #F5DC00;
	}

	.login-prompt {
		color: #8b949e;
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.info-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.info-item {
		display: flex;
		justify-content: space-between;
		padding: 0.5rem 0;
		border-bottom: 1px solid #21262d;
	}

	.info-item:last-child {
		border-bottom: none;
	}

	.info-label {
		color: #8b949e;
		font-size: 0.85rem;
	}

	.info-value {
		color: #f0f6fc;
		font-size: 0.85rem;
	}

	.menu-link {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.875rem;
		background: #21262d;
		border-radius: 8px;
		color: #f0f6fc;
		text-decoration: none;
		transition: background 0.15s;
	}

	.menu-link:hover {
		background: #30363d;
	}

	.menu-link .arrow {
		color: #8b949e;
	}

	/* Profile Section */
	.profile-loading {
		color: #8b949e;
		font-size: 0.85rem;
		padding: 0.5rem 0;
	}

	.profile-info {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.profile-type {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.profile-emoji {
		font-size: 1.5rem;
	}

	.profile-label {
		font-size: 1.1rem;
		font-weight: 600;
		color: var(--profile-color, #f0f6fc);
	}

	.btn-retake {
		padding: 0.5rem 1rem;
		border: 1px solid #30363d;
		border-radius: 8px;
		background: #21262d;
		color: #8b949e;
		font-size: 0.85rem;
		cursor: pointer;
		transition: all 0.15s;
	}

	.btn-retake:hover {
		border-color: #58a6ff;
		color: #58a6ff;
	}

	.no-profile {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.no-profile p {
		color: #8b949e;
		font-size: 0.9rem;
		margin: 0;
	}

	.btn-survey {
		padding: 0.5rem 1rem;
		border: none;
		border-radius: 8px;
		background: #238636;
		color: white;
		font-size: 0.85rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.15s;
	}

	.btn-survey:hover {
		background: #2ea043;
	}
</style>
