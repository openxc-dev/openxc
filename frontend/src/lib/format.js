export function formatTime(seconds) {
	if (seconds === null || seconds === undefined) return '—';
	const total = Number(seconds);
	const mins = Math.floor(total / 60);
	const secs = total - mins * 60;
	return `${mins}:${secs.toFixed(1).padStart(4, '0')}`;
}

export function parseTimeToSeconds(input) {
	if (!input) return null;
	const trimmed = String(input).trim();
	if (!trimmed) return null;
	if (/^\d+(\.\d+)?$/.test(trimmed)) return parseFloat(trimmed);

	const parts = trimmed.split(':').map((p) => p.trim());
	if (parts.some((p) => p === '' || isNaN(Number(p)))) return null;

	let seconds = 0;
	for (const part of parts) {
		seconds = seconds * 60 + parseFloat(part);
	}
	return seconds;
}

export function formatClock(seconds) {
	const total = Math.max(0, Math.floor(Number(seconds) || 0));
	const mins = Math.floor(total / 60);
	const secs = total % 60;
	return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

export function formatDate(dateStr) {
	if (!dateStr) return '';
	const d = new Date(dateStr + 'T00:00:00');
	return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function ordinal(n) {
	if (n === null || n === undefined) return '—';
	const s = ['th', 'st', 'nd', 'rd'];
	const v = n % 100;
	return n + (s[(v - 20) % 10] || s[v] || s[0]);
}
