/* ── State ── */
let projChart, ttChart, megaChart;
let routeMap, layer401, layer407;
let incidentLayer = null;       // Leaflet layer group for Ontario 511 incidents
let currentData = null; // latest /api/current response
let surveyLocation = { lat: null, lng: null, name: null };
let currentDirection = 'east'; // 'east' | 'west'
let chartDirection = 'east'; // direction used by chart tabs
let surveyRouteChoice = null; // '401' | '407'
let activeRange = '24h'; // currently selected mega-chart range

const DIRECTION_LABELS = {
    east: {
        from: 'PetroPoint West',
        to:   'PetroPoint East',
        label: 'Eastbound →',
        sub:   'Hornby → Bowmanville',
    },
    west: {
        from: 'PetroPoint East',
        to:   'PetroPoint West',
        label: '← Westbound',
        sub:   'Bowmanville → Hornby',
    },
};

/* ── Helpers ── */
function fmt(v, decimals = 0) {
    if (v == null || v === undefined) return '--';
    return Number(v).toFixed(decimals);
}

async function fetchJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

function setColor(el, market, thesis) {
    if (market == null) { el.className = 'big-number'; return; }
    const ratio = market / thesis;
    if (ratio <= 1.0) el.className = 'big-number good';
    else if (ratio <= 1.5) el.className = 'big-number moderate';
    else el.className = 'big-number bad';
}

/* ── Polyline decoder (Google encoded polyline → [lat, lng] array) ── */
function decodePolyline(encoded) {
    const points = [];
    let index = 0, lat = 0, lng = 0;
    while (index < encoded.length) {
        let b, shift = 0, result = 0;
        do { b = encoded.charCodeAt(index++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
        lat += (result & 1) ? ~(result >> 1) : (result >> 1);
        shift = 0; result = 0;
        do { b = encoded.charCodeAt(index++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
        lng += (result & 1) ? ~(result >> 1) : (result >> 1);
        points.push([lat / 1e5, lng / 1e5]);
    }
    return points;
}

/* ── Map ── */
function initMap() {
    routeMap = L.map('routeMap', {
        center: [43.72, -79.40],
        zoom: 9,
        zoomControl: true,
        attributionControl: true,
    });

    // Bright CARTO Voyager tiles
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
        maxZoom: 18,
    }).addTo(routeMap);

    // Default corridors: Hornby → Bowmanville via 401 or 407
    // 401 goes south through Toronto; 407 sweeps north. Replaced by live polylines.
    const default401 = [
        [43.567, -79.823], [43.60, -79.62], [43.65, -79.50],
        [43.70, -79.40], [43.76, -79.34], [43.80, -79.18],
        [43.85, -79.02], [43.87, -78.87], [43.892, -78.692]
    ];
    const default407 = [
        [43.567, -79.823], [43.60, -79.75], [43.70, -79.63],
        [43.80, -79.52], [43.84, -79.38], [43.87, -79.15],
        [43.88, -78.97], [43.90, -78.78], [43.892, -78.692]
    ];

    layer401 = L.polyline(default401, {
        color: '#3b82f6', weight: 5, opacity: 0.9,
        dashArray: null,
    }).addTo(routeMap).bindPopup('<strong>Hwy 401 — FREE</strong><br>Through Toronto<br>No toll');

    layer407 = L.polyline(default407, {
        color: '#8b5cf6', weight: 5, opacity: 0.9,
        dashArray: '10 6',
    }).addTo(routeMap).bindPopup('<strong>Hwy 407 — TOLL</strong><br>Bypass Toronto<br>407 ETR (toll) + 407 East (free)');

    // Truck stop markers (survey sites)
    const stopIcon = (label, color) => L.divIcon({
        html: `<div style="background:#fff;border:2px solid ${color};border-radius:8px;padding:3px 8px;font-size:11px;font-weight:700;color:${color};white-space:nowrap;box-shadow:0 2px 6px rgba(0,0,0,.18)">${label}</div>`,
        iconAnchor: [45, 14], className: '',
    });

    L.marker([43.5665, -79.8228], { icon: stopIcon('⛽ PetroPoint West', '#2563eb') })
        .addTo(routeMap).bindPopup('<strong>PetroPoint West — Hornby</strong><br>7443 Trafalgar Rd, Hornby · Survey site (WEST)<br><em>West of the 401/407 decision point</em>');
    L.marker([43.8919, -78.6918], { icon: stopIcon('⛽ PetroPoint East', '#7c3aed') })
        .addTo(routeMap).bindPopup('<strong>PetroPoint East — Bowmanville</strong><br>2475 Energy Dr · Survey site (EAST)<br><em>East of 407 East merge point</em>');

    // Diverge / converge markers
    const splitIcon = L.divIcon({
        html: '<div style="font-size:18px">🔀</div>',
        iconSize: [22, 22], iconAnchor: [11, 22], className: '',
    });
    const mergeIcon = L.divIcon({
        html: '<div style="font-size:18px">🔁</div>',
        iconSize: [22, 22], iconAnchor: [11, 22], className: '',
    });
    L.marker([43.545, -79.720], { icon: splitIcon })
        .addTo(routeMap).bindPopup('<strong>DIVERGE — 401 @ Hwy 403</strong><br>Last exit to take 407 ETR (toll)');
    L.marker([43.895, -78.755], { icon: mergeIcon })
        .addTo(routeMap).bindPopup('<strong>CONVERGE — 401 @ Hwy 418</strong><br>407 East (free) re-joins 401 here');

    // Fit full corridor
    const westPt = L.marker([43.5665, -79.8228]);
    const eastPt = L.marker([43.8919, -78.6918]);
    const group = L.featureGroup([layer401, layer407, westPt, eastPt]);
    routeMap.fitBounds(group.getBounds().pad(0.10));
}

function updateMapPolylines(r401, r407) {
    if (r401.polyline) {
        const coords = decodePolyline(r401.polyline);
        layer401.setLatLngs(coords);
    }
    if (r407.polyline) {
        const coords = decodePolyline(r407.polyline);
        layer407.setLatLngs(coords);
    }
    // Refit — include truck stop endpoints for full corridor view
    const wPt = L.marker([43.5665, -79.8228]);
    const ePt = L.marker([43.8919, -78.6918]);
    const group = L.featureGroup([layer401, layer407, wPt, ePt]);
    routeMap.fitBounds(group.getBounds().pad(0.10));
}

/* ── Current conditions ── */
async function updateCurrent() {
    try {
        const d = await fetchJSON(`/api/current?direction=${currentDirection}`);
        const r401 = d.route_401;
        const r407 = d.route_407;
        const toll = d.toll;
        const vot = d.vot;

        // ── Hero cards ──
        const el = (id) => document.getElementById(id);
        el('heroTT401').textContent = fmt(r401.tt_minutes);
        el('heroDelay401').textContent = fmt(r401.delay_minutes);
        el('heroDist401').textContent = fmt(r401.distance_km, 0);
        el('heroFF401').textContent = fmt(r401.freeflow_minutes, 0);

        el('heroTT407').textContent = fmt(r407.tt_minutes);
        el('heroDelay407').textContent = fmt(r407.delay_minutes);
        el('heroDist407').textContent = fmt(r407.distance_km, 0);
        el('heroFF407').textContent = fmt(r407.freeflow_minutes, 0);
        el('heroToll').textContent = `$${fmt(toll.total, 0)}`;
        const tp = toll.time_period;
        el('heroTimePeriod').textContent = tp.replace('_', '-') + ' toll';
        el('heroTollDetail').textContent = `${tp.replace('_','-')} rate`;

        // Time saved badge
        const saved = r401.tt_minutes - r407.tt_minutes;
        const savedBadge = el('timeSavedBadge');
        if (saved > 0) {
            savedBadge.textContent = `${fmt(saved, 0)} min saved on 407`;
            savedBadge.style.display = 'block';
        } else {
            savedBadge.textContent = `401 is faster right now`;
            savedBadge.style.background = 'rgba(59,130,246,0.15)';
            savedBadge.style.color = 'var(--accent)';
        }

        // Highlight the faster card
        el('heroCard401').style.opacity = saved <= 0 ? '1' : '0.85';
        el('heroCard407').style.opacity = saved > 0 ? '1' : '0.85';

        // ── VOT verdict ──
        const mvEl = el('marketVot');
        if (vot.market_vot != null && saved > 0) {
            mvEl.innerHTML = `${fmt(vot.market_vot)} <span class="verdict-unit">$/hr saved</span>`;
            const ratio = vot.market_vot / vot.thesis_vot_mean;
            mvEl.className = ratio <= 1.0 ? 'verdict-vot good' : ratio <= 2.0 ? 'verdict-vot moderate' : 'verdict-vot bad';
        } else {
            mvEl.innerHTML = `401 faster <span class="verdict-unit">right now</span>`;
            mvEl.className = 'verdict-vot good';
        }
        const ratio = vot.market_vot != null ? vot.market_vot / vot.thesis_vot_mean : 999;

        el('timeSavedStat').textContent = saved > 0 ? `${fmt(saved, 0)} min` : `401 faster`;
        el('tollCostStat').textContent = `$${fmt(toll.total, 0)}`;
        el('verdictText').textContent = vot.verdict;

        // Hidden elements that may exist in older page versions
        if (el('choiceProb')) el('choiceProb').textContent = `${fmt(vot.choice_probability_toll_simulated, 1)}%`;
        if (el('fairToll')) el('fairToll').textContent = `$${fmt(vot.fair_toll_at_mean_vot, 2)}`;

        // Verdict bar
        const bar = el('verdictBar');
        if (vot.market_vot != null) {
            const pct = Math.min(100, (vot.thesis_vot_mean / vot.market_vot) * 100);
            bar.style.width = pct + '%';
            bar.style.background = ratio <= 1.0 ? 'var(--green)' : ratio <= 2.0 ? 'var(--amber)' : 'var(--red)';
        }

        // ── Toll breakdown ──
        const segDiv = el('tollSegments');
        segDiv.innerHTML = toll.segments.map(s =>
            `<div class="toll-segment">
                <span class="seg-name">${s.from} → ${s.to} (${s.distance_km}km @ $${s.rate_per_km}/km)</span>
                <span class="seg-cost">$${s.cost.toFixed(2)}</span>
            </div>`
        ).join('') + `<div class="toll-segment">
            <span class="seg-name">Trip charge (transponder)</span>
            <span class="seg-cost">$${toll.trip_charge.toFixed(2)}</span>
        </div>`;
        el('tollTotal').textContent = `$${toll.total.toFixed(2)}`;
        const plabel = el('tollPeriodLabel');
        if (plabel) { plabel.textContent = tp.replace('_', '-'); plabel.className = `period-chip ${tp}`; }

        // Status
        const dot = document.getElementById('statusDot');
        const statusText = document.getElementById('statusText');
        dot.className = d.source === 'google_maps' ? 'status-dot' : 'status-dot estimated';
        statusText.textContent = d.source === 'google_maps' ? 'Live traffic data' : 'Estimated (no API key)';

        // Timestamps
        const ts = new Date(d.timestamp);
        const timeStr = ts.toLocaleTimeString();
        document.getElementById('lastUpdate').textContent = `Updated ${timeStr}`;
        document.getElementById('footerUpdate').textContent = `Updated ${timeStr}`;

        // Update map polylines
        updateMapPolylines(r401, r407);

        // Update popups with live data
        const dirLbl = DIRECTION_LABELS[currentDirection];
        layer401.setPopupContent(
            `<strong>Hwy 401 — Through Toronto</strong><br>` +
            `${dirLbl.sub}<br>` +
            `Travel time: ${fmt(r401.tt_minutes)} min<br>` +
            `Delay: ${fmt(r401.delay_minutes)} min · ${fmt(r401.distance_km)} km<br>` +
            `<em>Free — no toll</em>`
        );
        layer407.setPopupContent(
            `<strong>Hwy 407 ETR — Bypass Toronto</strong><br>` +
            `${dirLbl.sub}<br>` +
            `Travel time: ${fmt(r407.tt_minutes)} min<br>` +
            `Delay: ${fmt(r407.delay_minutes)} min · ${fmt(r407.distance_km)} km<br>` +
            `Toll: $${fmt(toll.total, 2)} (${toll.time_period.replace('_','-')})`
        );

        // Store for survey use
        currentData = d;
        updateSurveyConditions();

        // Keep projection charts in sync with live hero-card data
        injectLiveIntoCharts(r401, r407, vot);

    } catch (e) {
        console.error('Failed to fetch current data:', e);
        document.getElementById('statusDot').className = 'status-dot error';
        document.getElementById('statusText').textContent = 'Connection error';
    }
}

/* ── "Now" annotation for charts ── */
function nowAnnotation(labels) {
    const now = new Date();
    const nowMinutes = now.getHours() * 60 + now.getMinutes();
    // Find the nearest label index
    let bestIdx = 0, bestDiff = Infinity;
    labels.forEach((lbl, i) => {
        const [h, m] = lbl.split(':').map(Number);
        const diff = Math.abs(h * 60 + m - nowMinutes);
        if (diff < bestDiff) { bestDiff = diff; bestIdx = i; }
    });
    return {
        type: 'line',
        xMin: bestIdx,
        xMax: bestIdx,
        borderColor: 'rgba(37,99,235,0.55)',
        borderWidth: 2,
        borderDash: [4, 3],
        label: {
            display: true,
            content: 'Now',
            position: 'start',
            color: '#1a202c',
            font: { size: 10, weight: 'bold' },
            backgroundColor: 'rgba(255,255,255,0.9)',
            padding: 3,
        },
    };
}

/* ── 24h Projection ── */
async function updateProjection() {
    try {
        const d = await fetchJSON(`/api/projection?direction=${chartDirection}`);
        if (!d || !d.data) return;
        const data = d.data;
        const labels = data.map(p => p.time_label);
        const nowLine = nowAnnotation(labels);

        // Forecast box: everything after "now"
        const nowIdx = (() => {
            const now = new Date();
            const nowMinutes = now.getHours() * 60 + now.getMinutes();
            let bestIdx = 0, bestDiff = Infinity;
            labels.forEach((lbl, i) => {
                const [h, m] = lbl.split(':').map(Number);
                const diff = Math.abs(h * 60 + m - nowMinutes);
                if (diff < bestDiff) { bestDiff = diff; bestIdx = i; }
            });
            return bestIdx;
        })();

        const forecastBox = {
            type: 'box',
            xMin: nowIdx + 0.5,
            xMax: labels.length - 0.5,
            backgroundColor: 'rgba(148,163,184,0.10)',
            borderWidth: 0,
            label: { display: true, content: 'Forecast →', position: { x: 'start', y: 'start' }, color: '#94a3b8', font: { size: 10 } }
        };

        // Label: how many slots have real Google Maps data vs still waiting
        const realCount = d.real_count || 0;
        const total = d.total_slots || data.length;
        const dayLabel = `${d.day_name} (${d.date})`;
        const dataLabel = realCount > 0
            ? `${dayLabel} · ${realCount} real readings (every 6 min per direction)`
            : `${dayLabel} · Live data incoming — updates every 6 min per direction`;
        const projDayEl = document.getElementById('projDay');
        if (projDayEl) projDayEl.textContent = dataLabel;

        // ── VOT chart ──────────────────────────────────────────────────────
        const ctx1 = document.getElementById('projChart').getContext('2d');
        if (projChart) projChart.destroy();
        projChart = new Chart(ctx1, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Market VOT ($/hr) — capped at $800',
                        // Cap extreme outliers (near-zero time-saved → huge VOT)
                        data: data.map(p => p.market_vot != null ? Math.min(p.market_vot, 800) : null),
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239,68,68,0.06)',
                        fill: false,
                        tension: 0.3,
                        pointRadius: 3,
                        pointHoverRadius: 5,
                        borderWidth: 2,
                        spanGaps: false,
                    },
                ],
            },
            options: {
                ...chartOpts('$/hr', 0, 600),
                plugins: {
                    ...chartOpts('$/hr', 0, 600).plugins,
                    annotation: { annotations: { nowLine, forecastBox } },
                },
            },
        });

        // ── Time Saved vs Toll Cost chart ──────────────────────────────────
        const ctx2 = document.getElementById('ttChart').getContext('2d');
        if (ttChart) ttChart.destroy();
        ttChart = new Chart(ctx2, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Time Saved on 407 (min)',
                        data: data.map(p => p.time_saved),
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59,130,246,0.08)',
                        fill: 'origin',
                        tension: 0.3,
                        pointRadius: 2,
                        pointHoverRadius: 5,
                        borderWidth: 2,
                        spanGaps: false,
                        yAxisID: 'y',
                    },
                    {
                        label: 'Toll Cost ($)',
                        data: data.map(p => p.toll_cost),
                        borderColor: '#22c55e',
                        backgroundColor: 'rgba(34,197,94,0.0)',
                        fill: false,
                        tension: 0.3,
                        pointRadius: 2,
                        pointHoverRadius: 5,
                        borderWidth: 2,
                        spanGaps: false,
                        yAxisID: 'y2',
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { labels: { color: '#5c6b7e', font: { size: 11 } } },
                    tooltip: {
                        backgroundColor: '#1e293b', borderColor: '#334155', borderWidth: 1,
                        titleColor: '#f1f5f9', bodyColor: '#cbd5e1',
                    },
                    annotation: { annotations: { nowLine: nowAnnotation(labels), forecastBox } },
                },
                scales: {
                    x: {
                        ticks: { color: '#64748b', maxTicksLimit: 24, font: { size: 10 } },
                        grid: { color: 'rgba(221,228,237,0.8)' },
                    },
                    y: {
                        position: 'left',
                        title: { display: true, text: 'min saved', color: '#64748b' },
                        ticks: { color: '#64748b' },
                        grid: { color: 'rgba(221,228,237,0.8)' },
                    },
                    y2: {
                        position: 'right',
                        title: { display: true, text: 'toll $', color: '#64748b' },
                        ticks: { color: '#64748b' },
                        grid: { display: false },
                        suggestedMin: 0,
                    },
                },
            },
        });

    } catch (e) {
        console.error('Failed to fetch projection:', e);
    }
}

function chartOpts(yLabel, sugMin, sugMax) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: {
                labels: { color: '#5c6b7e', font: { size: 11 } },
            },
            tooltip: {
                backgroundColor: '#1e293b',
                borderColor: '#334155',
                borderWidth: 1,
                titleColor: '#f1f5f9',
                bodyColor: '#cbd5e1',
                callbacks: {
                    label: function(ctx) {
                        const val = ctx.parsed.y;
                        if (val == null) return ctx.dataset.label + ': N/A';
                        if (yLabel === '$/hr') return `${ctx.dataset.label}: $${val.toFixed(0)}/hr`;
                        if (yLabel === '%') return `${ctx.dataset.label}: ${val.toFixed(1)}%`;
                        return `${ctx.dataset.label}: ${val.toFixed(0)} ${yLabel}`;
                    },
                },
            },
        },
        scales: {
            x: {
                ticks: { color: '#64748b', maxTicksLimit: 24, font: { size: 10 } },
                grid: { color: 'rgba(221,228,237,0.8)' },
            },
            y: {
                title: { display: true, text: yLabel, color: '#64748b' },
                ticks: { color: '#64748b' },
                grid: { color: 'rgba(221,228,237,0.8)' },
                suggestedMin: sugMin,
                suggestedMax: sugMax,
            },
        },
    };
}

/* ── Methodology toggle ── */
function initMethodology() {
    const toggle = document.getElementById('methodologyToggle');
    const content = document.getElementById('methodologyContent');
    toggle.addEventListener('click', () => {
        const isOpen = toggle.getAttribute('aria-expanded') === 'true';
        toggle.setAttribute('aria-expanded', !isOpen);
        content.classList.toggle('open');
    });
}

/* ── Mega chart (unified historical) ── */
async function updateMegaChart(range = '24h') {
    activeRange = range;
    try {
        const d = await fetchJSON(`/api/history/range?range=${range}&direction=${chartDirection}`);
        if (!d.data || d.data.length === 0) {
            // Show a collecting-data message in the canvas area
            const ctx = document.getElementById('megaChart').getContext('2d');
            ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
            ctx.font = '14px system-ui';
            ctx.fillStyle = '#94a3b8';
            ctx.textAlign = 'center';
            ctx.fillText('Collecting data — live readings appear here every 3 min', ctx.canvas.width / 2, ctx.canvas.height / 2);
            return;
        }

        const data = d.data;
        const labels = data.map(p => {
            const lbl = p.time_label || '';
            if (range === '24h') {
                // Trim ISO timestamp to HH:MM
                return lbl.length > 16 ? lbl.substring(11, 16) : lbl;
            }
            if (range === '7d') return lbl.substring(5, 13); // MM-DD HH
            if (range === '30d') return lbl.substring(5, 10); // MM-DD
            return lbl.substring(5, 10); // 365d: MM-DD
        });

        const ctx = document.getElementById('megaChart').getContext('2d');
        if (megaChart) megaChart.destroy();

        megaChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: '401 Travel Time (min)',
                        data: data.map(p => p.tt_401),
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59,130,246,0.06)',
                        fill: false, tension: 0.3, pointRadius: 0, borderWidth: 2,
                        yAxisID: 'y',
                    },
                    {
                        label: '407 Travel Time (min)',
                        data: data.map(p => p.tt_407),
                        borderColor: '#8b5cf6',
                        backgroundColor: 'rgba(139,92,246,0.06)',
                        fill: false, tension: 0.3, pointRadius: 0, borderWidth: 2,
                        yAxisID: 'y',
                    },
                    {
                        label: 'Market VOT ($/hr)',
                        data: data.map(p => p.market_vot != null ? Math.min(p.market_vot, 800) : null),
                        borderColor: '#ef4444',
                        fill: false, tension: 0.3, pointRadius: 0, borderWidth: 2,
                        borderDash: [4, 2],
                        yAxisID: 'y2',
                    },
                    {
                        label: 'Toll Cost ($)',
                        data: data.map(p => p.toll_cost),
                        borderColor: '#22c55e',
                        fill: false, tension: 0.3, pointRadius: 0, borderWidth: 1.5,
                        yAxisID: 'y2',
                    },
                    {
                        label: 'Time Saved (min)',
                        data: data.map(p => p.time_saved),
                        borderColor: '#f59e0b',
                        fill: false, tension: 0.3, pointRadius: 0, borderWidth: 1.5,
                        borderDash: [6, 3],
                        yAxisID: 'y3',
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false }, // using custom legend
                    tooltip: {
                        backgroundColor: '#1e293b', borderColor: '#334155', borderWidth: 1,
                        titleColor: '#f1f5f9', bodyColor: '#cbd5e1',
                    },
                },
                scales: {
                    x: {
                        ticks: { color: '#64748b', maxTicksLimit: 16, font: { size: 10 } },
                        grid: { color: 'rgba(221,228,237,0.8)' },
                    },
                    y: {
                        position: 'left',
                        title: { display: true, text: 'Travel Time (min)', color: '#64748b' },
                        ticks: { color: '#64748b' },
                        grid: { color: 'rgba(221,228,237,0.6)' },
                    },
                    y2: {
                        position: 'right',
                        title: { display: true, text: '$/hr or $', color: '#64748b' },
                        ticks: { color: '#64748b' },
                        grid: { display: false },
                    },
                    y3: {
                        position: 'right',
                        title: { display: false },
                        ticks: { display: false },
                        grid: { display: false },
                        min: 0, max: 120,
                    },
                },
            },
        });
    } catch (e) {
        console.error('Mega chart error:', e);
    }
}

/* ── Chart direction tabs ── */
function initChartDirectionTabs() {
    document.querySelectorAll('.chart-dir-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const dir = btn.dataset.dir;
            if (dir === chartDirection) return;
            chartDirection = dir;
            // Update active state on ALL chart tab groups
            document.querySelectorAll('.chart-dir-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.dir === dir);
            });
            updateProjection();
            updateMegaChart(activeRange);
        });
    });
}

function initMegaChart() {
    // Range selector buttons
    document.querySelectorAll('.range-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            updateMegaChart(btn.dataset.range);
        });
    });

    // Custom legend toggle
    document.querySelectorAll('.mega-legend-item').forEach(item => {
        item.addEventListener('click', () => {
            if (!megaChart) return;
            const idx = parseInt(item.dataset.ds);
            const meta = megaChart.getDatasetMeta(idx);
            meta.hidden = !meta.hidden;
            item.classList.toggle('hidden');
            megaChart.update();
        });
    });

    updateMegaChart('24h');
}

/* ── Survey ── */
function initSurvey() {
    // Location button
    document.getElementById('locateBtn').addEventListener('click', () => {
        if (!navigator.geolocation) {
            document.getElementById('locationStatus').textContent = 'Geolocation not supported';
            return;
        }
        document.getElementById('locationStatus').textContent = 'Detecting...';
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                surveyLocation.lat = pos.coords.latitude;
                surveyLocation.lng = pos.coords.longitude;
                const btn = document.getElementById('locateBtn');
                btn.classList.add('located');
                btn.innerHTML = `<span class="locate-icon">✅</span> Location detected`;
                // Reverse geocode for display
                document.getElementById('locationStatus').textContent =
                    `${pos.coords.latitude.toFixed(3)}, ${pos.coords.longitude.toFixed(3)}`;
            },
            (err) => {
                document.getElementById('locationStatus').textContent = 'Location denied — no problem, survey still works!';
            },
            { timeout: 10000, enableHighAccuracy: false }
        );
    });

    // Option buttons (single select per group)
    document.querySelectorAll('.survey-options').forEach(group => {
        group.querySelectorAll('.survey-opt').forEach(btn => {
            btn.addEventListener('click', () => {
                group.querySelectorAll('.survey-opt').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                checkSurveyComplete();
            });
        });
    });

    // Route card selection
    const card401 = document.getElementById('surveyCard401');
    const card407 = document.getElementById('surveyCard407');
    if (card401) card401.addEventListener('click', () => {
        surveyRouteChoice = '401';
        card401.classList.add('selected');
        if (card407) card407.classList.remove('selected');
    });
    if (card407) card407.addEventListener('click', () => {
        surveyRouteChoice = '407';
        card407.classList.add('selected');
        if (card401) card401.classList.remove('selected');
    });

    // Submit
    document.getElementById('submitSurvey').addEventListener('click', submitSurvey);
    document.getElementById('resetSurvey').addEventListener('click', resetSurvey);

    // Load initial stats
    loadSurveyStats();
}

function checkSurveyComplete() {
    const vehicle = document.querySelector('#vehicleType .selected');
    const trip = document.querySelector('#tripType .selected');
    const company = document.querySelector('#companyPays .selected');
    const self = document.querySelector('#selfPays .selected');
    document.getElementById('submitSurvey').disabled = !(vehicle && trip && company && self);
}

async function submitSurvey() {
    const vehicle = document.querySelector('#vehicleType .selected')?.dataset.value;
    const trip = document.querySelector('#tripType .selected')?.dataset.value;
    const freq = document.querySelector('#frequency .selected')?.dataset.value;
    const company = document.querySelector('#companyPays .selected')?.dataset.value;
    const self = document.querySelector('#selfPays .selected')?.dataset.value;

    const payload = {
        lat: surveyLocation.lat,
        lng: surveyLocation.lng,
        location_name: surveyLocation.name,
        direction: currentDirection,
        tt_401: currentData?.route_401?.tt_minutes,
        tt_407: currentData?.route_407?.tt_minutes,
        toll_cost: currentData?.toll?.total,
        time_saved: currentData?.vot?.time_saved_minutes,
        market_vot: currentData?.vot?.market_vot,
        time_period: currentData?.toll?.time_period,
        vehicle_type: vehicle,
        trip_type: trip,
        frequency: freq,
        choice_if_company_pays: company,
        choice_if_self_pays: self,
        route_choice: surveyRouteChoice,
        user_agent: navigator.userAgent,
    };

    try {
        await fetch('/api/survey', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        // Show thanks + insights
        document.getElementById('surveyStep1').style.display = 'none';
        document.getElementById('surveyStep2').style.display = 'block';
        await loadSurveyStats(true);
    } catch (e) {
        console.error('Survey submit error:', e);
    }
}

function resetSurvey() {
    document.getElementById('surveyStep1').style.display = 'block';
    document.getElementById('surveyStep2').style.display = 'none';
    document.querySelectorAll('.survey-opt').forEach(b => b.classList.remove('selected'));
    document.querySelectorAll('.survey-route-card').forEach(c => c.classList.remove('selected'));
    surveyRouteChoice = null;
    document.getElementById('submitSurvey').disabled = true;
}

async function loadSurveyStats(showInsights = false) {
    try {
        const stats = await fetchJSON('/api/survey/stats');
        const count = stats.total_responses || 0;
        document.getElementById('insightBadge').textContent =
            count > 0 ? `${count} responses` : 'Be the first!';
        // Also update the verdict CTA stat
        const cta = document.getElementById('surveyCountStat');
        if (cta) cta.textContent = count > 0 ? `${count} drivers` : 'Be first!';

        if (showInsights || stats.total_responses > 0) {
            document.getElementById('insCompanyYes').textContent = `${stats.company_pays_yes_pct}%`;
            document.getElementById('insSelfYes').textContent = `${stats.self_pays_yes_pct}%`;
            document.getElementById('insTotal').textContent = stats.total_responses;
            document.getElementById('insToday').textContent = stats.responses_24h || 0;
        }
    } catch (e) {
        // Survey stats not critical
    }
}

function updateSurveyConditions() {
    if (!currentData) return;
    const r401 = currentData.route_401;
    const r407 = currentData.route_407;
    const toll = currentData.toll;
    const vot = currentData.vot;

    document.getElementById('survTT401').textContent = fmt(r401.tt_minutes);
    document.getElementById('survDelay401').textContent = fmt(r401.delay_minutes);
    document.getElementById('survTT407').textContent = fmt(r407.tt_minutes);
    document.getElementById('survToll').textContent = fmt(toll.total, 2);
    document.getElementById('survTimeSaved').textContent = fmt(vot.time_saved_minutes);

    // Update inline toll references in questions
    document.querySelectorAll('.survTollInline').forEach(el => {
        el.textContent = fmt(toll.total, 2);
    });
}

/* ── Inject current live reading into projection charts ── */
function injectLiveIntoCharts(r401, r407, vot) {
    // Find the 3-min bucket that contains right now
    const now = new Date();
    const h = now.getHours();
    const m = Math.floor(now.getMinutes() / 3) * 3;
    const label = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`;

    if (ttChart) {
        const idx = ttChart.data.labels?.findIndex(l => l === label) ?? -1;
        if (idx >= 0) {
            ttChart.data.datasets[0].data[idx] = r401.tt_minutes - r407.tt_minutes;
            ttChart.update('none');
        }
    }
    if (projChart) {
        const idx = projChart.data.labels?.findIndex(l => l === label) ?? -1;
        if (idx >= 0) {
            projChart.data.datasets[0].data[idx] = vot.market_vot;
            projChart.update('none');
        }
    }
}

/* ── Ontario 511 — Incidents layer on map ── */
async function updateIncidents() {
    try {
        const d = await fetchJSON('/api/incidents');
        if (!d || !d.events) return;

        // Remove old incident markers
        if (incidentLayer) {
            routeMap.removeLayer(incidentLayer);
        }
        incidentLayer = L.layerGroup();

        const severityColors = {
            critical: '#dc2626',
            major: '#f59e0b',
            minor: '#6b7280',
            info: '#94a3b8',
        };

        for (const ev of d.events) {
            if (!ev.lat || !ev.lng) continue;

            const color = severityColors[ev.severity] || '#6b7280';
            const icon = L.divIcon({
                html: `<div style="font-size:16px;filter:drop-shadow(0 1px 2px rgba(0,0,0,.4))">${ev.icon}</div>`,
                iconSize: [20, 20],
                iconAnchor: [10, 10],
                className: '',
            });

            const popup = `
                <div style="max-width:260px">
                    <strong style="color:${color}">${ev.icon} ${ev.type === 'accidentsAndIncidents' ? 'ACCIDENT' : ev.type.toUpperCase()}</strong>
                    <span style="float:right;font-size:10px;color:${color};font-weight:700">${ev.severity.toUpperCase()}</span>
                    <br><strong>${ev.highway === '401' ? 'Hwy 401' : 'Hwy 407'} ${ev.direction}</strong>
                    <br><span style="font-size:12px">${ev.description}</span>
                    <br><em style="font-size:11px;color:#64748b">Lanes: ${ev.lanes_affected || 'Unknown'}${ev.is_full_closure ? ' — FULL CLOSURE' : ''}</em>
                    ${ev.reported ? '<br><span style="font-size:10px;color:#94a3b8">Reported: ' + new Date(ev.reported).toLocaleString() + '</span>' : ''}
                </div>`;

            L.marker([ev.lat, ev.lng], { icon }).bindPopup(popup).addTo(incidentLayer);

            // If event has a polyline, draw it
            if (ev.encoded_polyline) {
                try {
                    const coords = decodePolyline(ev.encoded_polyline);
                    L.polyline(coords, {
                        color: color,
                        weight: 4,
                        opacity: 0.6,
                        dashArray: '6 4',
                    }).bindPopup(popup).addTo(incidentLayer);
                } catch(e) { /* some polylines may be invalid */ }
            }
        }

        incidentLayer.addTo(routeMap);

        // Update incident alert banner
        const banner = document.getElementById('incidentBanner');
        if (banner) {
            const s = d.summary;
            if (s.accidents > 0 || s.critical > 0) {
                const parts = [];
                if (s.accidents > 0) parts.push(`${s.accidents} accident${s.accidents > 1 ? 's' : ''}`);
                if (s.closures > 0) parts.push(`${s.closures} closure${s.closures > 1 ? 's' : ''}`);
                if (s.roadwork > 0) parts.push(`${s.roadwork} roadwork`);
                banner.innerHTML = `<span class="incident-alert-icon">🚨</span> Active on corridor: <strong>${parts.join(', ')}</strong> (${s.total_401} on 401, ${s.total_407} on 407)`;
                banner.style.display = 'flex';
                banner.className = s.accidents > 0 ? 'incident-banner critical' : 'incident-banner warning';
            } else if (s.roadwork > 0) {
                banner.innerHTML = `<span class="incident-alert-icon">🚧</span> ${s.roadwork} roadwork zone${s.roadwork > 1 ? 's' : ''} on corridor (${s.total_401} on 401, ${s.total_407} on 407)`;
                banner.style.display = 'flex';
                banner.className = 'incident-banner info';
            } else {
                banner.innerHTML = `<span class="incident-alert-icon">✅</span> No incidents on 401/407 corridor`;
                banner.style.display = 'flex';
                banner.className = 'incident-banner clear';
            }
        }
    } catch(e) {
        console.error('Incidents fetch error:', e);
    }
}

/* ── Direction selector ── */
function initDirectionSelector() {
    document.querySelectorAll('.dir-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.dataset.dir === currentDirection) return; // no-op
            document.querySelectorAll('.dir-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentDirection = btn.dataset.dir;
            updateDirectionLabels();
            updateCurrent(); // re-fetch with new direction
        });
    });
}

function updateDirectionLabels() {
    const lbl = DIRECTION_LABELS[currentDirection];
    // Header subtitle O→D
    const headerOD = document.getElementById('headerOD');
    if (headerOD) headerOD.textContent = `${lbl.from} → ${lbl.to}`;
    // Map card O→D
    const mapOD = document.getElementById('mapOD');
    if (mapOD) mapOD.textContent = `${lbl.from} → ${lbl.to}`;
    // Footer
    const footerUpdate = document.getElementById('footerUpdate');
    // footerUpdate only holds the timestamp, leave it alone
}

/* ── Init ── */
document.addEventListener('DOMContentLoaded', () => {
    initDirectionSelector();
    initChartDirectionTabs();
    initMap();
    initMethodology();
    initMegaChart();
    initSurvey();
    updateCurrent();
    updateProjection();
    updateIncidents();  // Ontario 511 road events

    // Auto-refresh: current every 30s, projection every 10 min,
    // mega chart every 5 min, incidents every 2 min
    setInterval(updateCurrent, 30_000);
    setInterval(updateProjection, 10 * 60_000);
    setInterval(() => { updateMegaChart(activeRange); }, 5 * 60_000);
    setInterval(updateIncidents, 2 * 60_000);
});
