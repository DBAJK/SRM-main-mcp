# ML Model Input Features for 5G Network Slice Allocation

The LSTM model for network slice allocation uses a sequence of feature vectors as input. Each feature vector contains 11 elements representing the current network state and conditions. Below is a detailed explanation of each feature:

## Feature Vector Structure

The feature vector consists of the following elements:

```
[traffic_load, time_of_day, day_of_week, embb_alloc, urllc_alloc, mmtc_alloc, embb_util, urllc_util, mmtc_util, client_count, bs_count]
```

## Feature Descriptions

### 1. Traffic Load
- **Description**: Aggregate network traffic load normalized to a 0-2 range
- **Calculation**: Sum of traffic across all slices divided by 3
- **Range**: 0.0 to 2.0
- **Significance**: Indicates overall network congestion level

### 2. Time of Day
- **Description**: Current hour normalized to a 0-1 range
- **Calculation**: `hour_of_day / 24.0`
- **Range**: 0.0 to 1.0
- **Significance**: Captures daily traffic patterns (e.g., peak hours vs. night hours)

### 3. Day of Week
- **Description**: Current day of week normalized to a 0-1 range
- **Calculation**: `day_of_week / 6.0`
- **Range**: 0.0 to 1.0
- **Significance**: Captures weekly traffic patterns (e.g., weekday vs. weekend)

### 4-6. Slice Allocations
- **Description**: Current resource allocation for each slice type
- **Elements**:
  - `embb_alloc`: Enhanced Mobile Broadband allocation
  - `urllc_alloc`: Ultra-Reliable Low-Latency Communications allocation
  - `mmtc_alloc`: Massive Machine Type Communications allocation
- **Range**: 0.1 to 0.8 (normalized to sum to 1.0)
- **Significance**: Current resource distribution across slices

### 7-9. Slice Utilizations
- **Description**: Current utilization level for each slice type
- **Elements**:
  - `embb_util`: eMBB utilization (traffic / allocation)
  - `urllc_util`: URLLC utilization (traffic / allocation)
  - `mmtc_util`: mMTC utilization (traffic / allocation)
- **Range**: 0.0 to 2.0+
- **Significance**: Indicates how efficiently each slice is using its allocated resources
- **Note**: Values > 1.0 indicate over-utilization (potential QoS violations)

### 10. Client Count
- **Description**: Normalized number of connected clients
- **Calculation**: Simulated based on time of day with random variation
- **Range**: 0.0 to 1.0
- **Significance**: Represents user load on the network

### 11. Base Station Count
- **Description**: Normalized number of active base stations
- **Calculation**: Simulated with random variation
- **Range**: 0.0 to 1.0
- **Significance**: Represents infrastructure capacity

## Sequence Input

The LSTM model takes a sequence of these feature vectors as input:
- **Sequence Length**: 10 time steps
- **Shape**: (10, 11) - 10 time steps with 11 features each

## Output

The model outputs a 3-element vector representing the optimal resource allocation:
```
[embb_allocation, urllc_allocation, mmtc_allocation]
```

These values are normalized to sum to 1.0, representing the proportion of resources that should be allocated to each slice type.

## Training Data Generation

The training data for the model is generated synthetically to cover various network scenarios:
- Normal daily/weekly patterns
- Emergency situations (high URLLC traffic)
- Special events (high eMBB traffic)
- IoT surges (high mMTC traffic)
- Mixed scenarios

This ensures the model can handle a wide range of network conditions and make appropriate allocation decisions. 