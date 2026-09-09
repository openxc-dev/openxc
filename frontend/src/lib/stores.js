import { writable } from 'svelte/store';
import { api } from './api';

function createMeetsStore() {
	const { subscribe, set } = writable([]);

	async function refresh() {
		const meets = await api.listMeets();
		set(meets);
		return meets;
	}

	return { subscribe, refresh };
}

export const meetsStore = createMeetsStore();
