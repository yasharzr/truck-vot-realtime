/* ── State ── */
let projChart, ttChart, megaChart;
let routeMap, layer401, layer407;
let incidentLayer = null;
let currentData = null;
let surveyLocation = { lat: null, lng: null, name: null };
let currentDirection = 'east'; // hero cards & live data fetch
let surveyRouteChoice = null;
let activeRange = '24h';

// Cached both-direction data for rich tooltips
let projEastData = null, projWestData = [];
let megaEastByIdx = [], megaWestByIdx = [];

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

/* ── Polyline decoder (Google encoded polyline -> [lat, lng] array) ── */
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

    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
        maxZoom: 18,
    }).addTo(routeMap);

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
        color: '#3b82f6', weight: 5, opacity: 0.9, dashArray: null,
    }).addTo(routeMap).bindPopup('<strong>Hwy 401 — FREE</strong><br>Through Toronto<br>No toll');

    layer407 = L.polyline(default407, {
        color: '#8b5cf6', weight: 5, opacity: 0.9, dashArray: '10 6',
    }).addTo(routeMap).bindPopup('<strong>Hwy 407 — TOLL</strong><br>Bypass Toronto<br>407 ETR (toll) + 407 East (free)');

    const stopIcon = (label, color) => L.divIcon({
        html: `<div style="background:#fff;border:2px solid ${color};border-radius:8px;padding:3px 8px;font-size:11px;font-weight:700;color:${color};white-space:nowrap;box-shadow:0 2px 6px rgba(0,0,0,.18)">${label}</div>`,
        iconAnchor: [45, 14], className: '',
    });

    L.marker([43.5665, -79.8228], { icon: stopIcon('⛽ PetroPoint West', '#2563eb') })
        .addTo(routeMap).bindPopup('<strong>PetroPoint West — Hornby</strong><br>7443 Trafalgar Rd, Hornby · Survey site (WEST)<br><em>West of the 401/407 decision point</em>');
    L.marker([43.8919, -78.6918], { icon: stopIcon('⛽ PetroPoint East', '#7c3aed') })
        .addTo(routeMap).bindPopup('<strong>PetroPoint East — Bowmanville</strong><br>2475 Energy Dr · Survey site (EAST)<br><em>East of 407 East merge point</em>');

    const splitIcon = L.divIcon({ html: '<div style="font-size:18px">🔀</div>', iconSize: [22, 22], iconAnchor: [11, 22], className: '' });
    const mergeIcon = L.divIcon({ html: '<div style="font-size:18px">🔁</div>', iconSize: [22, 22], iconAnchor: [11, 22], className: '' });
    L.marker([43.545, -79.720], { icon: splitIcon }).addTo(routeMap).bindPopup('<strong>DIVERGE — 401 @ Hwy 403</strong><br>Last exit to take 407 ETR (toll)');
    L.marker([43.895, -78.755], { icon: mergeIcon }).addTo(routeMap).bindPopup('<strong>CONVERGE — 401 @ Hwy 418</strong><br>407 East (free) re-joins 401 here');

    const westPt = L.marker([43.5665, -79.8228]);
    const eastPt = L.marker([43.8919, -78.6918]);
    const group = L.featureGroup([layer401, layer407, westPt, eastPt]);
    routeMap.fitBounds(group.getBounds().pad(0.10));
}

function updateMapPolylines(r401, r407) {
    if (r401.polyline) layer401.setLatLngs(decodePolyline(r401.polyline));
    if (r407.polyline) layer407.setLatLngs(decodePolyline(r407.polyline));
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

        const saved = r401.tt_minutes - r407.tt_minutes;
        const savedBadge = el('timeSavedBadge');
        if (saved > 0) {
            savedBadge.textContent = `${fmt(saved, 0)} min saved on 407`;
            savedBadge.style.display = 'block';
        } else {
            savedBadge.textContent = '401 is faster right now';
            savedBadge.style.background = 'rgba(59,130,246,0.15)';
            savedBadge.style.color = 'var(--accent)';
        }

        el('heroCard401').style.opacity = saved <= 0 ? '1' : '0.85';
        el('heroCard407').style.opacity = saved > 0 ? '1' : '0.85';

        const mvEl = el('marketVot');
        if (vot.market_vot != null && saved > 0) {
            mvEl.innerHTML = `${fmt(vot.market_vot)} <span class="verdict-unit">$/hr saved</span>`;
            const ratio = vot.market_vot / vot.thesis_vot_mean;
            mvEl.className = ratio <= 1.0 ? 'verdict-vot good' : ratio <= 2.0 ? 'verdict-vot moderate' : 'verdict-vot bad';
        } else {
            mvEl.innerHTML = '401 faster <span class="verdict-unit">right now</span>';
            mvEl.className = 'verdict-vot good';
        }

        el('timeSavedStat').textContent = saved > 0 ? `${fmt(saved, 0)} min` : '401 faster';
        el('tollCostStat').textContent = `$${fmt(toll.total, 0)}`;
        el('verdictText').textContent = vot.verdict;

        if (el('choiceProb')) el('choiceProb').textContent = `${fmt(vot.choice_probability_toll_simulated, 1)}%`;
        if (el('fairToll')) el('fairToll').textContent = `$${fmt(vot.fair_toll_at_mean_vot, 2)}`;

        const bar = el('verdictBar');
        if (vot.market_vot != null) {
            const ratio = vot.market_vot / vot.thesis_vot_mean;
            const pct = Math.min(100, (vot.thesis_vot_mean / vot.market_vot) * 100);
            bar.style.width = pct + '%';
            bar.style.background = ratio <= 1.0 ? 'var(--green)' : ratio <= 2.0 ? 'var(--amber)' : 'var(--red)';
        }

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

        const dot = document.getElementById('statusDot');
        const statusText = document.getElementById('statusText');
        dot.className = d.source === 'google_maps' ? 'status-dot' : 'status-dot estimated';
        statusText.textContent = d.source === 'google_maps' ? 'Live traffic data' : 'Estimated (no API key)';

        const ts = new Date(d.timestamp);
        const timeStr = ts.toLocaleTimeString();
        document.getElementById('lastUpdate').textContent = `Updated ${timeStr}`;
        document.getElementById('footerUpdate').textContent = `Updated ${timeStr}`;

        updateMapPolylines(r401, r407);

        const dirLbl = DIRECTION_LABELS[currentDirection];
        layer401.setPopupContent(
            `<strong>Hwy 401 — Through Toronto</strong><br>${dirLbl.sub}<br>` +
            `Travel time: ${fmt(r401.tt_minutes)} min<br>Delay: ${fmt(r401.delay_minutes)} min · ${fmt(r401.distance_km)} km<br><em>Free — no toll</em>`
        );
        layer407.setPopupContent(
            `<strong>Hwy 407 ETR — Bypass Toronto</strong><br>${dirLbl.sub}<br>` +
            `Travel time: ${fmt(r407.tt_minutes)} min<br>Delay: ${fmt(r407.delay_minutes)} min · ${fmt(r407.distance_km)} km<br>` +
            `Toll: $${fmt(toll.total, 2)} (${toll.time_period.replace('_','-')})`
        );

        currentData = d;
        updateSurveyConditions();
        injectLiveIntoCharts(r401, r407, d.vot);
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
    let bestIdx = 0, bestDiff = Infinity;
    labels.forEach((lbl, i) => {
        const [h, m] = lbl.split(':').map(Number);
        const diff = Math.abs(h * 60 + m - nowMinutes);
        if (diff < bestDiff) { bestDiff = diff; bestIdx = i; }
    });
    return {
        type: 'line', xMin: bestIdx, xMax: bestIdx,
        borderColor: 'rgba(37,99,235,0.55)', borderWidth: 2, borderDash: [4, 3],
        label: {
            display: true, content: 'Now', position: 'start',
            color: '#1a202c', font: { size: 10, weight: 'bold' },
            backgroundColor: 'rgba(255,255,255,0.9)', padding: 3,
        },
    };
}

/* ── Helper: safe data accessor for projection data ── */
function safeField(dataArr, labels, field) {
    if (!dataArr || dataArr.length < labels.length) return new Array(labels.length).fill(null);
    return dataArr.map(p => p[field] ?? null);
}
function safeFieldCapped(dataArr, labels, field, cap) {
    if (!dataArr || dataArr.length < labels.length) return new Array(labels.length).fill(null);
    return dataArr.map(p => p[field] != null ? Math.min(p[field], cap) : null);
}

/* ── 24h Projection — Both Directions Simultaneously ── */
async function updateProjection() {
    try {
        const [east, west] = await Promise.all([
            fetchJSON('/api/projection?direction=east'),
            fetchJSON('/api/projection?direction=west'),
        ]);
        if (!east?.data) return;

        projEastData = east.data;
        projWestData = west?.data || [];

        const labels = east.data.map(p => p.time_label);
        const nowLine = nowAnnotation(labels);

        // Find "now" index for forecast box
        const nowIdx = (() => {
            const now = new Date();
            const nowMin = now.getHours() * 60 + now.getMinutes();
            let best = 0, bestD = Infinity;
            labels.forEach((lbl, i) => {
                const [h, m] = lbl.split(':').map(Number);
                const diff = Math.abs(h * 60 + m - nowMin);
                if (diff < bestD) { bestD = diff; best = i; }
            });
            return best;
        })();

        const forecastBox = {
            type: 'box',
            xMin: nowIdx + 0.5, xMax: labels.length - 0.5,
            backgroundColor: 'rgba(148,163,184,0.08)', borderWidth: 0,
            label: { display: true, content: 'Forecast →', position: { x: 'start', y: 'start' }, color: '#94a3b8', font: { size: 10 } }
        };

        // Peak hour background boxes (AM 6-9, PM 4-7)
        const findIdx = (lbl) => { const i = labels.indexOf(lbl); return i >= 0 ? i : undefined; };
        const peakAnnotations = {};
        const amStart = findIdx('06:00'), amEnd = findIdx('09:00');
        const pmStart = findIdx('16:00'), pmEnd = findIdx('19:00');
        if (amStart != null && amEnd != null) {
            peakAnnotations.amPeak = {
                type: 'box', xMin: amStart, xMax: amEnd,
                backgroundColor: 'rgba(239,68,68,0.03)', borderWidth: 0,
                label: { display: true, content: 'AM Peak', position: { x: 'center', y: 'start' }, color: 'rgba(239,68,68,0.4)', font: { size: 9 } }
            };
        }
        if (pmStart != null && pmEnd != null) {
            peakAnnotations.pmPeak = {
                type: 'box', xMin: pmStart, xMax: pmEnd,
                backgroundColor: 'rgba(239,68,68,0.03)', borderWidth: 0,
                label: { display: true, content: 'PM Peak', position: { x: 'center', y: 'start' }, color: 'rgba(239,68,68,0.4)', font: { size: 9 } }
            };
        }

        // Data label
        const realE = east.real_count || 0;
        const realW = west?.real_count || 0;
        const dayLabel = `${east.day_name} (${east.date})`;
        const projDayEl = document.getElementById('projDay');
        if (projDayEl) projDayEl.textContent = `${dayLabel} · ${realE + realW} readings (${realE} east, ${realW} west)`;

        // ── Chart 1: Travel Times — both directions ──────────────────────
        const ctx1 = document.getElementById('projChart').getContext('2d');
        if (projChart) projChart.destroy();
        projChart = new Chart(ctx1, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: '401 Eastbound',
                        data: safeField(projEastData, labels, 'tt_401'),
                        borderColor: '#3b82f6',
                        borderWidth: 2.5,
                        tension: 0.35,
                        pointRadius: 0, pointHoverRadius: 4,
                        spanGaps: true,
                        fill: false,
                    },
                    {
                        label: '407 Eastbound',
                        data: safeField(projEastData, labels, 'tt_407'),
                        borderColor: '#93c5fd',
                        borderWidth: 2,
                        borderDash: [6, 3],
                        tension: 0.35,
                        pointRadius: 0, pointHoverRadius: 4,
                        spanGaps: true,
                        fill: false,
                    },
                    {
                        label: '401 Westbound',
                        data: safeField(projWestData, labels, 'tt_401'),
                        borderColor: '#8b5cf6',
                        borderWidth: 2.5,
                        tension: 0.35,
                        pointRadius: 0, pointHoverRadius: 4,
                        spanGaps: true,
                        fill: false,
                    },
                    {
                        label: '407 Westbound',
                        data: safeField(projWestData, labels, 'tt_407'),
                        borderColor: '#c4b5fd',
                        borderWidth: 2,
                        borderDash: [6, 3],
                        tension: 0.35,
                        pointRadius: 0, pointHoverRadius: 4,
                        spanGaps: true,
                        fill: false,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { labels: { color: '#5c6b7e', font: { size: 11 }, usePointStyle: true, pointStyleWidth: 16 } },
                    tooltip: {
                        backgroundColor: '#1e293b', borderColor: '#334155', borderWidth: 1,
                        titleColor: '#f1f5f9', bodyColor: '#cbd5e1',
                        callbacks: {
                            afterBody: function(ctx) {
                                const idx = ctx[0].dataIndex;
                                const eP = projEastData?.[idx];
                                const wP = projWestData?.[idx];
                                const lines = ['─────────────'];
                                if (eP && (eP.toll_cost != null || eP.time_saved != null)) {
                                    lines.push(`→ East: Toll $${fmt(eP.toll_cost,0)} · Saved ${fmt(eP.time_saved,0)} min · VOT $${fmt(eP.market_vot,0)}/hr`);
                                }
                                if (wP && (wP.toll_cost != null || wP.time_saved != null)) {
                                    lines.push(`← West: Toll $${fmt(wP.toll_cost,0)} · Saved ${fmt(wP.time_saved,0)} min · VOT $${fmt(wP.market_vot,0)}/hr`);
                                }
                                return lines.length > 1 ? lines : [];
                            }
                        },
                    },
                    annotation: { annotations: { nowLine, forecastBox, ...peakAnnotations } },
                },
                scales: {
                    x: { ticks: { color: '#64748b', maxTicksLimit: 24, font: { size: 10 } }, grid: { color: 'rgba(221,228,237,0.8)' } },
                    y: {
                        title: { display: true, text: 'Travel Time (min)', color: '#64748b' },
                        ticks: { color: '#64748b' },
                        grid: { color: 'rgba(221,228,237,0.6)' },
                    },
                },
            },
        });

        // ── Chart 2: Time Saved & VOT — dual axis ───────────────────────
        const thesisVot = east.thesis_vot_mean || 81;
        const ctx2 = document.getElementById('ttChart').getContext('2d');
        if (ttChart) ttChart.destroy();
        ttChart = new Chart(ctx2, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Time Saved East (min)',
                        data: safeField(projEastData, labels, 'time_saved'),
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59,130,246,0.06)',
                        fill: 'origin',
                        borderWidth: 2.5,
                        tension: 0.35,
                        pointRadius: 0, pointHoverRadius: 4,
                        spanGaps: true,
                        yAxisID: 'y',
                    },
                    {
                        label: 'Time Saved West (min)',
                        data: safeField(projWestData, labels, 'time_saved'),
                        borderColor: '#8b5cf6',
                        backgroundColor: 'rgba(139,92,246,0.04)',
                        fill: 'origin',
                        borderWidth: 2.5,
                        tension: 0.35,
                        pointRadius: 0, pointHoverRadius: 4,
                        spanGaps: true,
                        yAxisID: 'y',
                    },
                    {
                        label: 'VOT East ($/hr)',
                        data: safeFieldCapped(projEastData, labels, 'market_vot', 800),
                        borderColor: '#ef4444',
                        borderWidth: 2,
                        borderDash: [6, 3],
                        tension: 0.35,
                        pointRadius: 0, pointHoverRadius: 4,
                        spanGaps: true,
                        fill: false,
                        yAxisID: 'y2',
                    },
                    {
                        label: 'VOT West ($/hr)',
                        data: safeFieldCapped(projWestData, labels, 'market_vot', 800),
                        borderColor: '#f59e0b',
                        borderWidth: 2,
                        borderDash: [6, 3],
                        tension: 0.35,
                        pointRadius: 0, pointHoverRadius: 4,
                        spanGaps: true,
                        fill: false,
                        yAxisID: 'y2',
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { labels: { color: '#5c6b7e', font: { size: 11 }, usePointStyle: true, pointStyleWidth: 16 } },
                    tooltip: {
                        backgroundColor: '#1e293b', borderColor: '#334155', borderWidth: 1,
                        titleColor: '#f1f5f9', bodyColor: '#cbd5e1',
                        callbacks: {
                            afterBody: function(ctx) {
                                const idx = ctx[0].dataIndex;
                                const eP = projEastData?.[idx];
                                const wP = projWestData?.[idx];
                                const lines = [];
                                if (eP?.toll_cost != null) lines.push(`→ East toll: $${fmt(eP.toll_cost,0)}`);
                                if (wP?.toll_cost != null) lines.push(`← West toll: $${fmt(wP.toll_cost,0)}`);
                                return lines.length ? ['─────────────', ...lines] : [];
                            }
                        },
                    },
                    annotation: {
                        annotations: {
                            nowLine: nowAnnotation(labels),
                            forecastBox,
                            thesisVotRef: {
                                type: 'line',
                                yMin: thesisVot, yMax: thesisVot, yScaleID: 'y2',
                                borderColor: 'rgba(220,38,38,0.3)', borderWidth: 1.5, borderDash: [4, 4],
                                label: {
                                    display: true, content: `Thesis Mean VOT ($${thesisVot}/hr)`, position: 'end',
                                    color: '#dc2626', font: { size: 9 },
                                    backgroundColor: 'rgba(255,255,255,0.9)', padding: 3,
                                },
                            },
                            ...peakAnnotations,
                        },
                    },
                },
                scales: {
                    x: { ticks: { color: '#64748b', maxTicksLimit: 24, font: { size: 10 } }, grid: { color: 'rgba(221,228,237,0.8)' } },
                    y: {
                        position: 'left',
                        title: { display: true, text: 'Time Saved (min)', color: '#3b82f6' },
                        ticks: { color: '#64748b' },
                        grid: { color: 'rgba(221,228,237,0.6)' },
                    },
                    y2: {
                        position: 'right',
                        title: { display: true, text: 'VOT ($/hr)', color: '#ef4444' },
                        ticks: { color: '#ef4444' },
                        grid: { display: false },
                        suggestedMin: 0,
                        suggestedMax: 500,
                    },
                },
            },
        });

    } catch (e) {
        console.error('Failed to fetch projection:', e);
    }
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

/* ── Mega chart (unified historical — both directions) ── */
async function updateMegaChart(range = '24h') {
    activeRange = range;
    try {
        const [eastRes, westRes] = await Promise.all([
            fetchJSON(`/api/history/range?range=${range}&direction=east`),
            fetchJSON(`/api/history/range?range=${range}&direction=west`),
        ]);

        const eastData = eastRes?.data || [];
        const westData = westRes?.data || [];

        if (eastData.length === 0 && westData.length === 0) {
            const ctx = document.getElementById('megaChart').getContext('2d');
            ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
            ctx.font = '14px system-ui';
            ctx.fillStyle = '#94a3b8';
            ctx.textAlign = 'center';
            ctx.fillText('Collecting data — live readings appear here every 3 min', ctx.canvas.width / 2, ctx.canvas.height / 2);
            return;
        }

        // Format labels based on range
        const formatLabel = (lbl) => {
            if (!lbl) return '';
            if (range === '24h') {
                // Bucket ISO timestamps into 3-min intervals for alignment
                const hhmm = lbl.length > 16 ? lbl.substring(11, 16) : lbl;
                const parts = hhmm.split(':');
                if (parts.length === 2) {
                    const h = parseInt(parts[0], 10);
                    const m = Math.floor(parseInt(parts[1], 10) / 3) * 3;
                    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
                }
                return hhmm;
            }
            if (range === '7d') return lbl.substring(5, 13);
            if (range === '30d') return lbl.substring(5, 10);
            return lbl.substring(5, 10);
        };

        // Build merged label set and lookup maps
        const eastByLabel = {}, westByLabel = {};
        const allLabels = new Set();

        for (const p of eastData) {
            const l = formatLabel(p.time_label || '');
            allLabels.add(l);
            eastByLabel[l] = p; // last-write-wins if multiple in same bucket
        }
        for (const p of westData) {
            const l = formatLabel(p.time_label || '');
            allLabels.add(l);
            westByLabel[l] = p;
        }

        const labels = [...allLabels].sort();

        // Store for tooltip callbacks
        megaEastByIdx = labels.map(l => eastByLabel[l] || null);
        megaWestByIdx = labels.map(l => westByLabel[l] || null);

        const ctx = document.getElementById('megaChart').getContext('2d');
        if (megaChart) megaChart.destroy();

        megaChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: '401 East (min)',
                        data: labels.map(l => eastByLabel[l]?.tt_401 ?? null),
                        borderColor: '#3b82f6',
                        borderWidth: 2,
                        tension: 0.3, pointRadius: 0,
                        spanGaps: true, fill: false,
                        yAxisID: 'y',
                    },
                    {
                        label: '407 East (min)',
                        data: labels.map(l => eastByLabel[l]?.tt_407 ?? null),
                        borderColor: '#93c5fd',
                        borderWidth: 1.5,
                        borderDash: [6, 3],
                        tension: 0.3, pointRadius: 0,
                        spanGaps: true, fill: false,
                        yAxisID: 'y',
                    },
                    {
                        label: '401 West (min)',
                        data: labels.map(l => westByLabel[l]?.tt_401 ?? null),
                        borderColor: '#8b5cf6',
                        borderWidth: 2,
                        tension: 0.3, pointRadius: 0,
                        spanGaps: true, fill: false,
                        yAxisID: 'y',
                    },
                    {
                        label: '407 West (min)',
                        data: labels.map(l => westByLabel[l]?.tt_407 ?? null),
                        borderColor: '#c4b5fd',
                        borderWidth: 1.5,
                        borderDash: [6, 3],
                        tension: 0.3, pointRadius: 0,
                        spanGaps: true, fill: false,
                        yAxisID: 'y',
                    },
                    {
                        label: 'VOT East ($/hr)',
                        data: labels.map(l => {
                            const v = eastByLabel[l]?.market_vot;
                            return v != null ? Math.min(v, 800) : null;
                        }),
                        borderColor: '#ef4444',
                        borderWidth: 2,
                        borderDash: [4, 2],
                        tension: 0.3, pointRadius: 0,
                        spanGaps: true, fill: false,
                        yAxisID: 'y2',
                    },
                    {
                        label: 'VOT West ($/hr)',
                        data: labels.map(l => {
                            const v = westByLabel[l]?.market_vot;
                            return v != null ? Math.min(v, 800) : null;
                        }),
                        borderColor: '#f59e0b',
                        borderWidth: 2,
                        borderDash: [4, 2],
                        tension: 0.3, pointRadius: 0,
                        spanGaps: true, fill: false,
                        yAxisID: 'y2',
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#1e293b', borderColor: '#334155', borderWidth: 1,
                        titleColor: '#f1f5f9', bodyColor: '#cbd5e1',
                        callbacks: {
                            afterBody: function(ctx) {
                                const idx = ctx[0].dataIndex;
                                const eP = megaEastByIdx[idx];
                                const wP = megaWestByIdx[idx];
                                const lines = [];
                                if (eP) {
                                    const parts = [];
                                    if (eP.toll_cost != null) parts.push(`Toll $${Number(eP.toll_cost).toFixed(0)}`);
                                    if (eP.time_saved != null) parts.push(`Saved ${Number(eP.time_saved).toFixed(0)} min`);
                                    if (parts.length) lines.push(`→ East: ${parts.join(' · ')}`);
                                }
                                if (wP) {
                                    const parts = [];
                                    if (wP.toll_cost != null) parts.push(`Toll $${Number(wP.toll_cost).toFixed(0)}`);
                                    if (wP.time_saved != null) parts.push(`Saved ${Number(wP.time_saved).toFixed(0)} min`);
                                    if (parts.length) lines.push(`← West: ${parts.join(' · ')}`);
                                }
                                return lines.length ? ['─────────────', ...lines] : [];
                            }
                        },
                    },
                },
                scales: {
                    x: { ticks: { color: '#64748b', maxTicksLimit: 20, font: { size: 10 } }, grid: { color: 'rgba(221,228,237,0.8)' } },
                    y: {
                        position: 'left',
                        title: { display: true, text: 'Travel Time (min)', color: '#64748b' },
                        ticks: { color: '#64748b' },
                        grid: { color: 'rgba(221,228,237,0.6)' },
                    },
                    y2: {
                        position: 'right',
                        title: { display: true, text: 'VOT ($/hr)', color: '#ef4444' },
                        ticks: { color: '#ef4444' },
                        grid: { display: false },
                    },
                },
            },
        });
    } catch (e) {
        console.error('Mega chart error:', e);
    }
}

function initMegaChart() {
    document.querySelectorAll('.range-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            updateMegaChart(btn.dataset.range);
        });
    });

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
                btn.innerHTML = '<span class="locate-icon">✅</span> Location detected';
                document.getElementById('locationStatus').textContent =
                    `${pos.coords.latitude.toFixed(3)}, ${pos.coords.longitude.toFixed(3)}`;
            },
            () => {
                document.getElementById('locationStatus').textContent = 'Location denied — no problem, survey still works!';
            },
            { timeout: 10000, enableHighAccuracy: false }
        );
    });

    document.querySelectorAll('.survey-options').forEach(group => {
        group.querySelectorAll('.survey-opt').forEach(btn => {
            btn.addEventListener('click', () => {
                group.querySelectorAll('.survey-opt').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                checkSurveyComplete();
            });
        });
    });

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

    document.getElementById('submitSurvey').addEventListener('click', submitSurvey);
    document.getElementById('resetSurvey').addEventListener('click', resetSurvey);
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
        lat: surveyLocation.lat, lng: surveyLocation.lng,
        location_name: surveyLocation.name,
        direction: currentDirection,
        tt_401: currentData?.route_401?.tt_minutes,
        tt_407: currentData?.route_407?.tt_minutes,
        toll_cost: currentData?.toll?.total,
        time_saved: currentData?.vot?.time_saved_minutes,
        market_vot: currentData?.vot?.market_vot,
        time_period: currentData?.toll?.time_period,
        vehicle_type: vehicle, trip_type: trip, frequency: freq,
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
        const cta = document.getElementById('surveyCountStat');
        if (cta) cta.textContent = count > 0 ? `${count} drivers` : 'Be first!';

        if (showInsights || stats.total_responses > 0) {
            document.getElementById('insCompanyYes').textContent = `${stats.company_pays_yes_pct}%`;
            document.getElementById('insSelfYes').textContent = `${stats.self_pays_yes_pct}%`;
            document.getElementById('insTotal').textContent = stats.total_responses;
            document.getElementById('insToday').textContent = stats.responses_24h || 0;
        }
    } catch (e) { /* not critical */ }
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

    document.querySelectorAll('.survTollInline').forEach(el => {
        el.textContent = fmt(toll.total, 2);
    });
}

/* ── Inject current live reading into projection charts ── */
function injectLiveIntoCharts(r401, r407, vot) {
    const now = new Date();
    const h = now.getHours();
    const m = Math.floor(now.getMinutes() / 3) * 3;
    const label = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}`;

    // projChart datasets: 0=401E, 1=407E, 2=401W, 3=407W
    if (projChart) {
        const idx = projChart.data.labels?.findIndex(l => l === label) ?? -1;
        if (idx >= 0) {
            if (currentDirection === 'east') {
                projChart.data.datasets[0].data[idx] = r401.tt_minutes;
                projChart.data.datasets[1].data[idx] = r407.tt_minutes;
            } else {
                projChart.data.datasets[2].data[idx] = r401.tt_minutes;
                projChart.data.datasets[3].data[idx] = r407.tt_minutes;
            }
            projChart.update('none');
        }
    }
    // ttChart datasets: 0=TimeSavedE, 1=TimeSavedW, 2=VotE, 3=VotW
    if (ttChart) {
        const idx = ttChart.data.labels?.findIndex(l => l === label) ?? -1;
        if (idx >= 0) {
            const saved = r401.tt_minutes - r407.tt_minutes;
            if (currentDirection === 'east') {
                ttChart.data.datasets[0].data[idx] = saved;
                ttChart.data.datasets[2].data[idx] = vot.market_vot != null ? Math.min(vot.market_vot, 800) : null;
            } else {
                ttChart.data.datasets[1].data[idx] = saved;
                ttChart.data.datasets[3].data[idx] = vot.market_vot != null ? Math.min(vot.market_vot, 800) : null;
            }
            ttChart.update('none');
        }
    }
}

/* ── Ontario 511 — Incidents layer on map ── */
async function updateIncidents() {
    try {
        const d = await fetchJSON('/api/incidents');
        if (!d || !d.events) return;

        if (incidentLayer) routeMap.removeLayer(incidentLayer);
        incidentLayer = L.layerGroup();

        const severityColors = { critical: '#dc2626', major: '#f59e0b', minor: '#6b7280', info: '#94a3b8' };

        for (const ev of d.events) {
            if (!ev.lat || !ev.lng) continue;
            const color = severityColors[ev.severity] || '#6b7280';
            const icon = L.divIcon({
                html: `<div style="font-size:16px;filter:drop-shadow(0 1px 2px rgba(0,0,0,.4))">${ev.icon}</div>`,
                iconSize: [20, 20], iconAnchor: [10, 10], className: '',
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

            if (ev.encoded_polyline) {
                try {
                    const coords = decodePolyline(ev.encoded_polyline);
                    L.polyline(coords, { color, weight: 4, opacity: 0.6, dashArray: '6 4' }).bindPopup(popup).addTo(incidentLayer);
                } catch(e) { /* invalid polyline */ }
            }
        }

        incidentLayer.addTo(routeMap);

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
                banner.innerHTML = '<span class="incident-alert-icon">✅</span> No incidents on 401/407 corridor';
                banner.style.display = 'flex';
                banner.className = 'incident-banner clear';
            }
        }
    } catch(e) {
        console.error('Incidents fetch error:', e);
    }
}

/* ── Direction selector (hero cards only) ── */
function initDirectionSelector() {
    document.querySelectorAll('.dir-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.dataset.dir === currentDirection) return;
            document.querySelectorAll('.dir-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentDirection = btn.dataset.dir;
            updateDirectionLabels();
            updateCurrent();
        });
    });
}

function updateDirectionLabels() {
    const lbl = DIRECTION_LABELS[currentDirection];
    const headerOD = document.getElementById('headerOD');
    if (headerOD) headerOD.textContent = `${lbl.from} → ${lbl.to}`;
    const mapOD = document.getElementById('mapOD');
    if (mapOD) mapOD.textContent = `${lbl.from} → ${lbl.to}`;
}

/* ── Init ── */
document.addEventListener('DOMContentLoaded', () => {
    initDirectionSelector();
    initMap();
    initMethodology();
    initMegaChart();
    initSurvey();
    updateCurrent();
    updateProjection();
    updateIncidents();

    // Auto-refresh intervals
    setInterval(updateCurrent, 30_000);
    setInterval(updateProjection, 10 * 60_000);
    setInterval(() => { updateMegaChart(activeRange); }, 5 * 60_000);
    setInterval(updateIncidents, 2 * 60_000);
});
