import { env } from '$env/dynamic/private';
import type { PageServerLoad } from './$types';
import type {
	RegSHOResponse,
	RecommendationsResponse,
	BlogResponse,
	SqueezeResponse
} from '$lib/types';

interface AnnouncementsResponse {
	announcements: Array<{
		id: number;
		title: string;
		content: string;
		is_important: boolean;
		created_at: string | null;
	}>;
	count: number;
}

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

export const load: PageServerLoad = async ({ fetch, setHeaders }) => {
	setHeaders({ 'cache-control': 'no-cache, max-age=0' });

	// Portfolio is loaded client-side with auth token
	const [regsho, recommendations, blog, announcements, squeeze] = await Promise.all([
		fetchApi<RegSHOResponse>('/api/regsho', fetch),
		fetchApi<RecommendationsResponse>('/api/recommendations', fetch),
		fetchApi<BlogResponse>('/api/blog', fetch),
		fetchApi<AnnouncementsResponse>('/api/announcements/', fetch),
		fetchApi<SqueezeResponse>('/api/squeeze', fetch)
	]);

	const hasData = regsho || recommendations || blog || announcements || squeeze;

	return {
		regsho,
		recommendations,
		blog,
		announcements,
		squeeze,
		error: hasData ? null : 'Failed to load data from API'
	};
};
