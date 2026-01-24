import { env } from '$env/dynamic/private';
import type { PageServerLoad } from './$types';
import type {
	RegSHOResponse,
	RecommendationsResponse,
	BlogResponse
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

export const load: PageServerLoad = async ({ fetch }) => {
	// Portfolio is loaded client-side with auth token
	const [regsho, recommendations, blog, announcements] = await Promise.all([
		fetchApi<RegSHOResponse>('/api/regsho', fetch),
		fetchApi<RecommendationsResponse>('/api/recommendations', fetch),
		fetchApi<BlogResponse>('/api/blog', fetch),
		fetchApi<AnnouncementsResponse>('/api/announcements/', fetch)
	]);

	const hasData = regsho || recommendations || blog || announcements;

	return {
		regsho,
		recommendations,
		blog,
		announcements,
		error: hasData ? null : 'Failed to load data from API'
	};
};
