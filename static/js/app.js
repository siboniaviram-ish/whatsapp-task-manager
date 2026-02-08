// ============ SHARED UTILITIES ============

function escapeHtml(text) {
    if (!text) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

function openAddTaskModal() {
    document.getElementById('add-task-modal').classList.remove('hidden');
}

function closeAddTaskModal() {
    document.getElementById('add-task-modal').classList.add('hidden');
}

// ============ DASHBOARD PAGE ============

async function initDashboard(userId) {
    try {
        var responses = await Promise.all([
            fetch('/api/user/profile?user_id=' + userId),
            fetch('/api/dashboard/tasks-today?user_id=' + userId),
            fetch('/api/tasks?user_id=' + userId),
            fetch('/api/user/stats?user_id=' + userId)
        ]);
        var profile = await responses[0].json();
        var todayTasks = await responses[1].json();
        var allTasks = await responses[2].json();
        var stats = await responses[3].json();

        var nameEl = document.getElementById('user-name');
        if (nameEl) nameEl.textContent = profile.name || 'User';

        var badge = document.getElementById('notif-badge');
        if (badge) {
            var overdueCount = stats.overdue_count || 0;
            badge.textContent = overdueCount;
            if (overdueCount === 0) badge.classList.add('hidden');
        }

        renderTodayFocus(todayTasks);
        renderTaskList(allTasks);
    } catch (e) {
        console.error('Dashboard load error:', e);
    }
}

function renderTodayFocus(tasks) {
    var container = document.getElementById('today-focus-cards');
    if (!container) return;
    container.textContent = '';

    if (!tasks || !tasks.length) {
        var empty = document.createElement('div');
        empty.className = 'flex-shrink-0 w-72 bg-gray-50 rounded-2xl p-5 border border-dashed border-gray-200 flex flex-col items-center justify-center py-10';
        var icon = document.createElement('span');
        icon.className = 'material-symbols-outlined text-gray-300 text-4xl mb-2';
        icon.textContent = 'event_available';
        var text = document.createElement('p');
        text.className = 'text-sm text-gray-400';
        text.textContent = 'No tasks for today';
        empty.appendChild(icon);
        empty.appendChild(text);
        container.appendChild(empty);
        return;
    }

    tasks.slice(0, 5).forEach(function(task) {
        var card = document.createElement('div');
        card.className = 'flex-shrink-0 w-72 bg-white rounded-2xl p-5 shadow-card border border-gray-100';

        var priorityClass = (task.priority === 'high' || task.priority === 'urgent')
            ? 'bg-blue-50 text-primary' : 'bg-gray-50 text-gray-500';

        var sourceText = '';
        if (task.created_via === 'whatsapp_voice') {
            sourceText = 'VOICE';
        } else if (task.created_via === 'whatsapp_text') {
            sourceText = 'WA';
        } else {
            sourceText = 'WEB';
        }

        // Priority badge
        var topRow = document.createElement('div');
        topRow.className = 'flex justify-between items-start mb-4';
        var prBadge = document.createElement('span');
        prBadge.className = priorityClass + ' text-[10px] font-bold px-2.5 py-1 rounded-md uppercase tracking-wide';
        prBadge.textContent = task.priority || 'medium';
        var srcBadge = document.createElement('div');
        srcBadge.className = 'flex items-center gap-1 bg-green-50 px-2 py-1 rounded-md';
        var srcSpan = document.createElement('span');
        srcSpan.className = 'text-[10px] font-bold text-green-600 uppercase';
        srcSpan.textContent = sourceText;
        srcBadge.appendChild(srcSpan);
        topRow.appendChild(prBadge);
        topRow.appendChild(srcBadge);

        // Title
        var title = document.createElement('h3');
        title.className = 'font-bold text-lg mb-2 leading-tight text-gray-900';
        title.textContent = task.title;

        // Description
        var desc = document.createElement('p');
        desc.className = 'text-sm text-gray-500 mb-5 leading-relaxed line-clamp-2';
        desc.textContent = task.description || '';

        // Bottom row
        var bottom = document.createElement('div');
        bottom.className = 'flex items-center justify-between';
        var timeDiv = document.createElement('div');
        timeDiv.className = 'flex items-center gap-1.5 text-gray-400';
        var clockIcon = document.createElement('span');
        clockIcon.className = 'material-symbols-outlined text-[18px]';
        clockIcon.textContent = 'schedule';
        var timeText = document.createElement('span');
        timeText.className = 'text-xs font-medium';
        timeText.textContent = 'Due ' + (task.due_time || 'Today');
        timeDiv.appendChild(clockIcon);
        timeDiv.appendChild(timeText);

        var checkBtn = document.createElement('button');
        checkBtn.className = task.status === 'completed'
            ? 'bg-primary text-white size-9 rounded-xl flex items-center justify-center shadow-md shadow-primary/20'
            : 'bg-gray-50 text-gray-300 size-9 rounded-xl flex items-center justify-center border border-gray-100';
        checkBtn.onclick = function() { completeTaskAction(task.id); };
        var checkIcon = document.createElement('span');
        checkIcon.className = 'material-symbols-outlined text-xl';
        checkIcon.textContent = 'check';
        checkBtn.appendChild(checkIcon);

        bottom.appendChild(timeDiv);
        bottom.appendChild(checkBtn);

        card.appendChild(topRow);
        card.appendChild(title);
        card.appendChild(desc);
        card.appendChild(bottom);
        container.appendChild(card);
    });
}

function renderTaskList(tasks) {
    var container = document.getElementById('task-list');
    if (!container) return;
    container.textContent = '';

    if (!tasks || !tasks.length) {
        var empty = document.createElement('div');
        empty.className = 'text-center py-12';
        var icon = document.createElement('span');
        icon.className = 'material-symbols-outlined text-gray-200 text-5xl';
        icon.textContent = 'inbox';
        var text = document.createElement('p');
        text.className = 'text-sm text-gray-400 mt-2';
        text.textContent = 'No tasks yet';
        empty.appendChild(icon);
        empty.appendChild(text);
        container.appendChild(empty);
        return;
    }

    tasks.forEach(function(task) {
        var isCompleted = task.status === 'completed';
        var item = document.createElement('div');
        item.className = (isCompleted ? 'bg-gray-50/50' : 'bg-white') + ' p-4 rounded-2xl border border-gray-100 ' + (isCompleted ? '' : 'shadow-soft') + ' flex items-center gap-4';

        // Checkbox area
        var checkWrap = document.createElement('div');
        checkWrap.className = 'flex-shrink-0';
        var checkbox = document.createElement('div');
        checkbox.className = 'size-6 ' + (isCompleted ? 'bg-primary/20 border border-primary/10' : 'border-2 border-gray-200') + ' rounded-lg flex items-center justify-center cursor-pointer';
        checkbox.onclick = function() { completeTaskAction(task.id); };
        if (isCompleted) {
            var chk = document.createElement('span');
            chk.className = 'material-symbols-outlined text-primary text-base font-bold';
            chk.textContent = 'check';
            checkbox.appendChild(chk);
        }
        checkWrap.appendChild(checkbox);

        // Content
        var content = document.createElement('div');
        content.className = 'flex-1';
        var titleEl = document.createElement('h4');
        titleEl.className = 'font-bold text-sm ' + (isCompleted ? 'text-gray-300 line-through' : 'text-gray-900');
        titleEl.textContent = task.title;
        content.appendChild(titleEl);

        var meta = document.createElement('div');
        meta.className = 'flex items-center gap-2 mt-1';
        var source = (task.created_via === 'whatsapp_text' || task.created_via === 'whatsapp_voice')
            ? 'WhatsApp' : (task.category || 'General');
        var sourceSpan = document.createElement('span');
        sourceSpan.className = 'text-[10px] font-bold uppercase ' +
            ((task.created_via === 'whatsapp_text' || task.created_via === 'whatsapp_voice') ? 'text-primary' : 'text-gray-400');
        sourceSpan.textContent = source;
        meta.appendChild(sourceSpan);

        if (task.due_date) {
            var dot = document.createElement('span');
            dot.className = 'size-1 rounded-full bg-gray-200';
            meta.appendChild(dot);
            var dateSpan = document.createElement('span');
            dateSpan.className = 'text-[10px] text-gray-400 font-medium';
            dateSpan.textContent = task.due_date;
            meta.appendChild(dateSpan);
        }
        content.appendChild(meta);

        item.appendChild(checkWrap);
        item.appendChild(content);

        if (task.created_via === 'whatsapp_voice') {
            var micIcon = document.createElement('span');
            micIcon.className = 'material-symbols-outlined text-xl text-gray-300';
            micIcon.textContent = 'mic';
            item.appendChild(micIcon);
        }

        container.appendChild(item);
    });
}

var _currentUserId;
async function completeTaskAction(taskId) {
    await fetch('/api/tasks/' + taskId + '/complete', { method: 'POST' });
    if (typeof initDashboard === 'function' && _currentUserId) initDashboard(_currentUserId);
    if (typeof loadAllTasks === 'function') loadAllTasks();
}

// Override initDashboard to store userId
var _origInitDashboard = typeof initDashboard === 'function' ? initDashboard : null;
async function initDashboard(userId) {
    _currentUserId = userId;
    if (_origInitDashboard) return _origInitDashboard(userId);
}

// Re-define properly
initDashboard = async function(userId) {
    _currentUserId = userId;
    try {
        var responses = await Promise.all([
            fetch('/api/user/profile?user_id=' + userId),
            fetch('/api/dashboard/tasks-today?user_id=' + userId),
            fetch('/api/tasks?user_id=' + userId),
            fetch('/api/user/stats?user_id=' + userId)
        ]);
        var profile = await responses[0].json();
        var todayTasks = await responses[1].json();
        var allTasks = await responses[2].json();
        var stats = await responses[3].json();

        var nameEl = document.getElementById('user-name');
        if (nameEl) nameEl.textContent = profile.name || 'User';

        var badge = document.getElementById('notif-badge');
        if (badge) {
            var overdueCount = stats.overdue_count || 0;
            badge.textContent = overdueCount;
            if (overdueCount === 0) badge.classList.add('hidden');
        }

        var avatarEl = document.getElementById('user-avatar');
        if (avatarEl && profile.name) {
            avatarEl.textContent = profile.name.split(' ').map(function(n) { return n[0]; }).join('').toUpperCase().slice(0, 2);
        }

        renderTodayFocus(todayTasks);
        renderTaskList(allTasks);
    } catch (e) {
        console.error('Dashboard load error:', e);
    }
};


// ============ TASKS PAGE ============

var _tasksUserId;
var _allTasksCache = [];

async function initTasksPage(userId) {
    _tasksUserId = userId;
    _currentUserId = userId;

    var avatarEl = document.getElementById('user-avatar');
    if (avatarEl) {
        try {
            var res = await fetch('/api/user/profile?user_id=' + userId);
            var profile = await res.json();
            if (profile.name) {
                avatarEl.textContent = profile.name.split(' ').map(function(n) { return n[0]; }).join('').toUpperCase().slice(0, 2);
            }
        } catch(e) {}
    }

    // Search toggle
    var searchToggle = document.getElementById('search-toggle');
    if (searchToggle) {
        searchToggle.addEventListener('click', function() {
            document.getElementById('search-bar').classList.toggle('hidden');
            var input = document.getElementById('search-input');
            if (input) input.focus();
        });
    }
    var searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            var query = this.value.toLowerCase();
            var filtered = _allTasksCache.filter(function(t) {
                return t.title.toLowerCase().includes(query) || (t.description || '').toLowerCase().includes(query);
            });
            renderAllTasksList(filtered);
        });
    }

    // Filter buttons
    document.getElementById('task-filters').addEventListener('click', function(e) {
        var btn = e.target.closest('.filter-btn');
        if (!btn) return;
        document.querySelectorAll('.filter-btn').forEach(function(b) {
            b.classList.remove('bg-black', 'text-white');
            b.classList.add('bg-white', 'text-gray-500', 'border', 'border-gray-200');
        });
        btn.classList.remove('bg-white', 'text-gray-500', 'border', 'border-gray-200');
        btn.classList.add('bg-black', 'text-white');
        applyFilter(btn.dataset.filter);
    });

    await loadAllTasks();
}

async function loadAllTasks() {
    try {
        var res = await fetch('/api/tasks?user_id=' + _tasksUserId);
        _allTasksCache = await res.json();
        renderAllTasksList(_allTasksCache);
    } catch(e) {
        console.error('Load tasks error:', e);
    }
}

function applyFilter(filter) {
    var filtered;
    if (filter === 'all') {
        filtered = _allTasksCache;
    } else if (filter === 'pending') {
        filtered = _allTasksCache.filter(function(t) { return t.status === 'pending' || t.status === 'in_progress'; });
    } else if (filter === 'completed') {
        filtered = _allTasksCache.filter(function(t) { return t.status === 'completed'; });
    } else if (filter === 'overdue') {
        filtered = _allTasksCache.filter(function(t) { return t.status === 'overdue'; });
    } else if (filter === 'whatsapp') {
        filtered = _allTasksCache.filter(function(t) { return t.created_via === 'whatsapp_text' || t.created_via === 'whatsapp_voice'; });
    } else {
        filtered = _allTasksCache;
    }
    renderAllTasksList(filtered);
}

function renderAllTasksList(tasks) {
    var container = document.getElementById('all-tasks-list');
    if (!container) return;
    container.textContent = '';

    if (!tasks || !tasks.length) {
        var empty = document.createElement('div');
        empty.className = 'text-center py-16';
        var icon = document.createElement('span');
        icon.className = 'material-symbols-outlined text-gray-200 text-5xl';
        icon.textContent = 'inbox';
        var text = document.createElement('p');
        text.className = 'text-sm text-gray-400 mt-3';
        text.textContent = 'No tasks found';
        empty.appendChild(icon);
        empty.appendChild(text);
        container.appendChild(empty);
        return;
    }

    tasks.forEach(function(task) {
        var isCompleted = task.status === 'completed';
        var isVoice = task.created_via === 'whatsapp_voice';
        var isWhatsApp = task.created_via === 'whatsapp_text' || isVoice;

        var card = document.createElement('div');
        card.className = 'task-card flex flex-col gap-4' + (isCompleted ? ' opacity-30' : '');

        var topRow = document.createElement('div');
        topRow.className = 'flex justify-between items-start';

        var leftSide = document.createElement('div');
        leftSide.className = 'flex gap-4 flex-1';

        // Icon
        var iconBox = document.createElement('div');
        iconBox.className = 'flex items-center justify-center rounded-2xl shrink-0 size-12 shadow-sm ' +
            (isCompleted ? 'bg-gray-50 text-gray-400' : 'bg-gray-50 border border-gray-100 text-black');
        var iconSpan = document.createElement('span');
        iconSpan.className = 'material-symbols-outlined text-xl';
        iconSpan.textContent = isCompleted ? 'check_circle' : (isVoice ? 'mic' : 'notes');
        iconBox.appendChild(iconSpan);

        // Text
        var textDiv = document.createElement('div');
        textDiv.className = 'flex flex-col gap-1';
        var titleEl = document.createElement('h3');
        titleEl.className = 'text-base font-semibold leading-tight ' + (isCompleted ? 'text-gray-500 line-through' : 'text-black');
        titleEl.textContent = task.title;
        textDiv.appendChild(titleEl);

        if (task.description && !isCompleted) {
            var descEl = document.createElement('p');
            descEl.className = 'text-gray-400 text-sm font-light leading-relaxed' + (isVoice ? ' italic' : '');
            descEl.textContent = isVoice ? '"' + task.description + '"' : task.description;
            textDiv.appendChild(descEl);
        }

        leftSide.appendChild(iconBox);
        leftSide.appendChild(textDiv);

        // Checkbox
        var checkDiv = document.createElement('div');
        checkDiv.className = 'ml-4';
        var checkInput = document.createElement('input');
        checkInput.type = 'checkbox';
        checkInput.className = 'h-6 w-6 rounded-full border-gray-200 text-black focus:ring-0 focus:ring-offset-0 transition-all cursor-pointer';
        checkInput.checked = isCompleted;
        checkInput.onchange = function() { completeTaskAction(task.id); };
        if (isCompleted) {
            checkInput.className = 'h-6 w-6 rounded-full border-black bg-black text-white focus:ring-0 focus:ring-offset-0 cursor-pointer';
        }
        checkDiv.appendChild(checkInput);

        topRow.appendChild(leftSide);
        topRow.appendChild(checkDiv);
        card.appendChild(topRow);

        // Meta row
        if (!isCompleted) {
            var metaRow = document.createElement('div');
            metaRow.className = 'flex items-center gap-4 ml-16';

            var srcDiv = document.createElement('div');
            srcDiv.className = 'flex items-center gap-1 text-[10px] font-bold tracking-widest uppercase ' +
                (isWhatsApp ? 'text-whatsapp' : 'text-gray-300');
            var srcIcon = document.createElement('span');
            srcIcon.className = 'material-symbols-outlined text-xs';
            srcIcon.textContent = 'chat';
            srcDiv.appendChild(srcIcon);
            srcDiv.appendChild(document.createTextNode(isWhatsApp ? ' WhatsApp' : ' Dashboard'));
            metaRow.appendChild(srcDiv);

            if (task.due_date) {
                var dateDiv = document.createElement('div');
                dateDiv.className = 'flex items-center gap-1 text-[10px] font-medium text-gray-400 uppercase tracking-widest';
                var calIcon = document.createElement('span');
                calIcon.className = 'material-symbols-outlined text-xs';
                calIcon.textContent = 'schedule';
                dateDiv.appendChild(calIcon);
                var today = new Date().toISOString().split('T')[0];
                var label = task.due_date === today ? 'Due Today' : task.due_date;
                dateDiv.appendChild(document.createTextNode(' ' + label));
                metaRow.appendChild(dateDiv);
            }
            card.appendChild(metaRow);
        }

        container.appendChild(card);
    });
}

async function submitTaskFromList(e) {
    e.preventDefault();
    var form = e.target;
    var data = {
        user_id: _tasksUserId,
        title: form.title.value,
        description: form.description ? form.description.value : '',
        priority: form.priority ? form.priority.value : 'medium',
        due_date: form.due_date ? form.due_date.value : null,
        task_type: 'scheduled',
        created_via: 'web'
    };
    await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    closeAddTaskModal();
    form.reset();
    loadAllTasks();
}


// ============ DELEGATION PAGE ============

var _delegationUserId;

async function initDelegationPage(userId) {
    _delegationUserId = userId;
    _currentUserId = userId;
    await loadDelegationData();
}

async function loadDelegationData() {
    try {
        var responses = await Promise.all([
            fetch('/api/tasks?user_id=' + _delegationUserId + '&status=overdue'),
            fetch('/api/dashboard/delegated?user_id=' + _delegationUserId)
        ]);
        var overdueTasks = await responses[0].json();
        var delegatedTasks = await responses[1].json();

        renderOverdueTasks(overdueTasks);
        renderDelegatedTasks(delegatedTasks);
    } catch(e) {
        console.error('Delegation load error:', e);
    }
}

function renderOverdueTasks(tasks) {
    var container = document.getElementById('overdue-list');
    var badge = document.getElementById('overdue-badge');
    if (!container) return;
    container.textContent = '';

    if (badge) badge.textContent = tasks.length + ' TASKS';

    if (!tasks.length) {
        var section = document.getElementById('overdue-section');
        if (section) section.style.display = 'none';
        return;
    }

    tasks.forEach(function(task) {
        var card = document.createElement('div');
        card.className = 'bg-white rounded-xl p-4 shadow-sm border-l-4 border-red-500';

        var row = document.createElement('div');
        row.className = 'flex items-start gap-4';

        var checkDiv = document.createElement('div');
        checkDiv.className = 'mt-0.5';
        var checkInput = document.createElement('input');
        checkInput.type = 'checkbox';
        checkInput.className = 'h-6 w-6 rounded-full border-2 border-slate-300 text-primary focus:ring-primary cursor-pointer';
        checkInput.onchange = function() { completeTaskAction(task.id); };
        checkDiv.appendChild(checkInput);

        var content = document.createElement('div');
        content.className = 'flex-1';
        var title = document.createElement('h3');
        title.className = 'font-semibold text-slate-800 leading-snug';
        title.textContent = task.title;
        var sub = document.createElement('p');
        sub.className = 'text-sm text-red-500 font-medium mt-1';
        sub.textContent = (task.due_date || 'Overdue') + ' \u2022 ' + (task.priority || 'medium') + ' Priority';
        content.appendChild(title);
        content.appendChild(sub);

        // Buttons
        var btns = document.createElement('div');
        btns.className = 'flex items-center gap-2 mt-4';
        var delegateBtn = document.createElement('button');
        delegateBtn.className = 'flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-xs font-bold';
        var delIcon = document.createElement('span');
        delIcon.className = 'material-symbols-outlined text-base';
        delIcon.textContent = 'forward_to_inbox';
        delegateBtn.appendChild(delIcon);
        delegateBtn.appendChild(document.createTextNode('DELEGATE'));
        var editBtn = document.createElement('button');
        editBtn.className = 'flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 text-slate-600 text-xs font-bold';
        var editIcon = document.createElement('span');
        editIcon.className = 'material-symbols-outlined text-base';
        editIcon.textContent = 'edit';
        editBtn.appendChild(editIcon);
        editBtn.appendChild(document.createTextNode('EDIT'));
        btns.appendChild(delegateBtn);
        btns.appendChild(editBtn);
        content.appendChild(btns);

        row.appendChild(checkDiv);
        row.appendChild(content);
        card.appendChild(row);
        container.appendChild(card);
    });
}

function renderDelegatedTasks(tasks) {
    var container = document.getElementById('delegated-list');
    if (!container) return;
    container.textContent = '';

    if (!tasks || !tasks.length) {
        var empty = document.createElement('div');
        empty.className = 'text-center py-8';
        var text = document.createElement('p');
        text.className = 'text-sm text-gray-400';
        text.textContent = 'No delegated tasks yet';
        empty.appendChild(text);
        container.appendChild(empty);
        return;
    }

    tasks.forEach(function(task) {
        var card = document.createElement('div');
        card.className = 'bg-white/60 rounded-xl p-4 border border-slate-200';

        var top = document.createElement('div');
        top.className = 'flex items-start justify-between';

        var left = document.createElement('div');
        left.className = 'flex-1';

        var badge = document.createElement('div');
        badge.className = 'flex items-center gap-2 mb-1';
        var chatIcon = document.createElement('span');
        chatIcon.className = 'material-symbols-outlined text-green-500 text-base';
        chatIcon.textContent = 'chat';
        var badgeText = document.createElement('span');
        badgeText.className = 'text-[10px] font-bold tracking-widest uppercase text-slate-500';
        badgeText.textContent = 'Delegated via Bot';
        badge.appendChild(chatIcon);
        badge.appendChild(badgeText);
        left.appendChild(badge);

        var title = document.createElement('h3');
        title.className = 'font-medium text-slate-700';
        title.textContent = task.title;
        left.appendChild(title);

        var assignee = document.createElement('div');
        assignee.className = 'flex items-center gap-2 mt-2';
        var avatar = document.createElement('div');
        avatar.className = 'w-6 h-6 rounded-full bg-primary/20 flex items-center justify-center text-[10px] text-primary font-bold';
        avatar.textContent = (task.assignee_name || 'U')[0].toUpperCase();
        assignee.appendChild(avatar);
        var toText = document.createElement('p');
        toText.className = 'text-xs text-slate-500 font-medium';
        toText.textContent = 'To: ' + (task.assignee_name || task.assignee_phone || 'Unknown');
        assignee.appendChild(toText);
        left.appendChild(assignee);

        var right = document.createElement('div');
        right.className = 'flex flex-col items-end gap-1';
        var statusBadge = document.createElement('span');
        var st = task.status || 'pending';
        statusBadge.className = 'text-[10px] font-bold px-1.5 py-0.5 rounded ' +
            (st === 'completed' ? 'bg-green-100 text-green-700' :
             st === 'accepted' ? 'bg-blue-100 text-blue-700' : 'bg-yellow-100 text-yellow-700');
        statusBadge.textContent = st.toUpperCase();
        right.appendChild(statusBadge);

        top.appendChild(left);
        top.appendChild(right);
        card.appendChild(top);

        // Bottom actions
        var actions = document.createElement('div');
        actions.className = 'mt-4 pt-3 border-t border-slate-100 flex justify-between items-center';
        var nudgeBtn = document.createElement('button');
        nudgeBtn.className = 'text-xs font-bold text-primary flex items-center gap-1';
        var bellIcon = document.createElement('span');
        bellIcon.className = 'material-symbols-outlined text-sm';
        bellIcon.textContent = 'notifications';
        nudgeBtn.appendChild(bellIcon);
        nudgeBtn.appendChild(document.createTextNode('NUDGE ON WHATSAPP'));
        var recallBtn = document.createElement('button');
        recallBtn.className = 'text-xs font-bold text-slate-400';
        recallBtn.textContent = 'RECALL';
        actions.appendChild(nudgeBtn);
        actions.appendChild(recallBtn);
        card.appendChild(actions);

        container.appendChild(card);
    });
}

async function submitDelegatedTask(e) {
    e.preventDefault();
    var form = e.target;
    var data = {
        user_id: _delegationUserId,
        title: form.title.value,
        task_type: 'delegated',
        due_date: form.due_date ? form.due_date.value : null,
        created_via: 'web'
    };
    var res = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    var result = await res.json();
    if (result.id && form.assignee_phone && form.assignee_phone.value) {
        await fetch('/api/tasks/' + result.id + '/delegate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                assignee_phone: form.assignee_phone.value,
                assignee_name: form.assignee_name ? form.assignee_name.value : ''
            })
        });
    }
    closeAddTaskModal();
    form.reset();
    loadDelegationData();
}

// Dashboard task submit
async function submitTask(e) {
    e.preventDefault();
    var form = e.target;
    var data = {
        user_id: _currentUserId || 1,
        title: form.title.value,
        description: form.description ? form.description.value : '',
        priority: form.priority ? form.priority.value : 'medium',
        category: form.category ? form.category.value : 'general',
        due_date: form.due_date ? form.due_date.value : null,
        due_time: form.due_time ? form.due_time.value : null,
        task_type: form.task_type ? form.task_type.value : 'today',
        created_via: 'web'
    };
    await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    closeAddTaskModal();
    form.reset();
    if (_currentUserId) initDashboard(_currentUserId);
}
