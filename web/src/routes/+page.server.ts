import { env } from '$env/dynamic/private';
import type { PageServerLoad } from './$types';
import type {
	PortfolioResponse,
	RegSHOResponse,
	RecommendationsResponse
} from '$lib/types';

const API_BASE = env.API_URL || 'http://localhost:8000';

async function fetchApi<T>(endpoint: string, fetch: typeof globalThis.fetch): Promise<T | null> {
	try {
		const response = await fetch(`${API_BASE}${endpoint}`);
		if (!response.ok) {
			console.error(`API error ${endpoint}: ${response.status}`);
			return null;
		}
		return response.json();
	} catch (error) {
		console.error(`API fetch error ${endpoint}:`, error);
		return null;
	}
}

export const load: PageServerLoad = async ({ fetch }) => {
	const [portfolio, regsho, recommendations] = await Promise.all([
		fetchApi<PortfolioResponse>('/api/portfolio', fetch),
		fetchApi<RegSHOResponse>('/api/regsho', fetch),
		fetchApi<RecommendationsResponse>('/api/recommendations', fetch)
	]);

	const hasData = portfolio || regsho || recommendations;

	return {
		portfolio,
		regsho,
		recommendations,
		error: hasData ? null : 'Failed to load data from API'
	};
};
