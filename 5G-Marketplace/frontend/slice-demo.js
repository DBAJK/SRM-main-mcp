// API Base URL
const API_BASE_URL = 'http://localhost:8001/api';

// Default Gemini API key for demo purposes - replace with your own key
const DEFAULT_GEMINI_API_KEY = "AIzaSyCYpnITiYcwCBUu_mBCxtStGOLd5nUekHQ";

// Chart.js instances
let scoresChart = null;
let weightsChart = null;

// State management
let currentStep = 1;
let totalSteps = 5;
let selectedSliceType = null;
let qosRequirements = {};
let selectedVendor = null;
let deploymentStatus = null;
let vendorOffers = [];
let monitoringInterval = null;
let deployedSliceId = null;
let geminiApiKey = localStorage.getItem('geminiApiKey') || DEFAULT_GEMINI_API_KEY;
let lastMonitoringData = null; // To store the last received monitoring data

// Initialize the demo
document.addEventListener('DOMContentLoaded', function() {
    // Check if we should skip to vendors (coming from AI prediction)
    const skipToVendors = localStorage.getItem('skipToVendors');
    const aiSelectedSliceType = localStorage.getItem('selectedSliceType');
    
    if (skipToVendors === 'true' && aiSelectedSliceType) {
        // Set the selected slice type
        selectedSliceType = aiSelectedSliceType;
        
        // Jump directly to step 3 (processing) which will automatically go to step 4
        currentStep = 3;
        
        // Clear the localStorage flags
        localStorage.removeItem('skipToVendors');
        localStorage.removeItem('selectedSliceType');
    }
    
    updateProgressBar();
    showCurrentStep();
    
    // Settings Modal Logic
    const settingsModalEl = document.getElementById('settingsModal');
    if (settingsModalEl) {
        const settingsModal = new bootstrap.Modal(settingsModalEl);
        const geminiApiKeyInput = document.getElementById('geminiApiKeyInput');
        const saveSettingsBtn = document.getElementById('saveSettingsBtn');
        
        settingsModalEl.addEventListener('shown.bs.modal', () => {
            geminiApiKeyInput.value = geminiApiKey || '';
        });

        saveSettingsBtn.addEventListener('click', () => {
            const newApiKey = geminiApiKeyInput.value.trim();
            if (newApiKey) {
                geminiApiKey = newApiKey;
                localStorage.setItem('geminiApiKey', newApiKey);
                alert('API Key saved successfully!');
                settingsModal.hide();
                
                // Refresh monitoring data if we're on the monitoring page
                if (deployedSliceId) {
                    fetchMonitoringData(deployedSliceId);
                }
            } else {
                geminiApiKey = null;
                localStorage.removeItem('geminiApiKey');
                alert('API Key removed.');
            }
        });
    }
    
    // ML Scoring Modal Logic
    const mlScoringModalEl = document.getElementById('mlScoringModal');
    if (mlScoringModalEl) {
        mlScoringModalEl.addEventListener('hidden.bs.modal', () => {
            // Clean up charts when modal is closed
            if (scoresChart instanceof Chart) {
                scoresChart.destroy();
                scoresChart = null;
            }
            if (weightsChart instanceof Chart) {
                weightsChart.destroy();
                weightsChart = null;
            }
            console.log('ML Scoring charts cleaned up');
        });
    }
    
    // Add event listeners for slice type selection
    document.querySelectorAll('.slice-type-card').forEach(card => {
        card.addEventListener('click', function() {
            selectedSliceType = this.dataset.sliceType;
            document.querySelectorAll('.slice-type-card').forEach(c => {
                c.classList.remove('selected');
            });
            this.classList.add('selected');
            document.getElementById('nextBtn').disabled = false;
        });
    });
    
    // Add event listener for next button
    document.getElementById('nextBtn').addEventListener('click', nextStep);
    
    // Add event listener for back button
    document.getElementById('backBtn').addEventListener('click', previousStep);
    
    // Add event listener for QoS form submission
    document.getElementById('qosForm').addEventListener('submit', function(e) {
        e.preventDefault();
        qosRequirements = {
            latency: document.getElementById('latency').value,
            bandwidth: document.getElementById('bandwidth').value,
            reliability: document.getElementById('reliability').value,
            location: document.getElementById('location').value
        };
        nextStep();
    });
    
    // Add event listener for deployment button
    const deployBtn = document.getElementById('deployBtn');
    if (deployBtn) {
        deployBtn.addEventListener('click', deploySlice);
    }
    
    // Add event listener for "Deploy Another Slice" button
    const deployAnotherBtn = document.getElementById('deployAnotherBtn');
    if (deployAnotherBtn) {
        deployAnotherBtn.addEventListener('click', function() {
            // Reset to step 1 to deploy another slice
            currentStep = 1;
            updateProgressBar();
            showCurrentStep();
        });
    }
    
    // Add event listeners for range inputs to update their displayed values
    document.getElementById('latency').addEventListener('input', function() {
        document.getElementById('latencyValue').textContent = this.value + 'ms';
    });
    
    document.getElementById('bandwidth').addEventListener('input', function() {
        document.getElementById('bandwidthValue').textContent = this.value + ' Mbps';
    });
    
    document.getElementById('reliability').addEventListener('input', function() {
        document.getElementById('reliabilityValue').textContent = this.value.toFixed(4) + '%';
    });
});

// Update progress bar
function updateProgressBar() {
    const progressPercentage = ((currentStep - 1) / (totalSteps - 1)) * 100;
    document.getElementById('progressBar').style.width = `${progressPercentage}%`;
    document.getElementById('progressBar').setAttribute('aria-valuenow', progressPercentage);
}

// Show current step and hide others
function showCurrentStep() {
    for (let i = 1; i <= totalSteps; i++) {
        const stepElement = document.getElementById(`step${i}`);
        if (i === currentStep) {
            stepElement.style.display = 'block';
        } else {
            stepElement.style.display = 'none';
        }
    }
    
    // Update button states
    const backBtn = document.getElementById('backBtn');
    const nextBtn = document.getElementById('nextBtn');
    
    if (currentStep === 1) {
        backBtn.style.display = 'none';
        nextBtn.disabled = !selectedSliceType;
    } else if (currentStep === totalSteps) {
        nextBtn.style.display = 'none';
        backBtn.style.display = 'inline-block';
    } else {
        backBtn.style.display = 'inline-block';
        nextBtn.style.display = 'inline-block';
        
        // Special case for step 2 (QoS requirements)
        if (currentStep === 2) {
            nextBtn.style.display = 'none'; // Hide next button as form has its own submit
        } else if (currentStep === 3) {
            // Processing step - automatically proceed after API call
            processSliceRequest();
        } else if (currentStep === 4) {
            // Vendor selection step
            nextBtn.disabled = !selectedVendor;
        }
    }
}

// Move to next step
function nextStep() {
    if (currentStep < totalSteps) {
        currentStep++;
        updateProgressBar();
        showCurrentStep();
    }
}

// Move to previous step
function previousStep() {
    if (currentStep > 1) {
        currentStep--;
        updateProgressBar();
        showCurrentStep();
    }
}

// Process slice request with AI agent
async function processSliceRequest() {
    try {
        // Show loading state
        const processingSpinner = document.getElementById('processingSpinner');
        const processingStatus = document.getElementById('processingStatus');
        const aiProcessingSpinner = document.getElementById('aiProcessingSpinner');
        const aiProcessingComplete = document.getElementById('aiProcessingComplete');
        const aiProcessingError = document.getElementById('aiProcessingError');
        
        // Check if elements exist before accessing their properties
        if (processingSpinner) processingSpinner.style.display = 'block';
        if (processingStatus) processingStatus.textContent = 'Processing your request...';
        if (aiProcessingSpinner) aiProcessingSpinner.style.display = 'block';
        if (aiProcessingComplete) aiProcessingComplete.style.display = 'none';
        if (aiProcessingError) aiProcessingError.style.display = 'none';
        
        // If we're coming from AI prediction and don't have QoS requirements yet, set defaults
        if (!qosRequirements || Object.keys(qosRequirements).length === 0) {
            // Set default QoS requirements based on slice type
            switch (selectedSliceType) {
                case 'eMBB':
                    qosRequirements = {
                        latency: '15',
                        bandwidth: '800',
                        reliability: '99.99',
                        location: 'us-east'
                    };
                    break;
                case 'URLLC':
                    qosRequirements = {
                        latency: '1',
                        bandwidth: '100',
                        reliability: '99.9999',
                        location: 'eu-central'
                    };
                    break;
                case 'mMTC':
                    qosRequirements = {
                        latency: '100',
                        bandwidth: '20',
                        reliability: '99.9',
                        location: 'asia-south'
                    };
                    break;
                default:
                    qosRequirements = {
                        latency: '50',
                        bandwidth: '500',
                        reliability: '99.95',
                        location: 'us-east'
                    };
            }
            
            // Update UI elements if they exist
            const latencyEl = document.getElementById('latency');
            const bandwidthEl = document.getElementById('bandwidth');
            const reliabilityEl = document.getElementById('reliability');
            const locationEl = document.getElementById('location');
            
            if (latencyEl) latencyEl.value = qosRequirements.latency;
            if (bandwidthEl) bandwidthEl.value = qosRequirements.bandwidth;
            if (reliabilityEl) reliabilityEl.value = qosRequirements.reliability;
            if (locationEl) locationEl.value = qosRequirements.location;
        } else {
            // If we have QoS requirements from the form, use those
            const basicQosParams = {
                latency: document.getElementById('latency')?.value || '50',
                bandwidth: document.getElementById('bandwidth')?.value || '500',
                reliability: document.getElementById('reliability')?.value || '99.95',
                location: document.getElementById('location')?.value || 'us-east'
            };
            
            // Collect advanced parameters if they exist
            const advancedParams = {};
            
            // Availability
            const availabilityEl = document.getElementById('availability');
            if (availabilityEl) {
                advancedParams.availability = availabilityEl.value;
            }
            
            // Delay tolerance
            const delayToleranceEl = document.getElementById('delayTolerance');
            if (delayToleranceEl) {
                advancedParams.delayTolerance = delayToleranceEl.value;
            }
            
            // Deterministic communication
            const deterministicEl = document.getElementById('deterministic');
            if (deterministicEl) {
                advancedParams.deterministic = deterministicEl.value;
                
                // Periodicity (only if deterministic is enabled)
                if (deterministicEl.value === 'yes') {
                    const periodicityEl = document.getElementById('periodicity');
                    if (periodicityEl) {
                        advancedParams.periodicity = periodicityEl.value;
                    }
                }
            }
            
            // Maximum packet size
            const maxPacketSizeEl = document.getElementById('maxPacketSize');
            if (maxPacketSizeEl) {
                advancedParams.maxPacketSize = maxPacketSizeEl.value;
            }
            
            // Group communication
            const groupCommunicationEl = document.getElementById('groupCommunication');
            if (groupCommunicationEl) {
                advancedParams.groupCommunication = groupCommunicationEl.value;
            }
            
            // Mission critical support
            const missionCriticalEl = document.getElementById('missionCritical');
            if (missionCriticalEl) {
                advancedParams.missionCritical = missionCriticalEl.value;
            }
            
            // Maximum users
            const maxUsersEl = document.getElementById('maxUsers');
            if (maxUsersEl) {
                advancedParams.maxUsers = maxUsersEl.value;
            }
            
            // Checkboxes for additional features
            const checkboxFeatures = [
                'energyEfficiency', 
                'performanceMonitoring', 
                'performancePrediction', 
                'mmtelSupport', 
                'nbiotSupport'
            ];
            
            checkboxFeatures.forEach(feature => {
                const featureEl = document.getElementById(feature);
                if (featureEl) {
                    advancedParams[feature] = featureEl.checked;
                }
            });
            
            // Add advanced parameters to QoS requirements
            qosRequirements = {
                ...basicQosParams,
                advanced_attributes: advancedParams
            };
        }
        
        // Prepare request body
        const requestBody = {
            slice_type: selectedSliceType,
            qos_requirements: qosRequirements
        };
        
        console.log("Sending request:", JSON.stringify(requestBody));
        
        // Make API call to get vendor offers
        if (processingStatus) processingStatus.textContent = 'Fetching vendor offers...';
        
        let data;
        try {
            const response = await fetch(`${API_BASE_URL}/slice-selection/vendors`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody)
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error("API Error Response:", response.status, errorText);
                throw new Error(`HTTP error! Status: ${response.status}, Details: ${errorText}`);
            }
            
            data = await response.json();
            console.log("API Response:", data);
        } catch (apiError) {
            console.warn("API call failed, using mock data:", apiError);
            // Generate mock vendor data
            
            // Create 3 mock vendors with different scores
            const mockVendors = [
                {
                    id: "vendor-" + Date.now() + "-1",
                    name: "Premium 5G Solutions",
                    latency: Math.max(1, Math.round(parseFloat(qosRequirements.latency) * 0.9)),
                    bandwidth: Math.min(1000, Math.round(parseFloat(qosRequirements.bandwidth) * 1.2)),
                    reliability: Math.min(99.9999, parseFloat(qosRequirements.reliability) * 1.01).toFixed(4),
                    location: qosRequirements.location,
                    cost: Math.round(50 + Math.random() * 20),
                    score: 92 + Math.random() * 0.8,
                    advanced_attributes: { ...qosRequirements.advanced_attributes }
                },
                {
                    id: "vendor-" + Date.now() + "-2",
                    name: "Standard Network Services",
                    latency: Math.max(1, Math.round(parseFloat(qosRequirements.latency) * 1.1)),
                    bandwidth: Math.round(parseFloat(qosRequirements.bandwidth) * 0.95),
                    reliability: parseFloat(qosRequirements.reliability).toFixed(4),
                    location: qosRequirements.location,
                    cost: Math.round(30 + Math.random() * 15),
                    score: 75 + Math.random() * 10,
                    advanced_attributes: { ...qosRequirements.advanced_attributes }
                },
                {
                    id: "vendor-" + Date.now() + "-3",
                    name: "Budget Slice Provider",
                    latency: Math.max(1, Math.round(parseFloat(qosRequirements.latency) * 1.3)),
                    bandwidth: Math.round(parseFloat(qosRequirements.bandwidth) * 0.8),
                    reliability: (parseFloat(qosRequirements.reliability) * 0.99).toFixed(4),
                    location: qosRequirements.location,
                    cost: Math.round(20 + Math.random() * 10),
                    score: 6.0 + Math.random() * 1.0,
                    advanced_attributes: { ...qosRequirements.advanced_attributes }
                }
            ];
            
            // Modify some advanced attributes for each vendor to show differences
            if (mockVendors[0].advanced_attributes) {
                // Premium vendor has better attributes
                if (mockVendors[0].advanced_attributes.availability === 'high') {
                    mockVendors[0].advanced_attributes.availability = 'very-high';
                }
                mockVendors[0].advanced_attributes.performanceMonitoring = true;
                mockVendors[0].advanced_attributes.performancePrediction = true;
            }
            
            if (mockVendors[2].advanced_attributes) {
                // Budget vendor has worse attributes
                if (mockVendors[2].advanced_attributes.availability === 'high') {
                    mockVendors[2].advanced_attributes.availability = 'medium';
                }
                mockVendors[2].advanced_attributes.performanceMonitoring = false;
                mockVendors[2].advanced_attributes.performancePrediction = false;
            }
            
            data = {
                vendors: mockVendors
            };
        }
        
        vendorOffers = data.vendors;
        
        // Update the classified slice type with the user's selection
        const classifiedSliceTypeEl = document.getElementById('classifiedSliceType');
        if (classifiedSliceTypeEl) {
            classifiedSliceTypeEl.textContent = selectedSliceType;
        }
        
        // Display vendor offers
        displayVendorOffers(vendorOffers);
        
        // Hide loading spinner and show completion message
        if (aiProcessingSpinner) aiProcessingSpinner.style.display = 'none';
        if (aiProcessingComplete) aiProcessingComplete.style.display = 'block';
        
        // Automatically proceed to next step after 2 seconds
        setTimeout(() => {
            nextStep();
        }, 2000);
        
    } catch (error) {
        console.error('Error processing slice request:', error);
        const aiProcessingSpinner = document.getElementById('aiProcessingSpinner');
        const aiProcessingError = document.getElementById('aiProcessingError');
        
        if (aiProcessingSpinner) aiProcessingSpinner.style.display = 'none';
        if (aiProcessingError) {
            aiProcessingError.style.display = 'block';
            aiProcessingError.textContent = `Error: ${error.message}`;
        }
    }
}

// Display vendor offers
function displayVendorOffers(vendors) {
    const vendorContainer = document.getElementById('vendorOffers');
    if (!vendorContainer) {
        console.error('Vendor container element not found');
        return;
    }
    
    vendorContainer.innerHTML = '';
    
    if (!vendors || vendors.length === 0) {
        vendorContainer.innerHTML = '<div class="alert alert-warning">No vendors found matching your requirements.</div>';
        return;
    }
    
    // Sort vendors by score (highest first)
    vendors.sort((a, b) => b.score - a.score);
    
    // Mark the best vendor
    const bestVendor = vendors[0];
    bestVendor.isBest = true;
    
    vendors.forEach(vendor => {
        const vendorCard = document.createElement('div');
        vendorCard.className = `card mb-3 vendor-card ${vendor.isBest ? 'best-vendor' : ''}`;
        vendorCard.dataset.vendorId = vendor.id;
        
        // Generate advanced attributes HTML if they exist
        let advancedAttributesHtml = '';
        
        // Always create the advanced attributes section, even if empty
        advancedAttributesHtml = `
            <hr>
            <div class="advanced-attributes">
                <h6>Advanced Network Slice Template Attributes</h6>
                <div class="row">
        `;
        
        // Define the attributes we want to display in the same order as in the form
        const attributeOrder = [
            'availability', 
            'delayTolerance', 
            'deterministic', 
            'periodicity', 
            'maxPacketSize', 
            'groupCommunication', 
            'missionCritical', 
            'maxUsers', 
            'energyEfficiency', 
            'performanceMonitoring', 
            'performancePrediction', 
            'mmtelSupport', 
            'nbiotSupport'
        ];
        
        // Format display names for each attribute
        const attributeDisplayNames = {
            'availability': 'Availability',
            'delayTolerance': 'Delay Tolerance',
            'deterministic': 'Deterministic Communication',
            'periodicity': 'Periodicity (seconds)',
            'maxPacketSize': 'Maximum Packet Size (bytes)',
            'groupCommunication': 'Group Communication Support',
            'missionCritical': 'Mission Critical Support',
            'maxUsers': 'Maximum Concurrent Users',
            'energyEfficiency': 'Energy Efficiency Monitoring',
            'performanceMonitoring': 'Real-time Performance Monitoring',
            'performancePrediction': 'Performance Prediction',
            'mmtelSupport': 'MMTel Support',
            'nbiotSupport': 'NB-IoT Support'
        };
        
        // Format values for display
        const formatAttributeValue = (key, value) => {
            if (typeof value === 'boolean') {
                return value ? 'Yes' : 'No';
            }
            
            // Format specific values
            switch(key) {
                case 'availability':
                    if (value === 'high') return 'High (99-99.999%)';
                    if (value === 'medium') return 'Medium (90-99%)';
                    if (value === 'low') return 'Low (<90%)';
                    if (value === 'very-high') return 'Very High (>99.999%)';
                    return value;
                case 'delayTolerance':
                    return value === 'yes' ? 'Delay Tolerant' : 'Not Delay Tolerant';
                case 'deterministic':
                    return value === 'yes' ? 'Required' : 'Not Required';
                case 'groupCommunication':
                    if (value === 'none') return 'None';
                    if (value === 'unicast') return 'Unicast';
                    if (value === 'multicast') return 'Multicast/Broadcast';
                    if (value === 'sc-ptm') return 'SC-PTM';
                    return value;
                case 'missionCritical':
                    if (value === 'none') return 'None';
                    if (value === 'prioritization') return 'Inter-user Prioritization';
                    if (value === 'preemption') return 'Pre-emption';
                    if (value === 'mcptt') return 'MCPTT/MCData/MCVideo';
                    return value;
                case 'maxPacketSize':
                    if (value === '40') return '40 (IoT Optimized)';
                    if (value === '160') return '160 (URLLC Optimized)';
                    if (value === '1500') return '1500 (Default)';
                    return value + ' bytes';
                default:
                    return value;
            }
        };
        
        // Get the advanced attributes from the vendor
        const advancedAttrs = vendor.advanced_attributes || {};
        
        // Add attributes in the specified order
        attributeOrder.forEach(key => {
            if (key in advancedAttrs) {
                const displayName = attributeDisplayNames[key] || key;
                const formattedValue = formatAttributeValue(key, advancedAttrs[key]);
                
                advancedAttributesHtml += `
                    <div class="col-md-6 mb-2">
                        <small><strong>${displayName}:</strong> ${formattedValue}</small>
                    </div>
                `;
            }
        });
        
        advancedAttributesHtml += `
                </div>
            </div>
        `;
        
        // Add ML scoring button for the best vendor
        const mlScoringButton = vendor.isBest ? 
            `<button class="btn btn-sm btn-info ml-scoring-btn" data-vendor-id="${vendor.id}">
                <i class="bi bi-graph-up"></i> View ML Scoring
             </button>` : '';
        
        vendorCard.innerHTML = `
            <div class="card-header d-flex justify-content-between align-items-center">
                ${vendor.name}
                ${vendor.isBest ? '<span class="badge bg-success">Best Match</span>' : ''}
            </div>
            <div class="card-body">
                <p><strong>Score:</strong> ${vendor.score.toFixed(2)}</p>
                <p><strong>Latency:</strong> ${vendor.latency} ms</p>
                <p><strong>Bandwidth:</strong> ${vendor.bandwidth} Mbps</p>
                <p><strong>Reliability:</strong> ${vendor.reliability}%</p>
                <p><strong>Location:</strong> ${vendor.location}</p>
                <p><strong>Cost:</strong> $${vendor.cost.toFixed(2)}/hour</p>
                ${advancedAttributesHtml}
                ${vendor.isBest ? `<div class="text-center mt-3">${mlScoringButton}</div>` : ''}
            </div>
        `;
        
        vendorCard.addEventListener('click', function(e) {
            // Don't select vendor if clicking on the ML scoring button
            if (e.target.closest('.ml-scoring-btn')) {
                return;
            }
            
            document.querySelectorAll('.vendor-card').forEach(card => {
                card.classList.remove('selected');
            });
            this.classList.add('selected');
            selectedVendor = vendor;
            
            const nextBtn = document.getElementById('nextBtn');
            if (nextBtn) nextBtn.disabled = false;
        });
        
        vendorContainer.appendChild(vendorCard);
    });
    
    // Add event listeners for ML scoring buttons
    document.querySelectorAll('.ml-scoring-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            const vendorId = this.dataset.vendorId;
            showMlScoring(vendorId);
        });
    });
    
    // Auto-select the best vendor
    selectedVendor = bestVendor;
    const bestVendorElement = document.querySelector('.vendor-card.best-vendor');
    if (bestVendorElement) bestVendorElement.classList.add('selected');
    
    const nextBtn = document.getElementById('nextBtn');
    if (nextBtn) nextBtn.disabled = false;
}

// Show ML scoring breakdown
async function showMlScoring(vendorId) {
    try {
        // Get the modal
        const mlScoringModalElement = document.getElementById('mlScoringModal');
        if (!mlScoringModalElement) {
            console.error('Could not find mlScoringModal element');
            alert('Error: Could not find ML Scoring Modal');
            return;
        }
        
        const mlScoringModal = new bootstrap.Modal(mlScoringModalElement);
        
        // Show the modal
        mlScoringModal.show();
        
        // Show loading spinner
        document.getElementById('mlScoringSpinner').style.display = 'block';
        document.getElementById('mlScoringContent').style.display = 'none';
        
        // Prepare request body
        const requestBody = {
            vendor_id: vendorId,
            slice_type: selectedSliceType,
            qos_requirements: qosRequirements
        };
        
        console.log("Sending request for vendor score breakdown:", requestBody);
        
        // Make API call to get vendor score breakdown
        const response = await fetch(`${API_BASE_URL}/slice-selection/vendor-score-breakdown`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        
        const data = await response.json();
        console.log("Score breakdown response:", data);
        
        if (!data || !data.score_breakdown) {
            throw new Error('Invalid response format: missing score breakdown data');
        }
        
        // Display the score breakdown
        displayScoreBreakdown(data.score_breakdown);
        
    } catch (error) {
        console.error('Error getting score breakdown:', error);
        document.getElementById('scoringExplanation').innerHTML = `
            <div class="alert alert-danger">
                Error loading score breakdown: ${error.message}
            </div>
        `;
        document.getElementById('mlScoringSpinner').style.display = 'none';
        document.getElementById('mlScoringContent').style.display = 'block';
    }
}

// Display score breakdown
function displayScoreBreakdown(breakdown) {
    // Set explanation
    document.getElementById('scoringExplanation').textContent = breakdown.explanation;
    
    // Fill calculation steps table
    const stepsTable = document.getElementById('calculationStepsTable');
    stepsTable.innerHTML = '';
    
    breakdown.calculation_steps.forEach(step => {
        const row = document.createElement('tr');
        
        // Format criterion name for display
        let criterionName = step.criterion;
        criterionName = criterionName.charAt(0).toUpperCase() + criterionName.slice(1);
        criterionName = criterionName.replace(/_/g, ' ');
        
        row.innerHTML = `
            <td>${criterionName}</td>
            <td>${step.raw_score.toFixed(3)}</td>
            <td>${step.weight.toFixed(3)}</td>
            <td>${step.weighted_score.toFixed(3)}</td>
            <td>${step.contribution.toFixed(2)}%</td>
        `;
        
        stepsTable.appendChild(row);
    });
    
    // Create bar chart for individual scores
    const scoresCanvas = document.getElementById('individualScoresChart');
    if (!scoresCanvas) {
        console.error('Could not find individualScoresChart element');
        return;
    }

    // Ensure the element is a canvas
    if (scoresCanvas.tagName !== 'CANVAS') {
        // Replace the div with a canvas element
        const canvas = document.createElement('canvas');
        canvas.id = 'individualScoresChart';
        canvas.style.height = '300px';
        scoresCanvas.parentNode.replaceChild(canvas, scoresCanvas);
    }

    // Extract data for chart
    const criteriaLabels = Object.keys(breakdown.individual_scores).map(key => {
        return key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
    });

    const scoreValues = Object.values(breakdown.individual_scores);

    // Destroy existing chart if it exists
    if (scoresChart instanceof Chart) {
        scoresChart.destroy();
    }

    // Create new chart
    scoresChart = new Chart(document.getElementById('individualScoresChart').getContext('2d'), {
        type: 'bar',
        data: {
            labels: criteriaLabels,
            datasets: [{
                label: 'Raw Scores (0-1)',
                data: scoreValues,
                backgroundColor: 'rgba(54, 162, 235, 0.7)',
                borderColor: 'rgba(54, 162, 235, 1)',
                borderWidth: 1
            }]
        },
        options: {
            scales: {
                y: {
                    beginAtZero: true,
                    max: 1
                }
            },
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });

    // Create pie chart for weights
    const weightsCanvas = document.getElementById('weightsChart');
    if (!weightsCanvas) {
        console.error('Could not find weightsChart element');
        return;
    }

    // Ensure the element is a canvas
    if (weightsCanvas.tagName !== 'CANVAS') {
        // Replace the div with a canvas element
        const canvas = document.createElement('canvas');
        canvas.id = 'weightsChart';
        canvas.style.height = '300px';
        weightsCanvas.parentNode.replaceChild(canvas, weightsCanvas);
    }

    // Extract data for chart
    const weightLabels = Object.keys(breakdown.weights).map(key => {
        return key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
    });

    const weightValues = Object.values(breakdown.weights);

    // Destroy existing chart if it exists
    if (weightsChart instanceof Chart) {
        weightsChart.destroy();
    }

    // Create new chart
    weightsChart = new Chart(document.getElementById('weightsChart').getContext('2d'), {
        type: 'pie',
        data: {
            labels: weightLabels,
            datasets: [{
                data: weightValues,
                backgroundColor: [
                    'rgba(255, 99, 132, 0.7)',
                    'rgba(54, 162, 235, 0.7)',
                    'rgba(255, 206, 86, 0.7)',
                    'rgba(75, 192, 192, 0.7)',
                    'rgba(153, 102, 255, 0.7)',
                    'rgba(255, 159, 64, 0.7)',
                    'rgba(199, 199, 199, 0.7)',
                    'rgba(83, 102, 255, 0.7)',
                    'rgba(40, 159, 64, 0.7)',
                    'rgba(210, 99, 132, 0.7)'
                ],
                borderColor: [
                    'rgba(255, 99, 132, 1)',
                    'rgba(54, 162, 235, 1)',
                    'rgba(255, 206, 86, 1)',
                    'rgba(75, 192, 192, 1)',
                    'rgba(153, 102, 255, 1)',
                    'rgba(255, 159, 64, 1)',
                    'rgba(199, 199, 199, 1)',
                    'rgba(83, 102, 255, 1)',
                    'rgba(40, 159, 64, 1)',
                    'rgba(210, 99, 132, 1)'
                ],
                borderWidth: 1
            }]
        },
        options: {
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.raw || 0;
                            const percentage = Math.round(value * 100);
                            return `${label}: ${percentage}%`;
                        }
                    }
                }
            }
        }
    });
    
    // Create neural network visualization
    createNeuralNetworkVisualization(breakdown.neural_network);
    
    // Hide spinner and show content
    document.getElementById('mlScoringSpinner').style.display = 'none';
    document.getElementById('mlScoringContent').style.display = 'block';
}

// Create neural network visualization
function createNeuralNetworkVisualization(networkData) {
    try {
        // Clear previous visualization
        const container = document.getElementById('neuralNetworkViz');
        if (!container) {
            console.error('Could not find neuralNetworkViz element');
            return;
        }
        
        container.innerHTML = '';
        
        // Set dimensions
        const width = container.clientWidth || 600;
        const height = container.clientHeight || 400;
        const margin = { top: 20, right: 20, bottom: 20, left: 20 };
        
        // Create SVG
        const svg = d3.select(container)
            .append('svg')
            .attr('width', width)
            .attr('height', height);
        
        // Calculate layer positions
        const layerWidth = (width - margin.left - margin.right) / networkData.length;
        
        // Define colors for different layers
        const layerColors = {
            'input': '#3498db',
            'scoring': '#2ecc71',
            'weighting': '#e74c3c',
            'output': '#f39c12'
        };
        
        // Create groups for each layer
        networkData.forEach((layer, layerIndex) => {
            const layerGroup = svg.append('g')
                .attr('transform', `translate(${margin.left + layerIndex * layerWidth}, 0)`);
            
            // Calculate node positions
            const nodeCount = layer.nodes.length;
            const nodeSpacing = (height - margin.top - margin.bottom) / (nodeCount + 1);
            
            // Add layer label
            layerGroup.append('text')
                .attr('x', layerWidth / 2)
                .attr('y', margin.top / 2)
                .attr('text-anchor', 'middle')
                .attr('dominant-baseline', 'middle')
                .style('font-weight', 'bold')
                .text(layer.name.charAt(0).toUpperCase() + layer.name.slice(1));
            
            // Add nodes
            layer.nodes.forEach((node, nodeIndex) => {
                const nodeY = margin.top + (nodeIndex + 1) * nodeSpacing;
                
                // Add node circle
                layerGroup.append('circle')
                    .attr('cx', layerWidth / 2)
                    .attr('cy', nodeY)
                    .attr('r', 15)
                    .attr('fill', layerColors[layer.name] || '#9b59b6')
                    .attr('stroke', '#333')
                    .attr('stroke-width', 1);
                
                // Add node label
                layerGroup.append('text')
                    .attr('x', layerWidth / 2)
                    .attr('y', nodeY)
                    .attr('text-anchor', 'middle')
                    .attr('dominant-baseline', 'middle')
                    .style('font-size', '10px')
                    .style('fill', 'white')
                    .text(node.name.substring(0, 3));
                
                // Add node value
                layerGroup.append('text')
                    .attr('x', layerWidth / 2)
                    .attr('y', nodeY + 25)
                    .attr('text-anchor', 'middle')
                    .attr('dominant-baseline', 'middle')
                    .style('font-size', '10px')
                    .text(typeof node.value === 'number' ? node.value.toFixed(2) : node.value);
                
                // Add connections to next layer
                if (layerIndex < networkData.length - 1) {
                    const nextLayer = networkData[layerIndex + 1];
                    nextLayer.nodes.forEach((nextNode, nextNodeIndex) => {
                        const nextNodeY = margin.top + (nextNodeIndex + 1) * ((height - margin.top - margin.bottom) / (nextLayer.nodes.length + 1));
                        
                        // Draw connection line
                        svg.append('line')
                            .attr('x1', margin.left + layerIndex * layerWidth + layerWidth / 2 + 15)
                            .attr('y1', nodeY)
                            .attr('x2', margin.left + (layerIndex + 1) * layerWidth + layerWidth / 2 - 15)
                            .attr('y2', nextNodeY)
                            .attr('stroke', '#aaa')
                            .attr('stroke-width', 1)
                            .attr('stroke-opacity', 0.5);
                    });
                }
            });
        });
    } catch (error) {
        console.error('Error creating neural network visualization:', error);
        const container = document.getElementById('neuralNetworkViz');
        if (container) {
            container.innerHTML = '<div class="alert alert-danger">Error creating visualization</div>';
        }
    }
}

// After successful deployment, update UI with deployment details and JSON download option
function updateDeploymentSuccess(deploymentData) {
    const deploymentDetailsEl = document.getElementById('deploymentDetails');
    if (!deploymentDetailsEl) return;
    
    // Create a structured JSON for the deployment
    const deploymentJson = {
        "slice_id": deploymentData.slice_id || "s-002-UR-AI",
        "slice_type": selectedSliceType || "URLLC",
        "vendor_id": selectedVendor?.id || "vendor-7",
        "deployment_region": qosRequirements?.location || "New York, USA",
        "session_id": "sess-" + Math.floor(Math.random() * 100000000).toString().padStart(8, '0'),
        
        "amf_ip": "10.20.30.40",
        "smf_ip": "10.20.30.41",
        "upf_ip": "10.20.30.50",
        "dnn": "ai-robotics-net",
        "plmn_id": "310260",
        "authentication_method": "5G-AKA",
        
        "latency_target_ms": parseInt(qosRequirements?.latency) || 5,
        "bandwidth_guaranteed_mbps": parseInt(qosRequirements?.bandwidth) || 50,
        "priority_level": 1,
        "arp": 1,
        "qos_flow_template": {
            "5qi": 82,
            "gbr_ul": "100Mbps",
            "gbr_dl": "100Mbps"
        },
        
        "encryption_required": true,
        "isolation_level": "Level 3",
        "certificate_bundle_url": "https://vendor7.net/certs/bundle.pem",
        "slice_trust_score": 0.95,
        
        "activation_time_utc": new Date().toISOString(),
        "lease_duration_minutes": 120,
        "renewable": true
    };
    
    // Format the JSON for display
    const formattedJson = JSON.stringify(deploymentJson, null, 2);
    
    // Create the download button and JSON display
    const jsonSection = `
        <div class="card mt-4">
            <div class="card-header bg-dark text-white">
                <div class="d-flex justify-content-between align-items-center">
                    <h5 class="mb-0">Deployment Configuration</h5>
                    <button class="btn btn-sm btn-light" id="downloadJsonBtn">
                        <i class="bi bi-download"></i> Download JSON
                    </button>
                </div>
            </div>
            <div class="card-body">
                <pre class="bg-light p-3 border rounded" style="max-height: 400px; overflow-y: auto;"><code>${formattedJson}</code></pre>
            </div>
        </div>
    `;
    
    // Append the JSON section to the deployment details
    deploymentDetailsEl.insertAdjacentHTML('beforeend', jsonSection);
    
    // Add event listener for the download button
    const downloadBtn = document.getElementById('downloadJsonBtn');
    if (downloadBtn) {
        downloadBtn.addEventListener('click', () => {
            // Create a blob with the JSON data
            const blob = new Blob([formattedJson], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            
            // Create a temporary link and trigger download
            const a = document.createElement('a');
            a.href = url;
            a.download = `slice-deployment-${deploymentJson.slice_id}.json`;
            document.body.appendChild(a);
            a.click();
            
            // Clean up
            setTimeout(() => {
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }, 100);
        });
    }
    
    // Store the deployment JSON in the global state
    deploymentStatus = {
        ...deploymentData,
        configJson: deploymentJson
    };
}

// Update the deploySlice function to call updateDeploymentSuccess
async function deploySlice() {
    try {
        // Move to step 5 first
        currentStep = 5;
        updateProgressBar();
        showCurrentStep();
        
        // Show loading state
        document.getElementById('deploymentSpinner').style.display = 'block';
        document.getElementById('deploymentStatus').textContent = 'Deploying your network slice...';
        document.getElementById('deploymentError').style.display = 'none';
        document.getElementById('deploymentDetails').style.display = 'none';
        
        // Prepare request body
        const requestBody = {
            slice_type: selectedSliceType,
            qos_requirements: qosRequirements,
            vendor_id: selectedVendor.id
        };
        
        console.log("Sending deployment request:", JSON.stringify(requestBody));
        
        let deploymentData;
        try {
            const response = await fetch(`${API_BASE_URL}/slice-selection/deploy`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody)
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error("API Error Response:", response.status, errorText);
                throw new Error(`HTTP error! Status: ${response.status}, Details: ${errorText}`);
            }
            
            deploymentData = await response.json();
            console.log("API Response:", deploymentData);
        } catch (apiError) {
            console.warn("API call failed, using mock data:", apiError);
            // Generate mock deployment data
            deploymentData = {
                slice_id: `slice-${Date.now().toString(36)}`,
                vendor_id: selectedVendor.id,
                vendor_name: selectedVendor.name,
                deployment_time: new Date().toISOString(),
                status: "Deployed Successfully"
            };
        }
        
        // Update UI with deployment details
        document.getElementById('deploymentSpinner').style.display = 'none';
        document.getElementById('deploymentDetails').style.display = 'block';
        
        // Show deployment details
        document.getElementById('deployedSliceId').textContent = deploymentData.slice_id;
        document.getElementById('deployedVendor').textContent = deploymentData.vendor_name;
        document.getElementById('deploymentTime').textContent = deploymentData.deployment_time;
        
        // Store deployed slice ID for monitoring
        deployedSliceId = deploymentData.slice_id;
        
        // Add the JSON display and download button
        updateDeploymentSuccess(deploymentData);
        
        // Show the monitoring section
        document.getElementById('monitoringSection').style.display = 'block';
        
        // Start monitoring
        startMonitoring(deploymentData.slice_id);
        
    } catch (error) {
        console.error('Error deploying slice:', error);
        document.getElementById('deploymentSpinner').style.display = 'none';
        document.getElementById('deploymentError').style.display = 'block';
        document.getElementById('deploymentError').textContent = `Error: ${error.message}`;
    }
}

// Start monitoring the slice with Gemini API
function startMonitoring(sliceId) {
    // Create monitoring section if it doesn't exist
    if (!document.getElementById('monitoringSection')) {
        console.error("Monitoring section not found in DOM");
        return;
    }
    
    // Check if the monitoring content already exists
    if (!document.getElementById('monitoringContent')) {
        const monitoringSection = document.getElementById('monitoringSection');
        monitoringSection.innerHTML = `
            <div class="card dashboard-card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <span>Slice Monitoring (Powered by Gemini AI & Context7)</span>
                    <div>
                        <button class="btn btn-sm btn-primary" id="refreshMonitoringBtn">
                            <i class="bi bi-arrow-clockwise"></i> Refresh
                        </button>
                    </div>
                </div>
                <div class="card-body">
                    <div id="monitoringSpinner" class="text-center">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p class="mt-2">Loading monitoring data...</p>
                    </div>
                    <div id="monitoringContent" style="display: none;">
                        <div class="row">
                            <div class="col-md-6">
                                <h5>QoS Metrics</h5>
                                <ul class="list-group list-group-flush" id="qosMetricsList">
                                    <!-- QoS metrics will be inserted here -->
                                </ul>
                            </div>
                            <div class="col-md-6">
                                <h5>Health Score</h5>
                                <div class="progress mb-2">
                                    <div class="progress-bar" role="progressbar" id="healthScoreBar" 
                                         style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                                    </div>
                                </div>
                                <p id="healthScoreText">0%</p>
                            </div>
                        </div>
                        <div class="mt-3">
                            <h5>Gemini AI Analysis</h5>
                            <div class="alert alert-info" id="geminiAnalysis">
                                <!-- Gemini analysis will be inserted here -->
                            </div>
                        </div>
                        <div class="mt-3" id="context7Section">
                            <h5>Context7 Insights</h5>
                            <div class="alert alert-primary" id="context7Insights">
                                <!-- Context7 insights will be inserted here -->
                            </div>
                            <div id="bestPractices">
                                <h6>Best Practices</h6>
                                <ul class="list-group" id="bestPracticesList">
                                    <!-- Best practices will be inserted here -->
                                </ul>
                            </div>
                        </div>
                        <div class="mt-3">
                            <button class="btn btn-outline-primary" id="optimizeBtn">
                                Get Optimization Recommendations
                            </button>
                        </div>
                        <div class="mt-3" id="optimizationSection" style="display: none;">
                            <h5>Optimization Recommendations</h5>
                            <div class="alert alert-success" id="optimizationRecommendations">
                                <!-- Optimization recommendations will be inserted here -->
                            </div>
                            <div id="context7Guidance" class="mt-3">
                                <h6>Context7 Guidance</h6>
                                <div class="alert alert-light" id="context7GuidanceContent">
                                    <!-- Context7 guidance will be inserted here -->
                                </div>
                            </div>
                        </div>
                    </div>
                    <div id="monitoringError" class="alert alert-danger mt-4" style="display: none;">
                        Error loading monitoring data
                    </div>
                </div>
            </div>
        `;
        
        // Add event listener for refresh button
        const refreshBtn = document.getElementById('refreshMonitoringBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                fetchMonitoringData(sliceId);
            });
        }
        
        // Add event listener for optimize button
        const optimizeBtn = document.getElementById('optimizeBtn');
        if (optimizeBtn) {
            optimizeBtn.addEventListener('click', () => {
                fetchOptimizationRecommendations(sliceId);
            });
        }
    }
    
    // Fetch initial monitoring data
    fetchMonitoringData(sliceId);
    
    // Set up interval to refresh monitoring data every 30 seconds
    if (monitoringInterval) {
        clearInterval(monitoringInterval);
    }
    
    monitoringInterval = setInterval(() => {
        fetchMonitoringData(sliceId);
    }, 30000); // 30 seconds
}

// Generate real-time analysis for monitoring using Gemini API
async function generateGeminiAnalysis(sliceId, sliceType, qosActual, qosPromised, healthScore) {
    if (!geminiApiKey || geminiApiKey === "YOUR_GEMINI_API_KEY") {
        // Don't throw an error, just return null so the caller can fall back to mock data gracefully.
        console.warn("Gemini API key not set or is using the default placeholder. Skipping live analysis.");
        return null; 
    }

    const prompt = `
    As a 5G network monitoring expert, analyze the following network slice metrics and provide a concise analysis.

    Slice Type: ${sliceType}
    Health Score: ${healthScore}%
    
    Current QoS Metrics:
    - Latency: ${qosActual.latency}ms (Target: ${qosPromised.latency}ms)
    - Bandwidth: ${qosActual.bandwidth}Mbps (Target: ${qosPromised.bandwidth}Mbps)
    - Reliability: ${qosActual.reliability}% (Target: ${qosPromised.reliability}%)
    - Packet Loss: ${qosActual.packet_loss}%
    - Jitter: ${qosActual.jitter}ms

    Provide three separate, brief sections:
    1.  **Gemini AI Analysis**: A one-sentence summary of the slice's performance (e.g., Excellent, Good, Needs Attention) followed by a short sentence explaining why, based on the metrics.
    2.  **Context7 Insights**: A one-sentence insight based on industry best practices for this slice type (${sliceType}), comparing its performance to typical deployments.
    3.  **Best Practices**: List exactly 3 brief, actionable best practices relevant to the current performance.
    `;

    try {
        const response = await fetch('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-goog-api-key': geminiApiKey
            },
            body: JSON.stringify({ 
                contents: [{ parts: [{ text: prompt }] }],
                generationConfig: {
                    temperature: 0.2,
                    maxOutputTokens: 1024
                }
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error("Gemini API error response:", errorText);
            throw new Error(`Gemini API error: ${response.status} - ${errorText}`);
        }

        const geminiResponse = await response.json();
        if (!geminiResponse.candidates || !geminiResponse.candidates[0] || !geminiResponse.candidates[0].content || !geminiResponse.candidates[0].content.parts || !geminiResponse.candidates[0].content.parts[0].text) {
            console.error("Unexpected Gemini API response structure:", geminiResponse);
            throw new Error("Unexpected Gemini API response structure");
        }
        
        const generatedText = geminiResponse.candidates[0].content.parts[0].text;
        console.log("Generated analysis text from Gemini:", generatedText);
        
        // Parse the response to extract the sections
        const analysisMatch = generatedText.match(/Gemini AI Analysis:([\s\S]*?)Context7 Insights:/i);
        const insightsMatch = generatedText.match(/Context7 Insights:([\s\S]*?)Best Practices:/i);
        const practicesMatch = generatedText.match(/Best Practices:([\s\S]*)/i);

        const gemini_analysis = analysisMatch ? analysisMatch[1].trim() : "Analysis could not be generated.";
        const context7_insights = insightsMatch ? insightsMatch[1].trim() : "Insights could not be generated.";
        const best_practices = practicesMatch ? practicesMatch[1].trim().split(/\d+\.\s*|\n\s*[-*]\s*/).map(s => s.trim()).filter(Boolean) : [];

        return { gemini_analysis, context7_insights, best_practices };

    } catch (error) {
        console.error("Error calling Gemini API for analysis:", error);
        // Return null to indicate failure, allowing fallback to mock data.
        return null;
    }
}

// Fetch monitoring data for a slice
async function fetchMonitoringData(sliceId) {
    try {
        document.getElementById('monitoringSpinner').style.display = 'block';
        document.getElementById('monitoringContent').style.display = 'none';
        document.getElementById('monitoringError').style.display = 'none';
        
        // Get basic telemetry data first (either from API or mock data)
        let data;
        try {
            const response = await fetch(`${API_BASE_URL}/slice-selection/monitor/${sliceId}?analyze=false`);
            
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            
            data = await response.json();
            console.log("Basic telemetry data from API:", data);
        } catch (apiError) {
            console.warn("API call failed, using mock data for basic telemetry:", apiError);
            // Generate only the basic telemetry data without analysis
            data = {
                telemetry: {
                    slice_id: sliceId,
                    timestamp: new Date().toISOString(),
                    qos_actual: {
                        latency: (Math.random() * 5 + 8).toFixed(2),
                        bandwidth: (Math.random() * 500 + 1200).toFixed(2),
                        reliability: (99.9 + Math.random() * 0.09).toFixed(4),
                        jitter: (Math.random() * 3).toFixed(2),
                        packet_loss: (Math.random() * 0.2).toFixed(4)
                    },
                    qos_promised: {
                        latency: "10.00",
                        bandwidth: "1500.00",
                        reliability: "99.9500",
                        jitter: "2.00",
                        packet_loss: "0.10"
                    }
                },
                analysis: {
                    health_score: Math.round(Math.random() * 20 + 80) // 80-100 range
                }
            };
        }
        
        // Now get the analysis from Gemini API
        try {
            // Only proceed if we have a valid API key
            if (!geminiApiKey || geminiApiKey === "YOUR_GEMINI_API_KEY") {
                throw new Error("Valid Gemini API key required. Please set your API key in Settings.");
            }
            
            const analysisData = await generateGeminiAnalysis(
                sliceId,
                selectedSliceType,
                data.telemetry.qos_actual,
                data.telemetry.qos_promised,
                data.analysis.health_score
            );
            
            if (!analysisData) {
                throw new Error("Failed to generate analysis from Gemini API.");
            }
            
            // Update the data with Gemini analysis
            data.analysis.gemini_analysis = `
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <strong>Gemini AI Analysis</strong>
                    <span class="badge gemini-badge">Powered by Gemini</span>
                </div>
                <p>${analysisData.gemini_analysis}</p>
            `;
            
            // Update Context7 section with "coming soon" message
            data.analysis.context7_insights = `
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <strong>Context7 Insights</strong>
                    <span class="badge context7-badge">Coming Soon</span>
                </div>
                <p>Context7 integration is currently in development. This feature will provide additional insights based on industry best practices.</p>
            `;
            
            data.analysis.best_practices = analysisData.best_practices;
            
        } catch (geminiError) {
            console.error("Gemini API analysis failed:", geminiError);
            
            // Set error messages for analysis sections
            data.analysis.gemini_analysis = `
                <div class="alert alert-warning">
                    <strong>Gemini AI Analysis Unavailable:</strong> ${geminiError.message}
                    <p class="mt-2 mb-0">Please check your API key in <a href="#" data-bs-toggle="modal" data-bs-target="#settingsModal">Settings</a>.</p>
                </div>
            `;
            
            data.analysis.context7_insights = `
                <div class="alert alert-warning">
                    <strong>Context7 Insights Unavailable:</strong> Integration in progress.
                </div>
            `;
            
            data.analysis.best_practices = [];
        }
        
        // Update QoS metrics
        const qosMetricsList = document.getElementById('qosMetricsList');
        qosMetricsList.innerHTML = '';
        
        const qosActual = data.telemetry.qos_actual;
        const qosPromised = data.telemetry.qos_promised;
        
        for (const [key, value] of Object.entries(qosActual)) {
            const promisedValue = qosPromised[key] || 'N/A';
            const listItem = document.createElement('li');
            listItem.className = 'list-group-item d-flex justify-content-between align-items-center';
            
            // Format the metric name for display
            let metricName = key.charAt(0).toUpperCase() + key.slice(1);
            let unit = '';
            
            // Add units based on the metric
            if (key === 'latency' || key === 'jitter') {
                unit = 'ms';
            } else if (key === 'bandwidth') {
                unit = 'Mbps';
            } else if (key === 'reliability' || key === 'packet_loss') {
                unit = '%';
            }
            
            // Create the metric display with comparison to promised value
            const actualValueDisplay = `${value}${unit}`;
            const promisedValueDisplay = `${promisedValue}${unit}`;
            
            // Determine if the metric is meeting its target
            let badgeClass = 'bg-success';
            if (key === 'latency' || key === 'jitter' || key === 'packet_loss') {
                // For these metrics, lower is better
                if (parseFloat(value) > parseFloat(promisedValue) * 1.1) {
                    badgeClass = 'bg-danger';
                } else if (parseFloat(value) > parseFloat(promisedValue)) {
                    badgeClass = 'bg-warning';
                }
            } else {
                // For bandwidth and reliability, higher is better
                if (parseFloat(value) < parseFloat(promisedValue) * 0.9) {
                    badgeClass = 'bg-danger';
                } else if (parseFloat(value) < parseFloat(promisedValue)) {
                    badgeClass = 'bg-warning';
                }
            }
            
            listItem.innerHTML = `
                <div>
                    <span>${metricName}</span>
                    <small class="text-muted ms-2">(Target: ${promisedValueDisplay})</small>
                </div>
                <span class="badge ${badgeClass}">${actualValueDisplay}</span>
            `;
            
            qosMetricsList.appendChild(listItem);
        }
        
        // Update health score
        const healthScore = data.analysis.health_score;
        const healthScoreBar = document.getElementById('healthScoreBar');
        const healthScoreText = document.getElementById('healthScoreText');
        
        healthScoreBar.style.width = `${healthScore}%`;
        healthScoreText.textContent = `${healthScore}%`;
        
        // Set color based on health score
        if (healthScore >= 80) {
            healthScoreBar.className = 'progress-bar bg-success';
        } else if (healthScore >= 60) {
            healthScoreBar.className = 'progress-bar bg-warning';
        } else {
            healthScoreBar.className = 'progress-bar bg-danger';
        }
        
        // Update Gemini analysis
        if (data.analysis && data.analysis.gemini_analysis) {
            document.getElementById('geminiAnalysis').innerHTML = data.analysis.gemini_analysis;
        } else {
            document.getElementById('geminiAnalysis').innerHTML = `
                <div class="alert alert-warning">
                    <strong>Gemini AI Analysis Unavailable</strong>
                    <p class="mb-0">Please check your API key in <a href="#" data-bs-toggle="modal" data-bs-target="#settingsModal">Settings</a>.</p>
                </div>
            `;
        }
        
        // Update Context7 insights
        if (data.analysis && data.analysis.context7_insights) {
            document.getElementById('context7Insights').innerHTML = data.analysis.context7_insights;
            
            // Update best practices
            const bestPracticesList = document.getElementById('bestPracticesList');
            bestPracticesList.innerHTML = '';
            
            if (data.analysis.best_practices && data.analysis.best_practices.length > 0) {
                data.analysis.best_practices.forEach(practice => {
                    const listItem = document.createElement('li');
                    listItem.className = 'list-group-item';
                    listItem.innerHTML = `<i class="bi bi-check-circle-fill text-success me-2"></i> ${practice}`;
                    bestPracticesList.appendChild(listItem);
                });
                document.getElementById('bestPractices').style.display = 'block';
            } else {
                document.getElementById('bestPractices').style.display = 'none';
            }
        } else {
            document.getElementById('context7Insights').innerHTML = `
                <div class="alert alert-warning">
                    <strong>Context7 Insights Unavailable</strong>
                    <p class="mb-0">Please check your API key in <a href="#" data-bs-toggle="modal" data-bs-target="#settingsModal">Settings</a>.</p>
                </div>
            `;
            document.getElementById('bestPractices').style.display = 'none';
        }
        
        // Show monitoring content
        document.getElementById('monitoringSpinner').style.display = 'none';
        document.getElementById('monitoringContent').style.display = 'block';
        
        // Store the data for other functions to use
        lastMonitoringData = data;

    } catch (error) {
        console.error('Error fetching monitoring data:', error);
        document.getElementById('monitoringSpinner').style.display = 'none';
        document.getElementById('monitoringError').style.display = 'block';
        document.getElementById('monitoringError').textContent = `Error: ${error.message}`;
    }
}

// Generate recommendations using Gemini API based on actual monitoring data
async function generateGeminiRecommendations(sliceId, sliceType, qosActual, qosPromised, healthScore) {
    if (!geminiApiKey || geminiApiKey === "YOUR_GEMINI_API_KEY") {
        const errorMessage = `
            <div class="alert alert-warning">
                <strong>Missing API Key:</strong> Please set your Gemini API key in the 
                <a href="#" class="alert-link" data-bs-toggle="modal" data-bs-target="#settingsModal">Settings</a> 
                to get real-time AI-powered recommendations.
            </div>
        `;
        document.getElementById('optimizationRecommendations').innerHTML = errorMessage;
        throw new Error("Gemini API key not set or is using the default placeholder.");
    }

    console.log("Generating recommendations using Gemini API");
    
    // Create a prompt for Gemini API with the actual monitoring values
    const prompt = `
    As a 5G network optimization expert, analyze the following network slice metrics and provide specific optimization recommendations:
    
    Slice Type: ${sliceType}
    Slice ID: ${sliceId}
    Health Score: ${healthScore}%
    
    Current QoS Metrics:
    - Latency: ${qosActual.latency}ms (Target: ${qosPromised.latency}ms)
    - Bandwidth: ${qosActual.bandwidth}Mbps (Target: ${qosPromised.bandwidth}Mbps)
    - Reliability: ${qosActual.reliability}% (Target: ${qosPromised.reliability}%)
    - Packet Loss: ${qosActual.packet_loss}%
    - Jitter: ${qosActual.jitter}ms
    
    Based on these actual values compared to the promised targets, provide:
    1. 4-5 specific optimization recommendations with technical details and expected improvements
    2. General guidance for optimizing this type of slice (${sliceType})
    3. 4 best practices for this slice type
    4. 3 technical references or standards relevant to these optimizations
    
    Format the recommendations in a clear, actionable way with percentage improvements and specific technical parameters where possible.
    `;
    
    try {
        // Use a try-catch block to handle any API errors
        console.log("Sending request to Gemini API with prompt:", prompt);
        
        // Add a loading indicator to the UI
        document.getElementById('optimizationRecommendations').innerHTML = '<div class="text-center"><div class="spinner-border text-success" role="status"></div><p class="mt-2">Generating recommendations with Gemini AI...</p></div>';
        
        // Make request to Gemini API
        const response = await fetch('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-goog-api-key': geminiApiKey
            },
            body: JSON.stringify({
                contents: [{
                    parts: [{
                        text: prompt
                    }]
                }],
                generationConfig: {
                    temperature: 0.2,
                    maxOutputTokens: 1024
                }
            })
        });
        
        // Check if the response is OK
        if (!response.ok) {
            const errorText = await response.text();
            console.error("Gemini API error response:", errorText);
            throw new Error(`Gemini API error: ${response.status} - ${errorText}`);
        }
        
        // Parse the response
        const geminiResponse = await response.json();
        console.log("Gemini API response:", geminiResponse);
        
        // Check if the response has the expected structure
        if (!geminiResponse.candidates || !geminiResponse.candidates[0] || !geminiResponse.candidates[0].content || !geminiResponse.candidates[0].content.parts || !geminiResponse.candidates[0].content.parts[0].text) {
            console.error("Unexpected Gemini API response structure:", geminiResponse);
            throw new Error("Unexpected Gemini API response structure");
        }
        
        // Extract the generated text
        const generatedText = geminiResponse.candidates[0].content.parts[0].text;
        console.log("Generated text from Gemini:", generatedText);
        
        // Parse the response into our expected format
        const sections = parseGeminiResponse(generatedText, sliceType);
        
        // Add badges to show this is from Gemini and Context7
        const recommendations = `
            <div class="d-flex justify-content-between align-items-center mb-3">
                <strong>Optimization Recommendations</strong>
                <div>
                    <span class="badge gemini-badge me-2">Powered by Gemini</span>
                    <span class="badge context7-badge">Context7 Coming Soon</span>
                </div>
            </div>
            <div class="recommendations-content">
                ${sections.recommendations.replace(/\n/g, '<br>')}
            </div>
        `;
        
        return {
            recommendations: {
                slice_id: sliceId,
                timestamp: new Date().toISOString(),
                recommendations: recommendations
            },
            context7_guidance: {
                guidance: sections.guidance,
                best_practices: sections.bestPractices,
                references: sections.references
            }
        };
    } catch (error) {
        console.error("Error calling Gemini API:", error);
        
        // Show error in the UI
        document.getElementById('optimizationRecommendations').innerHTML = `
            <div class="alert alert-warning">
                <strong>Gemini API Error:</strong> ${error.message}<br>
                Please check your API key in the Settings.
            </div>
        `;
        
        // Throw the error to be caught by the caller
        throw error;
    }
}

// Parse the Gemini API response into structured sections
function parseGeminiResponse(text, sliceType) {
    console.log("Parsing Gemini response for slice type:", sliceType);
    
    // Default sections in case parsing fails
    let result = {
        recommendations: `Based on the analysis of your ${sliceType} slice performance, here are optimization recommendations:\n\n${text}`,
        guidance: "Context7 integration coming soon. This feature is yet to be implemented.",
        bestPractices: ["Context7 integration is coming soon"],
        references: ["Context7 documentation will be available once integration is complete"]
    };
    
    try {
        // Try to extract recommendations section (everything before "General guidance" or "Guidance")
        const recommendationsMatch = text.match(/(?:recommendations:|recommendations\s*\n|recommendations\s*\r\n)([\s\S]*?)(?:general guidance|guidance|best practices|$)/i);
        if (recommendationsMatch && recommendationsMatch[1]) {
            result.recommendations = recommendationsMatch[1].trim();
        }
        
        // Try to extract guidance section
        const guidanceMatch = text.match(/(?:general guidance|guidance)(?::|for\s*\w+\s*:)([\s\S]*?)(?:best practices|$)/i);
        if (guidanceMatch && guidanceMatch[1]) {
            result.guidance = guidanceMatch[1].trim();
        }
        
        // Try to extract best practices
        const bestPracticesMatch = text.match(/best practices(?::|for\s*\w+\s*:)([\s\S]*?)(?:references|technical references|$)/i);
        if (bestPracticesMatch && bestPracticesMatch[1]) {
            const practicesText = bestPracticesMatch[1].trim();
            // Split by numbered items or bullet points
            result.bestPractices = practicesText.split(/\d+\.\s*|\n\s*[-*]\s*|\r\n\s*[-*]\s*|\n\n|\r\n\r\n/)
                .map(item => item.trim())
                .filter(item => item.length > 0);
        }
        
        // Try to extract references
        const referencesMatch = text.match(/(?:references|technical references)(?::|for\s*\w+\s*:)([\s\S]*?)$/i);
        if (referencesMatch && referencesMatch[1]) {
            const referencesText = referencesMatch[1].trim();
            // Split by numbered items or bullet points
            result.references = referencesText.split(/\d+\.\s*|\n\s*[-*]\s*|\r\n\s*[-*]\s*|\n\n|\r\n\r\n/)
                .map(item => item.trim())
                .filter(item => item.length > 0);
        }
        
        console.log("Parsed Gemini response:", result);
    } catch (error) {
        console.warn("Error parsing Gemini response:", error);
    }
    
    return result;
}

// Fetch optimization recommendations for a slice
async function fetchOptimizationRecommendations(sliceId) {
    try {
        // Show loading state
        document.getElementById('optimizeBtn').disabled = true;
        document.getElementById('optimizeBtn').innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Loading...';
        
        // Ensure we have monitoring data to work with from the last refresh
        if (!lastMonitoringData) {
            throw new Error("No monitoring data available. Please refresh the monitoring panel first.");
        }

        // Get the current metrics from the stored data that is visible on screen
        const qosActual = lastMonitoringData.telemetry.qos_actual;
        const qosPromised = lastMonitoringData.telemetry.qos_promised;
        const healthScore = lastMonitoringData.analysis.health_score;
        
        // Only proceed if we have a valid API key
        if (!geminiApiKey || geminiApiKey === "YOUR_GEMINI_API_KEY") {
            throw new Error("Valid Gemini API key required. Please set your API key in Settings.");
        }
        
        // Get recommendations from Gemini API
        const data = await generateGeminiRecommendations(sliceId, selectedSliceType, qosActual, qosPromised, healthScore);
        console.log("Generated recommendations using Gemini API:", data);
        
        // Update optimization recommendations
        if (data.recommendations && data.recommendations.recommendations) {
            document.getElementById('optimizationRecommendations').innerHTML = data.recommendations.recommendations;
        } else {
            document.getElementById('optimizationRecommendations').textContent = 'No recommendations available';
        }
        
        // Update Context7 guidance
        if (data.context7_guidance) {
            let guidanceContent = `
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <strong>Context7 Guidance</strong>
                    <span class="badge context7-badge">Coming Soon</span>
                </div>
                <p>Context7 integration is currently in development. This feature will provide additional guidance, best practices, and technical references based on industry standards.</p>
            `;
            
            document.getElementById('context7GuidanceContent').innerHTML = guidanceContent;
        } else {
            document.getElementById('context7GuidanceContent').textContent = 'Context7 integration coming soon';
        }
        
        // Show optimization section
        document.getElementById('optimizationSection').style.display = 'block';
        
        // Reset button state
        document.getElementById('optimizeBtn').disabled = false;
        document.getElementById('optimizeBtn').innerHTML = 'Get Optimization Recommendations';
        
    } catch (error) {
        console.error('Error fetching optimization recommendations:', error);
        
        // Show error in the UI
        document.getElementById('optimizationRecommendations').innerHTML = `
            <div class="alert alert-danger">
                <strong>Error:</strong> ${error.message}
                <p class="mt-2 mb-0">Please check your API key in <a href="#" data-bs-toggle="modal" data-bs-target="#settingsModal">Settings</a>.</p>
            </div>
        `;
        
        // Reset button state
        document.getElementById('optimizeBtn').disabled = false;
        document.getElementById('optimizeBtn').innerHTML = 'Get Optimization Recommendations';
    }
} 