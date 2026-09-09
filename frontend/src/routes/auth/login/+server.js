import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

const PASSCODE = env.DASHBOARD_PASSCODE || '1234';
const COOKIE_NAME = 'openxc_dashboard_auth';
const COOKIE_MAX_AGE = 60 * 60 * 24 * 30; // 30 days

export async function POST({ request, cookies }) {
	const body = await request.json().catch(() => ({}));
	const passcode = typeof body.passcode === 'string' ? body.passcode : '';

	if (passcode !== PASSCODE) {
		return json({ ok: false }, { status: 401 });
	}

	cookies.set(COOKIE_NAME, 'granted', {
		path: '/',
		httpOnly: true,
		sameSite: 'lax',
		maxAge: COOKIE_MAX_AGE,
		// SvelteKit defaults `secure` to true for any hostname other than
		// literal "localhost" (see @sveltejs/kit cookie.js), which silently
		// drops this cookie when the dashboard is reached over plain HTTP
		// via a LAN IP or raspberrypi.local — exactly how this app is meant
		// to be used (nginx never terminates TLS here). Force it off.
		secure: false
	});
	return json({ ok: true });
}
