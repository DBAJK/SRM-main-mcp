#!/usr/bin/env python3
"""
DQN Training Dataset Generator

This script generates a synthetic dataset for training a DQN model for 5G network slice allocation.
The dataset includes states, actions, rewards, next states, and done flags.
"""

import numpy as np
import pandas as pd
import random
from datetime import datetime

# Define constants
NUM_SAMPLES = 10000
STATE_DIM = 14
ACTION_DIM = 27
OUTPUT_FILE = "dqn_training_data.csv"

def generate_state():
    """Generate a random state vector
    
    State structure:
    - traffic_load: Overall network traffic load [0.1-2.0]
    - time_of_day: Normalized time [0-1]
    - day_of_week: Normalized day [0-1]
    - embb_allocation: Current eMBB allocation [0-1]
    - urllc_allocation: Current URLLC allocation [0-1]
    - mmtc_allocation: Current mMTC allocation [0-1]
    - embb_utilization: Current eMBB utilization [0-2]
    - urllc_utilization: Current URLLC utilization [0-2]
    - mmtc_utilization: Current mMTC utilization [0-2]
    - client_count: Normalized client count [0-1]
    - bs_count: Normalized base station count [0-1]
    - qos_violations: QoS violations [0-3]
    - is_emergency: Emergency flag [0/1]
    - is_special_event: Special event flag [0/1]
    """
    # Generate time-based features
    time_of_day = np.random.uniform(0, 1)
    day_of_week = np.random.uniform(0, 1)
    
    # Generate traffic load based on time of day
    time_factor = 0.3 * np.sin(time_of_day * 2 * np.pi - np.pi/2) + 0.5  # Peak at mid-day
    day_factor = 0.1 * (0.5 - np.abs(day_of_week - 0.5))  # Midweek slightly busier
    base_traffic = 0.3 + time_factor + day_factor
    traffic_load = base_traffic + 0.3 * np.random.randn()
    traffic_load = np.clip(traffic_load, 0.1, 2.0)
    
    # Generate current slice allocations (sum to 1)
    current_allocation = np.random.dirichlet(np.ones(3) * 3)  # Less extreme allocations
    
    # Generate utilization based on allocation and traffic patterns
    # Higher utilization during business hours for eMBB
    embb_util_factor = 1.2 if 0.35 < time_of_day < 0.65 else 0.8
    # Higher utilization for URLLC during business hours
    urllc_util_factor = 1.1 if 0.3 < time_of_day < 0.7 else 0.9
    # Higher utilization for mMTC during night
    mmtc_util_factor = 1.3 if time_of_day < 0.25 or time_of_day > 0.9 else 0.9
    
    # Calculate utilization based on allocation and factors
    embb_util = min(2.0, traffic_load * embb_util_factor / max(0.1, current_allocation[0]))
    urllc_util = min(2.0, traffic_load * urllc_util_factor / max(0.1, current_allocation[1]))
    mmtc_util = min(2.0, traffic_load * mmtc_util_factor / max(0.1, current_allocation[2]))
    
    # Generate client count (correlated with traffic)
    client_count = 0.3 + 0.5 * traffic_load + 0.2 * np.random.random()
    client_count = np.clip(client_count, 0.1, 1.0)
    
    # Generate base station count (partially correlated with client count)
    bs_count = 0.3 + 0.4 * client_count + 0.3 * np.random.random()
    bs_count = np.clip(bs_count, 0.2, 1.0)
    
    # Generate QoS violations (0-3, integer)
    # More likely with high utilization
    max_util = max(embb_util, urllc_util, mmtc_util)
    violation_prob = max(0, (max_util - 1.0) * 0.8)
    qos_violations = np.random.binomial(3, violation_prob)
    
    # Generate special condition flags
    is_emergency = 1 if np.random.random() < 0.05 else 0  # 5% chance of emergency
    is_special_event = 1 if np.random.random() < 0.1 else 0  # 10% chance of special event
    
    # Create state vector
    state = np.array([
        traffic_load,
        time_of_day,
        day_of_week,
        current_allocation[0],  # eMBB
        current_allocation[1],  # URLLC
        current_allocation[2],  # mMTC
        embb_util,
        urllc_util,
        mmtc_util,
        client_count,
        bs_count,
        qos_violations,
        is_emergency,
        is_special_event
    ])
    
    return state

def get_action(state):
    """Get an action based on state
    
    This simulates a policy that:
    1. Allocates more resources to slices with high utilization
    2. Prioritizes URLLC during emergencies
    3. Prioritizes eMBB during special events
    4. Balances resources otherwise
    
    Returns:
        int: Action index (0-26)
    """
    # Extract relevant state components
    embb_util = state[6]
    urllc_util = state[7]
    mmtc_util = state[8]
    qos_violations = state[11]
    is_emergency = state[12]
    is_special_event = state[13]
    
    # Add some randomness to exploration
    if np.random.random() < 0.2:  # 20% random actions
        return np.random.randint(0, ACTION_DIM)
    
    # Handle special cases
    if is_emergency:
        # Prioritize URLLC during emergencies
        urllc_idx = 2  # High allocation
        
        # Determine other allocations based on utilization
        if embb_util > mmtc_util:
            embb_idx = 1  # Medium
            mmtc_idx = 0  # Low
        else:
            embb_idx = 0  # Low
            mmtc_idx = 1  # Medium
            
    elif is_special_event:
        # Prioritize eMBB during special events
        embb_idx = 2  # High allocation
        
        # Determine other allocations based on utilization
        if urllc_util > mmtc_util:
            urllc_idx = 1  # Medium
            mmtc_idx = 0  # Low
        else:
            urllc_idx = 0  # Low
            mmtc_idx = 1  # Medium
    
    else:
        # Normal operation: allocate based on utilization
        utils = [embb_util, urllc_util, mmtc_util]
        
        # Convert utilizations to indices (0=low, 1=medium, 2=high)
        indices = []
        for util in utils:
            if util < 0.7:
                indices.append(0)  # Low allocation
            elif util < 1.3:
                indices.append(1)  # Medium allocation
            else:
                indices.append(2)  # High allocation
        
        embb_idx, urllc_idx, mmtc_idx = indices
        
        # Ensure we're not giving everything low allocation
        if embb_idx == urllc_idx == mmtc_idx == 0:
            # Find highest utilization and give it medium allocation
            max_idx = np.argmax(utils)
            if max_idx == 0:
                embb_idx = 1
            elif max_idx == 1:
                urllc_idx = 1
            else:
                mmtc_idx = 1
    
    # Convert indices to action
    action = embb_idx * 9 + urllc_idx * 3 + mmtc_idx
    return action

def action_to_allocation(action):
    """Convert action to allocation vector
    
    Args:
        action (int): Action index (0-26)
        
    Returns:
        numpy.ndarray: Allocation vector [eMBB, URLLC, mMTC]
    """
    # Convert action to indices
    embb_idx = action // 9
    urllc_idx = (action % 9) // 3
    mmtc_idx = action % 3
    
    # Convert indices to allocation values
    embb_values = [0.2, 0.4, 0.6]
    urllc_values = [0.2, 0.4, 0.6]
    mmtc_values = [0.2, 0.4, 0.6]
    
    allocation = np.array([
        embb_values[embb_idx],
        urllc_values[urllc_idx],
        mmtc_values[mmtc_idx]
    ])
    
    # Normalize to ensure sum = 1
    allocation = allocation / np.sum(allocation)
    
    return allocation

def calculate_reward(state, action):
    """Calculate reward for a state-action pair
    
    Rewards:
    - Positive reward for maintaining utilization within target range (0.7-1.3)
    - Negative reward for QoS violations
    - Bonus for handling special conditions appropriately
    
    Args:
        state: Current state
        action: Action taken
        
    Returns:
        float: Reward value
    """
    # Extract state components
    embb_util = state[6]
    urllc_util = state[7]
    mmtc_util = state[8]
    qos_violations = state[11]
    is_emergency = state[12]
    is_special_event = state[13]
    
    # Get allocation from action
    allocation = action_to_allocation(action)
    embb_alloc, urllc_alloc, mmtc_alloc = allocation
    
    # Calculate new utilization based on allocation
    new_embb_util = embb_util * state[3] / max(0.1, embb_alloc)
    new_urllc_util = urllc_util * state[4] / max(0.1, urllc_alloc)
    new_mmtc_util = mmtc_util * state[5] / max(0.1, mmtc_alloc)
    
    # Base reward starts at 0
    reward = 0.0
    
    # Reward for keeping utilization in target range (0.7-1.3)
    for util in [new_embb_util, new_urllc_util, new_mmtc_util]:
        if 0.7 <= util <= 1.3:
            reward += 1.0
        elif util < 0.5 or util > 1.5:
            reward -= 1.0
        else:
            reward += 0.5
    
    # Penalty for QoS violations
    reward -= qos_violations * 2.0
    
    # Special condition handling
    if is_emergency:
        # During emergency, prioritize URLLC
        if urllc_alloc >= 0.5:
            reward += 3.0
        else:
            reward -= 2.0
    
    if is_special_event:
        # During special events, prioritize eMBB
        if embb_alloc >= 0.5:
            reward += 2.0
        else:
            reward -= 1.0
    
    return reward

def generate_next_state(state, action):
    """Generate next state based on current state and action
    
    Args:
        state: Current state
        action: Action taken
        
    Returns:
        numpy.ndarray: Next state
    """
    # Get allocation from action
    allocation = action_to_allocation(action)
    
    # Create a copy of the current state to modify
    next_state = state.copy()
    
    # Update allocations in next state
    next_state[3:6] = allocation
    
    # Update utilizations based on new allocations
    for i in range(3):
        # Adjust utilization based on allocation change
        old_alloc = state[3+i]
        new_alloc = allocation[i]
        old_util = state[6+i]
        
        # Calculate new utilization
        if new_alloc > 0:
            new_util = old_util * old_alloc / new_alloc
            # Add some random variation
            new_util += np.random.normal(0, 0.1)
            # Clip to valid range
            new_util = np.clip(new_util, 0, 2.0)
            next_state[6+i] = new_util
    
    # Update QoS violations based on utilization
    max_util = max(next_state[6:9])
    violation_prob = max(0, (max_util - 1.0) * 0.8)
    next_state[11] = np.random.binomial(3, violation_prob)
    
    # Special conditions may change
    # 5% chance emergency ends, 2% chance new emergency starts
    if state[12] == 1:
        next_state[12] = 0 if np.random.random() < 0.05 else 1
    else:
        next_state[12] = 1 if np.random.random() < 0.02 else 0
    
    # 10% chance special event ends, 5% chance new event starts
    if state[13] == 1:
        next_state[13] = 0 if np.random.random() < 0.1 else 1
    else:
        next_state[13] = 1 if np.random.random() < 0.05 else 0
    
    return next_state

def is_terminal(state, next_state):
    """Determine if the next state is terminal
    
    In this context, episodes can end when:
    - QoS violations exceed threshold
    - Emergency situation ends
    - Special event ends
    
    Args:
        state: Current state
        next_state: Next state
        
    Returns:
        bool: True if terminal state, False otherwise
    """
    # 5% random chance of episode ending
    if np.random.random() < 0.05:
        return True
    
    # Episode ends if QoS violations are high
    if next_state[11] >= 3:
        return True
    
    # Episode ends if emergency or special event ends
    if state[12] == 1 and next_state[12] == 0:
        return True
    if state[13] == 1 and next_state[13] == 0:
        return True
    
    # Otherwise, not terminal
    return False

def generate_dataset(num_samples):
    """Generate DQN training dataset
    
    Args:
        num_samples (int): Number of samples to generate
        
    Returns:
        pandas.DataFrame: Dataset
    """
    # Create lists to store data
    states = []
    actions = []
    rewards = []
    next_states = []
    dones = []
    
    # Generate samples
    print(f"Generating {num_samples} training samples...")
    
    for i in range(num_samples):
        if i % 1000 == 0 and i > 0:
            print(f"Generated {i} samples...")
        
        # Generate state
        state = generate_state()
        
        # Get action
        action = get_action(state)
        
        # Calculate reward
        reward = calculate_reward(state, action)
        
        # Generate next state
        next_state = generate_next_state(state, action)
        
        # Determine if terminal
        done = is_terminal(state, next_state)
        
        # Store data
        states.append(state)
        actions.append(action)
        rewards.append(reward)
        next_states.append(next_state)
        dones.append(1 if done else 0)
    
    # Create column names
    state_cols = [
        'traffic_load', 'time_of_day', 'day_of_week',
        'embb_allocation', 'urllc_allocation', 'mmtc_allocation',
        'embb_utilization', 'urllc_utilization', 'mmtc_utilization',
        'client_count', 'bs_count', 'qos_violations',
        'is_emergency', 'is_special_event'
    ]
    
    next_state_cols = ['next_' + col for col in state_cols]
    
    # Create DataFrame
    df_data = {}
    
    # Add state columns
    for i, col in enumerate(state_cols):
        df_data[col] = [state[i] for state in states]
    
    # Add action, reward
    df_data['action'] = actions
    df_data['reward'] = rewards
    
    # Add next state columns
    for i, col in enumerate(next_state_cols):
        df_data[col] = [next_state[i] for next_state in next_states]
    
    # Add done flag
    df_data['done'] = dones
    
    # Create DataFrame
    df = pd.DataFrame(df_data)
    
    return df

def main():
    """Main function"""
    print(f"Generating DQN training dataset with {NUM_SAMPLES} samples")
    start_time = datetime.now()
    
    # Generate dataset
    df = generate_dataset(NUM_SAMPLES)
    
    # Save to CSV
    df.to_csv(OUTPUT_FILE, index=False)
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print(f"Dataset generation complete!")
    print(f"Generated {len(df)} samples in {duration:.1f} seconds")
    print(f"Dataset saved to {OUTPUT_FILE}")
    
    # Print dataset statistics
    print("\nDataset Statistics:")
    print(f"Average reward: {df['reward'].mean():.2f}")
    print(f"Action distribution: {df['action'].value_counts().sort_index().to_dict()}")
    print(f"Terminal states: {df['done'].sum()} ({df['done'].mean()*100:.1f}%)")

if __name__ == "__main__":
    main() 