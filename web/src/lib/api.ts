/**
 * API client for Daily Stock Story
 */

import type {
	PortfolioResponse,
	RegSHOResponse,
	RecommendationsResponse,
	BriefingResponse
} from './types';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function fetchApi<T>(endpoint: string): Promise<T> {
	const response = await fetch(`${API_BASE}${endpoint}`);

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
		throw new Error(error.detail || `HTTP ${response.status}`);
	}

	return response.json();
}

export async function getBriefing(): Promise<BriefingResponse> {
	return fetchApi<BriefingResponse>('/api/briefing');
}

export async function getPortfolio(): Promise<PortfolioResponse> {
	return fetchApi<PortfolioResponse>('/api/portfolio');
}

export async function getRegSHO(): Promise<RegSHOResponse> {
	return fetchApi<RegSHOResponse>('/api/regsho');
}

export async function getRecommendations(): Promise<RecommendationsResponse> {
	return fetchApi<RecommendationsResponse>('/api/recommendations');
}
