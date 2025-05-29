document.addEventListener('DOMContentLoaded', () => {
    const chatContainer = document.getElementById('chat-chat-container');
    const qdrantContainer = document.getElementById('qdrant-container');
    const postgresContainer = document.getElementById('postgres-container');
    const messageForm = document.getElementById('message-form');
    const messageInput = document.getElementById('message-input');
    const healthButton = document.getElementById("health-button");
    const healthStatus = document.getElementById("health-status");

    const qdrantLoading = document.getElementById('qdrant-loading');
    const postgresLoading = document.getElementById('postgres-loading');

    const seenQdrantIds = new Set();
    const seenPostgresIds = new Set();

    // Create health overlay
    const healthOverlay = document.createElement('div');
    healthOverlay.id = 'health-overlay';
    healthOverlay.innerHTML = `
    <div class="health-content">
        <div class="health-header">
        <h3>System Health</h3>
        <button class="close-button">&times;</button>
        </div>
        <pre id="health-data">Loading health data...</pre>
    </div>`;
    document.body.appendChild(healthOverlay);

    // Health check functionality
    if (healthButton) {
        healthButton.addEventListener('click', async () => {
            console.log("Health button clicked");
            try {
                // Show overlay immediately
                healthOverlay.style.display = 'flex';
                document.getElementById('health-data').textContent = "Loading...";
                
                const response = await fetch('/health');
                const data = await response.json();
                
                if (data.success) {
                    document.getElementById('health-data').textContent = 
                        JSON.stringify(data.data, null, 2);
                } else {
                    document.getElementById('health-data').textContent = 
                        `Error: ${data.error}`;
                }
            } catch (err) {
                document.getElementById('health-data').textContent = 
                    `Network error: ${err.message}`;
            }
        });
    }

    document.getElementById('health-button').addEventListener('click', () => {
        healthOverlay.style.display = 'flex'; // Use flex display
    });

    document.querySelector('.close-button').addEventListener('click', () => {
        healthOverlay.style.display = 'none';
    });

    function createDiv(classes = [], text = '') {
        const div = document.createElement('div');
        div.classList.add(...classes);
        div.innerText = String(text);
        return div;
    }

    function addMessage(message, type = 'bot', status = '') {
        const messageDiv = createDiv([`${type}-message`], message);
        if (status) {
            messageDiv.classList.add(`message-${status}`);
            const statusIndicator = document.createElement('span');
            statusIndicator.className = 'status-indicator';
            statusIndicator.textContent = status === 'success' ? '✓' : '✗';
            messageDiv.prepend(statusIndicator);
        }
        chatContainer.appendChild(messageDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        return messageDiv;
    }

    function addQdrantLog(record) {
        if (seenQdrantIds.has(record.id)) return;

        const logDiv = createDiv(['log-message', 'qdrant-record']);
        let payloadDisplay = '';

        try {
            if (record.payload) {
                const telemetry = record.payload.telemetry || {};
                const robotId = record.payload.robot_id || 'Unknown';
                const timestamp = record.payload.timestamp || 'Unknown';

                payloadDisplay = JSON.stringify({
                    robot_id: robotId,
                    timestamp: timestamp,
                    position: telemetry.position || {},
                    navigation_status: telemetry.navigation_status || 'unknown',
                    is_stuck: telemetry.is_stuck || false
                }, null, 2);
            } else {
                payloadDisplay = 'No payload data';
            }
        } catch (e) {
            payloadDisplay = 'Error formatting payload: ' + e.message;
        }

        logDiv.innerHTML = `
            <div class="log-header">
                <strong>Qdrant Record</strong>
                <span class="log-time">${new Date().toLocaleString()}</span>
            </div>
            <div class="log-body">${payloadDisplay}</div>
            <div class="log-meta">
                <span class="log-id">ID: ${record.id}</span>
            </div>
        `;
        qdrantContainer.prepend(logDiv);
        seenQdrantIds.add(record.id);
    }

    function addPostgresLog(log, logType) {
        const id = log[0];
        if (seenPostgresIds.has(id)) return;

        const logDiv = createDiv(['log-message', `${logType}-record`]);
        const content = logType === 'relationship' ? log[2] : log[1];

        let timestamp = 'Unknown';
        try {
            if (log[3]) {
                timestamp = new Date(log[3]).toLocaleString();
            }
        } catch (e) {}

        logDiv.innerHTML = `
            <div class="log-header">
                <strong>${logType === 'relationship' ? 'Relationship' : 'Message Chain'}</strong>
                <span class="log-time">${timestamp}</span>
            </div>
            <div class="log-body">${JSON.stringify(content, null, 2)}</div>
            <div class="log-meta">
                <span class="log-id">ID: ${id}</span>
            </div>
        `;

        postgresContainer.prepend(logDiv);
        seenPostgresIds.add(id);
    }

    async function loadQdrantLogs() {
        qdrantLoading.textContent = "Loading Qdrant logs...";
        qdrantLoading.classList.add('loading-active');

        try {
            const response = await fetch('/qdrant_logs');
            const data = await response.json();

            if (data.status === 'error') {
                qdrantLoading.textContent = `Error: ${data.error}`;
                qdrantLoading.classList.add('error');
                return;
            }

            (data.records || []).forEach(addQdrantLog);
            qdrantLoading.textContent = `${data.records?.length || 0} Qdrant records loaded`;

        } catch (e) {
            qdrantLoading.textContent = `Error: ${e.message}`;
            qdrantLoading.classList.add('error');
        } finally {
            qdrantLoading.classList.remove('loading-active');
        }
    }

    async function loadPostgresLogs() {
        postgresLoading.textContent = "Loading PostgreSQL logs...";
        postgresLoading.classList.add('loading-active');

        try {
            const response = await fetch('/postgres_logs');
            const data = await response.json();

            if (data.status === 'error') {
                postgresLoading.textContent = `Error: ${data.error}`;
                postgresLoading.classList.add('error');
                return;
            }

            let relationshipCount = 0;
            let messageCount = 0;

            (data.relationships || []).forEach(log => {
                addPostgresLog(log, 'relationship');
                relationshipCount++;
            });

            (data.message_chains || []).forEach(log => {
                addPostgresLog(log, 'message');
                messageCount++;
            });

            postgresLoading.textContent =
                `${relationshipCount} relationships, ${messageCount} message chains loaded`;

        } catch (e) {
            postgresLoading.textContent = `Error: ${e.message}`;
            postgresLoading.classList.add('error');
        } finally {
            postgresLoading.classList.remove('loading-active');
        }
    }

    async function handleUserMessage(userInput) {
        addMessage(userInput, 'user');
        messageInput.value = '';

        const loadingIndicator = addMessage("Processing...", 'bot', 'loading');

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: userInput })
            });

            const data = await response.json();
            chatContainer.removeChild(loadingIndicator);

            if (data.success) {
                addMessage(data.data.response, 'bot', 'success');
                setTimeout(() => {
                    loadQdrantLogs();
                    loadPostgresLogs();
                }, 1000);
            } else {
                addMessage(`Error: ${data.error}`, 'bot', 'error');
            }
        } catch (err) {
            chatContainer.removeChild(loadingIndicator);
            addMessage(`Error: ${err.message}`, 'bot', 'error');
        }
    }

    messageForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const userInput = messageInput.value.trim();
        if (userInput) {
            handleUserMessage(userInput);
        }
    });

    function startPolling() {
        loadQdrantLogs();
        loadPostgresLogs();

        const interval = setInterval(() => {
            loadQdrantLogs();
            loadPostgresLogs();
        }, 5000);

        window.addEventListener('beforeunload', () => {
            clearInterval(interval);
        });
    }

    startPolling();
});
