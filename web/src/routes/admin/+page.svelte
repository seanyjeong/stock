<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import Icon from '$lib/components/Icons.svelte';

	interface User {
		id: number;
		kakao_id: string;
		nickname: string;
		email: string | null;
		profile_image: string | null;
		is_approved: boolean;
		is_admin: boolean;
		created_at: string | null;
		last_login: string | null;
	}

	let users = $state<User[]>([]);
	let totalCount = $state(0);
	let pendingCount = $state(0);
	let isLoading = $state(true);
	let error = $state('');
	let actionLoading = $state<number | null>(null);

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	onMount(async () => {
		await loadUsers();
	});

	function getAuthHeaders() {
		const token = localStorage.getItem('access_token');
		return {
			'Authorization': `Bearer ${token}`,
			'Content-Type': 'application/json',
		};
	}

	async function loadUsers() {
		isLoading = true;
		error = '';

		try {
			const response = await fetch(`${API_BASE}/api/auth/admin/users`, {
				headers: getAuthHeaders(),
			});

			if (response.status === 403) {
				error = '관리자 권한이 필요합니다';
				return;
			}

			if (response.status === 401) {
				goto('/login');
				return;
			}

			if (!response.ok) {
				throw new Error('사용자 목록을 불러올 수 없습니다');
			}

			const data = await response.json();
			users = data.users;
			totalCount = data.total_count;
			pendingCount = data.pending_count;
		} catch (e) {
			error = e instanceof Error ? e.message : '오류가 발생했습니다';
		} finally {
			isLoading = false;
		}
	}

	async function approveUser(userId: number) {
		actionLoading = userId;
		try {
			const response = await fetch(`${API_BASE}/api/auth/admin/users/${userId}/approve`, {
				method: 'POST',
				headers: getAuthHeaders(),
			});

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '승인에 실패했습니다');
			}

			await loadUsers();
		} catch (e) {
			alert(e instanceof Error ? e.message : '오류가 발생했습니다');
		} finally {
			actionLoading = null;
		}
	}

	async function revokeUser(userId: number) {
		if (!confirm('정말 승인을 취소하시겠습니까?')) return;

		actionLoading = userId;
		try {
			const response = await fetch(`${API_BASE}/api/auth/admin/users/${userId}/revoke`, {
				method: 'POST',
				headers: getAuthHeaders(),
			});

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '승인 취소에 실패했습니다');
			}

			await loadUsers();
		} catch (e) {
			alert(e instanceof Error ? e.message : '오류가 발생했습니다');
		} finally {
			actionLoading = null;
		}
	}

	async function deleteUser(userId: number, nickname: string) {
		if (!confirm(`정말 ${nickname}님을 삭제하시겠습니까?`)) return;

		actionLoading = userId;
		try {
			const response = await fetch(`${API_BASE}/api/auth/admin/users/${userId}`, {
				method: 'DELETE',
				headers: getAuthHeaders(),
			});

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '삭제에 실패했습니다');
			}

			await loadUsers();
		} catch (e) {
			alert(e instanceof Error ? e.message : '오류가 발생했습니다');
		} finally {
			actionLoading = null;
		}
	}

	function formatDate(dateStr: string | null): string {
		if (!dateStr) return '-';
		const date = new Date(dateStr);
		return date.toLocaleDateString('ko-KR', {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit',
		});
	}
</script>

<svelte:head>
	<title>관리자 - 주식 대시보드</title>
</svelte:head>

<div class="container">
	<h1><Icon name="user" size={24} /> 사용자 관리</h1>

	{#if error}
		<div class="error-box">{error}</div>
	{/if}

	{#if isLoading}
		<div class="loading">로딩 중...</div>
	{:else}
		<div class="stats">
			<div class="stat">
				<span class="stat-value">{totalCount}</span>
				<span class="stat-label">전체</span>
			</div>
			<div class="stat pending">
				<span class="stat-value">{pendingCount}</span>
				<span class="stat-label">승인 대기</span>
			</div>
			<div class="stat approved">
				<span class="stat-value">{totalCount - pendingCount}</span>
				<span class="stat-label">승인됨</span>
			</div>
		</div>

		<div class="user-list">
			{#each users as user}
				<div class="user-card" class:pending={!user.is_approved}>
					<div class="user-info">
						{#if user.profile_image}
							<img src={user.profile_image} alt="" class="avatar" />
						{:else}
							<div class="avatar placeholder"><Icon name="user" size={20} /></div>
						{/if}
						<div class="user-details">
							<div class="user-name">
								{user.nickname}
								{#if user.is_admin}
									<span class="badge admin">관리자</span>
								{/if}
								{#if !user.is_approved}
									<span class="badge pending">대기</span>
								{/if}
							</div>
							<div class="user-meta">
								{#if user.email}
									<span>{user.email}</span>
								{/if}
								<span>가입: {formatDate(user.created_at)}</span>
							</div>
						</div>
					</div>
					<div class="user-actions">
						{#if !user.is_admin}
							{#if !user.is_approved}
								<button
									class="btn approve"
									onclick={() => approveUser(user.id)}
									disabled={actionLoading === user.id}
								>
									{actionLoading === user.id ? '...' : '승인'}
								</button>
							{:else}
								<button
									class="btn revoke"
									onclick={() => revokeUser(user.id)}
									disabled={actionLoading === user.id}
								>
									{actionLoading === user.id ? '...' : '취소'}
								</button>
							{/if}
							<button
								class="btn delete"
								onclick={() => deleteUser(user.id, user.nickname)}
								disabled={actionLoading === user.id}
							>
								삭제
							</button>
						{/if}
					</div>
				</div>
			{/each}

			{#if users.length === 0}
				<div class="empty">등록된 사용자가 없습니다</div>
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
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 1.5rem;
		margin-bottom: 1rem;
	}

	.error-box {
		background: rgba(248, 81, 73, 0.15);
		border: 1px solid #f85149;
		color: #f85149;
		padding: 1rem;
		border-radius: 8px;
		margin-bottom: 1rem;
		text-align: center;
	}

	.loading {
		text-align: center;
		padding: 3rem;
		color: #8b949e;
	}

	.stats {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.75rem;
		margin-bottom: 1rem;
	}

	.stat {
		background: #21262d;
		padding: 0.75rem;
		border-radius: 8px;
		text-align: center;
	}

	.stat.pending {
		border: 1px solid #f0883e;
	}

	.stat.approved {
		border: 1px solid #238636;
	}

	.stat-value {
		display: block;
		font-size: 1.5rem;
		font-weight: 700;
		color: #f0f6fc;
	}

	.stat-label {
		font-size: 0.7rem;
		color: #8b949e;
	}

	.user-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.user-card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 10px;
		padding: 0.875rem;
	}

	.user-card.pending {
		border-color: #f0883e;
	}

	.user-info {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.avatar {
		width: 40px;
		height: 40px;
		border-radius: 50%;
		object-fit: cover;
	}

	.avatar.placeholder {
		background: #21262d;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.25rem;
	}

	.user-details {
		flex: 1;
		min-width: 0;
	}

	.user-name {
		font-weight: 600;
		color: #f0f6fc;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.badge {
		font-size: 0.6rem;
		padding: 0.125rem 0.375rem;
		border-radius: 4px;
		font-weight: 600;
	}

	.badge.admin {
		background: rgba(88, 166, 255, 0.2);
		color: #58a6ff;
	}

	.badge.pending {
		background: rgba(240, 136, 62, 0.2);
		color: #f0883e;
	}

	.user-meta {
		font-size: 0.7rem;
		color: #8b949e;
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.user-actions {
		display: flex;
		gap: 0.5rem;
	}

	.btn {
		flex: 1;
		padding: 0.5rem;
		border: none;
		border-radius: 6px;
		font-size: 0.8rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn.approve {
		background: #238636;
		color: white;
	}

	.btn.approve:hover:not(:disabled) {
		background: #2ea043;
	}

	.btn.revoke {
		background: #21262d;
		color: #f0883e;
		border: 1px solid #f0883e;
	}

	.btn.revoke:hover:not(:disabled) {
		background: rgba(240, 136, 62, 0.1);
	}

	.btn.delete {
		background: #21262d;
		color: #f85149;
		border: 1px solid #30363d;
	}

	.btn.delete:hover:not(:disabled) {
		border-color: #f85149;
	}

	.empty {
		text-align: center;
		padding: 3rem;
		color: #8b949e;
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 10px;
	}
</style>
