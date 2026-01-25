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
		profile_type: 'conservative' | 'balanced' | 'aggressive' | null;
		created_at: string | null;
		last_login: string | null;
	}

	const profileTypes = {
		conservative: { emoji: '🛡️', label: '안정형', color: '#58a6ff' },
		balanced: { emoji: '⚖️', label: '균형형', color: '#a371f7' },
		aggressive: { emoji: '🔥', label: '공격형', color: '#f85149' }
	};

	interface Announcement {
		id: number;
		title: string;
		content: string;
		is_important: boolean;
		is_active: boolean;
		created_at: string;
		created_by_name: string;
	}

	let users = $state<User[]>([]);
	let totalCount = $state(0);
	let pendingCount = $state(0);
	let isLoading = $state(true);
	let error = $state('');
	let actionLoading = $state<number | null>(null);

	// Announcements
	let announcements = $state<Announcement[]>([]);
	let announcementsLoading = $state(true);
	let showAnnouncementForm = $state(false);
	let editingAnnouncement = $state<Announcement | null>(null);
	let announcementForm = $state({ title: '', content: '', is_important: false });

	// AI Draft
	let showAiDraft = $state(false);
	let aiPrompt = $state('');
	let aiTone = $state<'friendly' | 'formal' | 'urgent'>('friendly');
	let aiLoading = $state(false);

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	onMount(async () => {
		await Promise.all([loadUsers(), loadAnnouncements()]);
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

	// Announcement functions
	async function loadAnnouncements() {
		announcementsLoading = true;
		try {
			const response = await fetch(`${API_BASE}/api/announcements/admin`, {
				headers: getAuthHeaders(),
			});
			if (response.ok) {
				const data = await response.json();
				announcements = data.announcements;
			}
		} catch (e) {
			console.error('Failed to load announcements:', e);
		} finally {
			announcementsLoading = false;
		}
	}

	function openNewAnnouncementForm() {
		editingAnnouncement = null;
		announcementForm = { title: '', content: '', is_important: false };
		showAnnouncementForm = true;
	}

	function openEditAnnouncementForm(a: Announcement) {
		editingAnnouncement = a;
		announcementForm = { title: a.title, content: a.content, is_important: a.is_important };
		showAnnouncementForm = true;
	}

	function closeAnnouncementForm() {
		showAnnouncementForm = false;
		editingAnnouncement = null;
		announcementForm = { title: '', content: '', is_important: false };
		showAiDraft = false;
		aiPrompt = '';
	}

	async function generateAiDraft() {
		if (!aiPrompt.trim()) {
			alert('내용을 입력하세요');
			return;
		}
		aiLoading = true;
		try {
			const response = await fetch(`${API_BASE}/api/announcements/draft`, {
				method: 'POST',
				headers: getAuthHeaders(),
				body: JSON.stringify({ prompt: aiPrompt, tone: aiTone }),
			});
			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || 'AI 생성 실패');
			}
			const data = await response.json();
			announcementForm = {
				title: data.draft.title,
				content: data.draft.content,
				is_important: data.draft.is_important,
			};
			showAiDraft = false;
			aiPrompt = '';
		} catch (e) {
			alert(e instanceof Error ? e.message : 'AI 생성 실패');
		} finally {
			aiLoading = false;
		}
	}

	async function saveAnnouncement() {
		if (!announcementForm.title.trim()) {
			alert('제목을 입력하세요');
			return;
		}

		try {
			const url = editingAnnouncement
				? `${API_BASE}/api/announcements/${editingAnnouncement.id}`
				: `${API_BASE}/api/announcements`;
			const method = editingAnnouncement ? 'PUT' : 'POST';

			const response = await fetch(url, {
				method,
				headers: getAuthHeaders(),
				body: JSON.stringify(announcementForm),
			});

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '저장에 실패했습니다');
			}

			closeAnnouncementForm();
			await loadAnnouncements();
		} catch (e) {
			alert(e instanceof Error ? e.message : '오류가 발생했습니다');
		}
	}

	async function deleteAnnouncement(id: number) {
		if (!confirm('정말 삭제하시겠습니까?')) return;

		try {
			const response = await fetch(`${API_BASE}/api/announcements/${id}`, {
				method: 'DELETE',
				headers: getAuthHeaders(),
			});

			if (!response.ok) {
				const data = await response.json();
				throw new Error(data.detail || '삭제에 실패했습니다');
			}

			await loadAnnouncements();
		} catch (e) {
			alert(e instanceof Error ? e.message : '오류가 발생했습니다');
		}
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
								{#if user.profile_type}
									<span class="badge profile-type {user.profile_type}">
										{profileTypes[user.profile_type].emoji} {profileTypes[user.profile_type].label}
									</span>
								{:else}
									<span class="badge no-profile">설문미완료</span>
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

	<!-- Announcements Section -->
	<section class="section">
		<div class="section-header">
			<h2><Icon name="bell" size={20} /> 공지사항 관리</h2>
			<button class="btn-add" onclick={openNewAnnouncementForm}>+ 새 공지</button>
		</div>

		{#if announcementsLoading}
			<div class="loading">로딩 중...</div>
		{:else}
			<div class="announcement-list">
				{#each announcements as a}
					<div class="announcement-card" class:important={a.is_important} class:inactive={!a.is_active}>
						<div class="announcement-info">
							<div class="announcement-title">
								{#if a.is_important}
									<span class="badge important">중요</span>
								{/if}
								{#if !a.is_active}
									<span class="badge inactive">비활성</span>
								{/if}
								{a.title}
							</div>
							<div class="announcement-content">{a.content || '(내용 없음)'}</div>
							<div class="announcement-meta">
								{a.created_by_name} · {formatDate(a.created_at)}
							</div>
						</div>
						<div class="announcement-actions">
							<button class="btn-icon" onclick={() => openEditAnnouncementForm(a)}>
								<Icon name="edit" size={16} />
							</button>
							<button class="btn-icon delete" onclick={() => deleteAnnouncement(a.id)}>
								<Icon name="trash" size={16} />
							</button>
						</div>
					</div>
				{/each}

				{#if announcements.length === 0}
					<div class="empty">등록된 공지사항이 없습니다</div>
				{/if}
			</div>
		{/if}
	</section>

	<!-- Announcement Form Modal -->
	{#if showAnnouncementForm}
		<div class="modal-overlay" onclick={closeAnnouncementForm}>
			<div class="modal" onclick={(e) => e.stopPropagation()}>
				<h3>{editingAnnouncement ? '공지사항 수정' : '새 공지사항'}</h3>

				<!-- AI Draft Section -->
				{#if !editingAnnouncement}
					<div class="ai-section">
						{#if showAiDraft}
							<div class="ai-form">
								<input
									type="text"
									bind:value={aiPrompt}
									placeholder="예: 내일 점검 있음, 새 기능 추가됨"
								/>
								<select bind:value={aiTone}>
									<option value="friendly">😊 친근</option>
									<option value="formal">📋 공식</option>
									<option value="urgent">🚨 긴급</option>
								</select>
								<button
									type="button"
									class="btn ai"
									onclick={generateAiDraft}
									disabled={aiLoading}
								>
									{aiLoading ? '생성중...' : '✨ 생성'}
								</button>
							</div>
						{:else}
							<button type="button" class="btn ai-toggle" onclick={() => showAiDraft = true}>
								🤖 AI로 작성
							</button>
						{/if}
					</div>
				{/if}

				<form onsubmit={(e) => { e.preventDefault(); saveAnnouncement(); }}>
					<div class="form-group">
						<label for="title">제목</label>
						<input
							id="title"
							type="text"
							bind:value={announcementForm.title}
							placeholder="공지 제목"
						/>
					</div>
					<div class="form-group">
						<label for="content">내용</label>
						<textarea
							id="content"
							bind:value={announcementForm.content}
							placeholder="공지 내용 (선택)"
							rows="3"
						></textarea>
					</div>
					<div class="form-group checkbox">
						<label>
							<input type="checkbox" bind:checked={announcementForm.is_important} />
							중요 공지로 표시
						</label>
					</div>
					<div class="form-actions">
						<button type="button" class="btn cancel" onclick={closeAnnouncementForm}>취소</button>
						<button type="submit" class="btn save">저장</button>
					</div>
				</form>
			</div>
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

	.badge.profile-type {
		font-size: 0.55rem;
	}

	.badge.conservative {
		background: rgba(88, 166, 255, 0.2);
		color: #58a6ff;
	}

	.badge.balanced {
		background: rgba(163, 113, 247, 0.2);
		color: #a371f7;
	}

	.badge.aggressive {
		background: rgba(248, 81, 73, 0.2);
		color: #f85149;
	}

	.badge.no-profile {
		background: rgba(110, 118, 129, 0.2);
		color: #6e7681;
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

	/* Announcements Section */
	.section {
		margin-top: 2rem;
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1rem;
	}

	.section-header h2 {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 1.25rem;
		margin: 0;
	}

	.btn-add {
		background: #238636;
		color: white;
		border: none;
		padding: 0.5rem 1rem;
		border-radius: 6px;
		font-size: 0.8rem;
		font-weight: 600;
		cursor: pointer;
	}

	.btn-add:hover {
		background: #2ea043;
	}

	.announcement-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.announcement-card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 10px;
		padding: 0.875rem;
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 0.75rem;
	}

	.announcement-card.important {
		border-color: #f0883e;
	}

	.announcement-card.inactive {
		opacity: 0.6;
	}

	.announcement-info {
		flex: 1;
		min-width: 0;
	}

	.announcement-title {
		font-weight: 600;
		color: #f0f6fc;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin-bottom: 0.25rem;
	}

	.announcement-content {
		font-size: 0.8rem;
		color: #8b949e;
		margin-bottom: 0.25rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.announcement-meta {
		font-size: 0.7rem;
		color: #6e7681;
	}

	.badge.important {
		background: rgba(240, 136, 62, 0.2);
		color: #f0883e;
	}

	.badge.inactive {
		background: rgba(110, 118, 129, 0.2);
		color: #6e7681;
	}

	.announcement-actions {
		display: flex;
		gap: 0.25rem;
	}

	.btn-icon {
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 6px;
		padding: 0.4rem;
		cursor: pointer;
		color: #8b949e;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.btn-icon:hover {
		color: #f0f6fc;
		border-color: #8b949e;
	}

	.btn-icon.delete:hover {
		color: #f85149;
		border-color: #f85149;
	}

	/* Modal */
	.modal-overlay {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.75);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: 1rem;
	}

	.modal {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 12px;
		padding: 1.5rem;
		width: 100%;
		max-width: 400px;
	}

	.modal h3 {
		margin: 0 0 1rem;
		font-size: 1.1rem;
	}

	.form-group {
		margin-bottom: 1rem;
	}

	.form-group label {
		display: block;
		font-size: 0.8rem;
		color: #8b949e;
		margin-bottom: 0.375rem;
	}

	.form-group.checkbox label {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		cursor: pointer;
		color: #f0f6fc;
	}

	.form-group input[type="text"],
	.form-group textarea {
		width: 100%;
		padding: 0.625rem;
		background: #0d1117;
		border: 1px solid #30363d;
		border-radius: 6px;
		color: #f0f6fc;
		font-size: 0.9rem;
	}

	.form-group input:focus,
	.form-group textarea:focus {
		outline: none;
		border-color: #58a6ff;
	}

	.form-group textarea {
		resize: vertical;
		font-family: inherit;
	}

	.form-actions {
		display: flex;
		gap: 0.5rem;
		margin-top: 1.5rem;
	}

	.form-actions .btn {
		flex: 1;
	}

	.btn.cancel {
		background: #21262d;
		color: #8b949e;
		border: 1px solid #30363d;
	}

	.btn.save {
		background: #238636;
		color: white;
	}

	.btn.save:hover {
		background: #2ea043;
	}

	/* AI Section */
	.ai-section {
		margin-bottom: 1rem;
		padding-bottom: 1rem;
		border-bottom: 1px solid #30363d;
	}

	.ai-toggle {
		width: 100%;
		padding: 0.5rem;
		background: rgba(136, 87, 229, 0.2);
		border: 1px dashed #8957e5;
		color: #a371f7;
	}

	.ai-toggle:hover {
		background: rgba(136, 87, 229, 0.3);
	}

	.ai-form {
		display: flex;
		gap: 0.5rem;
	}

	.ai-form input {
		flex: 1;
		padding: 0.5rem;
		background: #0d1117;
		border: 1px solid #30363d;
		border-radius: 6px;
		color: #f0f6fc;
		font-size: 0.85rem;
	}

	.ai-form select {
		padding: 0.5rem;
		background: #0d1117;
		border: 1px solid #30363d;
		border-radius: 6px;
		color: #f0f6fc;
		font-size: 0.85rem;
	}

	.btn.ai {
		padding: 0.5rem 0.75rem;
		background: #8957e5;
		color: white;
		white-space: nowrap;
	}

	.btn.ai:hover {
		background: #a371f7;
	}

	.btn.ai:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}
</style>
