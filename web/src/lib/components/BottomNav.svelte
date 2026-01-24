<script lang="ts">
	import { page } from '$app/stores';
	import Icon from './Icons.svelte';

	const navItems = [
		{ href: '/', label: '홈', icon: 'home' },
		{ href: '/portfolio', label: '포트폴리오', icon: 'wallet' },
		{ href: '/watchlist', label: '관심', icon: 'star' },
		{ href: '/history', label: '이력', icon: 'clock' },
		{ href: '/settings', label: '설정', icon: 'settings' }
	];

	let currentPath = $derived($page.url.pathname);
</script>

<nav class="bottom-nav">
	{#each navItems as item}
		<a
			href={item.href}
			class="nav-item"
			class:active={currentPath === item.href || (item.href !== '/' && currentPath.startsWith(item.href))}
		>
			<Icon name={item.icon} size={22} />
			<span class="nav-label">{item.label}</span>
		</a>
	{/each}
</nav>

<style>
	.bottom-nav {
		position: fixed;
		bottom: 0;
		left: 0;
		right: 0;
		display: flex;
		justify-content: space-around;
		align-items: center;
		background: #161b22;
		border-top: 1px solid #30363d;
		padding: 0.5rem 0;
		padding-bottom: calc(0.5rem + env(safe-area-inset-bottom, 0px));
		z-index: 1000;
	}

	.nav-item {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		padding: 0.375rem 0.5rem;
		text-decoration: none;
		color: #8b949e;
		transition: color 0.15s;
		border-radius: 8px;
		min-width: 56px;
	}

	.nav-item:hover {
		color: #f0f6fc;
	}

	.nav-item.active {
		color: #58a6ff;
	}

	.nav-label {
		font-size: 0.65rem;
		font-weight: 500;
	}
</style>
