<script lang="ts">
	import Icon from './Icons.svelte';

	const API_URL = import.meta.env.VITE_API_URL || 'https://stock-api.sean8320.dedyn.io';

	interface Message {
		role: 'user' | 'assistant';
		content: string;
		related_terms?: string[];
	}

	interface Props {
		onClose: () => void;
	}

	let { onClose }: Props = $props();

	let messages = $state<Message[]>([]);
	let inputValue = $state('');
	let loading = $state(false);
	let chatContainer = $state<HTMLDivElement | null>(null);

	function handleBackdropClick(e: MouseEvent) {
		if (e.target === e.currentTarget) {
			onClose();
		}
	}

	function scrollToBottom() {
		if (chatContainer) {
			setTimeout(() => {
				chatContainer!.scrollTop = chatContainer!.scrollHeight;
			}, 50);
		}
	}

	async function sendMessage(question?: string) {
		const q = question || inputValue.trim();
		if (!q || loading) return;

		// Add user message
		messages = [...messages, { role: 'user', content: q }];
		inputValue = '';
		loading = true;
		scrollToBottom();

		try {
			const res = await fetch(`${API_URL}/api/glossary/ask`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ question: q })
			});

			if (!res.ok) {
				throw new Error('응답을 가져올 수 없습니다');
			}

			const data = await res.json();
			messages = [
				...messages,
				{
					role: 'assistant',
					content: data.answer,
					related_terms: data.related_terms || []
				}
			];
		} catch (e) {
			messages = [
				...messages,
				{
					role: 'assistant',
					content: '죄송합니다. 답변을 가져오는 중 오류가 발생했습니다. 다시 시도해주세요.',
					related_terms: []
				}
			];
		} finally {
			loading = false;
			scrollToBottom();
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			sendMessage();
		}
	}

	function handleRelatedTermClick(term: string) {
		sendMessage(term);
	}
</script>

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div class="modal-backdrop" onclick={handleBackdropClick}>
	<div class="modal">
		<div class="modal-header">
			<h2><Icon name="book" size={20} /> 주식 용어사전</h2>
			<button class="close-btn" onclick={onClose}>
				<Icon name="x" size={20} />
			</button>
		</div>

		<div class="chat-container" bind:this={chatContainer}>
			{#if messages.length === 0}
				<div class="welcome-message">
					<p>주식 용어나 투자 관련 질문을 해보세요!</p>
					<div class="example-questions">
						<button class="example-btn" onclick={() => sendMessage('RSI가 뭐야?')}>
							RSI가 뭐야?
						</button>
						<button class="example-btn" onclick={() => sendMessage('숏스퀴즈 설명해줘')}>
							숏스퀴즈 설명해줘
						</button>
						<button class="example-btn" onclick={() => sendMessage('PER이랑 PBR 차이')}>
							PER이랑 PBR 차이
						</button>
					</div>
				</div>
			{:else}
				{#each messages as message}
					<div class="message {message.role}">
						<div class="message-content">
							{message.content}
						</div>
						{#if message.role === 'assistant' && message.related_terms && message.related_terms.length > 0}
							<div class="related-terms">
								<span class="related-label">관련 용어:</span>
								{#each message.related_terms as term}
									<button class="term-tag" onclick={() => handleRelatedTermClick(term)}>
										{term}
									</button>
								{/each}
							</div>
						{/if}
					</div>
				{/each}
			{/if}

			{#if loading}
				<div class="message assistant">
					<div class="message-content loading-dots">
						<span></span>
						<span></span>
						<span></span>
					</div>
				</div>
			{/if}
		</div>

		<div class="input-area">
			<input
				type="text"
				placeholder="용어나 질문을 입력하세요..."
				bind:value={inputValue}
				onkeydown={handleKeydown}
				disabled={loading}
			/>
			<button class="send-btn" onclick={() => sendMessage()} disabled={loading || !inputValue.trim()}>
				<Icon name="send" size={18} />
			</button>
		</div>
	</div>
</div>

<style>
	.modal-backdrop {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.8);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: 1rem;
	}

	.modal {
		background: #161b22;
		border: 1px solid #30363d;
		border-radius: 16px;
		width: 100%;
		max-width: 420px;
		max-height: 80vh;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.modal-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1rem 1.25rem;
		border-bottom: 1px solid #30363d;
	}

	.modal-header h2 {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin: 0;
		font-size: 1.1rem;
		color: #f0f6fc;
	}

	.close-btn {
		background: none;
		border: none;
		color: #8b949e;
		cursor: pointer;
		padding: 0.25rem;
		border-radius: 4px;
		transition: all 0.15s;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.close-btn:hover {
		background: #21262d;
		color: #f0f6fc;
	}

	.chat-container {
		flex: 1;
		overflow-y: auto;
		padding: 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		min-height: 300px;
		max-height: 400px;
	}

	.welcome-message {
		text-align: center;
		color: #8b949e;
		padding: 2rem 1rem;
	}

	.welcome-message p {
		margin: 0 0 1rem;
		font-size: 0.9rem;
	}

	.example-questions {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.example-btn {
		padding: 0.6rem 1rem;
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 8px;
		color: #58a6ff;
		cursor: pointer;
		font-size: 0.85rem;
		transition: all 0.15s;
	}

	.example-btn:hover {
		background: #30363d;
		border-color: #58a6ff;
	}

	.message {
		display: flex;
		flex-direction: column;
		max-width: 85%;
	}

	.message.user {
		align-self: flex-end;
	}

	.message.assistant {
		align-self: flex-start;
	}

	.message-content {
		padding: 0.75rem 1rem;
		border-radius: 12px;
		font-size: 0.9rem;
		line-height: 1.5;
		white-space: pre-wrap;
	}

	.message.user .message-content {
		background: #238636;
		color: white;
		border-bottom-right-radius: 4px;
	}

	.message.assistant .message-content {
		background: #21262d;
		color: #f0f6fc;
		border-bottom-left-radius: 4px;
	}

	.related-terms {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem;
		margin-top: 0.5rem;
		padding-left: 0.25rem;
	}

	.related-label {
		font-size: 0.7rem;
		color: #8b949e;
		width: 100%;
		margin-bottom: 0.125rem;
	}

	.term-tag {
		padding: 0.25rem 0.5rem;
		background: rgba(88, 166, 255, 0.15);
		border: 1px solid #58a6ff;
		border-radius: 12px;
		color: #58a6ff;
		font-size: 0.75rem;
		cursor: pointer;
		transition: all 0.15s;
	}

	.term-tag:hover {
		background: rgba(88, 166, 255, 0.3);
	}

	/* Loading animation */
	.loading-dots {
		display: flex;
		gap: 0.25rem;
		padding: 0.75rem 1rem;
	}

	.loading-dots span {
		width: 8px;
		height: 8px;
		background: #8b949e;
		border-radius: 50%;
		animation: bounce 1.4s infinite ease-in-out both;
	}

	.loading-dots span:nth-child(1) {
		animation-delay: -0.32s;
	}

	.loading-dots span:nth-child(2) {
		animation-delay: -0.16s;
	}

	@keyframes bounce {
		0%, 80%, 100% {
			transform: scale(0);
		}
		40% {
			transform: scale(1);
		}
	}

	.input-area {
		display: flex;
		gap: 0.5rem;
		padding: 1rem;
		border-top: 1px solid #30363d;
		background: #0d1117;
	}

	.input-area input {
		flex: 1;
		padding: 0.75rem 1rem;
		background: #21262d;
		border: 1px solid #30363d;
		border-radius: 8px;
		color: #f0f6fc;
		font-size: 0.9rem;
		outline: none;
		transition: border-color 0.15s;
	}

	.input-area input:focus {
		border-color: #58a6ff;
	}

	.input-area input::placeholder {
		color: #6e7681;
	}

	.input-area input:disabled {
		opacity: 0.6;
	}

	.send-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0 1rem;
		background: #238636;
		border: none;
		border-radius: 8px;
		color: white;
		cursor: pointer;
		transition: all 0.15s;
	}

	.send-btn:hover:not(:disabled) {
		background: #2ea043;
	}

	.send-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>
