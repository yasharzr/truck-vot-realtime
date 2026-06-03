let projChart, ttChart, probChart;

async function fetchJSON(url) {
    const res = await fetch(url);
    return res.json();
}

function fmt(v, decimals = 0) {
    if (v == null || v === undefined) return '--';
    return Number(v).toFixed(decimals);
}

function setColor(el, market, thesis) {
    if (market == null) { el.className = 'big-number'; return; }
    const ratio = market / thesis;
    if (ratio <= 1.0) el.className = 'big-number good';
    else if (ratio <= 1.5) el.className = 'big-number moderate';
    else el.className = 'big-number bad';
}

async function updateCurrent() {
    try {
        const d = await fetchJSON('/api/current');
        const r401 = d.route_401;
        const r407 = d.route_407;
        const toll = d.toll;
        const vot = d.vot;

        document.getElementById('tt401').innerHTML = `${fmt(r401.tt_minutes)}<span class="unit">min</span>`;
        document.getElementById('delay401').textContent = fmt(r401.delay_minutes);
        document.getElementById('dist401').textContent = fmt(r401.distance_km);

        document.getElementById('tt407').innerHTML = `${fmt(r407.tt_minutes)}<span class="unit">min</span>`;
        document.getElementById('delay407').textContent = fmt(r407.delay_minutes);
        document.getElementById('dist407').textContent = fmt(r407.distance_km);
        document.getElementById('tollCostSmall').textContent = `$${fmt(toll.total, 2)}`;

        const badge = document.getElementById('timePeriodBadge');
        badge.textContent = toll.time_period.replace('_', '-');
        badge.className = `time-period-badge ${toll.time_period}`;

        const mvEl = document.getElementById('marketVot');
        mvEl.innerHTML = `${vot.market_vot != null ? fmt(vot.market_vot) : '&infin;'}<span class="unit">$/hr</span>`;
        setColor(mvEl, vot.market_vot, vot.thesis_vot_mean);

        document.getElementById('timeSaved').textContent = `${fmt(vot.time_saved_minutes)}m`;
        document.getElementById('tollCost').textContent = `$${fmt(vot.toll_cost, 2)}`;
        document.getElementById('choiceProb').textContent = `${fmt(vot.choice_probability_toll_simulated, 1)}%`;
        document.getElementById('fairToll').textContent = `$${fmt(vot.fair_toll_at_mean_vot, 2)}`;
        document.getElementById('verdictText').textContent = vot.verdict;

        // Verdict bar: shows market_vot position relative to thesis_vot
        const bar = document.getElementById('verdictBar');
        if (vot.market_vot != null) {
            const pct = Math.min(100, (vot.thesis_vot_mean / vot.market_vot) * 100);
            bar.style.width = pct + '%';
            const ratio = vot.market_vot / vot.thesis_vot_mean;
            if (ratio <= 1.0) bar.style.background = 'var(--green)';
            else if (ratio <= 1.5) bar.style.background = 'var(--amber)';
            else bar.style.background = 'var(--red)';
        }

        // Toll breakdown
        const segDiv = document.getElementById('tollSegments');
        segDiv.innerHTML = toll.segments.map(s =>
            `<div class="toll-segment">
                <span class="seg-name">${s.from} → ${s.to} (${s.distance_km}km)</span>
                <span class="seg-cost">$${s.cost.toFixed(2)}</span>
            </div>`
        ).join('') + `<div class="toll-segment">
            <span class="seg-name">Trip charge (${toll.has_transponder ? 'transponder' : 'video'})</span>
            <span class="seg-cost">$${toll.trip_charge.toFixed(2)}</span>
        </div>`;
        document.getElementById('tollTotal').textContent = `$${toll.total.toFixed(2)}`;

        // Status
        const dot = document.getElementById('statusDot');
        const statusText = document.getElementById('statusText');
        dot.className = d.source === 'google_maps' ? 'status-dot' : 'status-dot estimated';
        statusText.textContent = d.source === 'google_maps'
            ? 'Live traffic data'
            : 'Estimated (no API key)';

        const ts = new Date(d.timestamp);
        document.getElementById('lastUpdate').textContent =
            `Updated ${ts.toLocaleTimeString()}`;
    } catch (e) {
        console.error('Failed to fetch current data:', e);
    }
}

async function updateProjection() {
    try {
        const d = await fetchJSON('/api/projection');
        document.getElementById('projDay').textContent = `${d.day_name} (${d.date})`;
        const data = d.data;
        const labels = data.map(p => p.time_label);
        const thesisLine = data.map(() => d.thesis_vot_mean);

        // Projection chart: market VOT vs thesis VOT
        const ctx1 = document.getElementById('projChart').getContext('2d');
        if (projChart) projChart.destroy();
        projChart = new Chart(ctx1, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Market VOT (407 charges)',
                        data: data.map(p => p.market_vot),
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239,68,68,0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 2,
                    },
                    {
                        label: 'Thesis VOT ($81/hr)',
                        data: thesisLine,
                        borderColor: '#22c55e',
                        borderDash: [6, 4],
                        pointRadius: 0,
                        borderWidth: 2,
                    },
                ],
            },
            options: chartOpts('$/hr', 0, 250),
        });

        // Travel time chart
        const ctx2 = document.getElementById('ttChart').getContext('2d');
        if (ttChart) ttChart.destroy();
        ttChart = new Chart(ctx2, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: '401 Travel Time',
                        data: data.map(p => p.tt_401),
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59,130,246,0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 2,
                    },
                    {
                        label: '407 Travel Time',
                        data: data.map(p => p.tt_407),
                        borderColor: '#8b5cf6',
                        backgroundColor: 'rgba(139,92,246,0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        borderWidth: 2,
                    },
                ],
            },
            options: chartOpts('minutes', 30, 140),
        });

        // Choice probability chart
        const ctx3 = document.getElementById('probChart').getContext('2d');
        if (probChart) probChart.destroy();
        probChart = new Chart(ctx3, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: 'P(choose 407)',
                        data: data.map(p => p.choice_prob_toll),
                        backgroundColor: data.map(p => {
                            if (p.choice_prob_toll >= 40) return 'rgba(34,197,94,0.7)';
                            if (p.choice_prob_toll >= 25) return 'rgba(245,158,11,0.7)';
                            return 'rgba(239,68,68,0.5)';
                        }),
                        borderRadius: 2,
                    },
                ],
            },
            options: chartOpts('%', 0, 60),
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
                labels: { color: '#8b8d97', font: { size: 11 } },
            },
            tooltip: {
                backgroundColor: '#1a1d27',
                borderColor: '#2a2d3a',
                borderWidth: 1,
                titleColor: '#e4e4e7',
                bodyColor: '#e4e4e7',
            },
        },
        scales: {
            x: {
                ticks: {
                    color: '#8b8d97',
                    maxTicksLimit: 12,
                    font: { size: 10 },
                },
                grid: { color: 'rgba(42,45,58,0.5)' },
            },
            y: {
                title: { display: true, text: yLabel, color: '#8b8d97' },
                ticks: { color: '#8b8d97' },
                grid: { color: 'rgba(42,45,58,0.5)' },
                suggestedMin: sugMin,
                suggestedMax: sugMax,
            },
        },
    };
}

// Initial load
updateCurrent();
updateProjection();

// Auto-refresh current every 60 seconds
setInterval(updateCurrent, 60_000);

// Refresh projection every 15 minutes
setInterval(updateProjection, 15 * 60_000);
