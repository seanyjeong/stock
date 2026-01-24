/// <reference types="@sveltejs/kit" />
/// <reference lib="webworker" />

declare let self: ServiceWorkerGlobalScope;

import { build, files, version } from '$service-worker';

// Cache names
const STATIC_CACHE = `static-${version}`;
const API_CACHE = 'api-cache';

// Static assets to cache
const STATIC_ASSETS = [
	...build, // built JS/CSS files
	...files  // static files (icons, manifest, etc.)
];

// API endpoints to cache for offline
const API_PATTERNS = [
	'/api/briefing'
];

// Install: cache static assets
self.addEventListener('install', (event) => {
	event.waitUntil(
		caches.open(STATIC_CACHE).then((cache) => {
			return cache.addAll(STATIC_ASSETS);
		})
	);
	// Activate immediately
	self.skipWaiting();
});

// Activate: clean up old caches
self.addEventListener('activate', (event) => {
	event.waitUntil(
		caches.keys().then((keys) => {
			return Promise.all(
				keys
					.filter((key) => key.startsWith('static-') && key !== STATIC_CACHE)
					.map((key) => caches.delete(key))
			);
		})
	);
	// Take control of all pages immediately
	self.clients.claim();
});

// Fetch: serve from cache with network fallback
self.addEventListener('fetch', (event) => {
	const { request } = event;
	const url = new URL(request.url);

	// Skip non-GET requests
	if (request.method !== 'GET') {
		return;
	}

	// Handle API requests (network first, cache fallback)
	if (API_PATTERNS.some((pattern) => url.pathname.startsWith(pattern))) {
		event.respondWith(networkFirst(request));
		return;
	}

	// Handle static assets (cache first)
	if (url.origin === self.location.origin) {
		event.respondWith(cacheFirst(request));
	}
});

// Cache-first strategy for static assets
async function cacheFirst(request: Request): Promise<Response> {
	const cached = await caches.match(request);
	if (cached) {
		return cached;
	}

	try {
		const response = await fetch(request);
		// Cache successful responses
		if (response.ok && response.type === 'basic') {
			const cache = await caches.open(STATIC_CACHE);
			cache.put(request, response.clone());
		}
		return response;
	} catch {
		// Return offline fallback if available
		return new Response('Offline', { status: 503 });
	}
}

// Network-first strategy for API requests
async function networkFirst(request: Request): Promise<Response> {
	try {
		const response = await fetch(request);
		// Cache successful API responses
		if (response.ok) {
			const cache = await caches.open(API_CACHE);
			cache.put(request, response.clone());
		}
		return response;
	} catch {
		// Fallback to cached response when offline
		const cached = await caches.match(request);
		if (cached) {
			return cached;
		}
		// Return error response if no cache
		return new Response(
			JSON.stringify({ error: 'Offline', cached: false }),
			{
				status: 503,
				headers: { 'Content-Type': 'application/json' }
			}
		);
	}
}
