export function historyRange(preset, fromDate = "", throughDate = "") {
    if (preset === "all") return {};
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const start = new Date(today);
    const end = new Date(today);
    end.setDate(end.getDate() + 1);
    if (preset === "yesterday") {
        start.setDate(start.getDate() - 1);
        end.setTime(today.getTime());
    } else if (preset === "week") {
        start.setDate(start.getDate() - 6);
    } else if (preset === "month") {
        start.setDate(start.getDate() - 29);
    } else if (preset === "custom") {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(fromDate) || !/^\d{4}-\d{2}-\d{2}$/.test(throughDate)) {
            throw new Error("Choose both dates.");
        }
        start.setTime(new Date(`${fromDate}T00:00:00`).getTime());
        end.setTime(new Date(`${throughDate}T00:00:00`).getTime());
        end.setDate(end.getDate() + 1);
    }
    if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || start >= end) {
        throw new Error("The end date must be on or after the start date.");
    }
    return { from: start.toISOString(), until: end.toISOString() };
}

export function eventInRange(event, range) {
    const timestamp = new Date(event.received_at).getTime();
    return (!range.from || timestamp >= new Date(range.from).getTime())
        && (!range.until || timestamp < new Date(range.until).getTime());
}
