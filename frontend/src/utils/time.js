/**
 * Utility functions for Indian Standard Time (IST) formatting
 */

export function formatIST(dateVal) {
  if (!dateVal) return 'N/A';
  try {
    let date;
    if (typeof dateVal === 'number') {
      date = new Date(dateVal > 1e11 ? dateVal : dateVal * 1000);
    } else if (typeof dateVal === 'string') {
      const s = dateVal.trim();
      if (/^\d+(\.\d+)?$/.test(s)) {
        const num = Number(s);
        date = new Date(num > 1e11 ? num : num * 1000);
      } else {
        // If naive UTC string without Z or offset, append Z so JS treats as UTC
        const iso = s.endsWith('Z') || s.includes('+') ? s : s + 'Z';
        date = new Date(iso);
      }
    } else if (dateVal instanceof Date) {
      date = dateVal;
    } else {
      date = new Date(dateVal);
    }

    if (isNaN(date.getTime())) return String(dateVal);

    return (
      date.toLocaleTimeString('en-IN', {
        timeZone: 'Asia/Kolkata',
        hour: 'numeric',
        minute: '2-digit',
        second: '2-digit',
        hour12: true,
      }) + ' IST'
    );
  } catch {
    return String(dateVal);
  }
}

/**
 * Ensures any timeline string (e.g. "[14:47:18] [LOG] ...") is converted to IST format.
 */
export function formatTimelineEntryIST(entry) {
  if (!entry || typeof entry !== 'string') return entry;
  if (entry.includes('IST')) return entry;

  const match = entry.match(/^\[(\d{1,2}):(\d{2}):(\d{2})(?:\.\d+)?\](.*)/);
  if (!match) return entry;

  const hours = parseInt(match[1], 10);
  const minutes = parseInt(match[2], 10);
  const seconds = parseInt(match[3], 10);

  // UTC time shifted to IST (+5h 30m)
  let totalMinutes = hours * 60 + minutes + 330;
  totalMinutes = (totalMinutes + 1440) % 1440;
  const istHours24 = Math.floor(totalMinutes / 60);
  const istMinutes = totalMinutes % 60;
  const ampm = istHours24 >= 12 ? 'pm' : 'am';
  const istHours12 = istHours24 % 12 || 12;
  const pad = (n) => String(n).padStart(2, '0');

  const istTimeStr = `[${istHours12}:${pad(istMinutes)}:${pad(seconds)} ${ampm} IST]`;
  return `${istTimeStr}${match[4]}`;
}
