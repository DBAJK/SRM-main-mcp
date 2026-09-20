# 5G Network Slice Marketplace

A platform for dynamic 5G network slice selection and vendor negotiation using AI agents.

## Overview

The 5G Network Slice Marketplace is a comprehensive platform that enables customers to request and deploy network slices from multiple vendors based on their specific QoS requirements. The platform uses AI agents to classify slice types, select optimal vendors, and continuously monitor slice performance.

## Architecture

The platform follows a modular architecture with the following key components:

- **Customer API**: Handles customer slice requests and management
- **Vendor API**: Manages vendor registration and slice offerings
- **Vendor Registry**: Maintains information about vendors and their offerings
- **AI Agent**: Classifies slice types and scores vendor offerings using pre-trained models
- **Slice Selection Engine**: Selects optimal vendor slices based on requirements
- **Network Digital Twin**: Simulates and validates slice performance
- **Compliance Monitor**: Monitors slice compliance with SLAs and detects violations
- **Feedback Loop**: Learns from slice performance data to improve future decisions
- **Dashboard API**: Provides system metrics and analytics for the platform

## Core Components

### Customer API

The Customer API allows customers to:
- Submit slice requests with specific QoS requirements
- Check the status of slice requests
- View details of deployed slices
- Terminate slices when no longer needed

### Vendor API

The Vendor API enables vendors to:
- Register with the marketplace
- Update their slice capabilities
- Create and manage slice offerings
- Deploy slices when selected by customers

### Vendor Registry

The Vendor Registry maintains:
- Vendor information and credentials
- Vendor slice capabilities
- Slice offerings from vendors

### AI Agent

The AI Agent provides:
- Slice type classification (eMBB, URLLC, mMTC) using a pre-trained DQN model
- Vendor offer scoring based on QoS requirements
- Integration with LLMs for advanced reasoning
- Resource allocation prediction using a pre-trained LSTM model

The AI agent uses pre-trained models from the 5G-Network-Slicing project:
- DQN Traffic Classifier: Classifies network traffic to determine optimal slice types
- LSTM Slice Allocation Predictor: Predicts optimal resource allocation across slice types

### Slice Selection Engine

The Slice Selection Engine:
- Classifies slice requests using the AI agent
- Queries vendors for matching offerings
- Selects the best offer based on customer preferences
- Deploys slices with selected vendors

### Network Digital Twin

The Network Digital Twin:
- Simulates network slice behavior
- Validates slice performance against promised QoS
- Provides telemetry data for active slices

### Compliance Monitor

The Compliance Monitor:
- Continuously monitors slice compliance with SLAs
- Detects QoS violations in real-time
- Triggers actions when violations occur
- Provides violation data to the feedback loop

### Feedback Loop

The Feedback Loop:
- Collects performance data from slices
- Updates vendor ratings based on performance
- Improves AI agent decision-making over time
- Provides insights for future slice selection

### Dashboard API

The Dashboard API provides:
- System-wide metrics and analytics
- Active slice information
- Vendor performance metrics
- QoS violation reports
- System health status

## Setup Instructions

### Prerequisites

- Python 3.8+
- FastAPI
- Uvicorn
- TensorFlow 2.15.0+
- Other dependencies in requirements.txt

### Installation

1. Clone the repository:
```
git clone https://github.com/yourusername/5G-Marketplace.git
cd 5G-Marketplace
```

2. Install dependencies:
```
pip install -r requirements.txt
```

3. Start the application:
```
python run.py --init-data
```

The API will be available at http://localhost:8000

## Using Pre-trained Models

The platform uses pre-trained models from the 5G-Network-Slicing project. These models are located in:
- DQN Traffic Classifier: `5G-Network-Slicing/models/dqn_model_20250601_012010`
- LSTM Slice Allocation Predictor: `5G-Network-Slicing/models/lstm_model_20250601_011235`

To use these models, ensure the 5G-Network-Slicing project is available at the same directory level as the 5G-Marketplace project, or update the model paths in `src/ai_agent/agent.py`.

## API Documentation

Once the application is running, you can access the API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Testing

Run the test suite:
```
pytest
```

## License

This project is licensed under the MIT License - see the LICENSE file for details. 