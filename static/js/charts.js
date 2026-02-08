// ============ ANALYTICS PAGE ============

var _analyticsUserId;

async function initAnalyticsPage(userId) {
    _analyticsUserId = userId;

    // Period selector
    var selector = document.getElementById('period-selector');
    if (selector) {
        selector.addEventListener('click', function(e) {
            var btn = e.target.closest('.period-btn');
            if (!btn) return;
            selector.querySelectorAll('.period-btn').forEach(function(b) {
                b.classList.remove('bg-white', 'shadow-sm', 'font-semibold');
                b.classList.add('font-medium');
            });
            btn.classList.add('bg-white', 'shadow-sm', 'font-semibold');
            btn.classList.remove('font-medium');
        });
    }

    await loadAnalytics();
}

async function loadAnalytics() {
    try {
        var responses = await Promise.all([
            fetch('/api/dashboard/overview?user_id=' + _analyticsUserId),
            fetch('/api/dashboard/weekly-performance?user_id=' + _analyticsUserId),
            fetch('/api/dashboard/source-flow?user_id=' + _analyticsUserId),
            fetch('/api/dashboard/recent-activity?user_id=' + _analyticsUserId)
        ]);

        var overview = await responses[0].json();
        var weekly = await responses[1].json();
        var sourceFlow = await responses[2].json();
        var activity = await responses[3].json();

        renderKPIs(overview);
        renderWeeklyChart(weekly);
        renderSourceFlow(sourceFlow);
        renderActivityLog(activity);
    } catch(e) {
        console.error('Analytics load error:', e);
    }
}

function renderKPIs(overview) {
    var completionEl = document.getElementById('completion-rate');
    if (completionEl) completionEl.textContent = (overview.completion_rate || 0).toFixed(1) + '%';

    var changeEl = document.getElementById('completion-change');
    if (changeEl) changeEl.textContent = '+5.1%';

    var totalEl = document.getElementById('total-tasks');
    if (totalEl) totalEl.textContent = overview.total_tasks || 0;

    var tasksChangeEl = document.getElementById('tasks-change');
    if (tasksChangeEl) {
        var pending = overview.pending || 0;
        tasksChangeEl.textContent = pending > 0 ? '-' + pending : '0';
    }
}

function renderWeeklyChart(weekly) {
    var container = document.getElementById('weekly-chart');
    if (!container) return;
    container.textContent = '';

    var days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    var maxVal = 1;

    // Normalize data
    var data = days.map(function(day, i) {
        var entry = weekly[i] || { completed: 0, created: 0 };
        if (entry.created > maxVal) maxVal = entry.created;
        if (entry.completed > maxVal) maxVal = entry.completed;
        return { day: day, completed: entry.completed || 0, created: entry.created || 0 };
    });

    var today = new Date().getDay();
    var todayIdx = today === 0 ? 6 : today - 1; // Convert Sun=0 to Mon=0 index

    data.forEach(function(entry, idx) {
        var col = document.createElement('div');
        col.className = 'flex flex-col items-center gap-3 w-full';

        var barWrap = document.createElement('div');
        barWrap.className = 'w-7 bg-gray-50 rounded-lg h-32 flex flex-col justify-end overflow-hidden relative';

        var createdBar = document.createElement('div');
        var createdHeight = maxVal > 0 ? (entry.created / maxVal * 100) : 0;
        createdBar.className = 'w-full bg-primary/20 absolute bottom-0';
        createdBar.style.height = Math.max(createdHeight, 5) + '%';

        var completedBar = document.createElement('div');
        var completedHeight = maxVal > 0 ? (entry.completed / maxVal * 100) : 0;
        completedBar.className = 'w-full bg-primary absolute bottom-0 rounded-t-[2px]';
        completedBar.style.height = Math.max(completedHeight, 3) + '%';

        barWrap.appendChild(createdBar);
        barWrap.appendChild(completedBar);

        var label = document.createElement('span');
        label.className = 'text-[11px] font-semibold ' + (idx === todayIdx ? 'text-slate-900' : 'text-slate-400');
        label.textContent = entry.day;

        col.appendChild(barWrap);
        col.appendChild(label);
        container.appendChild(col);
    });
}

function renderSourceFlow(sourceFlow) {
    var voicePct = document.getElementById('voice-pct');
    var voiceBar = document.getElementById('voice-bar');
    var textPct = document.getElementById('text-pct');
    var textBar = document.getElementById('text-bar');

    var vp = sourceFlow.voice_pct || 0;
    var tp = sourceFlow.text_pct || 0;

    if (voicePct) voicePct.textContent = vp.toFixed(0) + '%';
    if (voiceBar) voiceBar.style.width = vp + '%';
    if (textPct) textPct.textContent = tp.toFixed(0) + '%';
    if (textBar) textBar.style.width = tp + '%';
}

function renderActivityLog(activities) {
    var container = document.getElementById('activity-log');
    if (!container) return;
    container.textContent = '';

    if (!activities || !activities.length) {
        var empty = document.createElement('div');
        empty.className = 'p-4 text-center text-sm text-gray-400';
        empty.textContent = 'No recent activity';
        container.appendChild(empty);
        return;
    }

    activities.forEach(function(task) {
        var item = document.createElement('div');
        item.className = 'flex items-center p-4';

        var content = document.createElement('div');
        content.className = 'flex-1';
        var title = document.createElement('p');
        title.className = 'text-[15px] font-semibold text-slate-900';
        title.textContent = task.title;
        content.appendChild(title);

        var meta = document.createElement('div');
        meta.className = 'flex items-center gap-2 mt-0.5';

        var isVoice = task.created_via === 'whatsapp_voice';
        var typeBadge = document.createElement('span');
        typeBadge.className = 'text-[11px] font-bold uppercase px-1.5 py-0.5 rounded ' +
            (isVoice ? 'text-primary bg-primary/5' : 'text-accent-warning bg-accent-warning/5');
        typeBadge.textContent = isVoice ? 'Voice' : 'Text';
        meta.appendChild(typeBadge);

        var dateSpan = document.createElement('span');
        dateSpan.className = 'text-[12px] text-slate-400';
        dateSpan.textContent = task.created_at ? formatRelativeDate(task.created_at) : '';
        meta.appendChild(dateSpan);
        content.appendChild(meta);

        var statusIcon = document.createElement('span');
        statusIcon.className = 'material-symbols-outlined text-[20px] ' +
            (task.status === 'completed' ? 'text-accent-success' : 'text-slate-200');
        statusIcon.textContent = task.status === 'completed' ? 'check_circle' : 'radio_button_unchecked';

        item.appendChild(content);
        item.appendChild(statusIcon);
        container.appendChild(item);
    });
}

function formatRelativeDate(dateStr) {
    var date = new Date(dateStr);
    var now = new Date();
    var diffMs = now - date;
    var diffHours = Math.floor(diffMs / (1000 * 60 * 60));

    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return 'Today, ' + date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    if (diffHours < 48) return 'Yesterday';
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
