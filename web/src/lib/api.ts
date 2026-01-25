/**
 * API client for Daily Stock Story
 */

import type {
	PortfolioResponse,
	RegSHOResponse,
	RecommendationsResponse,
	BriefingResponse,
	UserProfile,
	ProfileCreateRequest,
	ProfileCheckResponse
} from './types';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function getAuthHeaders(): Record<string, string> {
	const token = typeof localStorage !== 'undefined' ? localStorage.getItem('access_token') : null;
	return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchApi<T>(endpoint: string): Promise<T> {
	const response = await fetch(`${API_BASE}${endpoint}`);

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
		throw new Error(error.detail || `HTTP ${response.status}`);
	}

	return response.json();
}

async function fetchApiAuth<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
	const response = await fetch(`${API_BASE}${endpoint}`, {
		...options,
		headers: {
			'Content-Type': 'application/json',
			...getAuthHeaders(),
			...options.headers
		}
	});

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

// Profile API functions
export async function checkProfile(): Promise<ProfileCheckResponse> {
	return fetchApiAuth<ProfileCheckResponse>('/api/profile/check');
}

export async function getProfile(): Promise<UserProfile> {
	return fetchApiAuth<UserProfile>('/api/profile/');
}

export async function createProfile(data: ProfileCreateRequest): Promise<UserProfile> {
	return fetchApiAuth<UserProfile>('/api/profile/', {
		method: 'POST',
		body: JSON.stringify(data)
	});
}

export async function updateProfile(data: ProfileCreateRequest): Promise<UserProfile> {
	return fetchApiAuth<UserProfile>('/api/profile/', {
		method: 'PUT',
		body: JSON.stringify(data)
	});
}
