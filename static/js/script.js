document.addEventListener('DOMContentLoaded', () => {
    const chatContainer = document.getElementById('chat-chat-container');
    const qdrantContainer = document.getElementById('qdrant-container');
    const postgresContainer = document.getElementById('postgres-container');
    const messageForm = document.getElementById('message-form');
    const messageInput = document.getElementById('message-input');

    const qdrantLoading = document.getElementById('qdrant-loading');
    const postgresLoading = document.getElementById('postgres-loading');

    const seenQdrantIds = new Set();
    const seenPostgresIds = new Set();

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

        console.log("Adding Qdrant record:", record); // Debug log

        const logDiv = createDiv(['log-message', 'qdrant-record']);
        
        // Handle the payload formatting
        let payloadDisplay = '';
        try {
            if (record.payload) {
                // Extract relevant telemetry info for display
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
            console.error("Error formatting Qdrant payload:", e);
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

        console.log("Adding Postgres log:", log, logType); // Debug log

        const logDiv = createDiv(['log-message', `${logType}-record`]);
        const content = logType === 'relationship' ? log[2] : log[1];

        // Format timestamp
        let timestamp = 'Unknown';
        try {
            if (log[3]) {
                timestamp = new Date(log[3]).toLocaleString();
            }
        } catch (e) {
            console.error("Error parsing timestamp:", e);
        }

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
            console.log("Fetching Qdrant logs..."); // Debug log
            const response = await fetch('/qdrant_logs');
            const data = await response.json();
            
            console.log("Qdrant response:", data); // Debug log

            if (data.status === 'error') {
                qdrantLoading.textContent = `Error: ${data.error}`;
                qdrantLoading.classList.add('error');
                return;
            }

            if (data.records && Array.isArray(data.records)) {
                console.log(`Processing ${data.records.length} Qdrant records`);
                data.records.forEach(record => addQdrantLog(record));
                qdrantLoading.textContent = `${data.records.length} Qdrant records loaded`;
            } else {
                console.log("No records found in Qdrant response");
                qdrantLoading.textContent = "No Qdrant records found";
            }
        } catch (e) {
            console.error("Qdrant load error:", e);
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
            console.log("Fetching Postgres logs..."); // Debug log
            const response = await fetch('/postgres_logs');
            const data = await response.json();

            console.log("Postgres response:", data); // Debug log

            if (data.status === 'error') {
                postgresLoading.textContent = `Error: ${data.error}`;
                postgresLoading.classList.add('error');
                return;
            }

            let relationshipCount = 0;
            let messageCount = 0;

            if (data.relationships && Array.isArray(data.relationships)) {
                console.log(`Processing ${data.relationships.length} relationship records`);
                data.relationships.forEach(log => addPostgresLog(log, 'relationship'));
                relationshipCount = data.relationships.length;
            }
            
            if (data.message_chains && Array.isArray(data.message_chains)) {
                console.log(`Processing ${data.message_chains.length} message chain records`);
                data.message_chains.forEach(log => addPostgresLog(log, 'message'));
                messageCount = data.message_chains.length;
            }

            postgresLoading.textContent =
                `${relationshipCount} relationships, ${messageCount} message chains loaded`;
                
        } catch (e) {
            console.error("PostgreSQL load error:", e);
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
            const response = await fetch('/llm_command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: userInput })
            });

            const data = await response.json();
            chatContainer.removeChild(loadingIndicator);

            const style = data.success ? 'success' : 'error';
            addMessage(data.response, 'bot', style);

            // Refresh logs after successful command
            setTimeout(() => {
                loadQdrantLogs();
                loadPostgresLogs();
            }, 1000);
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
        console.log("Starting log polling..."); // Debug log
        
        // Initial load
        loadQdrantLogs();
        loadPostgresLogs();

        // Set up polling interval
        const interval = setInterval(() => {
            console.log("Polling for new logs..."); // Debug log
            loadQdrantLogs();
            loadPostgresLogs();
        }, 5000); // Increased to 5 seconds to reduce server load

        // Clean up interval on page unload
        window.addEventListener('beforeunload', () => {
            console.log("Cleaning up polling interval");
            clearInterval(interval);
        });
    }

    startPolling();
});