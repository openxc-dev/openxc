export function load({ cookies }) {
	return {
		authenticated: cookies.get('openxc_dashboard_auth') === 'granted'
	};
}
