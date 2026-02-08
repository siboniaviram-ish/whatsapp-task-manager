// ============ CALENDAR PAGE ============

var _calendarUserId;
var _currentYear;
var _currentMonth;
var _selectedDate;
var _calendarData = {};

async function initCalendarPage(userId) {
    _calendarUserId = userId;
    var now = new Date();
    _currentYear = now.getFullYear();
    _currentMonth = now.getMonth();
    _selectedDate = now.toISOString().split('T')[0];

    // Load overdue count
    try {
        var res = await fetch('/api/user/stats?user_id=' + userId);
        var stats = await res.json();
        if (stats.overdue_count > 0) {
            var banner = document.getElementById('overdue-banner');
            if (banner) banner.style.display = '';
            var countText = document.getElementById('overdue-count-text');
            if (countText) countText.textContent = stats.overdue_count + ' Tasks Overdue';
        }
    } catch(e) {}

    await loadCalendarMonth();
}

async function loadCalendarMonth() {
    try {
        var res = await fetch('/api/dashboard/calendar?user_id=' + _calendarUserId + '&year=' + _currentYear + '&month=' + (_currentMonth + 1));
        _calendarData = await res.json();
    } catch(e) {
        _calendarData = {};
    }
    renderCalendar();
    loadAgenda(_selectedDate);
}

function changeMonth(delta) {
    _currentMonth += delta;
    if (_currentMonth < 0) { _currentMonth = 11; _currentYear--; }
    if (_currentMonth > 11) { _currentMonth = 0; _currentYear++; }
    loadCalendarMonth();
}

function goToToday() {
    var now = new Date();
    _currentYear = now.getFullYear();
    _currentMonth = now.getMonth();
    _selectedDate = now.toISOString().split('T')[0];
    loadCalendarMonth();
}

function renderCalendar() {
    var months = ['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December'];
    var titleEl = document.getElementById('calendar-month-title');
    if (titleEl) titleEl.textContent = months[_currentMonth] + ' ' + _currentYear;

    var grid = document.getElementById('calendar-grid');
    if (!grid) return;
    grid.textContent = '';

    var firstDay = new Date(_currentYear, _currentMonth, 1).getDay();
    var daysInMonth = new Date(_currentYear, _currentMonth + 1, 0).getDate();
    var daysInPrevMonth = new Date(_currentYear, _currentMonth, 0).getDate();
    var today = new Date().toISOString().split('T')[0];

    // Previous month days
    for (var i = firstDay - 1; i >= 0; i--) {
        var cell = document.createElement('div');
        cell.className = 'aspect-square flex items-center justify-center text-slate-300 text-sm';
        cell.textContent = daysInPrevMonth - i;
        grid.appendChild(cell);
    }

    // Current month days
    for (var d = 1; d <= daysInMonth; d++) {
        var dateStr = _currentYear + '-' + String(_currentMonth + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
        var isToday = dateStr === today;
        var isSelected = dateStr === _selectedDate;
        var tasksForDay = _calendarData[dateStr] || [];

        var cell = document.createElement('div');
        cell.className = 'aspect-square flex flex-col items-center justify-center relative cursor-pointer group';
        cell.dataset.date = dateStr;
        cell.onclick = function() {
            _selectedDate = this.dataset.date;
            renderCalendar();
            loadAgenda(this.dataset.date);
        };

        if (isToday || isSelected) {
            var bg = document.createElement('div');
            bg.className = 'absolute inset-1 rounded-lg ' + (isToday ? 'bg-primary' : 'bg-primary/10');
            cell.appendChild(bg);
        }

        var num = document.createElement('span');
        num.className = 'text-sm font-medium relative z-10 ' + (isToday ? 'font-bold text-white' : '');
        num.textContent = d;
        cell.appendChild(num);

        if (tasksForDay.length > 0) {
            var dots = document.createElement('div');
            dots.className = 'flex gap-0.5 mt-1 relative z-10';
            var colors = { work: 'bg-blue-400', personal: 'bg-green-400', urgent: 'bg-orange-400', general: 'bg-blue-400' };
            tasksForDay.slice(0, 3).forEach(function(t) {
                var dot = document.createElement('div');
                dot.className = 'calendar-dot ' + (isToday ? 'bg-white/60' : (colors[t.category] || 'bg-blue-400'));
                dots.appendChild(dot);
            });
            cell.appendChild(dots);
        }

        grid.appendChild(cell);
    }

    // Next month days
    var totalCells = firstDay + daysInMonth;
    var remaining = (7 - (totalCells % 7)) % 7;
    for (var i = 1; i <= remaining; i++) {
        var cell = document.createElement('div');
        cell.className = 'aspect-square flex items-center justify-center text-slate-300 text-sm';
        cell.textContent = i;
        grid.appendChild(cell);
    }

    // Update agenda date display
    var dateEl = document.getElementById('agenda-date');
    if (dateEl) dateEl.textContent = _selectedDate;
    var titleEl2 = document.getElementById('agenda-title');
    if (titleEl2) {
        titleEl2.textContent = _selectedDate === today ? 'Agenda for Today' : 'Agenda for ' + _selectedDate;
    }
}

async function loadAgenda(dateStr) {
    var container = document.getElementById('agenda-list');
    if (!container) return;
    container.textContent = '';

    try {
        var res = await fetch('/api/tasks?user_id=' + _calendarUserId + '&due_date=' + dateStr);
        var tasks = await res.json();

        if (!tasks.length) {
            var empty = document.createElement('div');
            empty.className = 'bg-slate-100 p-4 rounded-xl border border-dashed border-slate-300 flex flex-col items-center justify-center py-8';
            var icon = document.createElement('span');
            icon.className = 'material-symbols-outlined text-slate-300 text-[40px] mb-2';
            icon.textContent = 'event_available';
            var text = document.createElement('p');
            text.className = 'text-xs font-medium text-slate-400';
            text.textContent = 'No tasks for this day';
            empty.appendChild(icon);
            empty.appendChild(text);
            container.appendChild(empty);
            return;
        }

        tasks.forEach(function(task) {
            var isWhatsApp = task.created_via === 'whatsapp_text' || task.created_via === 'whatsapp_voice';
            var isUrgent = task.priority === 'urgent' || task.priority === 'high';

            var card = document.createElement('div');
            card.className = 'bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-start gap-4' +
                (isUrgent ? ' border-l-4 border-l-primary' : '');

            // Icon
            var iconBox = document.createElement('div');
            iconBox.className = 'w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ' +
                (isWhatsApp ? 'bg-green-100' : 'bg-primary/10');
            var iconSpan = document.createElement('span');
            iconSpan.className = 'material-symbols-outlined ' + (isWhatsApp ? 'text-green-600' : 'text-primary');
            iconSpan.textContent = isWhatsApp ? 'chat_bubble' : 'laptop_mac';
            iconBox.appendChild(iconSpan);

            // Content
            var content = document.createElement('div');
            content.className = 'flex-1';

            var topRow = document.createElement('div');
            topRow.className = 'flex items-center justify-between';
            var title = document.createElement('h4');
            title.className = 'text-sm font-bold';
            title.textContent = task.title;
            topRow.appendChild(title);

            var catBadge = document.createElement('span');
            catBadge.className = 'text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider ' +
                (isUrgent ? 'bg-primary/10 text-primary' : 'bg-blue-100 text-blue-600');
            catBadge.textContent = task.category || task.priority || 'work';
            topRow.appendChild(catBadge);
            content.appendChild(topRow);

            if (task.description) {
                var desc = document.createElement('p');
                desc.className = 'text-xs text-slate-500 mt-0.5 line-clamp-1';
                desc.textContent = task.description;
                content.appendChild(desc);
            }

            var meta = document.createElement('div');
            meta.className = 'flex items-center gap-3 mt-3';
            if (task.due_time) {
                var timeDiv = document.createElement('div');
                timeDiv.className = 'flex items-center gap-1 text-[11px] font-medium text-slate-400';
                var clockIcon = document.createElement('span');
                clockIcon.className = 'material-symbols-outlined text-[14px]';
                clockIcon.textContent = 'schedule';
                timeDiv.appendChild(clockIcon);
                timeDiv.appendChild(document.createTextNode(task.due_time));
                meta.appendChild(timeDiv);
            }
            if (isWhatsApp) {
                var syncDiv = document.createElement('div');
                syncDiv.className = 'flex items-center gap-1 text-[11px] font-medium text-green-500';
                var syncIcon = document.createElement('span');
                syncIcon.className = 'material-symbols-outlined text-[14px]';
                syncIcon.textContent = 'sync';
                syncDiv.appendChild(syncIcon);
                syncDiv.appendChild(document.createTextNode('Synced'));
                meta.appendChild(syncDiv);
            }
            content.appendChild(meta);

            card.appendChild(iconBox);
            card.appendChild(content);
            container.appendChild(card);
        });
    } catch(e) {
        console.error('Load agenda error:', e);
    }
}

async function submitCalendarTask(e) {
    e.preventDefault();
    var form = e.target;
    var data = {
        user_id: _calendarUserId,
        title: form.title.value,
        due_date: form.due_date ? form.due_date.value : _selectedDate,
        due_time: form.due_time ? form.due_time.value : null,
        category: form.category ? form.category.value : 'work',
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
    loadCalendarMonth();
}
