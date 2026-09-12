import { writable } from 'svelte/store';

const STORAGE_KEY = 'theme';

function initial() {
	if (typeof document !== 'undefined' && document.documentElement.dataset.theme === 'light') {
		return 'light';
	}
	return 'dark';
}

export const theme = writable(initial());

theme.subscribe((value) => {
	if (typeof document === 'undefined') return;
	document.documentElement.dataset.theme = value;
	try {
		localStorage.setItem(STORAGE_KEY, value);
	} catch {
		// private browsing / storage disabled — theme just won't persist
	}
});

export function toggleTheme() {
	theme.update((v) => (v === 'light' ? 'dark' : 'light'));
}
