# Open5GS Integration for AI-Native Network Slicing

This document provides instructions for integrating the AI-based network slicing solution with Open5GS for real-world testing and validation.

## Overview

The integration allows you to deploy and test the AI-based network slicing solution in a real 5G environment using Open5GS, an open-source implementation of 5G core network functions. The AI components (LSTM predictor and DQN classifier) are used to optimize network slice allocation and traffic classification in real-time.

## Prerequisites

- Open5GS installed and configured
- Python 3.8 or higher
- Required Python packages (see `requirements.txt`)
- Network access to the Open5GS API endpoint

## Installation

1. Install Open5GS by following the instructions at [https://open5gs.org/open5gs/docs/guide/01-quickstart/](https://open5gs.org/open5gs/docs/guide/01-quickstart/)

2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure the Open5GS integration by modifying the `open5gs_config.json` file:
   ```json
   {
     "open5gs_api_url": "http://localhost:3000/api",
     "api_token": "your_api_token_if_required"
   }
   ```

## Usage

### Running the Integration Demo

The integration demo script (`open5gs_ai_demo.py`) showcases the integration between the AI-based network slicing solution and Open5GS. It creates network slices, collects metrics, runs AI optimization, and visualizes the results.

```bash
python open5gs_ai_demo.py --config open5gs_config.json --duration 300 --interval 10
```

Options:
- `--config`: Path to the configuration file (default: `open5gs_config.json`)
- `--duration`: Duration for tests in seconds (default: 300)
- `--interval`: Interval between metric collections in seconds (default: 10)
- `--compare`: Run comparison between AI and non-AI optimization
- `--output-dir`: Directory to save results (default: `results`)

### Comparing AI vs. Non-AI Performance

To compare the performance of the network with and without AI optimization:

```bash
python open5gs_ai_demo.py --compare --duration 600
```

This will run two tests:
1. Without AI optimization
2. With AI optimization

The results will be visualized and saved to the output directory.

### Using the Open5GS Adapter in Your Code

You can use the `Open5GSAdapter` class in your own code to integrate with Open5GS:

```python
from open5gs_integration import Open5GSAdapter

# Initialize the adapter
adapter = Open5GSAdapter(config_file='open5gs_config.json')

# Create network slices
embb_slice_id = adapter.create_network_slice('embb')
urllc_slice_id = adapter.create_network_slice('urllc')
mmtc_slice_id = adapter.create_network_slice('mmtc')

# Start monitoring and optimization
adapter.start_monitoring()

# Stop monitoring when done
adapter.stop_monitoring()
```

## Architecture

The integration consists of the following components:

1. **Open5GS Adapter**: Interfaces between the AI-based network slicing solution and Open5GS. It handles communication with the Open5GS API, creates and manages network slices, and collects metrics.

2. **AI Components**:
   - **LSTM Predictor**: Predicts optimal resource allocation for network slices based on historical data.
   - **DQN Classifier**: Classifies traffic and assigns it to the appropriate network slice.

3. **Slice Optimizer**: Uses the AI components to optimize network slice allocation and traffic classification.

4. **Monitoring Thread**: Continuously monitors network metrics and applies AI-based optimization.

## Network Slice Types

The integration supports three types of network slices:

1. **eMBB (Enhanced Mobile Broadband)**:
   - High data rates
   - High bandwidth
   - Used for video streaming, web browsing, etc.

2. **URLLC (Ultra-Reliable Low-Latency Communication)**:
   - Low latency
   - High reliability
   - Used for autonomous vehicles, industrial automation, etc.

3. **mMTC (Massive Machine-Type Communication)**:
   - Large number of devices
   - Low data rates
   - Used for IoT devices, sensors, etc.

## Metrics

The integration collects and visualizes the following metrics:

- **Throughput**: Data transfer rate in bits per second
- **Latency**: End-to-end delay in milliseconds
- **Packet Loss**: Percentage of packets lost
- **Resource Usage**: Percentage of allocated resources used
- **Connected Users**: Number of connected users/devices

## Troubleshooting

### Open5GS Connection Issues

If you encounter connection issues with Open5GS:

1. Ensure Open5GS is running:
   ```bash
   systemctl status open5gs-*
   ```

2. Check the API endpoint is accessible:
   ```bash
   curl http://localhost:3000/api/health
   ```

3. Verify firewall settings allow connections to the API endpoint.

### API Authentication Issues

If you encounter authentication issues:

1. Ensure the API token in the configuration file is correct.
2. Check Open5GS logs for authentication errors:
   ```bash
   journalctl -u open5gs-webui
   ```

## Contributing

Contributions to improve the Open5GS integration are welcome. Please follow these steps:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is licensed under the same license as the main project.