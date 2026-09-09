const BASE = '/api';

async function request(path, options = {}) {
	const res = await fetch(`${BASE}${path}`, {
		headers: { 'content-type': 'application/json' },
		...options
	});

	if (!res.ok) {
		let detail = res.statusText;
		try {
			const body = await res.json();
			detail = body.detail || detail;
		} catch {
			// ignore
		}
		throw new Error(detail);
	}

	if (res.status === 204) return null;
	return res.json();
}

const get = (path) => request(path);
const post = (path, data) => request(path, { method: 'POST', body: JSON.stringify(data) });
const patch = (path, data) => request(path, { method: 'PATCH', body: JSON.stringify(data) });
const del = (path) => request(path, { method: 'DELETE' });

export const api = {
	// Meets
	listMeets: () => get('/meets'),
	getMeet: (id) => get(`/meets/${id}`),
	getActiveMeet: () => get('/meets/active'),
	createMeet: (data) => post('/meets', data),
	updateMeet: (id, data) => patch(`/meets/${id}`, data),
	deleteMeet: (id) => del(`/meets/${id}`),

	// Races
	listRaces: (meetId) => get(`/meets/${meetId}/races`),
	getRace: (id) => get(`/races/${id}`),
	createRace: (meetId, data) => post(`/meets/${meetId}/races`, data),
	updateRace: (id, data) => patch(`/races/${id}`, data),
	deleteRace: (id) => del(`/races/${id}`),

	// Starts
	listStarts: (meetId) => get(`/meets/${meetId}/starts`),
	createStart: (meetId, data) => post(`/meets/${meetId}/starts`, data),
	deleteStart: (id) => del(`/starts/${id}`),

	// Teams
	listTeams: (meetId) => get(`/meets/${meetId}/teams`),
	createTeam: (meetId, data) => post(`/meets/${meetId}/teams`, data),
	bulkCreateTeams: (meetId, names) => post(`/meets/${meetId}/teams/bulk`, { names }),
	updateTeam: (id, data) => patch(`/teams/${id}`, data),
	deleteTeam: (id) => del(`/teams/${id}`),

	// Athletes
	listAthletes: (meetId, params = {}) => {
		const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v));
		const suffix = qs.toString() ? `?${qs}` : '';
		return get(`/meets/${meetId}/athletes${suffix}`);
	},
	createAthlete: (meetId, data) => post(`/meets/${meetId}/athletes`, data),
	bulkCreateAthletes: (meetId, athletes) => post(`/meets/${meetId}/athletes/bulk`, { athletes }),
	updateAthlete: (id, data) => patch(`/athletes/${id}`, data),
	deleteAthlete: (id) => del(`/athletes/${id}`),
	bulkUpdateAthleteTeam: (meetId, athleteIds, teamId) =>
		patch(`/meets/${meetId}/athletes/bulk`, { athlete_ids: athleteIds, team_id: teamId }),
	bulkUpdateAthleteRace: (meetId, athleteIds, raceId) =>
		patch(`/meets/${meetId}/athletes/bulk`, { athlete_ids: athleteIds, race_id: raceId }),

	// Time entry — meet-scoped; race is resolved server-side from the bib,
	// so several races can be timed concurrently through one entry stream.
	listFinishes: (meetId) => get(`/meets/${meetId}/finishes`),
	recordFinish: (meetId, data) => post(`/meets/${meetId}/finishes`, data),

	// Finish order — race-scoped viewing/correction of one race's results.
	listFinishers: (raceId) => get(`/races/${raceId}/finishers`),
	updateFinisher: (id, data) => patch(`/finishers/${id}`, data),
	deleteFinisher: (id) => del(`/finishers/${id}`),
	reorderFinishers: (raceId, orderedIds) =>
		post(`/races/${raceId}/finishers/reorder`, { ordered_finisher_ids: orderedIds }),

	// Results
	getRaceResults: (raceId) => get(`/races/${raceId}/results`),
	getMeetResults: (meetId) => get(`/meets/${meetId}/results`),
	getRaceResultsBySlug: (meetId, raceSlug) => get(`/meets/${meetId}/races/${raceSlug}/results`),

	// Readers — not meet-scoped; a reader is hardware, reused across meets.
	listReaders: () => get('/readers'),
	getReader: (label) => get(`/readers/${label}`),
	createReader: (data) => post('/readers', data),
	connectReader: (label) => post(`/readers/${label}/connect`),
	disconnectReader: (label) => post(`/readers/${label}/disconnect`),
	startReading: (label) => post(`/readers/${label}/start`),
	stopReading: (label) => post(`/readers/${label}/stop`),
	listReaderTags: (label) => get(`/readers/${label}/tags`)
};
