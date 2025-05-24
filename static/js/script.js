document.addEventListener('DOMContentLoaded', () => {
    const chatContainer = document.getElementById('chat-chat-container');
    const qdrantContainer = document.getElementById('qdrant-container');
    const postgresContainer = document.getElementById('postgres-container');
    const messageForm = document.getElementById('message-form');
    const messageInput = document.getElementById('message-input');
    
    // Separate loading states
    const qdrantLoading = document.getElementById('qdrant-loading');
    const postgresLoading = document.getElementById('postgres-loading');
    
    // Track seen IDs for both feeds
    const seenQdrantIds = new Set();
    const seenPostgresIds = new Set();

    function createDiv(classes = [], text = '') {
        const div = document.createElement('div');
        div.classList.add(...classes);
        div.innerText = String(text);
        return div;
    }

    // Modified message display
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

    // Qdrant log handler
    function addQdrantLog(record) {
        if (seenQdrantIds.has(record.id)) return;

        const logDiv = createDiv(['log-message', 'qdrant-record']);
        logDiv.innerHTML = `
            <div class="log-header">
                <strong>Qdrant Record</strong>
                <span class="log-time">${new Date().toLocaleString()}</span>
            </div>
            <div class="log-body">${JSON.stringify(record.payload, null, 2)}</div>
            <div class="log-meta">
                <span class="log-id">ID: ${record.id}</span>
            </div>
        `;
        
        qdrantContainer.prepend(logDiv);
        seenQdrantIds.add(record.id);
    }

    // PostgreSQL log handler
    function addPostgresLog(log, logType) {
        const id = log[0];
        if (seenPostgresIds.has(id)) return;

        const logDiv = createDiv(['log-message', `${logType}-record`]);
        const content = logType === 'relationship' ? log[2] : log[1];
        
        logDiv.innerHTML = `
            <div class="log-header">
                <strong>${logType === 'relationship' ? 'Relationship' : 'Message Chain'}</strong>
                <span class="log-time">${new Date(log[3]).toLocaleString()}</span>
            </div>
            <div class="log-body">${JSON.stringify(content, null, 2)}</div>
            <div class="log-meta">
                <span class="log-id">ID: ${id}</span>
            </div>
        `;

        postgresContainer.prepend(logDiv);
        seenPostgresIds.add(id);
    }

    // Separate loaders for each feed
    async function loadQdrantLogs() {
        qdrantLoading.textContent = "Loading Qdrant logs...";
        qdrantLoading.classList.add('loading-active');
        
        try {
            const response = await fetch('/qdrant_logs');
            const data = await response.json();
            
            if (data.records) {
                data.records.forEach(record => addQdrantLog(record));
                qdrantLoading.textContent = `${data.records.length} Qdrant records loaded`;
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
            const response = await fetch('/postgres_logs');
            const data = await response.json();
            
            if (data.relationships) {
                data.relationships.forEach(log => addPostgresLog(log, 'relationship'));
            }
            if (data.message_chains) {
                data.message_chains.forEach(log => addPostgresLog(log, 'message'));
            }
            
            postgresLoading.textContent = 
                `${data.relationships?.length || 0} relationships, 
                 ${data.message_chains?.length || 0} message chains loaded`;
        } catch (e) {
            console.error("PostgreSQL load error:", e);
            postgresLoading.textContent = `Error: ${e.message}`;
            postgresLoading.classList.add('error');
        } finally {
            postgresLoading.classList.remove('loading-active');
        }
    }

    // Polling with separate intervals
    function startPolling() {
        setInterval(() => {
            loadQdrantLogs();
            loadPostgresLogs();
        }, 3000);
        
        // Initial load
        loadQdrantLogs();
        loadPostgresLogs();
    }

    // Message submission (unchanged)
    messageForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const userInput = messageInput.value.trim();
        if (!userInput) return;

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

            // Refresh feeds after command
            setTimeout(() => {
                loadQdrantLogs();
                loadPostgresLogs();
            }, 1000);

        } catch (err) {
            chatContainer.removeChild(loadingIndicator);
            addMessage(`Error: ${err.message}`, 'bot', 'error');
        }
    });

    function startPolling() {
        // Initial immediate load
        loadQdrantLogs();
        loadPostgresLogs();
        
        // Set up regular polling
        const pollInterval = setInterval(() => {
            loadQdrantLogs();
            loadPostgresLogs();
        }, 3000);

        // Cleanup on window close (optional)
        window.addEventListener('beforeunload', () => {
            clearInterval(pollInterval);
        });
    }

    startPolling();
});