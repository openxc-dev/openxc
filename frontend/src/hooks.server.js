import { env } from '$env/dynamic/private';

const API_TARGET = env.INTERNAL_API_URL || 'http://backend:8000';

/** Proxies /api/* requests from the browser to the backend service.
 * This lets the browser always talk to a single origin (this frontend),
 * regardless of what host/IP the app is accessed from (laptop, Pi, etc).
 */
export async function handle({ event, resolve }) {
	if (event.url.pathname.startsWith('/api')) {
		const target = API_TARGET + event.url.pathname + event.url.search;
		const headers = new Headers(event.request.headers);
		headers.delete('host');
		headers.delete('content-length');

		const hasBody = !['GET', 'HEAD'].includes(event.request.method);

		let res;
		try {
			res = await fetch(target, {
				method: event.request.method,
				headers,
				body: hasBody ? await event.request.arrayBuffer() : undefined
			});
		} catch (err) {
			return new Response(JSON.stringify({ detail: 'Backend unavailable' }), {
				status: 502,
				headers: { 'content-type': 'application/json' }
			});
		}

		const resHeaders = new Headers(res.headers);
		resHeaders.delete('content-encoding');
		resHeaders.delete('transfer-encoding');

		return new Response(res.body, { status: res.status, headers: resHeaders });
	}

	return resolve(event);
}
