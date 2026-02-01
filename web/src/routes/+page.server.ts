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
		// 캐시 무효화를 위해 타임스탬프 추가
		const separator = endpoint.includes('?') ? '&' : '?';
		const url = `${API_BASE}${endpoint}${separator}_t=${Date.now()}`;
		const response = await fetch(url, {
			headers: {
				'Cache-Control': 'no-cache, no-store, must-revalidate',
				'Pragma': 'no-cache'
			}
		});
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
	// 브라우저 캐시 완전 비활성화
	setHeaders({
		'cache-control': 'no-cache, no-store, must-revalidate',
		'pragma': 'no-cache',
		'expires': '0'
	});

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
		// 데이터 로드 시간을 포함해 클라이언트에서 캐시 여부 확인 가능
		_loadedAt: Date.now(),
		error: hasData ? null : 'Failed to load data from API'
	};
};
