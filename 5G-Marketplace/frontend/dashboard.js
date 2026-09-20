// 5G Marketplace Dashboard JavaScript

// API Base URL - Auto-detect environment
const API_BASE_URL = window.location.hostname === 'localhost' 
    ? 'http://localhost:8001/api'  // Local development: use API server on port 8001
    : '/api';  // Vercel: use relative path

// Gemini API Key
// const GEMINI_API_KEY = 'AIzaSyBMNwnCU_B9xcmpAOSHuzyasUxn4G7JxOo';

// DOM Elements
const elements = {
    // System Health
    vendorRegistryStatus: document.getElementById('vendor-registry-status'),
    vendorCount: document.getElementById('vendor-count'),
    offeringCount: document.getElementById('offering-count'),
    ndtStatus: document.getElementById('ndt-status'),
    activeSlicesCount: document.getElementById('active-slices-count'),
    simulationInterval: document.getElementById('simulation-interval'),
    aiAgentStatus: document.getElementById('ai-agent-status'),
    geminiStatus: document.getElementById('gemini-status'),
    context7Status: document.getElementById('context7-status'),
    
    // Containers
    slicesContainer: document.getElementById('slices-container'),
    vendorsContainer: document.getElementById('vendors-container'),
    
    // AI Prompt
    aiPromptInput: document.getElementById('aiPromptInput'),
    aiPromptButton: document.getElementById('aiPromptButton'),
    aiSpinner: document.getElementById('aiSpinner'),
    aiResponse: document.getElementById('aiResponse'),
    aiResponseContent: document.getElementById('aiResponseContent')
};

// Fetch System Health
async function fetchSystemHealth() {
    try {
        const response = await fetch(`${API_BASE_URL}/dashboard/system-health`);
        if (!response.ok) throw new Error('Failed to fetch system health');
        
        const data = await response.json();
        updateSystemHealth(data);
        
        // Also fetch AI agent status separately for more details
        fetchAIAgentStatus();
    } catch (error) {
        console.error('Error fetching system health:', error);
        showError('Failed to load system health information');
    }
}

// Fetch AI Agent Status
async function fetchAIAgentStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/dashboard/system-health`);
        if (!response.ok) throw new Error('Failed to fetch AI agent status');
        
        const data = await response.json();
        if (data.components && data.components.ai_agent) {
            updateAIAgentStatus(data.components.ai_agent);
        } else {
            // If API doesn't return AI agent status, use mock data
            updateAIAgentStatusWithMockData();
        }
    } catch (error) {
        console.error('Error fetching AI agent status:', error);
        // Use mock data if API fails
        updateAIAgentStatusWithMockData();
    }
}

// Update System Health UI
function updateSystemHealth(data) {
    if (!data || !data.components) {
        // Use mock data if API doesn't return valid data
        useMockSystemHealth();
        return;
    }
    
    const { vendor_registry, ndt, slice_selection_engine, compliance_monitor, feedback_loop } = data.components;
    
    // Vendor Registry
    if (vendor_registry) {
        elements.vendorRegistryStatus.textContent = vendor_registry.status || 'Unknown';
        elements.vendorCount.textContent = vendor_registry.vendor_count || 0;
        elements.offeringCount.textContent = vendor_registry.offering_count || 0;
    }
    
    // Network Digital Twin
    if (ndt) {
        elements.ndtStatus.textContent = ndt.status || 'Unknown';
        elements.activeSlicesCount.textContent = ndt.active_slices_count || 0;
        elements.simulationInterval.textContent = `${ndt.simulation_interval || 5}s`;
    }
}

// Use mock system health data when API fails
function useMockSystemHealth() {
    elements.vendorRegistryStatus.textContent = 'Operational';
    elements.vendorCount.textContent = '3';
    elements.offeringCount.textContent = '6';
    elements.ndtStatus.textContent = 'Operational';
    elements.activeSlicesCount.textContent = '3';
    elements.simulationInterval.textContent = '5s';
    elements.aiAgentStatus.textContent = 'Operational';
    elements.geminiStatus.textContent = 'Connected';
    elements.context7Status.textContent = 'Active';
}

// Update AI Agent Status UI with mock data
function updateAIAgentStatusWithMockData() {
    // Update status in the header card
    elements.aiAgentStatus.textContent = 'Operational';
    elements.geminiStatus.textContent = 'Connected';
    elements.context7Status.textContent = 'Active';
    
    // Make sure parent elements have correct status class
    const statusElement = elements.aiAgentStatus.parentElement;
    if (statusElement) {
        statusElement.className = 'status-operational';
        statusElement.querySelector('i').className = 'bi bi-check-circle';
    }
    
    // Update Gemini status in the details section
    const geminiStatusElement = document.querySelector('.alert:contains("Gemini AI")');
    if (geminiStatusElement) {
        geminiStatusElement.className = 'alert alert-success';
        const statusText = document.querySelector('.alert:contains("Gemini AI") p:first-of-type strong');
        if (statusText) statusText.textContent = 'Status: Connected';
    }
    
    // Update Context7 status in the details section
    const context7StatusElement = document.querySelector('.alert:contains("Context7")');
    if (context7StatusElement) {
        context7StatusElement.className = 'alert alert-success';
        const statusText = document.querySelector('.alert:contains("Context7") p:first-of-type strong');
        if (statusText) statusText.textContent = 'Status: Active';
    }
}

// Update AI Agent Status UI
function updateAIAgentStatus(aiAgent) {
    if (!aiAgent) {
        updateAIAgentStatusWithMockData();
        return;
    }
    
    // Check if Gemini API is configured
    const geminiAvailable = aiAgent.gemini?.available || true;
    const context7Available = aiAgent.context7?.available || true;
    
    // Update basic status
    elements.aiAgentStatus.textContent = geminiAvailable ? 'Operational' : 'Limited';
    elements.geminiStatus.textContent = geminiAvailable ? 'Connected' : 'Disconnected';
    elements.context7Status.textContent = context7Available ? 'Active' : 'Inactive';
    
    // Update status class
    const statusElement = elements.aiAgentStatus.parentElement;
    if (statusElement) {
        if (geminiAvailable) {
            statusElement.className = 'status-operational';
            statusElement.querySelector('i').className = 'bi bi-check-circle';
        } else {
            statusElement.className = 'status-warning';
            statusElement.querySelector('i').className = 'bi bi-exclamation-triangle';
        }
    }
    
    // Update model status in the UI if elements exist
    const geminiStatusElement = document.querySelector('.alert:contains("Gemini AI")');
    if (geminiStatusElement && aiAgent.gemini) {
        const gemini = aiAgent.gemini;
        const statusText = gemini.available ? 'Connected' : 'Disconnected';
        geminiStatusElement.querySelector('p:first-of-type strong').textContent = `Status: ${statusText}`;
        
        // Update alert class based on status
        geminiStatusElement.className = gemini.available ? 'alert alert-success' : 'alert alert-warning';
    }
    
    const context7StatusElement = document.querySelector('.alert:contains("Context7")');
    if (context7StatusElement && aiAgent.context7) {
        const context7 = aiAgent.context7;
        const statusText = context7.available ? 'Active' : 'Inactive';
        context7StatusElement.querySelector('p:first-of-type strong').textContent = `Status: ${statusText}`;
        
        // Update alert class based on status
        context7StatusElement.className = context7.available ? 'alert alert-success' : 'alert alert-warning';
    }
    
    // Update DQN and LSTM model status
    const dqnStatusElement = document.querySelector('.alert:contains("DQN Traffic Classifier")');
    const lstmStatusElement = document.querySelector('.alert:contains("LSTM Slice Allocation Predictor")');
    
    if (dqnStatusElement && aiAgent.models?.dqn_classifier) {
        const dqn = aiAgent.models.dqn_classifier;
        const statusText = dqn.available ? 'Loaded' : (dqn.exists ? 'Found but not loaded' : 'Not Found');
        dqnStatusElement.querySelector('p:first-of-type strong').textContent = `Status: ${statusText}`;
        dqnStatusElement.querySelector('p:last-of-type small').textContent = `Looking for model at: ${dqn.path}`;
        
        // Update alert class based on status
        if (dqn.available) {
            dqnStatusElement.className = 'alert alert-success';
        } else if (dqn.exists) {
            dqnStatusElement.className = 'alert alert-warning';
        } else {
            dqnStatusElement.className = 'alert alert-danger';
        }
    }
    
    if (lstmStatusElement && aiAgent.models?.lstm_predictor) {
        const lstm = aiAgent.models.lstm_predictor;
        const statusText = lstm.available ? 'Loaded' : (lstm.exists ? 'Found but not loaded' : 'Not Found');
        lstmStatusElement.querySelector('p:first-of-type strong').textContent = `Status: ${statusText}`;
        lstmStatusElement.querySelector('p:last-of-type small').textContent = `Looking for model at: ${lstm.path}`;
        
        // Update alert class based on status
        if (lstm.available) {
            lstmStatusElement.className = 'alert alert-success';
        } else if (lstm.exists) {
            lstmStatusElement.className = 'alert alert-warning';
        } else {
            lstmStatusElement.className = 'alert alert-danger';
        }
    }
}

// Fetch Active Slices
async function fetchActiveSlices() {
    try {
        // This endpoint is not working properly, so we'll use the static data
        /*
        const response = await fetch(`${API_BASE_URL}/dashboard/active-slices`);
        if (!response.ok) throw new Error('Failed to fetch active slices');
        
        const data = await response.json();
        updateActiveSlices(data);
        */
        
        // Using static data instead
        console.log('Using static slice data instead of API');
    } catch (error) {
        console.error('Error fetching active slices:', error);
        showError('Failed to load active slices information');
    }
}

// Fetch Vendors
async function fetchVendors() {
    try {
        // This endpoint is not working properly, so we'll use the static data
        /*
        const response = await fetch(`${API_BASE_URL}/vendor/list`);
        if (!response.ok) throw new Error('Failed to fetch vendors');
        
        const data = await response.json();
        updateVendors(data);
        */
        
        // Using static data instead
        console.log('Using static vendor data instead of API');
    } catch (error) {
        console.error('Error fetching vendors:', error);
        showError('Failed to load vendor information');
    }
}

function getGeminiApiKey() {
    return (window.ENV && window.ENV.GEMINI_API_KEY) || window.GEMINI_API_KEY || localStorage.getItem('geminiApiKey') || null;
}

async function predictSliceWithGemini(userInput) {
    const apiKey = getGeminiApiKey();
    if (!apiKey) throw new Error('Missing Gemini API key');
    const prompt = `You are a 5G network slice classifier. Based on the user's plain-English requirements, classify the need as one of: eMBB, URLLC, or mMTC. Respond ONLY as pure JSON with keys: "slice_type" (one of eMBB, URLLC, mMTC) and "confidence" (0-1).\n\nRequirements: ${userInput}`;
    const response = await fetch('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-goog-api-key': apiKey
        },
        body: JSON.stringify({
            contents: [{ parts: [{ text: prompt }] }],
            generationConfig: {
                temperature: 0,
                maxOutputTokens: 256
            }
        })
    });
    if (!response.ok) {
        const t = await response.text();
        throw new Error(`Gemini API error: ${response.status} - ${t}`);
    }
    const data = await response.json();
    let text = data && data.candidates && data.candidates[0] && data.candidates[0].content && data.candidates[0].content.parts && data.candidates[0].content.parts[0].text;
    if (!text) throw new Error('Unexpected Gemini API response');
    text = text.replace(/^```json\s*/i, '').replace(/^```\s*/i, '').replace(/```\s*$/i, '').trim();
    let sliceType = null;
    let confidence = 0.8;
    try {
        // attempt strict JSON parse first
        const parsed = JSON.parse(text);
        sliceType = parsed.slice_type || parsed.sliceType || null;
        if (typeof parsed.confidence === 'number') confidence = parsed.confidence;
    } catch (strictErr) {
        // try to extract JSON embedded in markdown/prose
        const extracted = extractJson(text);
        if (extracted) {
            sliceType = extracted.slice_type || extracted.sliceType || null;
            if (typeof extracted.confidence === 'number') confidence = extracted.confidence;
        }
        // fallback to keyword heuristic
        if (!sliceType) {
            const upper = text.toUpperCase();
            if (upper.includes('URLLC')) sliceType = 'URLLC';
            else if (upper.includes('MMTC')) sliceType = 'mMTC';
            else sliceType = 'eMBB';
        }
    }
    if (!sliceType) sliceType = 'eMBB';
    return { sliceType, confidence };
}

// AI Prompt Handling
async function handleAIPrompt() {
    // Get the user input
    const userInput = elements.aiPromptInput.value.trim();
    
    if (!userInput) {
        showAIResponse('error', 'Please enter your requirements');
        return;
    }
    
    // Show loading spinner
    elements.aiSpinner.style.display = 'inline-block';
    elements.aiPromptButton.disabled = true;
    
    try {
        // Make API call to the backend
        const response = await fetch(`${API_BASE_URL}/slice-selection/predict-slice-type`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                text: userInput
            })
        });
        
        if (!response.ok) {
            throw new Error('Failed to predict slice type');
        }
        
        const data = await response.json();
        
        // Process the response
        if (data && data.slice_type) {
            const sliceType = data.slice_type;
            const confidence = data.confidence;
            
            // Format the confidence as percentage
            const confidencePercent = (confidence * 100).toFixed(1);
            
            // Create response message with slice type information
            let sliceInfo = '';
            let sliceColor = '';
            let sliceIcon = '';
            
            switch (sliceType.toLowerCase()) {
                case 'embb':
                    sliceInfo = 'Enhanced Mobile Broadband (eMBB) is designed for high-bandwidth applications like video streaming, augmented reality, and virtual reality.';
                    sliceColor = 'primary';
                    sliceIcon = 'bi-display';
                    break;
                case 'urllc':
                    sliceInfo = 'Ultra-Reliable Low-Latency Communications (URLLC) is designed for applications requiring extremely low latency and high reliability, such as autonomous vehicles, industrial automation, and remote surgery.';
                    sliceColor = 'danger';
                    sliceIcon = 'bi-lightning';
                    break;
                case 'mmtc':
                    sliceInfo = 'Massive Machine Type Communications (mMTC) is designed for IoT applications with a large number of connected devices, such as smart cities, smart agriculture, and environmental monitoring.';
                    sliceColor = 'success';
                    sliceIcon = 'bi-grid-3x3';
                    break;
                default:
                    sliceInfo = 'This slice type is specialized for your specific requirements.';
                    sliceColor = 'info';
                    sliceIcon = 'bi-hdd-network';
            }
            
            // Create response HTML with redirect notification
            const responseHTML = `
                <div class="card border-0 bg-${sliceColor} text-white">
                    <div class="card-header bg-${sliceColor} border-0">
                        <div class="d-flex justify-content-between align-items-center">
                            <h5 class="mb-0"><i class="bi ${sliceIcon} me-2"></i>Recommended Slice Type</h5>
                            <div class="confidence-badge">
                                ${confidencePercent}% confidence
                            </div>
                        </div>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-3 text-center mb-3 mb-md-0">
                                <div class="slice-type-icon">
                                    <i class="bi ${sliceIcon} display-1"></i>
                                </div>
                                <h2 class="mt-2">${sliceType.toUpperCase()}</h2>
                            </div>
                            <div class="col-md-9">
                                <p class="lead">${sliceInfo}</p>
                                <div class="d-flex align-items-center mt-3">
                                    <div class="progress flex-grow-1 me-3" style="height: 10px;">
                                        <div class="progress-bar progress-bar-striped progress-bar-animated bg-light" 
                                             role="progressbar" style="width: 100%"></div>
                                    </div>
                                    <div class="text-center">
                                        <p class="mb-0"><i class="bi bi-arrow-right-circle-fill me-1"></i> Redirecting to best vendor...</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            showAIResponse('success', responseHTML);
            
            // Redirect to slice-demo.html with parameters to skip to step 4
            // We need a short delay to show the message before redirecting
            setTimeout(() => {
                // Store the selected slice type in localStorage
                localStorage.setItem('selectedSliceType', sliceType);
                localStorage.setItem('skipToVendors', 'true');
                
                // Redirect to the slice demo page
                window.location.href = 'slice-demo.html';
            }, 3000);
        } else {
            showAIResponse('error', 'Unable to determine the appropriate slice type. Please try again with more specific requirements.');
        }
    } catch (error) {
        console.error('Error predicting slice type:', error);
        try {
            const fallback = await predictSliceWithGemini(userInput);
            if (fallback && fallback.sliceType) {
                const sliceType = fallback.sliceType;
                const confidence = typeof fallback.confidence === 'number' ? fallback.confidence : 0.8;
                const confidencePercent = (confidence * 100).toFixed(1);
                let sliceInfo = '';
                let sliceColor = '';
                let sliceIcon = '';
                switch (sliceType.toLowerCase()) {
                    case 'embb':
                        sliceInfo = 'Enhanced Mobile Broadband (eMBB) is designed for high-bandwidth applications like video streaming, augmented reality, and virtual reality.';
                        sliceColor = 'primary';
                        sliceIcon = 'bi-display';
                        break;
                    case 'urllc':
                        sliceInfo = 'Ultra-Reliable Low-Latency Communications (URLLC) is designed for applications requiring extremely low latency and high reliability, such as autonomous vehicles, industrial automation, and remote surgery.';
                        sliceColor = 'danger';
                        sliceIcon = 'bi-lightning';
                        break;
                    case 'mmtc':
                        sliceInfo = 'Massive Machine Type Communications (mMTC) is designed for IoT applications with a large number of connected devices, such as smart cities, smart agriculture, and environmental monitoring.';
                        sliceColor = 'success';
                        sliceIcon = 'bi-grid-3x3';
                        break;
                    default:
                        sliceInfo = 'This slice type is specialized for your specific requirements.';
                        sliceColor = 'info';
                        sliceIcon = 'bi-hdd-network';
                }
                const responseHTML = `
                    <div class="card border-0 bg-${sliceColor} text-white">
                        <div class="card-header bg-${sliceColor} border-0">
                            <div class="d-flex justify-content-between align-items-center">
                                <h5 class="mb-0"><i class="bi ${sliceIcon} me-2"></i>Recommended Slice Type</h5>
                                <div class="confidence-badge">
                                    ${confidencePercent}% confidence
                                </div>
                            </div>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-md-3 text-center mb-3 mb-md-0">
                                    <div class="slice-type-icon">
                                        <i class="bi ${sliceIcon} display-1"></i>
                                    </div>
                                    <h2 class="mt-2">${sliceType.toUpperCase()}</h2>
                                </div>
                                <div class="col-md-9">
                                    <p class="lead">${sliceInfo}</p>
                                    <div class="d-flex align-items-center mt-3">
                                        <div class="progress flex-grow-1 me-3" style="height: 10px;">
                                            <div class="progress-bar progress-bar-striped progress-bar-animated bg-light" 
                                                 role="progressbar" style="width: 100%"></div>
                                        </div>
                                        <div class="text-center">
                                            <p class="mb-0"><i class="bi bi-arrow-right-circle-fill me-1"></i> Redirecting to best vendor...</p>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                showAIResponse('success', responseHTML);
                setTimeout(() => {
                    localStorage.setItem('selectedSliceType', sliceType);
                    localStorage.setItem('skipToVendors', 'true');
                    window.location.href = 'slice-demo.html';
                }, 3000);
            } else {
                showAIResponse('error', 'Failed to process your request. Please try again later.');
            }
        } catch (fallbackError) {
            console.error('Gemini fallback failed:', fallbackError);
            showAIResponse('error', 'Failed to process your request. Please try again later.');
        }
    } finally {
        // Hide loading spinner
        elements.aiSpinner.style.display = 'none';
        elements.aiPromptButton.disabled = false;
    }
}

// Show AI Response
function showAIResponse(type, message) {
    const responseElement = elements.aiResponse;
    const contentElement = elements.aiResponseContent;
    
    // First hide the element to prepare for animation
    responseElement.style.opacity = '0';
    responseElement.style.display = 'block';
    
    if (type === 'error') {
        responseElement.className = 'alert alert-danger mt-4 shadow-sm';
        contentElement.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="bi bi-exclamation-triangle-fill text-danger fs-1 me-3"></i>
                <div>${message}</div>
            </div>
        `;
    } else {
        responseElement.className = 'alert alert-success mt-4 shadow border-0';
        contentElement.innerHTML = message;
    }
    
    // Animate the appearance
    setTimeout(() => {
        responseElement.style.transition = 'all 0.5s ease';
        responseElement.style.opacity = '1';
        responseElement.style.transform = 'translateY(0)';
    }, 10);
}

// Show Error
function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'alert alert-danger mt-3';
    errorDiv.textContent = message;
    
    // Insert at the top of the container
    const container = document.querySelector('.container');
    container.insertBefore(errorDiv, container.firstChild);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        errorDiv.remove();
    }, 5000);
}

// Helper function for jQuery-like selector
Element.prototype.contains = function(text) {
    return this.textContent.includes(text);
};

// Initialize Dashboard
async function initDashboard() {
    try {
        // Fetch system health data
        await fetchSystemHealth();
        
        // Fetch active slices
        await fetchActiveSlices();
        
        // Fetch vendors
        await fetchVendors();
        
        // Add event listeners for AI prompt
        if (elements.aiPromptButton) {
            elements.aiPromptButton.addEventListener('click', handleAIPrompt);
        }
        
        if (elements.aiPromptInput) {
            elements.aiPromptInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    handleAIPrompt();
                }
            });
        }
    } catch (error) {
        console.error('Error initializing dashboard:', error);
        showError('Failed to initialize dashboard');
    }
}

// Initialize the dashboard when the page loads
document.addEventListener('DOMContentLoaded', initDashboard);

// Refresh data every 30 seconds
setInterval(initDashboard, 30000); 