<script lang="ts">
	import { goto } from '$app/navigation';

	let pin = $state('');
	let error = $state('');
	let isLoading = $state(false);

	const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '', '0', 'backspace'];

	function handleKeyPress(key: string) {
		if (isLoading) return;
		error = '';

		if (key === 'backspace') {
			pin = pin.slice(0, -1);
		} else if (key && pin.length < 4) {
			pin = pin + key;
		}

		if (pin.length === 4) {
			submitPin();
		}
	}

	async function submitPin() {
		isLoading = true;
		error = '';

		try {
			const response = await fetch('/api/auth/login', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ pin })
			});

			if (response.ok) {
				goto('/');
			} else {
				const data = await response.json();
				error = data.message || 'Invalid PIN';
				pin = '';
			}
		} catch (e) {
			error = 'Connection error';
			pin = '';
		} finally {
			isLoading = false;
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key >= '0' && event.key <= '9') {
			handleKeyPress(event.key);
		} else if (event.key === 'Backspace') {
			handleKeyPress('backspace');
		}
	}
</script>

<svelte:head>
	<title>Login - Daily Stock Story</title>
</svelte:head>

<svelte:window onkeydown={handleKeydown} />

<div class="login-container">
	<div class="login-card">
		<h1>Daily Stock Story</h1>
		<p class="subtitle">Enter PIN to continue</p>

		<div class="pin-display">
			{#each Array(4) as _, i}
				<div class="pin-dot" class:filled={i < pin.length} class:error={error}></div>
			{/each}
		</div>

		{#if error}
			<p class="error-message">{error}</p>
		{/if}

		<div class="keypad">
			{#each KEYS as key}
				{#if key === ''}
					<div class="key empty"></div>
				{:else if key === 'backspace'}
					<button
						class="key backspace"
						onclick={() => handleKeyPress(key)}
						disabled={isLoading || pin.length === 0}
						aria-label="Backspace"
					>
						<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M21 4H8l-7 8 7 8h13a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2z" />
							<line x1="18" y1="9" x2="12" y2="15" />
							<line x1="12" y1="9" x2="18" y2="15" />
						</svg>
					</button>
				{:else}
					<button
						class="key"
						onclick={() => handleKeyPress(key)}
						disabled={isLoading || pin.length >= 4}
					>
						{key}
					</button>
				{/if}
			{/each}
		</div>

		{#if isLoading}
			<div class="loading">Verifying...</div>
		{/if}
	</div>
</div>

<style>
	.login-container {
		min-height: 100vh;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
	}

	.login-card {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 12px;
		padding: 2rem;
		width: 100%;
		max-width: 320px;
		text-align: center;
	}

	h1 {
		font-size: 1.5rem;
		font-weight: 600;
		margin: 0;
		color: #f0f6fc;
	}

	.subtitle {
		color: #8b949e;
		margin: 0.5rem 0 2rem;
		font-size: 0.9rem;
	}

	.pin-display {
		display: flex;
		justify-content: center;
		gap: 1rem;
		margin-bottom: 1.5rem;
	}

	.pin-dot {
		width: 16px;
		height: 16px;
		border-radius: 50%;
		border: 2px solid #30363d;
		background: transparent;
		transition: all 0.15s ease;
	}

	.pin-dot.filled {
		background: #58a6ff;
		border-color: #58a6ff;
	}

	.pin-dot.error {
		border-color: #f85149;
		animation: shake 0.3s ease;
	}

	.pin-dot.filled.error {
		background: #f85149;
	}

	@keyframes shake {
		0%, 100% { transform: translateX(0); }
		25% { transform: translateX(-4px); }
		75% { transform: translateX(4px); }
	}

	.error-message {
		color: #f85149;
		font-size: 0.875rem;
		margin: 0 0 1rem;
	}

	.keypad {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 0.75rem;
		max-width: 240px;
		margin: 0 auto;
	}

	.key {
		aspect-ratio: 1;
		border: none;
		border-radius: 50%;
		font-size: 1.5rem;
		font-weight: 500;
		background: #21262d;
		color: #f0f6fc;
		cursor: pointer;
		transition: all 0.15s ease;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.key:hover:not(:disabled) {
		background: #30363d;
	}

	.key:active:not(:disabled) {
		background: #484f58;
		transform: scale(0.95);
	}

	.key:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.key.empty {
		background: transparent;
		cursor: default;
	}

	.key.backspace {
		background: #21262d;
	}

	.key.backspace svg {
		width: 24px;
		height: 24px;
	}

	.loading {
		margin-top: 1rem;
		color: #8b949e;
		font-size: 0.875rem;
	}

	@media (max-width: 380px) {
		.login-card {
			padding: 1.5rem;
		}

		.keypad {
			gap: 0.5rem;
		}

		.key {
			font-size: 1.25rem;
		}
	}
</style>
