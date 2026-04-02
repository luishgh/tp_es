(function () {
    function updateUrl(nextUrl) {
        const next = new URL(nextUrl, window.location.origin);
        window.history.replaceState({}, '', next.pathname + next.search);
    }

    async function replacePanel(link) {
        const panelId = link.dataset.asyncPanel;
        if (!panelId) {
            return;
        }

        const currentPanel = document.getElementById(panelId);
        if (!currentPanel) {
            return;
        }

        currentPanel.classList.add('is-loading');

        try {
            const response = await fetch(link.href, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                },
            });

            if (!response.ok) {
                throw new Error('Request failed');
            }

            const html = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const nextPanel = doc.getElementById(panelId);

            if (!nextPanel) {
                throw new Error('Panel not found');
            }

            currentPanel.replaceWith(nextPanel);
            updateUrl(link.href);
        } catch (error) {
            window.location.href = link.href;
        }
    }

    document.addEventListener('click', function (event) {
        const link = event.target.closest('a.page-button[data-async-panel]');
        if (!link) {
            return;
        }

        event.preventDefault();
        replacePanel(link);
    });
})();
