<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import Icon from '$lib/components/Icons.svelte';

	let isSupported = $state(false);
	let permission = $state<NotificationPermission>('default');
	let isSubscribed = $state(false);
	let isLoading = $state(true);
	let error = $state('');

	// Settings
	let dataUpdateAlerts = $state(true);
	let priceAlerts = $state(true);
	let regshoAlerts = $state(true);
	let blogAlerts = $state(true);
	let isSaving = $state(false);

	const API_BASE = browser ? (import.meta.env.VITE_API_URL || 'http://localhost:8000') : '';

	onMount(async () => {
		if (!browser) return;

		// Check if push notifications are supported
		isSupported = 'serviceWorker' in navigator && 'PushManager' in window;

		if (!isSupported) {
			isLoading = false;
			return;
		}

		permission = Notification.permission;

		// Check subscription status
		await checkSubscription();
		await loadSettings();
		isLoading = false;
	});

	function getAuthHeaders() {
		const token = localStorage.getItem('access_token');
		if (!token) {
			goto('/login');
			return {};
		}
		return {
			'Authorization': `Bearer ${token}`,
			'Content-Type': 'application/json',
		};
	}

	async function checkSubscription() {
		try {
			const registration = await navigator.serviceWorker.ready;
			const subscription = await registration.pushManager.getSubscription();
			isSubscribed = !!subscription;
		} catch {
			isSubscribed = false;
		}
	}

	async function loadSettings() {
		try {
			const response = await fetch(`${API_BASE}/api/notifications/settings`, {
				headers: getAuthHeaders(),
			});

			if (response.ok) {
				const data = await response.json();
				dataUpdateAlerts = data.data_update_alerts ?? true;
				priceAlerts = data.price_alerts;
				regshoAlerts = data.regsho_alerts;
				blogAlerts = data.blog_alerts;
			}
		} catch (e) {
			console.error('Failed to load settings:', e);
		}
	}

	async function requestPermission() {
		try {
			const result = await Notification.requestPermission();
			permission = result;

			if (result === 'granted') {
				await subscribe();
			}
		} catch (e) {
			error = '알림 권한 요청 실패';
		}
	}

	async function subscribe() {
		try {
			// Get VAPID public key
			const keyResponse = await fetch(`${API_BASE}/api/notifications/vapid-public-key`, {
				headers: getAuthHeaders(),
			});

			if (!keyResponse.ok) {
				error = '푸시 알림이 서버에서 설정되지 않았습니다';
				return;
			}

			const { publicKey } = await keyResponse.json();

			// Convert VAPID key
			const applicationServerKey = urlBase64ToUint8Array(publicKey);

			// Subscribe
			const registration = await navigator.serviceWorker.ready;
			const subscription = await registration.pushManager.subscribe({
				userVisibleOnly: true,
				applicationServerKey
			});

			// Send to server
			const response = await fetch(`${API_BASE}/api/notifications/subscribe`, {
				method: 'POST',
				headers: getAuthHeaders(),
				body: JSON.stringify({
					endpoint: subscription.endpoint,
					keys: {
						p256dh: arrayBufferToBase64(subscription.getKey('p256dh')),
						auth: arrayBufferToBase64(subscription.getKey('auth'))
					}
				}),
			});

			if (response.ok) {
				isSubscribed = true;
				error = '';
			} else {
				throw new Error('구독 등록 실패');
			}
		} catch (e) {
			error = e instanceof Error ? e.message : '구독 실패';
		}
	}

	async function unsubscribe() {
		try {
			const registration = await navigator.serviceWorker.ready;
			const subscription = await registration.pushManager.getSubscription();

			if (subscription) {
				// Unsubscribe from browser
				await subscription.unsubscribe();

				// Remove from server
				await fetch(`${API_BASE}/api/notifications/subscribe`, {
					method: 'DELETE',
					headers: getAuthHeaders(),
					body: JSON.stringify({
						endpoint: subscription.endpoint,
						keys: {}
					}),
				});
			}

			isSubscribed = false;
		} catch (e) {
			error = '구독 해제 실패';
		}
	}

	async function saveSettings() {
		isSaving = true;
		try {
			const response = await fetch(`${API_BASE}/api/notifications/settings`, {
				method: 'PUT',
				headers: getAuthHeaders(),
				body: JSON.stringify({
					data_update_alerts: dataUpdateAlerts,
					price_alerts: priceAlerts,
					regsho_alerts: regshoAlerts,
					blog_alerts: blogAlerts,
				}),
			});

			if (!response.ok) {
				throw new Error('설정 저장 실패');
			}
		} catch (e) {
			error = e instanceof Error ? e.message : '설정 저장 실패';
		} finally {
			isSaving = false;
		}
	}

	function urlBase64ToUint8Array(base64String: string): Uint8Array {
		const padding = '='.repeat((4 - base64String.length % 4) % 4);
		const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
		const rawData = window.atob(base64);
		const outputArray = new Uint8Array(rawData.length);
		for (let i = 0; i < rawData.length; ++i) {
			outputArray[i] = rawData.charCodeAt(i);
		}
		return outputArray;
	}

	function arrayBufferToBase64(buffer: ArrayBuffer | null): string {
		if (!buffer) return '';
		const bytes = new Uint8Array(buffer);
		let binary = '';
		for (let i = 0; i < bytes.byteLength; i++) {
			binary += String.fromCharCode(bytes[i]);
		}
		return window.btoa(binary);
	}
</script>

<svelte:head>
	<title>알림 설정 - 달러농장</title>
</svelte:head>

<div class="container">
	<h1>Push 알림 설정</h1>

	{#if error}
		<div class="error-box">{error}</div>
	{/if}

	{#if isLoading}
		<div class="loading">로딩 중...</div>
	{:else if !isSupported}
		<div class="card warning">
			<p>이 브라우저는 푸시 알림을 지원하지 않습니다.</p>
			<p class="sub">Chrome, Firefox, Edge 등 최신 브라우저를 사용해주세요.</p>
		</div>
	{:else}
		<section class="card">
			<h2>알림 권한</h2>

			{#if permission === 'denied'}
				<div class="status-box denied">
					<span class="status-icon"><Icon name="x" size={24} /></span>
					<div>
						<p>알림이 차단되었습니다</p>
						<p class="sub">브라우저 설정에서 알림을 허용해주세요</p>
					</div>
				</div>
			{:else if permission === 'granted' && isSubscribed}
				<div class="status-box granted">
					<span class="status-icon"><Icon name="check" size={24} /></span>
					<div>
						<p>알림이 활성화되었습니다</p>
						<p class="sub">가격 알림, RegSHO 등재 알림을 받을 수 있습니다</p>
					</div>
				</div>
				<button class="btn secondary" onclick={unsubscribe}>
					알림 끄기
				</button>
			{:else}
				<div class="status-box default">
					<span class="status-icon"><Icon name="bell" size={24} /></span>
					<div>
						<p>알림이 비활성화되었습니다</p>
						<p class="sub">중요한 가격 변동을 놓치지 마세요</p>
					</div>
				</div>
				<button class="btn primary" onclick={requestPermission}>
					알림 켜기
				</button>
			{/if}
		</section>

		{#if isSubscribed}
			<section class="card">
				<h2>알림 종류</h2>

				<div class="toggle-list">
					<label class="toggle-item">
						<div class="toggle-info">
							<span class="toggle-label">데이터 업데이트</span>
							<span class="toggle-desc">주가 데이터 수집 완료 시 알림</span>
						</div>
						<input type="checkbox" bind:checked={dataUpdateAlerts} onchange={saveSettings} />
					</label>

					<label class="toggle-item">
						<div class="toggle-info">
							<span class="toggle-label">가격 알림</span>
							<span class="toggle-desc">목표가/알림가 도달 시 알림</span>
						</div>
						<input type="checkbox" bind:checked={priceAlerts} onchange={saveSettings} />
					</label>

					<label class="toggle-item">
						<div class="toggle-info">
							<span class="toggle-label">RegSHO 알림</span>
							<span class="toggle-desc">보유 종목 RegSHO 등재/해제 시 알림</span>
						</div>
						<input type="checkbox" bind:checked={regshoAlerts} onchange={saveSettings} />
					</label>

					<label class="toggle-item">
						<div class="toggle-info">
							<span class="toggle-label">블로그 알림</span>
							<span class="toggle-desc">새 블로그 글 업로드 시 알림</span>
						</div>
						<input type="checkbox" bind:checked={blogAlerts} onchange={saveSettings} />
					</label>
				</div>

				{#if isSaving}
					<p class="saving">저장 중...</p>
				{/if}
			</section>
		{/if}

		<section class="card info">
			<h2>알림 안내</h2>
			<ul>
				<li>푸시 알림은 앱이 꺼져 있어도 도착합니다</li>
				<li>알림 데이터 사용량은 미미합니다</li>
			</ul>
		</section>
	{/if}

	<a href="/settings" class="back-link">← 설정으로 돌아가기</a>
</div>

<style>
	.container {
		max-width: 500px;
		margin: 0 auto;
		padding: 1rem;
	}

	h1 {
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

	.card.warning {
		border-color: #f0883e;
		background: rgba(240, 136, 62, 0.1);
	}

	.card.info {
		background: #0d1117;
	}

	h2 {
		font-size: 0.85rem;
		font-weight: 600;
		color: #8b949e;
		margin: 0 0 1rem;
		text-transform: uppercase;
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

	.status-box {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
		padding: 1rem;
		border-radius: 8px;
		margin-bottom: 1rem;
	}

	.status-box.granted {
		background: rgba(63, 185, 80, 0.1);
	}

	.status-box.denied {
		background: rgba(248, 81, 73, 0.1);
	}

	.status-box.default {
		background: rgba(139, 148, 158, 0.1);
	}

	.status-icon {
		font-size: 1.5rem;
	}

	.status-box p {
		margin: 0;
		color: #f0f6fc;
	}

	.status-box .sub {
		font-size: 0.8rem;
		color: #8b949e;
		margin-top: 0.25rem;
	}

	.btn {
		display: block;
		width: 100%;
		padding: 0.875rem;
		border: none;
		border-radius: 8px;
		font-size: 0.9rem;
		font-weight: 600;
		cursor: pointer;
	}

	.btn.primary {
		background: #238636;
		color: white;
	}

	.btn.secondary {
		background: #21262d;
		color: #f85149;
		border: 1px solid #30363d;
	}

	.toggle-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.toggle-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.75rem;
		background: #0d1117;
		border-radius: 8px;
		cursor: pointer;
	}

	.toggle-info {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.toggle-label {
		font-weight: 500;
		color: #f0f6fc;
	}

	.toggle-desc {
		font-size: 0.75rem;
		color: #8b949e;
	}

	.toggle-item input[type="checkbox"] {
		width: 44px;
		height: 24px;
		appearance: none;
		background: #30363d;
		border-radius: 12px;
		position: relative;
		cursor: pointer;
		transition: background 0.2s;
	}

	.toggle-item input[type="checkbox"]::after {
		content: '';
		position: absolute;
		top: 2px;
		left: 2px;
		width: 20px;
		height: 20px;
		background: #f0f6fc;
		border-radius: 50%;
		transition: transform 0.2s;
	}

	.toggle-item input[type="checkbox"]:checked {
		background: #238636;
	}

	.toggle-item input[type="checkbox"]:checked::after {
		transform: translateX(20px);
	}

	.saving {
		text-align: center;
		font-size: 0.8rem;
		color: #8b949e;
		margin-top: 0.5rem;
	}

	.info ul {
		margin: 0;
		padding: 0 0 0 1.25rem;
		color: #8b949e;
		font-size: 0.85rem;
	}

	.info li {
		margin-bottom: 0.5rem;
	}

	.back-link {
		display: block;
		text-align: center;
		color: #58a6ff;
		text-decoration: none;
		padding: 1rem;
		font-size: 0.9rem;
	}
</style>
