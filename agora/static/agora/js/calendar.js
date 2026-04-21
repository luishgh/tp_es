(function () {
    const dataElement = document.getElementById('calendar-data');
    const calendarGrid = document.getElementById('calendar-grid');
    const monthLabel = document.getElementById('calendar-month-label');
    const monthControls = document.getElementById('calendar-month-controls');
    const prevButton = document.getElementById('calendar-prev-month');
    const nextButton = document.getElementById('calendar-next-month');
    const todayButton = document.getElementById('calendar-today-month');

    if (!dataElement || !calendarGrid || !monthControls || !monthLabel || !prevButton || !nextButton || !todayButton) {
        return;
    }

    function parseDate(value) {
        const parsed = new Date(value);

        if (!Number.isNaN(parsed.getTime())) {
            return parsed;
        }

        const fallback = String(value || '').match(/(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
        if (!fallback) {
            return null;
        }

        const [, year, month, day, hour, minute] = fallback;
        return new Date(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute));
    }

    function localTimeLabel(date) {
        return date.toLocaleTimeString('pt-BR', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
        });
    }

    const activities = (function () {
        const rawItems = (() => {
            try {
                return JSON.parse(dataElement.textContent || '[]');
            } catch (_error) {
                return [];
            }
        })();

        return rawItems
            .map(function (activity) {
                const dueDate = parseDate(activity.due_iso);
                if (!dueDate) {
                    return null;
                }

                return {
                    ...activity,
                    dueDate,
                    time_label: activity.time_label || localTimeLabel(dueDate),
                };
            })
            .filter(Boolean)
            .sort(function (a, b) {
                return a.dueDate.getTime() - b.dueDate.getTime();
            });
    })();

    const itemsByDate = (() => {
        const groups = {};

        for (let i = 0; i < activities.length; i += 1) {
            const activity = activities[i];
            const dateKey = `${activity.dueDate.getFullYear()}-${activity.dueDate.getMonth()}-${activity.dueDate.getDate()}`;

            if (!groups[dateKey]) {
                groups[dateKey] = [];
            }

            groups[dateKey].push(activity);
        }

        return groups;
    })();

    let visibleDate = new Date();
    visibleDate.setDate(1);

    function monthLabelText(year, month) {
        const monthName = new Date(year, month, 1).toLocaleString('pt-BR', {
            month: 'long',
        });

        const formattedMonth = monthName.charAt(0).toUpperCase() + monthName.slice(1);
        return `${formattedMonth} de ${year}`;
    }

    function isCurrentMonth() {
        const today = new Date();
        return visibleDate.getFullYear() === today.getFullYear()
            && visibleDate.getMonth() === today.getMonth();
    }

    function syncMonthControls() {
        const isCurrent = isCurrentMonth();
        todayButton.disabled = isCurrent;
        todayButton.classList.toggle('is-current-month', isCurrent);
        todayButton.setAttribute(
            'aria-pressed',
            isCurrent ? 'true' : 'false'
        );
        todayButton.setAttribute(
            'aria-label',
            isCurrent ? 'Você já está no mês atual' : 'Voltar para o mês atual'
        );
        monthControls.setAttribute(
            'aria-label',
            `Navegação do mês de ${monthLabelText(visibleDate.getFullYear(), visibleDate.getMonth())}`
        );

        if (isCurrent) {
            todayButton.setAttribute('title', 'Você está no mês atual');
        } else {
            todayButton.removeAttribute('title');
        }
    }

    function goToMonth(year, month) {
        visibleDate = new Date(year, month, 1);
        renderCalendar();
    }

    function clear(node) {
        while (node.firstChild) {
            node.removeChild(node.firstChild);
        }
    }

    function createActivityNode(activity) {
        const link = document.createElement('a');
        link.className = `calendar-badge ${activity.status_tone === 'sent' ? 'sent' : 'pending'}`;
        link.href = activity.detail_url;
        link.setAttribute('aria-label', `${activity.course_code} ${activity.title}`);

        const courseCode = document.createElement('strong');
        courseCode.textContent = activity.course_code;

        const title = document.createElement('span');
        title.textContent = activity.title;

        const meta = document.createElement('span');
        meta.className = 'calendar-item-meta';
        meta.textContent = activity.time_label;

        link.appendChild(courseCode);
        link.appendChild(title);
        link.appendChild(meta);

        return link;
    }

    function createDayCell(year, month, dayNumber, isToday) {
        const cell = document.createElement('article');
        cell.className = isToday ? 'day-card is-today' : 'day-card';

        const day = document.createElement('div');
        day.className = 'day-number';
        day.textContent = String(dayNumber);
        cell.appendChild(day);

        const dayItems = itemsByDate[`${year}-${month}-${dayNumber}`] || [];

        if (!dayItems.length) {
            const empty = document.createElement('p');
            empty.className = 'day-empty';
            empty.textContent = 'Sem tarefas';
            cell.appendChild(empty);
            return cell;
        }

        if (dayItems.length > 1) {
            cell.classList.add('has-multiple-items');

            const indicator = document.createElement('span');
            indicator.className = 'day-multi-indicator';
            indicator.textContent = `${dayItems.length}`;
            indicator.title = `${dayItems.length} tarefas no dia`;
            indicator.setAttribute('aria-label', `${dayItems.length} tarefas no dia ${dayNumber}`);
            cell.appendChild(indicator);
        }

        const dayItemsWrapper = document.createElement('div');
        dayItemsWrapper.className = 'day-items';

        dayItems
            .slice(0, 2)
            .forEach(function (activity) {
                dayItemsWrapper.appendChild(createActivityNode(activity));
            });

        cell.appendChild(dayItemsWrapper);

        const extraCount = dayItems.length - 2;
        if (extraCount > 0) {
            const extra = document.createElement('span');
            extra.className = 'extra-label';
            extra.textContent = `+${extraCount} tarefa${extraCount > 1 ? 's' : ''}`;
            cell.appendChild(extra);
        }

        return cell;
    }

    function createEmptyCell() {
        const emptyCell = document.createElement('article');
        emptyCell.className = 'day-card is-empty';
        return emptyCell;
    }

    function renderCalendar() {
        const year = visibleDate.getFullYear();
        const month = visibleDate.getMonth();
        const firstDay = new Date(year, month, 1);
        const firstWeekday = (firstDay.getDay() + 6) % 7;
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const today = new Date();

        monthLabel.textContent = monthLabelText(year, month);
        syncMonthControls();
        clear(calendarGrid);

        for (let day = 1; day <= 42; day += 1) {
            const dayOfMonth = day - firstWeekday;

            if (dayOfMonth < 1 || dayOfMonth > daysInMonth) {
                calendarGrid.appendChild(createEmptyCell());
                continue;
            }

            const isToday = today.getFullYear() === year
                && today.getMonth() === month
                && today.getDate() === dayOfMonth;

            calendarGrid.appendChild(createDayCell(year, month, dayOfMonth, isToday));
        }
    }

    prevButton.addEventListener('click', function () {
        goToMonth(visibleDate.getFullYear(), visibleDate.getMonth() - 1);
    });

    nextButton.addEventListener('click', function () {
        goToMonth(visibleDate.getFullYear(), visibleDate.getMonth() + 1);
    });

    todayButton.addEventListener('click', function () {
        const now = new Date();
        goToMonth(now.getFullYear(), now.getMonth());
    });

    prevButton.addEventListener('keydown', function (event) {
        if (event.key === 'Home') {
            event.preventDefault();
            const now = new Date();
            goToMonth(now.getFullYear(), now.getMonth());
            return;
        }

        if (event.key === 'ArrowLeft') {
            event.preventDefault();
            goToMonth(visibleDate.getFullYear(), visibleDate.getMonth() - 1);
            return;
        }

        if (event.key === 'ArrowRight') {
            event.preventDefault();
            nextButton.focus();
        }
    });

    nextButton.addEventListener('keydown', function (event) {
        if (event.key === 'Home') {
            event.preventDefault();
            const now = new Date();
            goToMonth(now.getFullYear(), now.getMonth());
            return;
        }

        if (event.key === 'ArrowRight') {
            event.preventDefault();
            goToMonth(visibleDate.getFullYear(), visibleDate.getMonth() + 1);
            return;
        }

        if (event.key === 'ArrowLeft') {
            event.preventDefault();
            prevButton.focus();
        }
    });

    todayButton.addEventListener('keydown', function (event) {
        if (event.key === 'Home') {
            event.preventDefault();
            const now = new Date();
            goToMonth(now.getFullYear(), now.getMonth());
            return;
        }

        if (event.key === 'ArrowLeft') {
            event.preventDefault();
            goToMonth(visibleDate.getFullYear(), visibleDate.getMonth() - 1);
            prevButton.focus();
        }

        if (event.key === 'ArrowRight') {
            event.preventDefault();
            goToMonth(visibleDate.getFullYear(), visibleDate.getMonth() + 1);
            nextButton.focus();
        }
    });

    renderCalendar();
})();
