<script lang="ts">
	interface Props {
		ticker: string;
		holdingsOnList: string[];
	}

	let { ticker, holdingsOnList }: Props = $props();

	const isOnRegSHO = $derived(holdingsOnList.includes(ticker));
</script>

{#if isOnRegSHO}
	<span class="regsho-badge" title="RegSHO Threshold List">
		RegSHO
	</span>
{/if}

<style>
	.regsho-badge {
		display: inline-flex;
		align-items: center;
		font-size: 0.625rem;
		font-weight: 600;
		padding: 0.125rem 0.375rem;
		border-radius: 3px;
		background: linear-gradient(135deg, #f85149 0%, #da3633 100%);
		color: white;
		margin-left: 0.5rem;
		text-transform: uppercase;
		letter-spacing: 0.025em;
		box-shadow: 0 1px 2px rgba(248, 81, 73, 0.3);
		cursor: help;
	}
</style>
