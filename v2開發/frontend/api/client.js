/* Same-origin request helper. Caller owns replacement/race state. */
window.FoodiemoAPI = {
    async recommendations(cursor, signal) {
        const query = new URLSearchParams({count:"3", t:String(Date.now())});
        if (cursor) query.set("cursor", cursor);
        const controller = new AbortController();
        const abort = () => controller.abort();
        signal?.addEventListener("abort", abort, {once:true});
        if (signal?.aborted) controller.abort();
        const timeout = setTimeout(abort, 10000);
        try {
            const response = await fetch(DB_CONFIG.apiUrl + "/restaurants/recommendations?" + query,
                {signal:controller.signal, credentials:"include", cache:"no-store"});
            if (!response.ok) throw new Error("RECOMMENDATIONS_UNAVAILABLE");
            const result = await response.json();
            if (!Array.isArray(result.items) || result.source !== "postgresql" ||
                result.items.length > 3 || result.items.some(x => !x || typeof x.id !== "string") ||
                new Set(result.items.map(x=>x.id)).size !== result.items.length ||
                !(result.next_cursor == null || typeof result.next_cursor === "string")) {
                throw new Error("INVALID_RECOMMENDATIONS");
            }
            return result;
        } finally {
            clearTimeout(timeout);
            signal?.removeEventListener("abort",abort);
        }
    }
};

